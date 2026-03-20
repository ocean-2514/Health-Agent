import requests
import json
import logging

class LLMService:
    """
    Utility to interact with local Ollama API for real AI reasoning.
    """
    def __init__(self, base_url="http://localhost:11434", default_model="gpt-oss:120b-cloud"):
        self.base_url = f"{base_url}/api/generate"
        self.default_model = default_model

    def generate_response(self, prompt: str, model: str = None) -> str:
        """
        Send a prompt to Ollama and get the generated text.
        """
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9
            }
        }
        
        try:
            logging.info(f"Calling Ollama with model {target_model}...")
            response = requests.post(self.base_url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            logging.error(f"Ollama integration error: {str(e)}")
            return f"AI 推理失败: {str(e)}"

if __name__ == "__main__":
    # Test script
    service = LLMService()
    test_prompt = "请简要解释什么是变压器油色谱分析。"
    print(f"Prompt: {test_prompt}")
    print(f"Response: {service.generate_response(test_prompt)}")
