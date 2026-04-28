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

    def test_open_notepad_and_type_hello_world_is_sequential(self):
        query = "open notepad and type hello world"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        assert len(phases) == 5, f"Expected 5 sequential phases, got {len(phases)}: {descriptions}"
        assert names == ["desktop_automation"] * 5, f"Expected all desktop phases, got {names}"
        assert "open notepad" in descriptions[0]
        assert "verify notepad is open" in descriptions[1]
        assert "focus the notepad window" in descriptions[2]
        assert "type the requested text into notepad" in descriptions[3]
        assert "verify the text was entered in notepad" in descriptions[4]

    def test_open_notepad_and_type_generated_opinion_includes_content_generation(self):
        query = "open notepad and type your opinion on avengers doomsday vs secret wars"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        assert len(phases) == 6, f"Expected 6 phases for generated content flow, got {len(phases)}: {descriptions}"
        assert names[0] == "desktop_automation"
        assert names[1] == "desktop_automation"
        assert names[2] == "content_generation", f"Expected content generation before typing, got {names}"
        assert names[3:] == ["desktop_automation", "desktop_automation", "desktop_automation"]
        assert "generate the text content requested by the user" in descriptions[2]
        assert "type the requested text into notepad" in descriptions[4]

    def test_open_chrome_and_search_latest_ai_news_is_sequential(self):
        query = "open chrome and search latest AI news"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        assert len(phases) == 4, f"Expected 4 browser phases, got {len(phases)}: {descriptions}"
        assert names == ["browser_navigation"] * 4, f"Expected browser-only phases, got {names}"
        assert "open the browser" in descriptions[0]
        assert "verify the browser window is open" in descriptions[1]
        # Phase 3 description must include the extracted search query, not the entire prompt.
        assert "search for" in descriptions[2]
        assert "latest ai news" in descriptions[2]
        assert "verify search results loaded" in descriptions[3]

    def test_browser_summarize_notepad_save_full_workflow(self):
        query = "open chrome search latest AI news summarize top result paste into notepad save file"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        # Base 4 browser phases + extract + summarize + 3 notepad + file_write + ctrl+s mirror = 11
        assert len(phases) == 11, f"Expected 11 phases, got {len(phases)}: {names}"
        assert names[:4] == ["browser_navigation"] * 4
        # Phase 3 must search "latest ai news", not the entire user prompt.
        assert "latest ai news" in descriptions[2]
        assert "summarize top result paste into notepad save file" not in descriptions[2]
        # Phase 5: extract top result.
        assert names[4] == "browser_navigation"
        assert "top search result" in descriptions[4]
        # Phase 6: summarize.
        assert names[5] == "document_processing"
        assert "summariz" in descriptions[5]
        # Phases 7-9: open / focus / type Notepad.
        assert names[6:9] == ["desktop_automation"] * 3
        assert "open notepad" in descriptions[6]
        assert "focus the notepad window" in descriptions[7]
        assert "type" in descriptions[8] and "notepad" in descriptions[8]
        # Phase 10: filesystem write (authoritative save).
        assert names[9] == "file_write"
        assert "summary.txt" in descriptions[9]
        assert "filesystem__write_file" in descriptions[9]
        # Phase 11: Notepad Ctrl+S mirror.
        assert names[10] == "desktop_automation"
        assert "ctrl+s" in descriptions[10]

    def test_browser_youtube_summarize_notepad_no_save(self):
        query = "open youtube search marvel trailers summarize comments paste into notepad"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        # Trigger must accept "open youtube" (known site, not just browser app).
        assert names[0] == "browser_navigation"
        assert "youtube.com" in descriptions[0]
        # Search query must be "marvel trailers".
        assert "marvel trailers" in descriptions[2]
        # Comments-extraction branch (not generic top-result branch).
        comments_phases = [d for d in descriptions if "comments" in d]
        assert comments_phases, f"Expected a comments-extraction phase, got {descriptions}"
        # Summarize phase present.
        assert "document_processing" in names
        # Notepad branch present (open/focus/type).
        desktop_count = sum(1 for n in names if n == "desktop_automation")
        assert desktop_count >= 3, f"Expected >=3 desktop phases for notepad, got {names}"
        # No file_write phase (no save keyword).
        assert "file_write" not in names, f"Did not expect file_write in {names}"

    def test_browser_search_and_save_summary_no_notepad(self):
        query = "open chrome search latest AI startups and save summary"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        descriptions = [p.description.lower() for p in phases]

        # Search query extraction must stop at "and save".
        assert "latest ai startups" in descriptions[2]
        assert "save summary" not in descriptions[2]
        # Summarize phase present (transform keyword "summary").
        assert "document_processing" in names, f"Expected summarize phase, got {names}"
        # File write phase present.
        assert "file_write" in names, f"Expected file_write phase, got {names}"
        # No notepad branch (no notepad/wordpad keyword and no paste verb).
        assert "desktop_automation" not in names, f"Did not expect desktop phases, got {names}"
