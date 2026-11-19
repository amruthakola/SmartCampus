
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_devops_status(client):
    response = client.get("/api/devops")

    assert response.status_code == 200
    assert response.json["status"] == "DEMO_READY"


def test_missing_booking_fields(client):
    response = client.post("/api/bookings", json={})

    assert response.status_code == 400
    assert "error" in response.json


def test_invalid_booking_date(client):
    response = client.post(
        "/api/bookings",
        json={
            "facility_id": 1,
            "user_name": "Student",
            "start_time": "invalid-date",
            "end_time": "2026-11-20T12:00:00",
            "purpose": "Meeting"
        }
    )

    assert response.status_code == 400


def test_missing_ticket_fields(client):
    response = client.post("/api/tickets", json={})

    assert response.status_code == 400
    assert "error" in response.json


def test_sensor_event_requires_id(client):
    response = client.post("/api/sensor-events", json={})

    assert response.status_code == 400
    assert "error" in response.json
