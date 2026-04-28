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

def test_desktop_grounding_includes_mcp_double_prefix_tools():
    """MCP desktop tools use a double-prefix namespace (desktop__desktop__*).

    These tools are registered at runtime by the MCP desktop server.  If they
    are omitted from CAPABILITY_TOOL_MAP, the grounding layer silently drops
    them and falls back to generic tools — the exact bug this suite guards
    against.
    """
    from app.tools.grounding import CAPABILITY_TOOL_MAP
    desktop_tools = CAPABILITY_TOOL_MAP.get("desktop_automation", [])
    mcp_tools = [
        "desktop__desktop__screenshot",
        "desktop__desktop__click",
        "desktop__desktop__type_text",
        "desktop__desktop__press_key",
        "desktop__desktop__get_window_list",
        "desktop__desktop__focus_window",
        "desktop__desktop__get_clipboard",
        "desktop__desktop__set_clipboard",
        "desktop__desktop__get_ui_tree",
        "desktop__desktop__click_element",
        "desktop__desktop__type_element",
        "desktop__desktop__focus_and_interact",
    ]
    for name in mcp_tools:
        assert name in desktop_tools, f"Missing MCP desktop tool in capability map: {name}"

def test_desktop_grounding_includes_actual_semantic_tools():
    from app.tools.grounding import CAPABILITY_TOOL_MAP
    desktop_tools = CAPABILITY_TOOL_MAP.get("desktop_automation", [])
    assert "desktop__get_ui_tree" in desktop_tools
    assert "desktop__click_element" in desktop_tools
    assert "desktop__type_element" in desktop_tools
    assert "desktop__focus_and_interact" in desktop_tools

import pytest

@pytest.mark.asyncio
async def test_desktop_app_opened_verifier():
    from app.capabilities.verification import DeterministicVerificationEngine
    engine = DeterministicVerificationEngine()
    report = await engine.verify(
        task_id="test-1", step_id="s1",
        verification_type="desktop_app_opened",
        criteria={"process_name": "python"}
    )
    assert report.result.value in ("pass", "fail")
    assert report.verifier_type == "deterministic"

@pytest.mark.asyncio
async def test_desktop_text_typed_verifier():
    from app.capabilities.verification import DeterministicVerificationEngine
    engine = DeterministicVerificationEngine()
    report = await engine.verify(
        task_id="test-1", step_id="s1",
        verification_type="desktop_text_typed",
        criteria={"text": "hello", "window_title": ""}
    )
    assert report.result.value in ("pass", "fail")
    assert report.verifier_type == "deterministic"

@pytest.mark.asyncio
async def test_verify_plan_detects_desktop_keywords():
    from app.capabilities.verification import DeterministicVerificationEngine
    engine = DeterministicVerificationEngine()
    plan = [
        {"id": "s1", "step": "Open Notepad"},
        {"id": "s2", "step": "Type hello into Notepad"},
    ]
    reports = await engine.verify_plan("test-task", plan)
    types = [r.checks[0]["type"] for r in reports if r.checks]
    assert "desktop_app_opened" in types or "desktop_text_typed" in types, f"Expected desktop verifiers in {types}"

def test_desktop_env_tools_have_parameter_schemas():
    from app.tools.registry import tool_registry
    for action in ["screenshot", "click", "type_text", "press_key", "get_window_list",
                   "focus_window", "get_clipboard", "set_clipboard", "get_mouse_position",
                   "scroll", "close"]:
        name = f"desktop_env__{action}"
        schema = tool_registry.get(name).get_schema()
        params = schema.get("parameters", {})
        assert isinstance(params, dict), f"{name} parameters is not a dict"
        assert "properties" in params or params == {}, f"{name} missing properties"
        if action == "type_text":
            props = params.get("properties", {})
            assert "text" in props, f"desktop_env__type_text missing 'text' property"

def test_browser_env_tools_have_parameter_schemas():
    from app.tools.registry import tool_registry
    for action in ["launch", "navigate", "search", "click", "type", "screenshot", "get_text", "close"]:
        name = f"browser_env__{action}"
        schema = tool_registry.get(name).get_schema()
        params = schema.get("parameters", {})
        assert isinstance(params, dict), f"{name} parameters is not a dict"
        assert "properties" in params or params == {}, f"{name} missing properties"
        if action == "navigate":
            props = params.get("properties", {})
            assert "url" in props, f"browser_env__navigate missing 'url' property"

def test_document_tools_have_parameter_schemas():
    from app.tools.registry import tool_registry
    for name in ["document__parse", "document__parse_pdf", "document__parse_docx", "document__parse_txt", "document__parse_markdown"]:
        schema = tool_registry.get(name).get_schema()
        params = schema.get("parameters", {})
        assert isinstance(params, dict), f"{name} parameters is not a dict"
        assert "properties" in params, f"{name} missing properties"
        assert "path" in params["properties"], f"{name} missing 'path' property"

def test_code_tools_have_parameter_schemas():
    from app.tools.registry import tool_registry
    name = "code_executor__run_python"
    schema = tool_registry.get(name).get_schema()
    params = schema.get("parameters", {})
    assert isinstance(params, dict), f"{name} parameters is not a dict"
    assert "properties" in params, f"{name} missing properties"
    assert "code" in params["properties"], f"{name} missing 'code' property"
