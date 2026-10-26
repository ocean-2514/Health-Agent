"""IoTDB time-series client for transformer monitoring.

Migrated from ``Python/Src/Synergy/IotDBTool.py``. Differences from the legacy
class:

* No ``crewai.tools.BaseTool`` inheritance — pure Python class.
* Equipment id and substation are explicit per-call arguments instead of
  mutable instance state, so concurrent callers cannot race on shared state.
* Returns Pydantic models (`SensorTrend`, `MaintenanceRecord`) instead of
  raw dicts / JSON strings, so the MCP server can introspect schemas.

Mock-mode generation (deterministic seeding by station+equipment+sensor)
is preserved bit-for-bit so existing tests stay reproducible.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig


# ---------------------------------------------------------------------------
# Pydantic models (these double as MCP tool schemas in Phase 2)
# ---------------------------------------------------------------------------

class SensorTrend(BaseModel):
    """One sensor's time series over a window."""
    sensor: str = Field(..., description="测点名称, 如 H2 / CH4 / oil_bdv")
    timestamps: List[str] = Field(..., description="ISO 时间戳, 升序")
    values: List[float] = Field(..., description="测量值")


class MaintenanceRecord(BaseModel):
    date: str
    type: str
    result: str
    operator: str


# ---------------------------------------------------------------------------
# Mock-mode trend configuration (preserved from legacy IotDBTool)
# ---------------------------------------------------------------------------

_BASE_CONFIGS: Dict[str, tuple] = {
    "H2":      (15.0,   0.2,  0.05),
    "CH4":     (8.0,    0.1,  0.03),
    "C2H6":    (5.0,    0.1,  0.02),
    "C2H4":    (2.0,    0.05, 0.01),
    "C2H2":    (0.1,    0.02, 0.005),
    "CO":      (200.0,  5.0,  1.0),
    "CO2":     (1500.0, 20.0, 5.0),
    "oil_bdv": (65.0,  -0.5,  2.0),
    "oil_water": (15.0, 0.3,  1.0),
    "furan":   (0.1,    0.01, 0.002),
}

_DGA_METRICS = ["H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2"]
_SCORING_METRICS = _DGA_METRICS + ["oil_bdv", "oil_water", "furan"]

_MOCK_IMAGE_MAP = {
    "tr01": "/mock/images/fire_defect.png",
    "tr02": "/mock/images/oil_leakage.png",
    "tr03": "/mock/images/normal_sample.png",
    "tr04": "/mock/images/normal_sample.png",
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class IotDBClient:
    """Stateless-ish IoTDB client. Connection settings come from GlobalConfig.

    In ``mode="mock"`` returns deterministic synthetic trends. In ``mode="real"``
    queries Apache IoTDB; if the connection or query fails the call falls back
    to the mock generator silently (matches legacy behavior — the system must
    keep functioning during demo / network outages).
    """

    def __init__(self, mode: str = "mock"):
        if mode not in ("mock", "real"):
            raise ValueError(f"mode must be 'mock' or 'real', got {mode!r}")
        self.mode = mode
        self.db_config = GlobalConfig.config.get("Database", {}).get("IoTDB", {})

    # ------------------------------------------------------------------ public

    def get_historical_trend(
        self,
        sensor_name: str,
        equipment_id: str,
        substation: str = "station1",
        days: int = 7,
        sampling_rate: int = 1,
    ) -> SensorTrend:
        """Fetch one sensor's trend for the past ``days`` days."""
        raw = self._fetch_trend(sensor_name, equipment_id, substation, days)
        if sampling_rate > 1:
            raw["timestamps"] = raw["timestamps"][::sampling_rate]
            raw["values"] = raw["values"][::sampling_rate]
        return SensorTrend(**raw)

    def get_all_scoring_data(
        self,
        equipment_id: str,
        substation: str = "station1",
        days: int = 7,
        sampling_rate: int = 4,
    ) -> Dict[str, SensorTrend]:
        """Fetch the full scoring metric set (DGA gases + oil indicators)."""
        return {
            m: self.get_historical_trend(m, equipment_id, substation, days, sampling_rate)
            for m in _SCORING_METRICS
        }

    def get_all_dga_trends(
        self,
        equipment_id: str,
        substation: str = "station1",
        days: int = 7,
    ) -> Dict[str, SensorTrend]:
        """Fetch only the seven DGA gas trends."""
        return {
            m: self.get_historical_trend(m, equipment_id, substation, days)
            for m in _DGA_METRICS
        }

    def get_device_image_url(
        self,
        equipment_id: str,
        substation: str = "station1",
    ) -> str:
        """Return a mock or IoTDB-stored image URL for the device.

        In mock mode returns a hardcoded mapping (extended by
        ``mock/devices_meta.json`` if present). In real mode queries IoTDB
        and falls back to the mock URL if no image is recorded.
        """
        mock_map = dict(_MOCK_IMAGE_MAP)
        meta_file = Path(project_root) / "mock" / "devices_meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    for dev in json.load(f):
                        mock_map[dev["id"]] = dev["image_url"]
            except Exception as e:
                print(f"[IotDBClient] Warning: failed to read {meta_file}: {e}")

        fallback = mock_map.get(equipment_id, "/assets/defects/normal_sample.png")
        if self.mode == "mock":
            return fallback

        try:
            from iotdb.Session import Session
            session = Session(
                self.db_config.get("Host", "127.0.0.1"),
                self.db_config.get("Port", "6667"),
                self.db_config.get("Username", "root"),
                self.db_config.get("Password", "root"),
            )
            session.open(False)
            device_path = (
                f"{self.db_config.get('DatabaseName', 'root.sg_dev')}"
                f".{substation}.{equipment_id}"
            )
            sql = f"SELECT image_url FROM {device_path} ORDER BY time DESC LIMIT 1"
            ds = session.execute_query_statement(sql)
            url: Optional[str] = None
            if ds.has_next():
                url = ds.next().get_fields()[0].get_string_value()
            session.close()
            return url or fallback
        except Exception:
            return fallback

    def get_maintenance_history(self, equipment_id: str) -> List[MaintenanceRecord]:
        """Return canned maintenance records (placeholder until a real
        records source is wired up)."""
        return [
            MaintenanceRecord(date="2024-05-10", type="常规巡检", result="正常", operator="张工"),
            MaintenanceRecord(date="2024-08-20", type="油样分析", result="微量乙炔", operator="李工"),
            MaintenanceRecord(date="2024-12-05", type="滤油作业", result="完成", operator="设备班"),
        ]

    def get_unstructured_notes(self, equipment_id: str) -> List[str]:
        """Return canned inspection notes (placeholder)."""
        return [
            "2025-01-15: 巡检人员反馈 2号变压器 声音略显沉闷，建议关注。",
            "2025-02-01: 红外成像显示套管 C相 接头温度为 55℃，略高于环境温度。",
        ]

    # ----------------------------------------------------------------- private

    def _fetch_trend(
        self,
        sensor_name: str,
        equipment_id: str,
        substation: str,
        days: int,
    ) -> dict:
        if self.mode == "mock":
            return self._generate_mock_trend(sensor_name, equipment_id, substation, days)

        try:
            from iotdb.Session import Session
            session = Session(
                self.db_config.get("Host", "127.0.0.1"),
                self.db_config.get("Port", "6667"),
                self.db_config.get("Username", "root"),
                self.db_config.get("Password", "root"),
            )
            session.open(False)
            device_path = (
                f"{self.db_config.get('DatabaseName', 'root.sg_dev')}"
                f".{substation}.{equipment_id}"
            )
            sql = f"SELECT {sensor_name} FROM {device_path} WHERE time > now() - {days}d"
            ds = session.execute_query_statement(sql)
            timestamps: List[str] = []
            values: List[float] = []
            while ds.has_next():
                row = ds.next()
                ts = datetime.datetime.fromtimestamp(row.get_timestamp() / 1000.0).strftime(
                    "%Y-%m-%d %H:%M"
                )
                timestamps.append(ts)
                values.append(round(row.get_fields()[0].get_double_value(), 2))
            session.close()
            if not values:
                return self._generate_mock_trend(sensor_name, equipment_id, substation, days)
            return {"sensor": sensor_name, "timestamps": timestamps, "values": values}
        except Exception:
            return self._generate_mock_trend(sensor_name, equipment_id, substation, days)

    @staticmethod
    def _generate_mock_trend(
        sensor_name: str,
        equipment_id: str,
        substation: str,
        days: int,
    ) -> dict:
        """Deterministic mock generator. Same seeding as legacy IotDBTool."""
        now = datetime.datetime.now()
        count = days * 24
        timestamps = [
            (now - datetime.timedelta(hours=i)).strftime("%Y-%m-%d %H:%M")
            for i in range(count)
        ]
        timestamps.reverse()

        seed_str = f"{substation}_{equipment_id}_{sensor_name}"
        seed = sum(ord(c) for c in seed_str) % 10000
        np.random.seed(seed)

        base, slope, noise_level = _BASE_CONFIGS.get(sensor_name, (10.0, 0.1, 0.05))
        device_offset = (seed % 20) - 10
        if base > 1.0:
            base = max(0.1, base + device_offset)
        else:
            base = max(0.01, base * (1.0 + device_offset / 100.0))

        trend = np.linspace(0, slope * count, count)
        scale = max(0.001, base * noise_level)
        noise = np.random.normal(0, scale, count)
        values = base + trend + noise
        values = [max(0.01, round(float(v), 2)) for v in values]
        return {"sensor": sensor_name, "timestamps": timestamps, "values": values}


if __name__ == "__main__":
    client = IotDBClient(mode="mock")
    trend = client.get_historical_trend("H2", equipment_id="tr01", days=2, sampling_rate=4)
    print(f"H2 sample (n={len(trend.values)}): {trend.values[:5]} ...")
    print(f"Image URL for tr01: {client.get_device_image_url('tr01')}")
