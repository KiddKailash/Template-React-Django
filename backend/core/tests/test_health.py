"""Smoke tests for the core app."""

from django.urls import reverse


def test_health_endpoint_is_public(api_client):
    response = api_client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_requires_auth(api_client):
    response = api_client.get(reverse("me"))
    assert response.status_code == 401


def test_me_returns_user(authenticated_client, user):
    response = authenticated_client.get(reverse("me"))
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user.username
    assert data["email"] == user.email
