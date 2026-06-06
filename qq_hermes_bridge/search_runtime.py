"""Runtime helpers for web search execution and verification prompts."""
from __future__ import annotations

from typing import Any, Callable

SPORTS_QUERY_MARKERS = ["欧冠", "英超", "中超", "西甲", "NBA", "国足", "比赛", "赛果", "比分", "赛程", "积分榜"]


def is_sports_query(query: str) -> bool:
    return any(marker in query for marker in SPORTS_QUERY_MARKERS)


def curl_verify_match_rule(query: str) -> str:
    if is_sports_query(query):
        return "赛事/日期必须匹配；如果问欧冠，只回答欧冠/UEFA Champions League；不要把 NBA、其他足球比赛或旧比赛当成欧冠。"
    return "不要套用体育/赛事校验；普通生活、新闻、天气、祝福类问题只需按搜索摘录给出相关事实或说明没有必要查证。"


def join_curl_evidence(outputs: list[str], *, per_item_limit: int = 4000, total_limit: int = 6000) -> str:
    return "\n\n---\n\n".join((item or "").strip()[:per_item_limit] for item in outputs)[:total_limit]


def build_curl_verify_prompt(*, query: str, normalized_query: str, evidence: str, date_context: str) -> str:
    match_rule = curl_verify_match_rule(query)
    return f"""只根据搜索摘录回答搜索问题，输出一句简短中文摘要；证据不足就说没查到可靠结果。
{date_context}
规则：按当前日期解释相对时间，不要默认成去年；{match_rule}

原问题：{query[:300]}
规范化查询：{normalized_query}
搜索摘录：
{evidence}"""


def build_llm_search_prompt(*, query: str, normalized_query: str, date_context: str) -> str:
    return f"""联网核对 QQ 群友提到的最新/实时信息，输出简短事实摘要，不要写最终回复。
{date_context}
规则：优先官方/赛事方/主流媒体；确认日期和赛事匹配；区分官宣、传闻和冲突说法；没可靠结果就说没查到，不要猜。

原问题：{query[:300]}
规范化查询：{normalized_query}"""


def finalize_llm_search_result(raw: str, *, normalized_query: str, max_chars: int, empty_reply_fn: Callable[[str], str]) -> str:
    result = (raw or "").strip()
    if not result:
        return empty_reply_fn(normalized_query)
    return result[:max_chars]


def run_curl_search(
    query: str,
    *,
    normalize_query_fn: Callable[[str], str],
    current_date_context_fn: Callable[[], str],
    plan_search_queries_fn: Callable[[str], list[str]],
    search_urls_for_query_fn: Callable[[str], list[str]],
    fetch_url_fn: Callable[[str], Any],
    usable_search_output_fn: Callable[[str], bool],
    verify_search_evidence_fn: Callable[..., str],
    log_fn: Callable[[dict[str, Any]], None],
    max_successful_fetches: int,
) -> str:
    normalized = normalize_query_fn(query)
    date_context = current_date_context_fn()
    search_queries = plan_search_queries_fn(query)
    urls: list[str] = []
    for search_query in search_queries:
        urls.extend(search_urls_for_query_fn(search_query))
    outputs: list[str] = []
    for url in urls:
        try:
            response = fetch_url_fn(url)
        except Exception as exc:
            log_fn({"type": "web_search_http_error", "query": normalized[:200], "error": type(exc).__name__, "message": str(exc)})
            continue
        if getattr(response, "returncode", None) == 0 and usable_search_output_fn(getattr(response, "stdout", "") or ""):
            outputs.append((getattr(response, "stdout", "") or "").strip()[:4000])
            if len(outputs) >= max_successful_fetches:
                break
    if not outputs:
        return ""
    evidence = join_curl_evidence(outputs)
    return verify_search_evidence_fn(
        query=query,
        normalized_query=normalized,
        evidence=evidence,
        date_context=date_context,
    )


def run_web_search(
    query: str,
    *,
    web_search_enabled: bool,
    web_search_backend: str,
    normalize_query_fn: Callable[[str], str],
    current_date_context_fn: Callable[[], str],
    run_curl_search_fn: Callable[[str], str],
    run_llm_search_fn: Callable[..., str],
    pick_template_fn: Callable[[str, str], str],
    log_fn: Callable[[dict[str, Any]], None],
    max_chars: int,
) -> str:
    if not web_search_enabled:
        return "（联网搜索已关闭）"
    normalized_query = normalize_query_fn(query)
    date_context = current_date_context_fn()
    if web_search_backend in {"curl", "http", "auto"}:
        result = run_curl_search_fn(query)
        if result:
            log_fn({"type": "web_search_done", "backend": "curl", "query": normalized_query[:200], "result": result[:300]})
            return result[:max_chars]
        if web_search_backend in {"curl", "http"}:
            return pick_template_fn("web_search_no_match", normalized_query)
    return run_llm_search_fn(query=query, normalized_query=normalized_query, date_context=date_context)
