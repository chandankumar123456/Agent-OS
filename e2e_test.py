"""
End-to-end FastAPI integration test for Agent-OS auth and tasks.
Uses TestClient with lifespan context to simulate full request lifecycle.
"""
import sys
from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as client:
    # 1. Health check
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health failed: {resp.text}"
    print("[PASS] Health check OK")

    # 2. Signup
    signup_resp = client.post("/api/v1/auth/signup", json={
        "email": "test@agentos.example.com",
        "password": "TestPass123",
        "name": "Test User"
    })
    assert signup_resp.status_code == 200, f"Signup failed: {signup_resp.text}"
    token = signup_resp.json()["access_token"]
    print("[PASS] Signup OK, token received")

    # 3. List tasks with Bearer token
    tasks_resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
    assert tasks_resp.status_code == 200, f"List tasks failed: {tasks_resp.text}"
    assert isinstance(tasks_resp.json(), list), "Tasks response is not a list"
    print("[PASS] List tasks (authed) OK")

    # 4. Create task
    create_resp = client.post("/api/v1/tasks", json={
        "query": "test query",
        "config": {"max_steps": 2, "timeout": 60},
        "mode": "task"
    }, headers={"Authorization": f"Bearer {token}"})
    assert create_resp.status_code == 200, f"Create task failed: {create_resp.text}"
    task_id = create_resp.json()["task_id"]
    print(f"[PASS] Create task OK (task_id={task_id})")

    # 5. Get task by ID
    get_resp = client.get(f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 200, f"Get task failed: {get_resp.text}"
    print("[PASS] Get task OK")

print("\n=== END-TO-END API VALIDATION PASSED ===")
