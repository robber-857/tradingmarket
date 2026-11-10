import pytest


@pytest.fixture(autouse=True)
def no_background_network(monkeypatch, tmp_path):
    # Tests exercise ingestion with explicit fixtures, never live polling on app startup.
    monkeypatch.setenv('NEWS_BACKGROUND_ENABLED', '0')
    monkeypatch.setenv('PUBLIC_FORECAST_BACKGROUND_ENABLED', '0')
    from server import public_forecasts
    monkeypatch.setattr(public_forecasts, 'STORE', tmp_path / 'public-forecasts.json')
