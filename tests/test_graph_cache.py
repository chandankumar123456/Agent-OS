"""Tests for graph cache LRU eviction (NFR2)."""
from unittest.mock import MagicMock
from core.langgraph.graphs import _graph_cache


def test_graph_cache_lru_eviction():
    """NFR2: Graph cache must evict oldest entries when max 50 exceeded."""
    # Inject 51 entries
    for i in range(51):
        _graph_cache[f"key-{i}"] = MagicMock()
    assert len(_graph_cache) <= 50
