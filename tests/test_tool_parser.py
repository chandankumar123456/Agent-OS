from app.tools.parser import ToolCallParser


def test_parser_detects_tool_call():
    output = {"result": "searching...", "tool_call": {"name": "web_search", "params": {"query": "test"}}}
    parsed = ToolCallParser.parse(output)
    assert parsed is not None
    assert parsed["name"] == "web_search"
    assert parsed["params"]["query"] == "test"


def test_parser_returns_none_without_tool_call():
    output = {"result": "done", "details": "no tools needed"}
    parsed = ToolCallParser.parse(output)
    assert parsed is None


def test_parser_handles_string_tool_call():
    output = {"result": "searching...", "tool_call": '{"name": "calculator", "params": {"expression": "2+2"}}'}
    parsed = ToolCallParser.parse(output)
    assert parsed is not None
    assert parsed["name"] == "calculator"


def test_has_tool_call_true():
    output = {"tool_call": {"name": "test"}}
    assert ToolCallParser.has_tool_call(output) is True


def test_has_tool_call_false():
    output = {"result": "done"}
    assert ToolCallParser.has_tool_call(output) is False
