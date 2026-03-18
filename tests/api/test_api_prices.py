from datetime import datetime, timezone

from app.price_history import (
    DEFAULT_WINDOW_SECONDS,
    sample_portfolio_values,
    sample_prices,
)


def test_prices_endpoint_returns_recent_points(api_client):
    sample_prices(datetime.now(timezone.utc))

    response = api_client.get(
        "/prices",
        params={"ticker": "OGC", "window": DEFAULT_WINDOW_SECONDS},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 2
    assert set(body[0].keys()) == {"date", "price"}
    assert isinstance(body[0]["price"], float)
    first_date = datetime.fromisoformat(body[0]["date"].replace("Z", "+00:00"))
    last_date = datetime.fromisoformat(body[-1]["date"].replace("Z", "+00:00"))
    assert (last_date - first_date).total_seconds() >= DEFAULT_WINDOW_SECONDS - 1


def test_prices_endpoint_rejects_invalid_window(api_client):
    response = api_client.get(
        "/prices",
        params={"ticker": "OGC", "window": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Window must be a positive integer."


def test_portfolio_values_endpoint_returns_recent_points(api_client):
    sample_portfolio_values(datetime.now(timezone.utc))

    response = api_client.get(
        "/api/portfolio_values",
        params={"window": DEFAULT_WINDOW_SECONDS},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 2
    assert set(body[0].keys()) == {"date", "value"}
    assert isinstance(body[0]["value"], float)
    first_date = datetime.fromisoformat(body[0]["date"].replace("Z", "+00:00"))
    last_date = datetime.fromisoformat(body[-1]["date"].replace("Z", "+00:00"))
    assert (last_date - first_date).total_seconds() >= DEFAULT_WINDOW_SECONDS - 1


def test_portfolio_values_endpoint_rejects_invalid_window(api_client):
    response = api_client.get(
        "/api/portfolio_values",
        params={"window": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Window must be a positive integer."


def test_portfolio_values_endpoint_accepts_mixed_case_identity_headers(api_client):
    sample_portfolio_values(datetime.now(timezone.utc))

    response = api_client.get(
        "/api/portfolio_values",
        params={"window": DEFAULT_WINDOW_SECONDS},
        headers={
            "X-Actor-User": "AMoRgAn",
            "X-Actor-Email": "Alex.Morgan@Demo.Local",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 2
