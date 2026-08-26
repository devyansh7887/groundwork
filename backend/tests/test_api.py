"""
tests/test_api.py — End-to-end smoke tests for the Groundwork FastAPI backend.

These tests use TestClient (synchronous) to hit the actual routes without
needing a running server. They verify that endpoints exist, return correct
HTTP status codes, and enforce input validation — catching the most common
class of regressions: a route being accidentally removed or a validation
schema breaking.

Run with:
  cd backend
  pytest tests/test_api.py -v
"""
import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app — this also validates that all imports succeed at startup
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ─── Health / Root ────────────────────────────────────────────────────────────

def test_health_endpoint_returns_200():
    """Backend must be reachable and return a 200."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


# ─── Input Validation ─────────────────────────────────────────────────────────

def test_analyze_rejects_non_github_url():
    """Non-GitHub URLs must be rejected with 422 (validation error)."""
    response = client.post("/api/analyze", json={"repo_url": "https://gitlab.com/user/repo"})
    assert response.status_code == 422


def test_analyze_rejects_empty_url():
    """Empty URL must be rejected."""
    response = client.post("/api/analyze", json={"repo_url": ""})
    assert response.status_code == 422


def test_analyze_rejects_malformed_url():
    """Completely invalid strings must be rejected."""
    response = client.post("/api/analyze", json={"repo_url": "not-a-url"})
    assert response.status_code == 422


def test_analyze_stream_rejects_non_github_url():
    """Analyze endpoint must reject non-GitHub URLs with 422."""
    response = client.post("/api/analyze", json={"repo_url": "https://evil.com/x/y"})
    assert response.status_code == 422


def test_qa_rejects_missing_repo():
    """Q&A endpoint must require repo_url."""
    response = client.post("/api/qa", json={"question": "What is the entry point?"})
    assert response.status_code == 422


def test_draft_rejects_missing_repo():
    """Draft endpoint must require repo_url."""
    response = client.post("/api/draft", json={"issue": {"title": "test", "number": 1}})
    assert response.status_code == 422


# ─── Valid URL Format Accepted ────────────────────────────────────────────────

def test_analyze_accepts_valid_github_url():
    """
    A valid GitHub URL must pass validation (not 422).
    We don't assert 200 because the analysis may be slow or quota-limited —
    we only verify the *input validation* layer passes.
    """
    response = client.post("/api/analyze", json={"repo_url": "https://github.com/encode/starlette"})
    # Should not be a validation error — could be 200 (cached) or 503 (no keys), but NOT 422
    assert response.status_code != 422


def test_key_pool_status_endpoint():
    """Key pool status route must exist and return key data."""
    response = client.get("/api/key-status")
    assert response.status_code == 200
    data = response.json()
    # Response is either a list or a dict with a 'keys' field
    assert isinstance(data, (list, dict))
