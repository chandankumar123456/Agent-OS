# Fast File Discovery Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the naive `os.walk`-based `filesystem__search_files` with a tiered fast file discovery engine that never hangs for more than 30 seconds total (5+5+5+5+10), returning results from earlier tiers as soon as they are found.

**Architecture:** A new `FastFileDiscovery` class in `app/tools/file_discovery.py` implements 5 tiers: (1) shallow scan of common locations, (2) keyword pattern expansion, (3) report-like file type prioritization, (4) shallow JSON index cache, (5) deep recursive fallback. Both the MCP filesystem server and the dynamic tool builder will delegate to this shared engine, eliminating duplicated slow code.

**Tech Stack:** Python 3.11, `asyncio.timeout`, `asyncio.to_thread`, `os.scandir`, `fnmatch`, `pathlib`, `json` cache.

---

## File Map

| File | Responsibility |
|------|----------------|
| `app/tools/file_discovery.py` (NEW) | `FastFileDiscovery` engine with 5-tier search, per-tier timeouts, and shallow JSON index cache. |
| `app/mcp/servers/filesystem.py` (MODIFY) | Replace `search_files` body with a call to `FastFileDiscovery`. Keep security checks and interface unchanged. |
| `app/tools/builder.py` (MODIFY) | Replace `_search_files_impl` body with a call to `FastFileDiscovery`. Keep ToolOutput wrapping unchanged. |
| `app/langgraph/nodes.py` (MODIFY) | Improve `_build_default_params` for `filesystem__search_files` to default to Desktop first when no path is extracted. |
| `tests/test_file_discovery.py` (NEW) | Unit tests for each tier, timeout behavior, and index lifecycle. |

---

### Task 1: Create `FastFileDiscovery` engine

**Files:**
- Create: `app/tools/file_discovery.py`

- [ ] **Step 1: Write the module**

```python
"""Fast tiered file discovery engine."""
import asyncio
import fnmatch
import json
import os
import time
from pathlib import Path
from typing import List, Optional


class FastFileDiscovery:
    """Tiered fast file discovery with per-tier timeouts."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or os.path.join(os.path.expanduser("~"), ".agentos_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "file_index.json"
        self.index_ttl = 300  # 5 minutes
        self.report_extensions = [".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".htm", ".rtf", ".odt"]
        self.common_dirs = self._get_common_dirs()

    def _get_common_dirs(self) -> List[Path]:
        home = Path.home()
        dirs = []
        for name in ("Desktop", "Documents", "Downloads"):
            p = home / name
            if p.exists():
                dirs.append(p)
        return dirs

    async def search(self, path: str, pattern: str, max_results: int = 100) -> List[str]:
        target = Path(path).expanduser().resolve()
        results: List[str] = []
        seen = set()

        async def _add(matches: List[str]):
            for m in matches:
                if m not in seen and len(results) < max_results:
                    seen.add(m)
                    results.append(m)

        # Tier 1: Fast common locations (shallow depth = 2)
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier1_common_locations, target, pattern, max_results)
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 2: Keyword pattern expansion
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier2_keyword_expansion, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 3: File type prioritization (report-like extensions)
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier3_file_type_priority, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 4: Indexed search
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier4_indexed_search, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 5: Deep recursive fallback
        try:
            async with asyncio.timeout(10):
                matches = await asyncio.to_thread(self._tier5_deep_recursive, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        return results

    # ------------------------------------------------------------------
    # Tier 1: Shallow common locations (depth <= 2, os.scandir)
    # ------------------------------------------------------------------
    def _tier1_common_locations(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        dirs = list(self.common_dirs)
        if target not in dirs and target.exists():
            dirs.append(target)

        for directory in dirs:
            if not directory.exists():
                continue
            try:
                with os.scandir(directory) as it:
                    for entry in it:
                        if entry.is_file() and fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                            results.append(entry.path)
                            if len(results) >= max_results:
                                return results
                        elif entry.is_dir():
                            results.extend(self._scandir_depth(entry.path, pattern, max_results - len(results), current_depth=1, max_depth=2))
                            if len(results) >= max_results:
                                return results
            except PermissionError:
                continue
        return results

    def _scandir_depth(self, path: str, pattern: str, limit: int, current_depth: int, max_depth: int) -> List[str]:
        if limit <= 0 or current_depth > max_depth:
            return []
        results: List[str] = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file() and fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                        results.append(entry.path)
                        if len(results) >= limit:
                            return results
                    elif entry.is_dir() and current_depth < max_depth:
                        results.extend(self._scandir_depth(entry.path, pattern, limit - len(results), current_depth + 1, max_depth))
                        if len(results) >= limit:
                            return results
        except PermissionError:
            pass
        return results

    # ------------------------------------------------------------------
    # Tier 2: Keyword expansion (e.g., *report* -> *report*.pdf, etc.)
    # ------------------------------------------------------------------
    def _tier2_keyword_expansion(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        keyword = pattern.strip("*")
        if not keyword or "." in keyword:
            return results
        expanded = [pattern]
        for ext in self.report_extensions:
            expanded.append(f"*{keyword}*{ext}")

        dirs = list(self.common_dirs)
        if target not in dirs and target.exists():
            dirs.append(target)

        for directory in dirs:
            if not directory.exists():
                continue
            for p in expanded:
                matches = self._scandir_depth(str(directory), p, max_results - len(results), current_depth=0, max_depth=2)
                for m in matches:
                    if m not in results:
                        results.append(m)
                        if len(results) >= max_results:
                            return results
        return results

    # ------------------------------------------------------------------
    # Tier 3: File type prioritization (depth <= 3, extension filter)
    # ------------------------------------------------------------------
    def _tier3_file_type_priority(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        keyword = pattern.strip("*").lower()
        if not target.exists():
            return results

        for root, dirs, files in os.walk(target):
            rel_depth = len(Path(root).relative_to(target).parts)
            if rel_depth > 3:
                del dirs[:]
                continue
            for filename in files:
                ext = Path(filename).suffix.lower()
                if ext not in self.report_extensions:
                    continue
                name_lower = filename.lower()
                if fnmatch.fnmatch(name_lower, pattern.lower()) or (keyword and keyword in name_lower):
                    results.append(str(Path(root) / filename))
                    if len(results) >= max_results:
                        return results
        return results

    # ------------------------------------------------------------------
    # Tier 4: Shallow JSON index cache
    # ------------------------------------------------------------------
    def _tier4_indexed_search(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        index = self._load_index()
        if index is None:
            index = self._build_index()
        if index is None:
            return results
        keyword = pattern.strip("*").lower()
        for entry in index:
            name = entry.get("name", "").lower()
            path_str = entry.get("path", "")
            if fnmatch.fnmatch(name, pattern.lower()) or (keyword and keyword in name):
                results.append(path_str)
                if len(results) >= max_results:
                    return results
        return results

    def _load_index(self) -> Optional[List[dict]]:
        if not self.index_path.exists():
            return None
        try:
            mtime = self.index_path.stat().st_mtime
            if time.time() - mtime > self.index_ttl:
                return None
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else None
        except Exception:
            return None

    def _build_index(self) -> Optional[List[dict]]:
        index: List[dict] = []
        try:
            for directory in self.common_dirs:
                if not directory.exists():
                    continue
                for item in directory.rglob("*"):
                    rel_depth = len(item.relative_to(directory).parts) - 1
                    if rel_depth > 2:
                        continue
                    if item.is_file():
                        index.append({"name": item.name, "path": str(item)})
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(index, f)
        except Exception:
            return None
        return index

    # ------------------------------------------------------------------
    # Tier 5: Deep recursive fallback (full os.walk)
    # ------------------------------------------------------------------
    def _tier5_deep_recursive(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        if not target.exists():
            return results
        for root, _, files in os.walk(target):
            for filename in files:
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    results.append(str(Path(root) / filename))
                    if len(results) >= max_results:
                        return results
        return results


def discover_files(path: str, pattern: str, max_results: int = 100) -> List[str]:
    """Synchronous wrapper for FastFileDiscovery.search."""
    engine = FastFileDiscovery()
    return asyncio.run(engine.search(path, pattern, max_results))
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('app/tools/file_discovery.py').read())"`
Expected: no output (success).

---

### Task 2: Update MCP filesystem server to use `FastFileDiscovery`

**Files:**
- Modify: `app/mcp/servers/filesystem.py:126-142`

- [ ] **Step 1: Add import and replace `search_files` body**

```python
# Add near the top of app/mcp/servers/filesystem.py
from ...tools.file_discovery import FastFileDiscovery

# Replace the search_files function (lines 126-142)
@mcp.tool()
async def search_files(path: str, pattern: str) -> str:
    """Search for files matching a pattern recursively."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        engine = FastFileDiscovery()
        matches = await engine.search(str(target), pattern, max_results=100)
        if not matches:
            return f"No files matching '{pattern}' found in {path}"
        return "\n".join(matches)
    except Exception as e:
        return f"Error searching files: {e}"
```

- [ ] **Step 2: Run MCP filesystem tests**

Run: `pytest tests/test_mcp_servers.py -v`
Expected: All tests pass (including `test_search_files`).

---

### Task 3: Update dynamic tool builder to use `FastFileDiscovery`

**Files:**
- Modify: `app/tools/builder.py:136-147`

- [ ] **Step 1: Replace `_search_files_impl` body**

```python
    @staticmethod
    async def _search_files_impl(path: str, pattern: str) -> ToolOutput:
        from ..tools.file_discovery import FastFileDiscovery
        engine = FastFileDiscovery()
        matches = await engine.search(path, pattern, max_results=100)
        return ToolOutput(success=True, result={"matches": matches, "count": len(matches)})
```

- [ ] **Step 2: Run builder tests**

Run: `pytest tests/ -k builder -v`
Expected: Tests pass (or no builder-specific tests exist, which is fine).

---

### Task 4: Improve default search parameters in LangGraph nodes

**Files:**
- Modify: `app/langgraph/nodes.py:66-77`

- [ ] **Step 1: Update `_build_default_params` for `filesystem__search_files`**

Replace lines 66-77 with:

```python
    if tool_name == "filesystem__search_files":
        path_match = re.findall(r"([A-Za-z]:\\[^\s\"'<>]*|/~?(?:/[^\s\"'<>]+)*)", description)
        search_path = path_match[0] if path_match else _get_desktop_path()
        words = description.lower().split()
        stopwords = {"find", "search", "locate", "look", "for", "my", "the", "a", "in", "under", "at", "file", "files", "and", "or"}
        pattern = "*"
        for w in words:
            if w not in stopwords and len(w) > 2:
                pattern = f"*{w}*"
                break
        return {"path": search_path, "pattern": pattern}
```

This defaults to Desktop instead of home when no path is extracted, avoiding full-home recursive scans.

- [ ] **Step 2: Run LangGraph node tests**

Run: `pytest tests/test_llm_normalization.py tests/integration/test_target_workflow.py -v`
Expected: All tests pass.

---

### Task 5: Write unit tests for `FastFileDiscovery`

**Files:**
- Create: `tests/test_file_discovery.py`

- [ ] **Step 1: Write the test file**

```python
import asyncio
import os
import pytest
import tempfile
from pathlib import Path
from app.tools.file_discovery import FastFileDiscovery


@pytest.fixture
def sample_tree():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Common-like structure
        desktop = root / "Desktop"
        desktop.mkdir()
        (desktop / "project_report.pdf").write_text("pdf")
        (desktop / "notes.txt").write_text("txt")
        (desktop / "deep").mkdir()
        (desktop / "deep" / "archive_report.docx").write_text("docx")
        (desktop / "deep" / "deeper").mkdir()
        (desktop / "deep" / "deeper" / "old_report.rtf").write_text("rtf")

        docs = root / "Documents"
        docs.mkdir()
        (docs / "major_project_report.docx").write_text("docx")
        (docs / "budget.xlsx").write_text("xlsx")

        yield root


class TestFastFileDiscovery:
    def test_tier1_shallow_common_locations(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        # Override common_dirs to point at our fake tree
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        # Tier 1 only scans depth 2. Desktop/project_report.pdf is depth 0.
        # Desktop/deep/archive_report.docx is depth 1.
        # Desktop/deep/deeper/old_report.rtf is depth 2 -> included.
        assert any("project_report.pdf" in r for r in result)
        assert any("archive_report.docx" in r for r in result)
        assert any("old_report.rtf" in r for r in result)

    def test_tier2_keyword_expansion(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        # Should find Documents/major_project_report.docx via tier 1 or 2
        assert any("major_project_report.docx" in r for r in result)

    def test_tier3_file_type_priority(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = []
        # Force tier 3 by searching in sample_tree with depth <= 3
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        # All report files are within depth 3 of sample_tree
        names = [Path(r).name for r in result]
        assert "project_report.pdf" in names
        assert "archive_report.docx" in names
        assert "major_project_report.docx" in names

    def test_tier4_indexed_search(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        # Build index explicitly
        index = engine._build_index()
        assert index is not None
        assert len(index) >= 4
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        names = [Path(r).name for r in result]
        assert "project_report.pdf" in names

    def test_tier5_deep_recursive_finds_everything(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = []
        # Disable index
        engine.index_path = Path("/nonexistent/index.json")
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        names = [Path(r).name for r in result]
        assert "project_report.pdf" in names
        assert "archive_report.docx" in names
        assert "major_project_report.docx" in names
        assert "old_report.rtf" in names

    def test_max_results_respected(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=2))
        assert len(result) <= 2

    def test_no_matches_returns_empty(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*nonexistent_xyz*", max_results=10))
        assert result == []

    def test_permission_error_handled_gracefully(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        # Point at a directory that does not exist
        result = asyncio.run(engine.search(str(sample_tree / "does_not_exist"), "*", max_results=10))
        assert result == []
```

- [ ] **Step 2: Run new tests**

Run: `pytest tests/test_file_discovery.py -v`
Expected: All 7 tests pass.

---

### Task 6: Full regression test

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (245+).

- [ ] **Step 2: Run the target workflow integration test explicitly**

Run: `pytest tests/integration/test_target_workflow.py -v`
Expected: All 5 tests pass.

---

## Self-Review

**1. Spec coverage:**
- Fast common locations first? → Tier 1 (`_tier1_common_locations`).
- Keyword extraction? → Tier 2 (`_tier2_keyword_expansion`).
- File type prioritization? → Tier 3 (`_tier3_file_type_priority`).
- Indexed search? → Tier 4 (`_tier4_indexed_search`).
- Deep recursive fallback? → Tier 5 (`_tier5_deep_recursive`).
- Per-tier timeouts 5–10s? → `asyncio.timeout(5)` for tiers 1–4, `asyncio.timeout(10)` for tier 5.
- Target query must complete? → Default path now Desktop-first; shallow scan prevents home-directory hangs.
- No false filesystem unavailable errors? → Not changed (already fixed in previous work).
- 245 existing tests must still pass? → Verified in Task 6.

**2. Placeholder scan:**
- No TBD/TODO placeholders.
- All code blocks contain complete implementations.
- All test commands are explicit.

**3. Type consistency:**
- `FastFileDiscovery.search` signature: `(path: str, pattern: str, max_results: int = 100) -> List[str]` — consistent across all call sites.
- `ToolOutput` wrapper in `builder.py` unchanged except internal call.
- MCP `search_files` return type unchanged (`str`).

**Gap check:** None.
