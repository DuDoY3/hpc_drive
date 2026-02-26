import requests

url = "http://localhost:7777/api/v1/class-storage/1/folders"
headers = {"Authorization": "Bearer dummy"}
data = {"name": "Test Folder", "parent_id": None}

try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
