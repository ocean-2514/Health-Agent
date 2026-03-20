import requests

# 测试API连接
def test_ollama():
    # 1. 测试API是否可用
    try:
        response = requests.get("http://localhost:11434/api/tags")
        print(f"API连接成功: {response.status_code}")
        print(f"可用模型: {response.json()}")
    except Exception as e:
        print(f"API连接失败: {e}")
    
    # 2. 测试生成请求
    try:
        payload = {
            "model": "gpt-oss:120b-cloud",  # 云模型
            "prompt": "Hello",
            "stream": False
        }
        response = requests.post("http://localhost:11434/api/generate", json=payload)
        print(f"生成请求状态: {response.status_code}")
        if response.status_code == 200:
            print(f"响应: {response.json()}")
        else:
            print(f"错误: {response.text}")
    except Exception as e:
        print(f"生成请求失败: {e}")

if __name__ == "__main__":
    test_ollama()