import asyncio
import os
import pytest
import tempfile
from pathlib import Path
from core.tools.file_discovery import FastFileDiscovery


@pytest.fixture
def sample_tree():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
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
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        assert any("project_report.pdf" in r for r in result)
        assert any("archive_report.docx" in r for r in result)
        assert any("old_report.rtf" in r for r in result)

    def test_tier2_keyword_expansion(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        assert any("major_project_report.docx" in r for r in result)

    def test_tier3_file_type_priority(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = []
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        names = [Path(r).name for r in result]
        assert "project_report.pdf" in names
        assert "archive_report.docx" in names
        assert "major_project_report.docx" in names

    def test_tier4_indexed_search(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = [sample_tree / "Desktop", sample_tree / "Documents"]
        index = engine._build_index()
        assert index is not None
        assert len(index) >= 4
        result = asyncio.run(engine.search(str(sample_tree), "*report*", max_results=10))
        names = [Path(r).name for r in result]
        assert "project_report.pdf" in names

    def test_tier5_deep_recursive_finds_everything(self, sample_tree):
        engine = FastFileDiscovery(cache_dir=str(sample_tree / "cache"))
        engine.common_dirs = []
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
        result = asyncio.run(engine.search(str(sample_tree / "does_not_exist"), "*", max_results=10))
        assert result == []
