import sys
import time
import logging
import requests
from pathlib import Path
from typing import Optional

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig


class LLMService:
    """
    Utility to interact with local Ollama API for real AI reasoning.

    Reads configuration from GlobalConfig.yaml (LLM.Local). Constructor
    parameters override config values. Returns plain str so existing
    callers stay compatible; degraded responses are prefixed with
    FALLBACK_PREFIX so callers can detect them.
    """

    FALLBACK_PREFIX = "[AI 推理服务暂不可用]"

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        cfg = GlobalConfig.config.get("LLM", {}).get("Local", {})
        resolved_base = base_url or cfg.get("BaseURL", "http://localhost:11434")
        resolved_base = resolved_base.rstrip("/")

        self.base_url = f"{resolved_base}/api/generate"
        self.tags_url = f"{resolved_base}/api/tags"
        self.default_model = default_model or cfg.get("ModelName", "gpt-oss:120b-cloud")
        self.temperature = float(temperature if temperature is not None else cfg.get("Temperature", 0.7))
        self.timeout = float(timeout if timeout is not None else cfg.get("Timeout", 90))
        self.max_retries = int(max_retries if max_retries is not None else cfg.get("MaxRetries", 2))

    def is_available(self) -> bool:
        """Quick health check against Ollama /api/tags. Returns True if reachable."""
        try:
            r = requests.get(self.tags_url, timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def generate_response(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Send a prompt to Ollama and return the generated text.

        Retries transient failures (ConnectionError, Timeout) up to
        max_retries times with exponential backoff (1s, 2s, 4s, ...).
        HTTP 4xx/5xx responses are not retried (usually a config issue).
        On permanent failure returns a string starting with FALLBACK_PREFIX
        so callers can detect a degraded response.
        """
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature, "top_p": 0.9},
        }

        last_err: Optional[Exception] = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            try:
                logging.info(f"Calling Ollama (model={target_model}, attempt={attempt + 1}/{attempts})")
                response = requests.post(self.base_url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()
                text = result.get("response", "").strip()
                if not text:
                    return f"{self.FALLBACK_PREFIX} 模型返回空响应"
                return text
            except requests.exceptions.HTTPError as e:
                logging.error(f"Ollama HTTP error (no retry): {e}")
                return f"{self.FALLBACK_PREFIX} 模型 API 错误: {e}"
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
                if attempt < attempts - 1:
                    wait = 2 ** attempt
                    logging.warning(f"Ollama transient error: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
            except Exception as e:
                logging.error(f"Ollama integration error: {e}")
                return f"{self.FALLBACK_PREFIX} {e}"

        return f"{self.FALLBACK_PREFIX} 重试 {self.max_retries} 次后仍失败: {last_err}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = LLMService()
    print(f"Ollama available: {service.is_available()}")
    test_prompt = "请简要解释什么是变压器油色谱分析。"
    print(f"Prompt: {test_prompt}")
    print(f"Response: {service.generate_response(test_prompt)}")
