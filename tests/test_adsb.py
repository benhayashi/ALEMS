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
