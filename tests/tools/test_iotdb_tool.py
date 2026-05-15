"""Tests for IotDBClient mock-mode behavior."""
import pytest

from Python.Src.Tools.iotdb_tool import IotDBClient, SensorTrend


def test_mock_trend_shape():
    client = IotDBClient(mode="mock")
    trend = client.get_historical_trend("H2", equipment_id="tr01", days=1, sampling_rate=1)
    assert isinstance(trend, SensorTrend)
    assert trend.sensor == "H2"
    assert len(trend.timestamps) == len(trend.values) == 24


def test_mock_is_deterministic_per_equipment():
    client = IotDBClient(mode="mock")
    a = client.get_historical_trend("CH4", equipment_id="tr01", days=1)
    b = client.get_historical_trend("CH4", equipment_id="tr01", days=1)
    assert a.values == b.values, "mock generator should be reproducible"


def test_different_equipment_produces_different_series():
    client = IotDBClient(mode="mock")
    a = client.get_historical_trend("CH4", equipment_id="tr01", days=1)
    b = client.get_historical_trend("CH4", equipment_id="tr02", days=1)
    assert a.values != b.values, "different equipment must seed different series"


def test_get_all_scoring_data_covers_all_metrics():
    client = IotDBClient(mode="mock")
    bundle = client.get_all_scoring_data(equipment_id="tr01", days=1, sampling_rate=4)
    expected = {"H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2", "oil_bdv", "oil_water", "furan"}
    assert set(bundle.keys()) == expected


def test_image_url_fallback_for_unknown_equipment():
    client = IotDBClient(mode="mock")
    url = client.get_device_image_url(equipment_id="tr_nonexistent")
    assert url.endswith("normal_sample.png")


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        IotDBClient(mode="hybrid")
