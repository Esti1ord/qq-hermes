from types import SimpleNamespace

from qq_hermes_bridge import search_runtime


def test_build_curl_verify_prompt_uses_sports_rule_for_sports_queries():
    prompt = search_runtime.build_curl_verify_prompt(
        query="今晚欧冠比分",
        normalized_query="今晚欧冠比分 2026-06-03",
        evidence="摘录内容",
        date_context="当前日期：2026-06-03。",
    )

    assert "今晚欧冠比分" in prompt
    assert "今晚欧冠比分 2026-06-03" in prompt
    assert "摘录内容" in prompt
    assert "如果问欧冠，只回答欧冠/UEFA Champions League" in prompt


def test_build_curl_verify_prompt_uses_non_sports_rule_for_normal_queries():
    prompt = search_runtime.build_curl_verify_prompt(
        query="驻马店天气",
        normalized_query="驻马店天气 2026-06-03",
        evidence="天气摘录",
        date_context="当前日期：2026-06-03。",
    )

    assert "不要套用体育/赛事校验" in prompt
    assert "驻马店天气 2026-06-03" in prompt


def test_join_curl_evidence_truncates_item_and_total_lengths():
    outputs = ["甲" * 5000, "乙" * 5000]

    evidence = search_runtime.join_curl_evidence(outputs, per_item_limit=10, total_limit=30)

    assert evidence == (("甲" * 10) + "\n\n---\n\n" + ("乙" * 10))[:30]


def test_build_llm_search_prompt_includes_date_and_normalized_query():
    prompt = search_runtime.build_llm_search_prompt(
        query="Esti 最新消息",
        normalized_query="最新消息 2026-06-03",
        date_context="当前日期：2026-06-03。",
    )

    assert "联网核对 QQ 群友提到的最新/实时信息" in prompt
    assert "当前日期：2026-06-03。" in prompt
    assert "原问题：Esti 最新消息" in prompt
    assert "规范化查询：最新消息 2026-06-03" in prompt


def test_finalize_llm_search_result_maps_empty_and_truncates():
    assert search_runtime.finalize_llm_search_result("", normalized_query="问题", max_chars=10, empty_reply_fn=lambda q: f"空:{q}") == "空:问题"
    assert search_runtime.finalize_llm_search_result("  123456789012345  ", normalized_query="问题", max_chars=10, empty_reply_fn=lambda q: f"空:{q}") == "1234567890"


def test_run_curl_search_collects_usable_outputs_and_verifies():
    fetched = []
    logs = []

    def fetch_url(url):
        fetched.append(url)
        return SimpleNamespace(returncode=0, stdout=f"正文 {url}")

    result = search_runtime.run_curl_search(
        "问题",
        normalize_query_fn=lambda query: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        plan_search_queries_fn=lambda query: ["q1", "q2"],
        search_urls_for_query_fn=lambda query: [f"{query}-a", f"{query}-b"],
        fetch_url_fn=fetch_url,
        usable_search_output_fn=lambda text: True,
        verify_search_evidence_fn=lambda *, query, normalized_query, evidence, date_context: f"verified:{normalized_query}:{date_context}:{evidence}",
        log_fn=logs.append,
        max_successful_fetches=2,
    )

    assert fetched == ["q1-a", "q1-b"]
    assert result == "verified:规范问题:当前日期:正文 q1-a\n\n---\n\n正文 q1-b"
    assert logs == []


def test_run_curl_search_logs_fetch_errors_and_returns_empty_without_outputs():
    logs = []

    def fetch_url(url):
        raise TimeoutError("slow")

    result = search_runtime.run_curl_search(
        "问题",
        normalize_query_fn=lambda query: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        plan_search_queries_fn=lambda query: ["q1"],
        search_urls_for_query_fn=lambda query: ["url1"],
        fetch_url_fn=fetch_url,
        usable_search_output_fn=lambda text: True,
        verify_search_evidence_fn=lambda **kwargs: "should not run",
        log_fn=logs.append,
        max_successful_fetches=2,
    )

    assert result == ""
    assert logs[0]["type"] == "web_search_http_error"
    assert logs[0]["query"] == "规范问题"


def test_run_web_search_disabled_and_curl_backend_paths():
    assert search_runtime.run_web_search(
        "问题",
        web_search_enabled=False,
        web_search_backend="auto",
        normalize_query_fn=lambda q: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        run_curl_search_fn=lambda q: "unused",
        run_llm_search_fn=lambda **kwargs: "unused",
        pick_template_fn=lambda name, q: f"{name}:{q}",
        log_fn=lambda event: None,
        max_chars=20,
    ) == "（联网搜索已关闭）"

    logs = []
    assert search_runtime.run_web_search(
        "问题",
        web_search_enabled=True,
        web_search_backend="curl",
        normalize_query_fn=lambda q: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        run_curl_search_fn=lambda q: "curl结果很长",
        run_llm_search_fn=lambda **kwargs: "unused",
        pick_template_fn=lambda name, q: f"{name}:{q}",
        log_fn=logs.append,
        max_chars=6,
    ) == "curl结果"
    assert logs[0]["type"] == "web_search_done"

    assert search_runtime.run_web_search(
        "问题",
        web_search_enabled=True,
        web_search_backend="http",
        normalize_query_fn=lambda q: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        run_curl_search_fn=lambda q: "",
        run_llm_search_fn=lambda **kwargs: "unused",
        pick_template_fn=lambda name, q: f"{name}:{q}",
        log_fn=lambda event: None,
        max_chars=20,
    ) == "web_search_no_match:规范问题"


def test_run_web_search_auto_falls_back_to_llm_search():
    calls = []
    result = search_runtime.run_web_search(
        "问题",
        web_search_enabled=True,
        web_search_backend="auto",
        normalize_query_fn=lambda q: "规范问题",
        current_date_context_fn=lambda: "当前日期",
        run_curl_search_fn=lambda q: "",
        run_llm_search_fn=lambda *, query, normalized_query, date_context: calls.append((query, normalized_query, date_context)) or "llm结果",
        pick_template_fn=lambda name, q: f"{name}:{q}",
        log_fn=lambda event: None,
        max_chars=20,
    )

    assert result == "llm结果"
    assert calls == [("问题", "规范问题", "当前日期")]
