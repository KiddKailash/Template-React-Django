"""Stream a long LLM turn to the browser as server-sent events.

Ported from LLMStockAnalysis (`analyzer/views.py` `_stream_agent_turn`), where
streaming is what fixed timeouts on every platform with an LLM in it.

**Why stream at all.** A tool-calling turn can make LLM_MAX_TOOL_TURNS + 1 model
calls, each allowed OPENROUTER_REQUEST_TIMEOUT seconds. A plain JSON request
sends nothing until the end, and every hop in front of Django gives up on a
silent connection long before that: nginx after `proxy_read_timeout` (60 s),
Cloudflare after ~100 s (a 524), browsers and phone networks after their own
idle limits. The user sees an error while the server keeps working, and pays
for an answer nobody receives. A stream writes something at least every
HEARTBEAT_SECONDS, so no hop ever sees an idle connection, and it shows real
progress (which tool is running) instead of a spinner that looks the same
whether the turn is working or hung.

**Wire format.** One JSON object per frame:

    event: start        {"status": "working"}
    event: iteration    {"type": "iteration", "iteration": 1}
    event: tool_start   {"type": "tool_start", "name": ..., "args": {...}}
    event: tool_result  {"type": "tool_result", "name": ..., "ok": true, "preview": ...}
    event: finalising   {"type": "finalising", "reason": "max_turns"}
    event: done         <exactly the JSON body the non-streaming endpoint returns>
    event: error        {"error": "<message for the user>"}
    : keep-alive        (a comment, every HEARTBEAT_SECONDS of silence)

`done` and `error` are terminal. Because `done` matches the JSON endpoint, a
client can fall back to it, and that endpoint stays.

**A turn outlives its listener.** The client may leave mid-turn (closed tab,
reload, lost signal) while the model is still being paid for. Whoever is still
around when the turn settles finishes it (``persist`` on success,
``on_failure`` on error), exactly once: the response generator on the
ordinary path (so `done` is only sent once the answer is in the database), or
the worker thread when the generator has already been closed. `claim()`
decides which, under a lock.

**Threads and the database.** Only `runner` is guaranteed to run on the worker
thread. Do the database work a turn needs before it (in the view) or in
``persist`` / ``on_failure``, which run on the request thread unless the client
has left.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests
from django.conf import settings
from django.db import connection as db_connection
from django.http import StreamingHttpResponse
from rest_framework import exceptions
from rest_framework.renderers import JSONRenderer

logger = logging.getLogger(__name__)

# A byte at least this often. Well inside nginx's 60 s proxy_read_timeout and
# Cloudflare's ~100 s, and short enough that a departed client is noticed (the
# failed write is what closes the generator).
HEARTBEAT_SECONDS = 15

KEEP_ALIVE = ": keep-alive\n\n"


def max_wait_seconds() -> int:
    """Ceiling on waiting for the worker: the loop's own worst case plus slack.

    (LLM_MAX_TOOL_TURNS + 1 forced final call) × OPENROUTER_REQUEST_TIMEOUT.
    Anything past it has hung somewhere the per-request timeouts do not reach.
    """
    turns = int(getattr(settings, "LLM_MAX_TOOL_TURNS", 10)) + 1
    per_call = int(getattr(settings, "OPENROUTER_REQUEST_TIMEOUT", 60))
    return turns * per_call + 60


def sse(event: str, payload: dict[str, Any]) -> str:
    """One SSE frame."""
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def user_message_for(error: BaseException) -> str:
    """What the client is told when a turn fails (details stay in the log)."""
    if isinstance(error, requests.Timeout):
        return "The assistant took too long to respond. Please try again."
    if isinstance(error, requests.HTTPError):
        return "The assistant's model request failed. Please try again."
    return "Something went wrong. Please try again."


def event_stream_response(frames: Iterator[str]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(frames, content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-transform"
    # nginx buffers proxied responses by default, which would hold every frame
    # until the turn finished. This header turns that off for this response
    # only (nginx honours X-Accel-Buffering from the upstream).
    response["X-Accel-Buffering"] = "no"
    return response


def stream_turn(
    runner: Callable[[Callable[[dict[str, Any]], None]], Any],
    persist: Callable[[Any], dict[str, Any]],
    *,
    on_failure: Callable[[BaseException], None] | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_wait: float | None = None,
) -> StreamingHttpResponse:
    """Run ``runner(on_event)`` on a worker thread and stream it as SSE.

    ``runner`` takes the progress callback and returns the turn's result.
    ``persist(result)`` saves it and returns the ``done`` payload; it runs
    exactly once per successful turn, whether or not the client stayed.
    ``on_failure(error)`` runs exactly once if ``runner`` raises (e.g. to mark
    the run failed), also whether or not the client stayed.
    """
    events: queue.Queue = queue.Queue()
    outcome: dict[str, Any] = {}
    lock = threading.Lock()
    state = {"settled": False, "abandoned": False}

    def claim() -> bool:
        """True for exactly one caller once the turn has a result or an error."""
        with lock:
            if state["settled"] or not ({"result", "error"} & outcome.keys()):
                return False
            state["settled"] = True
            return True

    def settle_quietly() -> None:
        """Finish a turn nobody is listening to any more."""
        try:
            if "error" in outcome:
                if on_failure is not None:
                    on_failure(outcome["error"])
            else:
                persist(outcome["result"])
        except Exception:
            logger.exception("sse.settle_abandoned_turn_failed")

    def worker() -> None:
        try:
            outcome["result"] = runner(events.put)
        except Exception as exc:  # surfaced to the client as an error frame
            outcome["error"] = exc
        finally:
            with lock:
                orphaned = state["abandoned"]
            if orphaned and claim():
                settle_quietly()
            try:
                db_connection.close()
            except Exception:  # pragma: no cover
                pass
            events.put(None)

    thread = threading.Thread(target=worker, name="llm-stream", daemon=True)
    thread.start()
    limit = max_wait if max_wait is not None else max_wait_seconds()

    def relay() -> Iterator[str]:
        yield sse("start", {"status": "working"})
        deadline = time.monotonic() + limit
        while True:
            if time.monotonic() > deadline:
                yield sse("error", {"error": "The assistant took too long to respond."})
                return
            try:
                event = events.get(timeout=heartbeat_seconds)
            except queue.Empty:
                # A comment frame keeps every hop from timing the connection
                # out, without adding an event the client must understand.
                yield KEEP_ALIVE
                continue
            if event is None:
                break
            yield sse(str(event.get("type", "progress")), event)

        thread.join(timeout=5)
        if not claim():  # pragma: no cover - only one relay per turn
            return
        error = outcome.get("error")
        if error is not None:
            logger.error("sse.turn_failed: %r", error, exc_info=error)
            if on_failure is not None:
                try:
                    on_failure(error)
                except Exception:
                    logger.exception("sse.on_failure_failed")
            yield sse("error", {"error": user_message_for(error)})
            return
        try:
            payload = persist(outcome["result"])
        except Exception:
            logger.exception("sse.persist_failed")
            yield sse("error", {"error": "The answer could not be saved. Please try again."})
            return
        yield sse("done", payload)

    def generate() -> Iterator[str]:
        try:
            yield from relay()
        finally:
            # Closed early (the client left) or returned without settling
            # (deadline). If the turn has settled, finish it here; otherwise
            # the worker does when the runner returns.
            with lock:
                state["abandoned"] = True
            if claim():
                settle_quietly()

    return event_stream_response(generate())


def single_frame_stream(event: str, payload: dict[str, Any]) -> StreamingHttpResponse:
    """A finished answer, delivered on the stream's terms (e.g. cost cap hit)."""

    def frames() -> Iterator[str]:
        yield sse("start", {"status": "working"})
        yield sse(event, payload)

    return event_stream_response(frames())


class SSEAcceptMixin:
    """Let an APIView be asked for ``text/event-stream`` without a 406.

    The client sends ``Accept: text/event-stream``, and DRF negotiates before
    ``post()`` runs, rejecting any media type no renderer claims. A successful
    turn is a raw ``StreamingHttpResponse`` that never goes through a renderer;
    everything that does is an early rejection (400/401/503), and those stay
    JSON so the client can read ``detail`` and decide whether to fall back.
    """

    def perform_content_negotiation(self, request, force=False):
        try:
            return super().perform_content_negotiation(request, force)
        except exceptions.NotAcceptable:
            if "text/event-stream" not in request.META.get("HTTP_ACCEPT", ""):
                raise
            renderer = JSONRenderer()
            return (renderer, renderer.media_type)
