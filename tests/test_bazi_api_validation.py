from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.bazi_api import router


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def valid_payload():
    return {
        "year": 2002,
        "month": 10,
        "day": 12,
        "hour": 21,
        "minute": 31,
        "gender": "男",
        "timezone": "Asia/Shanghai",
        "analysis_mode": "simple",
    }


def test_bazi_analyze_rejects_invalid_hour_before_workflow():
    payload = valid_payload()
    payload["hour"] = 24

    response = create_client().post("/api/v1/bazi/analyze", json=payload)

    assert response.status_code == 422


def test_bazi_analyze_rejects_invalid_minute_before_workflow():
    payload = valid_payload()
    payload["minute"] = 60

    response = create_client().post("/api/v1/bazi/analyze", json=payload)

    assert response.status_code == 422


def test_bazi_analyze_rejects_invalid_coordinates_before_workflow():
    payload = valid_payload()
    payload["latitude"] = 91
    payload["longitude"] = 181

    response = create_client().post("/api/v1/bazi/analyze", json=payload)

    assert response.status_code == 422
