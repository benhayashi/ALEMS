import pytest
from alems.collectors.adsb_client import normalize_readsb_url, decode_readsb_protobuf

def test_normalize_readsb_url():
    assert normalize_readsb_url("192.168.1.216:8081") == "http://192.168.1.216:8081/data/aircraft.pb"
    assert normalize_readsb_url("192.168.1.216/8081") == "http://192.168.1.216:8081/data/aircraft.pb"
    assert normalize_readsb_url("http://192.168.1.216:8081/tar1090/data/aircraft.json") == "http://192.168.1.216:8081/tar1090/data/aircraft.json"
    assert normalize_readsb_url("http://192.168.1.216:8081") == "http://192.168.1.216:8081/data/aircraft.pb"
    assert normalize_readsb_url("") == ""

def test_decode_readsb_empty_buf():
    res = decode_readsb_protobuf(b"")
    assert res == []

def test_adsb_client_providers():
    from alems.collectors.adsb_client import ADSBClient
    client_local = ADSBClient(provider="readsb_local")
    assert client_local.provider == "readsb_local"

    client_lol = ADSBClient(provider="adsb_lol")
    assert client_lol.provider == "adsb_lol"

    client_os = ADSBClient(provider="opensky")
    assert client_os.provider == "opensky"

    client_custom = ADSBClient(endpoint_url="http://example.com/aircraft.json", provider="custom_url")
    assert client_custom.provider == "custom_url"

