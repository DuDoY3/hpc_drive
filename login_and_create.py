import requests
import json

base_url = "http://localhost:7777/api/v1"
auth_url = "http://hpc_web:80/api/v1/login"

resp = requests.post(auth_url, json={"username": "gv_gv001", "password": "123456"})
if resp.status_code != 200:
    print("Login failed:", resp.text)
    # wait, could be hpc_web. Let's try hpc_web
    import sys
    sys.exit(1)

token = resp.json().get("access_token") or resp.json().get("token")
if not token:
    print("No token in response:", resp.json())
    import sys
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}
print("Got token, calling auto-generate")
create_resp = requests.post(f"{base_url}/class-storage/auto-generate/1", headers=headers)
print("Create status:", create_resp.status_code)
try:
    print(json.dumps(create_resp.json(), indent=2))
except:
    print(create_resp.text)
