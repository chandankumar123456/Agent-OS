import asyncio
import os
import pytest
from core.memory.redis_pubsub import RedisPubSubClient


@pytest.mark.skipif(not os.environ.get("REDIS_URL"), reason="REDIS_URL not set")
@pytest.mark.asyncio
async def test_pubsub_connect_publish_subscribe():
    client = RedisPubSubClient()
    await client.connect()
    channel = "agentos:test:pubsub"
    received: list[str] = []

    async def listener():
        async for msg in client.subscribe(channel):
            received.append(msg)
            if len(received) >= 1:
                break

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.2)
    await client.publish(channel, "hello")
    await asyncio.wait_for(task, timeout=5)
    await client.disconnect()
    assert received == ["hello"]


@pytest.mark.skipif(not os.environ.get("REDIS_URL"), reason="REDIS_URL not set")
@pytest.mark.asyncio
async def test_pubsub_reconnect_after_dead_connection():
    client = RedisPubSubClient()
    await client.connect()
    # Forcefully close underlying connection to simulate death
    if client._client:
        await client._client.aclose()
        client._client = None
    # Next operation should reconnect transparently
    await client.connect()
    assert client._client is not None
    await client.disconnect()
