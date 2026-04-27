def test_build_default_params_never_returns_empty_dict_for_desktop():
    from app.langgraph.nodes import _build_default_params
    for action in ["screenshot", "click", "type_text", "press_key", "get_window_list",
                   "focus_window", "get_clipboard", "set_clipboard", "get_mouse_position",
                   "scroll", "close"]:
        result = _build_default_params(f"desktop_env__{action}", f"do {action}")
        assert result is None, f"desktop_env__{action} returned {result}, expected None"

def test_build_default_params_never_returns_empty_dict_for_browser():
    from app.langgraph.nodes import _build_default_params
    for action in ["launch", "navigate", "search", "click", "type", "screenshot", "get_text", "close"]:
        result = _build_default_params(f"browser_env__{action}", f"do {action}")
        assert result is None, f"browser_env__{action} returned {result}, expected None"

def test_desktop_grounding_has_no_double_prefix_tools():
    from app.tools.grounding import CAPABILITY_TOOL_MAP
    desktop_tools = CAPABILITY_TOOL_MAP.get("desktop_automation", [])
    for name in desktop_tools:
        assert "desktop__desktop__" not in name, f"Found double-prefix tool: {name}"

def test_desktop_grounding_includes_actual_semantic_tools():
    from app.tools.grounding import CAPABILITY_TOOL_MAP
    desktop_tools = CAPABILITY_TOOL_MAP.get("desktop_automation", [])
    assert "desktop__get_ui_tree" in desktop_tools
    assert "desktop__click_element" in desktop_tools
    assert "desktop__type_element" in desktop_tools
    assert "desktop__focus_and_interact" in desktop_tools
