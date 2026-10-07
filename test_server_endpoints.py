"""Verify that /api/chat/procure and /favicon.ico exist and respond properly."""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.server import app

from fastapi.testclient import TestClient

def test_routes():
    client = TestClient(app)

    # 1. Test /favicon.ico
    fav_res = client.get("/favicon.ico")
    print(f"GET /favicon.ico status: {fav_res.status_code}")
    assert fav_res.status_code in [200, 204]

    # 2. Test /api/health
    health_res = client.get("/api/health")
    print(f"GET /api/health status: {health_res.status_code}, data: {health_res.json()}")
    assert health_res.status_code == 200

    # 3. Test /api/chat/procure
    procure_res = client.post("/api/chat/procure", json={"prompt": "switch poe"})
    print(f"POST /api/chat/procure status: {procure_res.status_code}")
    assert procure_res.status_code == 200
    print("PASS: /api/chat/procure responds with 200 OK!")

if __name__ == "__main__":
    test_routes()
