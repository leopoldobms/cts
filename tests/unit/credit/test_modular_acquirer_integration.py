import pathlib
import pytest
import sys
sys.path.insert(1, "../../../")
from app import app
import json

def required_fields():
    with open(str(pathlib.Path(__file__).parent.absolute())+'/required_fields.json') as f:
        return json.load(f)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    client = app.test_client()

    yield client

def test_missing_service(client):
    res = client.post("v1/",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299

def test_missing_provider(client):
    res = client.post("v1/credit",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299     

def test_missing_action(client):
    res = client.post("v1/credit/cielo",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299    

def test_wrong_provider(client):
    res = client.post("v1/credit/xxxx/authorize",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299  

def test_wrong_service(client):
    res = client.post("v1/xxxx/cielo/authorize",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299

def test_wrong_action(client):
    res = client.post("v1/credit/cielo/xxxx",json=required_fields())
    assert res.status_code < 200 or res.status_code > 299   

def test_cielo_authorize(client):
    res = client.post("v1/credit/cielo/authorize",json=required_fields())
    assert res.status_code >= 200 and res.status_code <= 299       

def test_cielo_capture(client):
    res = client.post("v1/credit/cielo/capture",json=required_fields())
    assert res.status_code >= 200 and res.status_code <= 299       

def test_cielo_cancel(client):
    res = client.post("v1/credit/cielo/cancel",json=required_fields())
    assert res.status_code >= 200 and res.status_code <= 299       

def test_cielo_consult(client):
    res = client.post("v1/credit/cielo/consult",json=required_fields())
    assert res.status_code >= 200 and res.status_code <= 299       
