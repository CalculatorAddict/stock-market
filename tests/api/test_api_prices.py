from datetime import datetime, timezone

from app.price_history import DEFAULT_WINDOW_SECONDS, sample_prices


def test_prices_endpoint_returns_recent_points(api_client):
    sample_prices(datetime.now(timezone.utc))

    response = api_client.get(
        "/prices",
        params={"ticker": "AAPL", "window": DEFAULT_WINDOW_SECONDS},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 2
    assert set(body[0].keys()) == {"date", "price"}
    assert isinstance(body[0]["price"], float)


def test_prices_endpoint_rejects_invalid_window(api_client):
    response = api_client.get(
        "/prices",
        params={"ticker": "AAPL", "window": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Window must be a positive integer."
