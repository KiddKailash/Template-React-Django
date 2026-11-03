"""API surface hardening carried over from Store-Arbitrage.

├── OPTIONS never publishes a view's docstring (PublicMetadata)
└── outside DEBUG the API answers JSON only (no browsable renderer)
"""

import os

from django.conf import settings
from django.urls import reverse


def test_options_omits_docstring(api_client):
    res = api_client.options(reverse("health"))
    assert res.status_code == 200
    assert "description" not in res.json()


def test_browsable_renderer_only_in_debug():
    renderers = settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]
    assert renderers[0] == "rest_framework.renderers.JSONRenderer"
    # pytest-django forces settings.DEBUG off during tests, so compare with the
    # variable the setting was built from.
    debug = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
    assert ("rest_framework.renderers.BrowsableAPIRenderer" in renderers) == debug
