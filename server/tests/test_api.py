from fastapi.testclient import TestClient
import importlib
import json
from unittest.mock import MagicMock
from server.app import app

client=TestClient(app)


def test_health_does_not_expose_credentials(monkeypatch):
    from server import narrative
    monkeypatch.setattr(narrative,'settings',lambda: ('','gpt-5-mini'))
    response=client.get('/api/health')
    assert response.status_code==200
    assert response.json()['llmEnabled'] is False
    assert '@' not in response.text


def test_crypto_does_not_receive_corporate_model():
    assert client.get('/api/research/BTC').status_code==404


def test_unknown_snapshot_is_not_replaced_with_latest_data():
    response=client.post('/api/research/INTC/valuation',json={
        'snapshot_id':'0'*24,'report_end':'2025-12-31','assumptions':{'debt':10,'shares':10}})
    assert response.status_code==409


def test_snapshot_id_cannot_traverse_directories():
    response=client.post('/api/research/INTC/valuation',json={
        'snapshot_id':'../../.env','report_end':'2025-12-31','assumptions':{'debt':10,'shares':10}})
    assert response.status_code==422


def test_capm_api_returns_deterministic_result():
    response=client.post('/api/research-tools/wacc',json={'risk_free':.04,'beta':1,
        'equity_risk_premium':.05,'cost_of_debt':.05,'tax_rate':.25,
        'equity_market_value':80,'debt_market_value':20})
    assert response.status_code==200
    assert abs(response.json()['wacc']-.0795)<1e-10


def test_snapshot_cannot_be_reused_for_another_company_or_period(monkeypatch):
    module=importlib.import_module('server.app')
    reports=MagicMock()
    reports.__truediv__.return_value.exists.return_value=True
    reports.__truediv__.return_value.read_text.return_value=json.dumps({'symbol':'INTC','quarters':[]})
    monkeypatch.setattr(module,'REPORTS',reports)
    sid='1'*24
    body={'snapshot_id':sid,'report_end':'2025-12-31','assumptions':{'debt':10,'shares':10}}
    assert client.post('/api/research/NVDA/valuation',json=body).status_code==409
    assert client.post('/api/research/INTC/valuation',json=body).status_code==422
