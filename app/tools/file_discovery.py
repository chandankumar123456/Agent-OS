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
        if not target.exists():
            return []

        results: List[str] = []
        seen = set()

        async def _add(matches: List[str]):
            for m in matches:
                if m not in seen and len(results) < max_results:
                    seen.add(m)
                    results.append(m)

        # Tier 1: Shallow fast scan of target (depth <= 2)
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier1_shallow_fast, target, pattern, max_results)
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 2: Keyword pattern expansion in target shallow
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier2_keyword_expansion, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 3: File type prioritization (report-like extensions, depth <= 3)
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier3_file_type_priority, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 4: Indexed search (only when target is home or a common dir)
        try:
            async with asyncio.timeout(5):
                matches = await asyncio.to_thread(self._tier4_indexed_search, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        if len(results) >= max_results:
            return results

        # Tier 5: Deep recursive fallback (full os.walk)
        try:
            async with asyncio.timeout(10):
                matches = await asyncio.to_thread(self._tier5_deep_recursive, target, pattern, max_results - len(results))
                await _add(matches)
        except asyncio.TimeoutError:
            pass

        return results

    # ------------------------------------------------------------------
    # Tier 1: Shallow fast scan of target (depth <= 2, os.scandir)
    # ------------------------------------------------------------------
    def _tier1_shallow_fast(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        if not target.exists():
            return results
        try:
            with os.scandir(target) as it:
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
            pass
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

        if not target.exists():
            return results

        for p in expanded:
            matches = self._scandir_depth(str(target), p, max_results - len(results), current_depth=0, max_depth=2)
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
    # Tier 4: Shallow JSON index cache (only for home / common dirs)
    # ------------------------------------------------------------------
    def _tier4_indexed_search(self, target: Path, pattern: str, max_results: int) -> List[str]:
        results: List[str] = []
        home = Path.home().resolve()
        # Only use index when target is home or a common dir (index covers common dirs)
        if target != home and target not in self.common_dirs:
            return results

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
