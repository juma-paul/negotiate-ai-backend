"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "NegotiateAI"


def test_detailed_health(client):
    """Test detailed health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "openai_configured" in data


def test_create_session(client):
    """Test session creation."""
    response = client.post("/api/negotiate", json={
        "item_description": "Test freight shipment",
        "target_price": 2500,
        "max_price": 3500,
        "num_providers": 3,
        "strategy": "balanced"
    })
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert len(data["providers"]) == 3


def test_invalid_request(client):
    """Test invalid request validation."""
    response = client.post("/api/negotiate", json={
        "item_description": "x",  # Too short
        "target_price": 100,
        "max_price": 200,
    })
    assert response.status_code == 422


def test_session_not_found(client):
    """Test 404 for non-existent session."""
    response = client.get("/api/negotiate/nonexistent123")
    assert response.status_code == 404


def test_min_price_not_exposed(client):
    """Test that min_price is not exposed to clients."""
    response = client.post("/api/negotiate", json={
        "item_description": "Test shipment item",
        "target_price": 1000,
        "max_price": 2000,
        "num_providers": 2,
    })
    session_id = response.json()["session_id"]

    response = client.get(f"/api/negotiate/{session_id}")
    data = response.json()
    for provider in data["providers"]:
        assert "min_price" not in provider
