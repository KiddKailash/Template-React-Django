"""Name a device from its request: browser, OS, form factor and client IP.

The user-agent parse is deliberately small. It only has to turn a session
into something a person recognises in a list ("Safari on iPhone", "Chrome on
Windows"), not identify every browser ever shipped — anything it does not
recognise falls back to "Unknown browser" / "Unknown OS" rather than
guessing. Order matters: Edge, Opera and Samsung Internet all claim to be
Chrome, and Chrome claims to be Safari.
"""

from __future__ import annotations

import ipaddress
import re

# (name, pattern) — first match wins.
_BROWSERS = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/")),
    ("Opera", re.compile(r"\bOPR/|\bOPiOS/")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/")),
    ("Firefox", re.compile(r"\bFirefox/|\bFxiOS/")),
    ("Chrome", re.compile(r"\bChrome/|\bCriOS/")),
    ("Safari", re.compile(r"\bSafari/")),
)

_OSES = (
    ("iPhone", re.compile(r"\biPhone\b")),
    ("iPad", re.compile(r"\biPad\b")),
    ("Android", re.compile(r"\bAndroid\b")),
    ("ChromeOS", re.compile(r"\bCrOS\b")),
    ("Windows", re.compile(r"\bWindows\b")),
    ("macOS", re.compile(r"\bMacintosh\b|\bMac OS X\b")),
    ("Linux", re.compile(r"\bLinux\b")),
)


def describe(user_agent: str) -> dict:
    """``{"browser", "os", "kind", "label"}`` for a user-agent string.

    ``kind`` is ``"mobile"``, ``"tablet"`` or ``"desktop"`` — what icon to show.
    """
    ua = user_agent or ""
    browser = next((name for name, rx in _BROWSERS if rx.search(ua)), None)
    os_name = next((name for name, rx in _OSES if rx.search(ua)), None)

    if os_name == "iPad" or (os_name == "Android" and "Mobile" not in ua):
        kind = "tablet"
    elif os_name in ("iPhone", "Android") or "Mobile" in ua:
        kind = "mobile"
    else:
        kind = "desktop"

    if browser and os_name:
        label = f"{browser} on {os_name}"
    else:
        label = browser or os_name or "Unknown device"
    return {
        "browser": browser or "Unknown browser",
        "os": os_name or "Unknown OS",
        "kind": kind,
        "label": label,
    }


def client_ip(request) -> str | None:
    """The caller's IP, as reported by the proxy in front of Django.

    Traffic through a Cloudflare Tunnel carries ``CF-Connecting-IP``; other
    reverse proxies (nginx, Caddy) set ``X-Forwarded-For``. It is shown to the
    user beside a session and never used for a security decision, so a spoofed
    header can only mislabel the spoofer's own session.
    """
    meta = getattr(request, "META", {}) or {}
    candidates = (
        meta.get("HTTP_CF_CONNECTING_IP", ""),
        meta.get("HTTP_X_FORWARDED_FOR", "").split(",")[0],
        meta.get("REMOTE_ADDR", ""),
    )
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            continue
    return None


def user_agent_of(request) -> str:
    return (getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT", "")[:512]
