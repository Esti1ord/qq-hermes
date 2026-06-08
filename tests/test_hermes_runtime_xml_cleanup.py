from qq_hermes_bridge import hermes_runtime


def test_strip_tool_call_xml_removes_function_calls_blocks():
    raw = "text <function_calls>content</function_calls> more"
    clean = hermes_runtime.strip_tool_call_xml(raw)
    assert "<function_calls>" not in clean
    assert "text" in clean
    assert "more" in clean


def test_strip_tool_call_xml_removes_parameter_tags():
    raw = "start <parameter>val</parameter> end"
    clean = hermes_runtime.strip_tool_call_xml(raw)
    assert "<parameter>" not in clean
    assert "start" in clean
    assert "end" in clean


def test_strip_tool_call_xml_removes_standalone_tags():
    raw = "a <function_calls> b </invoke> c"
    clean = hermes_runtime.strip_tool_call_xml(raw)
    assert "<function_calls>" not in clean
    assert "</invoke>" not in clean
    assert "a" in clean
    assert "b" in clean
    assert "c" in clean


def test_strip_session_footer_includes_xml_cleanup():
    raw = "reply <function_calls>x</function_calls> more\nsession_id: abc123"
    clean = hermes_runtime.strip_session_footer(raw)
    assert "<function_calls>" not in clean
    assert "session_id" not in clean
    assert "reply" in clean
    assert "more" in clean


def test_strip_tool_call_xml_preserves_normal_text():
    raw = "normal text without tags"
    clean = hermes_runtime.strip_tool_call_xml(raw)
    assert clean == raw
