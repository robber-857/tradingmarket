import pytest


@pytest.fixture(autouse=True)
def no_background_network(monkeypatch):
    # Tests exercise ingestion with explicit fixtures, never live polling on app startup.
    monkeypatch.setenv('NEWS_BACKGROUND_ENABLED', '0')
