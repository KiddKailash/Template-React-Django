"""llm.utils.sse.stream_turn — framing, heartbeats, and save-exactly-once.

Plain callables stand in for the turn, so no database or LLM is involved.

Coverage:
  ├── start, progress frames in order, done carrying persist()'s payload
  ├── a keep-alive comment while the runner is silent
  ├── runner raises → error frame (mapped message), on_failure once, no persist
  ├── persist raises → error frame
  ├── deadline → error frame; the late result is still saved, once
  ├── client leaves before the turn settles → the worker saves it, once
  ├── client leaves before a failure → the worker runs on_failure, once
  └── client leaves after it settled → the generator saves it, once
"""

from __future__ import annotations

import threading
import time

import pytest
import requests

from llm.utils.sse import KEEP_ALIVE, stream_turn

# response.close() (how a server ends a response) fires request_finished, which
# closes database connections; pytest-django wants that allowed explicitly.
pytestmark = pytest.mark.django_db


def body(response) -> str:
    return "".join(c.decode() if isinstance(c, bytes) else c for c in response.streaming_content)


def test_frames_in_order_and_done_payload():
    saved = []

    def runner(on_event):
        on_event({"type": "iteration", "iteration": 1})
        on_event({"type": "tool_start", "name": "t", "args": {}})
        return "result"

    def persist(result):
        saved.append(result)
        return {"answer": result}

    text = body(stream_turn(runner, persist))
    assert text.startswith("event: start\n")
    assert (
        text.index("event: iteration") < text.index("event: tool_start") < text.index("event: done")
    )
    assert 'data: {"answer": "result"}' in text
    assert saved == ["result"]


def test_keep_alive_while_silent():
    def runner(on_event):
        time.sleep(0.25)
        return "r"

    text = body(stream_turn(runner, lambda r: {}, heartbeat_seconds=0.05))
    assert text.count(KEEP_ALIVE) >= 2
    assert "event: done" in text


def test_runner_failure_is_an_error_frame():
    failures = []
    persisted = []

    def runner(on_event):
        raise requests.Timeout("slow model")

    text = body(stream_turn(runner, persisted.append, on_failure=failures.append))
    assert "event: error" in text and "took too long" in text
    assert "event: done" not in text
    assert len(failures) == 1 and isinstance(failures[0], requests.Timeout)
    assert persisted == []


def test_persist_failure_is_an_error_frame():
    def persist(result):
        raise RuntimeError("db down")

    text = body(stream_turn(lambda on_event: "r", persist))
    assert "event: error" in text and "could not be saved" in text


def test_deadline_gives_up_but_the_turn_is_still_saved_once():
    release = threading.Event()
    saved = []

    def runner(on_event):
        release.wait(5)
        return "late"

    text = body(stream_turn(runner, saved.append, heartbeat_seconds=0.02, max_wait=0.1))
    assert "event: error" in text and "too long" in text
    release.set()
    _wait_for(lambda: saved == ["late"])
    time.sleep(0.05)
    assert saved == ["late"]


def test_client_leaves_mid_turn_worker_saves_once():
    release = threading.Event()
    saved = []

    def runner(on_event):
        release.wait(5)
        return "answer"

    response = stream_turn(runner, saved.append, heartbeat_seconds=0.02)
    stream = response.streaming_content
    next(stream)  # the start frame reached the client...
    response.close()  # ...then it left (the WSGI server closes the response)
    assert saved == []
    release.set()
    _wait_for(lambda: saved == ["answer"])
    time.sleep(0.05)
    assert saved == ["answer"]


def test_client_leaves_after_the_turn_settled_generator_saves_once():
    finished = threading.Event()
    saved = []

    def runner(on_event):
        finished.set()
        return "answer"

    response = stream_turn(runner, saved.append, heartbeat_seconds=0.02)
    stream = response.streaming_content
    next(stream)
    finished.wait(5)
    time.sleep(0.05)  # let the worker return and see the client still there
    response.close()
    _wait_for(lambda: saved == ["answer"])
    time.sleep(0.05)
    assert saved == ["answer"]


def test_client_leaves_before_a_failure_worker_runs_on_failure_once():
    release = threading.Event()
    failures = []

    def runner(on_event):
        release.wait(5)
        raise RuntimeError("model down")

    response = stream_turn(runner, lambda r: {}, on_failure=failures.append, heartbeat_seconds=0.02)
    stream = response.streaming_content
    next(stream)
    response.close()
    release.set()
    _wait_for(lambda: len(failures) == 1)
    time.sleep(0.05)
    assert len(failures) == 1


def _wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)
