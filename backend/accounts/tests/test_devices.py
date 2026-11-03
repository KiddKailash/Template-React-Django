"""Tests for accounts.utils.devices (user-agent naming and client IP)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from accounts.utils.devices import client_ip, describe

UAS = {
    "safari-iphone": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        ("Safari", "iPhone", "mobile"),
    ),
    "chrome-iphone": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) CriOS/129.0.6668.69 Mobile/15E148 Safari/604.1",
        ("Chrome", "iPhone", "mobile"),
    ),
    "safari-ipad": (
        "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        ("Safari", "iPad", "tablet"),
    ),
    "chrome-android-phone": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
        ("Chrome", "Android", "mobile"),
    ),
    "chrome-android-tablet": (
        "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        ("Chrome", "Android", "tablet"),
    ),
    "samsung-android": (
        "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
        ("Samsung Internet", "Android", "mobile"),
    ),
    "chrome-mac": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        ("Chrome", "macOS", "desktop"),
    ),
    "safari-mac": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        ("Safari", "macOS", "desktop"),
    ),
    "edge-windows": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.2792.65",
        ("Edge", "Windows", "desktop"),
    ),
    "opera-windows": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 OPR/114.0.0.0",
        ("Opera", "Windows", "desktop"),
    ),
    "firefox-linux": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
        ("Firefox", "Linux", "desktop"),
    ),
    "chrome-chromeos": (
        "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        ("Chrome", "ChromeOS", "desktop"),
    ),
}


@pytest.mark.parametrize("ua, expected", UAS.values(), ids=UAS.keys())
def test_describe(ua, expected):
    browser, os_name, kind = expected
    assert describe(ua) == {
        "browser": browser,
        "os": os_name,
        "kind": kind,
        "label": f"{browser} on {os_name}",
    }


@pytest.mark.parametrize("ua", ["", "curl/8.4.0"])
def test_unrecognised(ua):
    assert describe(ua) == {
        "browser": "Unknown browser",
        "os": "Unknown OS",
        "kind": "desktop",
        "label": "Unknown device",
    }


def _req(**meta):
    return SimpleNamespace(META=meta)


@pytest.mark.parametrize(
    "meta, expected",
    [
        ({"HTTP_CF_CONNECTING_IP": "203.0.113.7", "REMOTE_ADDR": "172.23.0.2"}, "203.0.113.7"),
        (
            {"HTTP_X_FORWARDED_FOR": "198.51.100.4, 10.0.0.1", "REMOTE_ADDR": "172.23.0.2"},
            "198.51.100.4",
        ),
        ({"REMOTE_ADDR": "192.168.0.118"}, "192.168.0.118"),
        ({"HTTP_CF_CONNECTING_IP": "not-an-ip", "REMOTE_ADDR": "2001:db8::1"}, "2001:db8::1"),
        ({}, None),
    ],
    ids=["cloudflare", "caddy", "direct", "invalid-header-skipped", "none"],
)
def test_client_ip(meta, expected):
    assert client_ip(_req(**meta)) == expected
