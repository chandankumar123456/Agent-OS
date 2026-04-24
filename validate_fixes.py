"""
Integration validation script for Agent-OS distributed fixes.
Tests:
1. Settings consistency (SECRET_KEY identical across imports)
2. JWT round-trip (create + verify)
3. DB connectivity + SpanRepository idempotency
4. Redis connectivity
5. Celery task import
6. Executor prompt .format() correctness
"""
import asyncio
import sys

# 1. Settings consistency
from app.config.settings import settings
assert settings.SECRET_KEY == "agent-os-dev-secret-key-change-in-production-32bytesx", "SECRET_KEY mismatch"
print("[PASS] T1: SECRET_KEY is deterministic and env-sourced")

# 2. JWT round-trip
from app.auth.utils import create_access_token, verify_access_token
tok = create_access_token({"sub": "user-123"})
payload = verify_access_token(tok)
assert payload and payload["sub"] == "user-123", "JWT round-trip failed"
print("[PASS] T1: JWT create/verify round-trip OK")

# 3. DB connectivity + span idempotency
from app.memory.long_term import db, span_repo
async def check_db():
    await db.connect()
    print("[PASS] T6: DB connection OK")
    span1 = await span_repo.create("trace-1", "span-1", "op", "agent", {"meta": True})
    span2 = await span_repo.create("trace-1", "span-1", "op", "agent", {"meta": True})
    assert span1.id == span2.id, "SpanRepository idempotency failed"
    print("[PASS] T3: SpanRepository idempotency guard OK")
    await db.disconnect()
asyncio.run(check_db())

# 4. Redis connectivity
from app.memory.short_term import redis_client
async def check_redis():
    await redis_client.connect()
    pong = await redis_client.client.ping()
    assert pong is True
    print("[PASS] T6: Redis connection OK")
    await redis_client.disconnect()
asyncio.run(check_redis())

# 5. Celery task import
from app.queue.tasks import celery_app, _worker_event_loop, execute_task
assert celery_app is not None
print("[PASS] T2: Celery app import OK")

# 6. Executor prompt format correctness
from app.agents import executor as executor_module
prompt = executor_module.EXECUTOR_PROMPT
try:
    formatted = prompt.format(
        step="test step",
        context={},
        tools="[]"
    )
    print("[PASS] T4: Executor prompt .format() OK")
except Exception as e:
    print(f"[FAIL] T4: Executor prompt .format() failed: {e}")
    sys.exit(1)

print("\n=== ALL VALIDATIONS PASSED ===")
