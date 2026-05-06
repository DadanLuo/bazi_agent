from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.bazi_chart_api import router


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_chart_api_accepts_datetime_payload():
    client = create_client()
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_datetime": "2002-10-12T21:31:00",
            "timezone": "Asia/Shanghai",
            "gender": "男",
            "analysis_depth": "详细",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["four_pillars"]["year"]["ganzhi"] == "壬午"


def test_chart_api_rejects_unknown_city():
    client = create_client()
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "year": 1990,
            "month": 5,
            "day": 15,
            "hour": 10,
            "gender": "男",
            "timezone": "Asia/Shanghai",
            "location": "火星基地",
        },
    )

    assert response.status_code == 400
    assert "改用" in response.json()["detail"]
