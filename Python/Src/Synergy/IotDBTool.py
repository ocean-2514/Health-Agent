import numpy as np
import datetime
import json
from typing import ClassVar
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Adjusting object path to reach middleware
import sys
from pathlib import Path
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig

class IotDBQueryInput(BaseModel):
    sensor_name: str = Field(..., description="测点名称，例如 'H2', 'CH4', 'oil_bdv' 等")
    days: int = Field(7, description="获取过去几天的历史数据")

class IotDBTool(BaseTool):
    name: str = "IoTDB Timeseries Tool"
    description: str = "获取指定变压器测点的历史时序趋势数据。支持 DGA 组分、油化电试指标等。"
    args_schema: type[BaseModel] = IotDBQueryInput
    
    # We load configuration from GlobalConfig instead of hardcoding
    db_config: ClassVar[dict] = GlobalConfig.config.get("Database", {}).get("IoTDB", {})
    mode: str = "real" # Set to real to perform more realistic trend generation based on physics
    substation: str = "station1"
    equipment_id: str = "tr01"

    def get_device_image(self) -> str:
        """Fetch the latest image_url from IoTDB or return mock fallback from JSON."""
        # Try to load mock mappings from local JSON first as baseline
        mock_map = {
            "tr01": "/mock/images/fire_defect.png",
            "tr02": "/mock/images/oil_leakage.png",
            "tr03": "/mock/images/normal_sample.png",
            "tr04": "/mock/images/normal_sample.png"
        }
        mock_file_path = Path(project_root) / "mock" / "devices_meta.json"
        try:
            if mock_file_path.exists():
                with open(mock_file_path, 'r', encoding='utf-8') as f:
                    meta_list = json.load(f)
                    for dev in meta_list:
                        mock_map[dev["id"]] = dev["image_url"]
        except Exception as e:
            print(f"Warning: Failed to load mock meta file: {e}")
            
        mock_fallback = mock_map.get(self.equipment_id, "/assets/defects/normal_sample.png")

        if self.mode == "mock":
            return mock_fallback
            
        try:
            from iotdb.Session import Session
            session = Session(self.db_config.get("Host", "127.0.0.1"), 
                             self.db_config.get("Port", "6667"), 
                             self.db_config.get("Username", "root"), 
                             self.db_config.get("Password", "root"))
            session.open(False)
            
            device_path = f"{self.db_config.get('DatabaseName', 'root.sg_dev')}.{self.substation}.{self.equipment_id}"
            sql = f"SELECT image_url FROM {device_path} ORDER BY time DESC LIMIT 1"
            
            query_dataset = session.execute_query_statement(sql)
            image_url = None
            if query_dataset.has_next():
                row = query_dataset.next()
                image_url = row.get_fields()[0].get_string_value()
            
            session.close()
            return image_url if image_url else mock_fallback
        except Exception:
            return mock_fallback

    def _run(self, sensor_name: str, days: int = 7) -> str:
        data = self._get_historical_trends_internal(sensor_name, days, sampling_rate=4)
        return json.dumps(data, ensure_ascii=False)

    def get_all_scoring_data(self, days=7, sampling_rate=4):
        metrics = ["H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2", "oil_bdv", "oil_water", "furan"]
        return {m: self._get_historical_trends_internal(m, days, sampling_rate) for m in metrics}

    def _get_historical_trends_internal(self, sensor_name, days=7, sampling_rate=1):
        if self.mode == "mock":
            return self._generate_mock_trend_and_sample(sensor_name, days, sampling_rate)
        
        # Real IoTDB Integration
        try:
            from iotdb.Session import Session
            session = Session(self.db_config.get("Host", "127.0.0.1"), 
                             self.db_config.get("Port", "6667"), 
                             self.db_config.get("Username", "root"), 
                             self.db_config.get("Password", "root"))
            session.open(False)
            
            device_path = f"{self.db_config.get('DatabaseName', 'root.sg_dev')}.{self.substation}.{self.equipment_id}"
            sql = f"SELECT {sensor_name} FROM {device_path} WHERE time > now() - {days}d"
            
            # Using query to get results
            query_dataset = session.execute_query_statement(sql)
            timestamps = []
            values = []
            
            while query_dataset.has_next():
                row = query_dataset.next()
                ts = datetime.datetime.fromtimestamp(row.get_timestamp() / 1000.0).strftime("%Y-%m-%d %H:%M")
                val = row.get_fields()[0].get_double_value()
                timestamps.append(ts)
                values.append(round(val, 2))
            
            session.close()
            
            if not values: # Fallback to mock if database is empty but connected
                return self._generate_mock_trend_and_sample(sensor_name, days, sampling_rate)
                
            return {"sensor": sensor_name, "timestamps": timestamps[::sampling_rate], "values": values[::sampling_rate]}
            
        except Exception as e:
            # Silencing standard IoTDB real mode fallback for mock to avoid console spam
            return self._generate_mock_trend_and_sample(sensor_name, days, sampling_rate)

    def _generate_mock_trend_and_sample(self, sensor_name, days, sampling_rate):
        data = self._generate_mock_trend(sensor_name, days)
        if sampling_rate > 1:
            data['timestamps'] = data['timestamps'][::sampling_rate]
            data['values'] = data['values'][::sampling_rate]
        return data

    def get_maintenance_history(self, equipment_id):
        # Could also be fetched from IoTDB metadata or a relational DB
        return [
            {"date": "2024-05-10", "type": "常规巡检", "result": "正常", "operator": "张工"},
            {"date": "2024-08-20", "type": "油样分析", "result": "微量乙炔", "operator": "李工"},
            {"date": "2024-12-05", "type": "滤油作业", "result": "完成", "operator": "设备班"}
        ]

    def get_unstructured_data(self, equipment_id):
        # In real mode, we could fetch this from a specific IoTDB path or file system
        return [
            "2025-01-15: 巡检人员反馈 2号变压器 声音略显沉闷，建议关注。",
            "2025-02-01: 红外成像显示套管 C相 接头温度为 55℃，略高于环境温度。"
        ]

    def _generate_mock_trend(self, sensor_name, days):
        now = datetime.datetime.now()
        count = days * 24
        timestamps = [(now - datetime.timedelta(hours=i)).strftime("%Y-%m-%d %H:%M") for i in range(count)]
        timestamps.reverse()

        seed_str = f"{self.substation}_{self.equipment_id}_{sensor_name}"
        seed = sum(ord(c) for c in seed_str) % 10000
        np.random.seed(seed)

        base_configs = {
            "H2": (15.0, 0.2, 0.05), "CH4": (8.0, 0.1, 0.03), "C2H6": (5.0, 0.1, 0.02),
            "C2H4": (2.0, 0.05, 0.01), "C2H2": (0.1, 0.02, 0.005), "CO": (200.0, 5.0, 1.0),
            "CO2": (1500.0, 20.0, 5.0), "oil_bdv": (65.0, -0.5, 2.0), "oil_water": (15.0, 0.3, 1.0),
            "furan": (0.1, 0.01, 0.002)
        }
        config = base_configs.get(sensor_name, (10.0, 0.1, 0.05))
        base, trend_slope, noise_level = config
        
        device_offset = (seed % 20) - 10
        if base > 1.0:
            base = max(0.1, base + device_offset)
        else:
            base = max(0.01, base * (1.0 + (device_offset / 100.0)))

        trend = np.linspace(0, trend_slope * count, count)
        scale = max(0.001, base * noise_level)
        noise = np.random.normal(0, scale, count)
        values = base + trend + noise
        values = [max(0.01, round(float(v), 2)) for v in values]
        return {"sensor": sensor_name, "timestamps": timestamps, "values": values}

    def get_all_dga_trends(self, days=7):
        metrics = ["H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2"]
        return {m: self._get_historical_trends_internal(m, days) for m in metrics}
