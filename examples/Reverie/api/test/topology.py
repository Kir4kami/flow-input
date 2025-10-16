#测试拓扑接口

import requests

url = "http://localhost:8001/generate-topology"
data = {"torSwitches": 8, "spineSwitches": 4}

try:
    print("正在发送请求...")
    response = requests.post(url, json=data)
    print(f"响应状态码: {response.status_code}")
    print("响应内容:")
    print(response.json())
except requests.exceptions.ConnectionError as e:
    print(f"连接错误: {e}")
except requests.exceptions.RequestException as e:
    print(f"请求错误: {e}")
except Exception as e:
    print(f"其他错误: {e}")