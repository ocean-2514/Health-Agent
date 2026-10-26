import os
import yaml
from pathlib import Path

class ConfigManager:
    """
    Singleton class to manage global configurations from GlobalConfig.yaml.
    """
    _instance = None
    _config = None

    def __new__(cls, config_path: str = None):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            if config_path is None:
                # Default path relatively from Middleware (Python/Src/Middleware -> Config)
                base_dir = Path(__file__).resolve().parent.parent.parent.parent
                config_path = base_dir / "Config" / "GlobalConfig.yaml"
            cls._instance._load_config(config_path)
        return cls._instance

    def _load_config(self, config_path: str):
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found at {path.absolute()}")
        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

    @property
    def config(self):
        return self._config

# Pre-instantiate singleton instance
GlobalConfig = ConfigManager()

# config = GlobalConfig.config
# print(config.get("Defects").get("ModelWeights"))
