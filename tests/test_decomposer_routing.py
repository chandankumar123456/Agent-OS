import pytest
from app.workflows.decomposer import WorkflowDecomposer


class TestDecomposerRouting:
    def setup_method(self):
        self.decomposer = WorkflowDecomposer()

    def test_desktop_app_notepad_routes_to_desktop(self):
        query = "open notepad and write hello world"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names, f"Expected desktop_automation in {names}"
        assert "shell_execution" not in names, f"Shell shortcut should not appear for GUI apps, got {names}"

    def test_desktop_app_calculator_routes_to_desktop(self):
        query = "open calculator and click 1 + 1"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names, f"Expected desktop_automation in {names}"

    def test_desktop_app_vscode_routes_to_desktop(self):
        query = "open vscode and type some code"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names, f"Expected desktop_automation in {names}"

    def test_browser_search_routes_to_browser(self):
        query = "search google for python tutorials"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "browser_navigation" in names, f"Expected browser_navigation in {names}"
        assert "desktop_automation" not in names, f"Desktop should not appear for pure web query, got {names}"

    def test_browser_chrome_routes_to_browser(self):
        query = "open chrome and go to youtube"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "browser_navigation" in names, f"Expected browser_navigation in {names}"

    def test_mixed_prompt_splits_sequentially_desktop_first(self):
        query = "open notepad write hello then open chrome and search python"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names, f"Expected desktop_automation in {names}"
        assert "browser_navigation" in names, f"Expected browser_navigation in {names}"
        desktop_idx = names.index("desktop_automation")
        browser_idx = names.index("browser_navigation")
        assert desktop_idx < browser_idx, f"Desktop phases must precede browser phases, got {names}"

    def test_pure_shell_command_still_works(self):
        query = "run git status and then npm install"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "shell_execution" in names, f"Expected shell_execution in {names}"

    def test_file_explorer_is_filesystem_not_desktop_ui(self):
        query = "open file explorer and find my report"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "file_search" in names, f"Expected file_search for file explorer query, got {names}"
        assert "desktop_automation" not in names, f"file explorer should NOT route to desktop_automation, got {names}"
