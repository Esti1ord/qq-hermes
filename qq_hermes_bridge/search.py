"""Search planning and search-output utility helpers.

This module contains stateless query normalization, URL planning, and fallback
text logic. Runtime actions such as curl execution and LLM verification remain
in bridge.py for now and call these helpers through compatibility wrappers.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from . import matching


def needs_web_search(text: str, *, web_search_enabled: bool = True) -> bool:
    if not web_search_enabled:
        return False
    text = text.strip()
    if not text:
        return False

    lower = text.lower()
    no_search_phrases = [
        "今天好累", "今晚吃什么", "现在有点", "刚才笑死", "目前这个代码", "这个代码怎么", "怎么写",
        "没懂", "解释一下", "讲一下", "这个梗", "什么意思", "为啥", "为什么", "怎么办",
    ]
    if matching.contains_any_phrase(text, no_search_phrases):
        return False
    if re.search(r"(python|java|c\+\+|代码|函数|装饰器|报错|bug|论文|作业|项目).*(怎么|解释|什么意思|为啥|为什么|写|改)", lower, re.I):
        return False

    strong_current_markers = [
        "最新", "实时", "新闻", "热搜", "官宣", "辟谣", "真的假的", "是真的吗",
        "赛果", "比分", "积分榜", "赛程", "转会", "阵容", "伤病", "停赛",
        "事件", "发生", "发生了什么", "大事", "要闻", "新闻汇总", "足坛", "足球事件",
        "汇率", "股价", "天气", "价格", "发布会", "名单", "行程", "巡游", "开售", "发售", "售票",
    ]
    if matching.contains_any_phrase(text, strong_current_markers):
        return True

    time_markers = ["今天", "今晚", "昨晚", "昨夜", "夜里", "凌晨", "现在", "刚刚", "刚才", "目前", "明天", "昨天"]
    fact_markers = [
        "结果", "多少", "几比几", "谁赢", "排名", "榜", "比赛", "国足", "英超", "中超", "欧冠", "西甲", "NBA",
        "足球", "足坛", "事件", "发生", "大事", "要闻", "新闻汇总",
        "发布", "宣布", "确认", "真假", "消息", "新闻", "天气", "价格", "股价", "汇率", "名单", "赛程",
    ]
    if matching.contains_any_phrase(text, time_markers) and matching.contains_any_phrase(text, fact_markers):
        return True

    if re.search(r"(20\d{2}|\d{1,2}月\d{1,2}日|周[一二三四五六日天]|星期[一二三四五六日天])", text) and matching.contains_any_phrase(text, fact_markers):
        return True
    return False


def current_date_context(now: datetime | None = None) -> str:
    dt = now or datetime.now().astimezone()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    tz = dt.strftime("%Z") or "本地时区"
    offset = dt.strftime("%z")
    return f"当前日期：{dt:%Y-%m-%d}（{weekday}，{tz}{offset}）。相对时间必须按这个日期解释：今天={dt:%Y-%m-%d}，昨天={(dt - timedelta(days=1)):%Y-%m-%d}，昨晚/昨夜通常指 {(dt - timedelta(days=1)):%Y-%m-%d} 晚间到 {dt:%Y-%m-%d} 凌晨。"


def normalize_search_query(query: str, now: datetime | None = None) -> str:
    text = re.sub(r"@\S+", " ", query or "")
    text = re.sub(r"\[CQ:at,qq=\d+\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    today = now or datetime.now().astimezone()
    dates: list[str] = []
    if matching.contains_any_phrase(text, ["昨晚", "昨夜", "昨天夜里", "昨天凌晨"]):
        dates.extend([
            (today - timedelta(days=1)).strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d"),
        ])
    if "昨天" in text and not dates:
        dates.append((today - timedelta(days=1)).strftime("%Y-%m-%d"))
    if matching.contains_any_phrase(text, ["今天", "今晚", "现在"]):
        dates.append(today.strftime("%Y-%m-%d"))
    if not dates and matching.contains_any_phrase(text, ["夜里", "凌晨", "刚刚", "刚才"]):
        dates.append(today.strftime("%Y-%m-%d"))
    normalized = " ".join([text, *dates]).strip()
    return re.sub(r"\s+", " ", normalized)[:500]


def compact_search_terms(text: str, limit: int = 160) -> str:
    clean = re.sub(r"(?m)^(原问题|被回复/引用消息|群聊近期上下文)：", " ", text or "")
    clean = re.sub(r"[，。；、：:（）()\[\]【】]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


def salient_latin_terms(text: str) -> list[str]:
    terms = re.findall(r"\b[A-Za-z][A-Za-z0-9+_.-]{1,}\b", text or "")
    out: list[str] = []
    for term in terms:
        low = term.lower()
        if low in {"http", "https", "www", "com", "cn", "org", "net", "html", "source", "url"}:
            continue
        if term not in out:
            out.append(term)
    return out[:8]


def plan_search_queries(query: str, now: datetime | None = None) -> list[str]:
    normalized = normalize_search_query(query, now=now)
    today = (now or datetime.now().astimezone()).strftime("%Y-%m-%d")
    compact = compact_search_terms(normalized)
    latin = " ".join(salient_latin_terms(normalized))
    variants = [normalized]
    if compact and compact != normalized:
        variants.append(compact)
    if compact:
        variants.append(f"{compact} {today}")
        variants.append(f"{compact} 官方 最新")
    if latin:
        variants.append(f"{latin} schedule matches today {today}")
        variants.append(f"{latin} official news {today}")
    return [q for q in dict.fromkeys(re.sub(r"\s+", " ", v).strip() for v in variants) if q][:6]


def candidate_urls_from_query(q: str) -> list[str]:
    candidates: list[str] = []
    for raw in re.findall(r"https?://[^\s，。；、)）>]+|(?<!@)\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s，。；、)）>]*)?", q or ""):
        url = raw.strip().rstrip(".,;，。；")
        if not url:
            continue
        if not re.match(r"https?://", url, re.I):
            url = "http://" + url
        if url not in candidates:
            candidates.append(url)
    return candidates


def jina_url_for_source(url: str) -> str:
    clean = (url or "").strip()
    if clean.startswith("https://"):
        return "https://r.jina.ai/" + clean
    if clean.startswith("http://"):
        return "https://r.jina.ai/" + clean
    return "https://r.jina.ai/http://" + clean


def search_urls_for_query(q: str) -> list[str]:
    encoded = quote_plus(q)
    urls = [jina_url_for_source(url) for url in candidate_urls_from_query(q)]
    urls.extend([
        f"https://r.jina.ai/http://www.baidu.com/s?wd={encoded}",
        f"https://r.jina.ai/http://www.bing.com/search?q={encoded}",
        f"https://r.jina.ai/http://cn.bing.com/search?q={encoded}",
        f"https://r.jina.ai/http://www.sogou.com/web?query={encoded}",
        f"https://r.jina.ai/http://www.so.com/s?q={encoded}",
        f"https://r.jina.ai/http://www.google.com/search?q={encoded}",
        f"https://r.jina.ai/http://duckduckgo.com/html/?q={encoded}",
    ])
    return list(dict.fromkeys(urls))


def usable_search_output(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    bad_markers = [
        '"code":451',
        '"code":429',
        "SecurityCompromiseError",
        "RateLimitTriggeredError",
        "Per IP rate limit exceeded",
        "Too Many Requests",
        "Target URL returned error 429",
        "retryAfter",
        "CAPTCHA",
        "Access Denied",
        "Anonymous access to domain",
        "blocked until",
        "Suspicious action",
    ]
    if matching.contains_any_phrase(clean, bad_markers):
        return False
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", clean))
    alnum_count = len(re.findall(r"[A-Za-z0-9]", clean))
    if len(clean) < 120 and cjk_count < 4 and alnum_count < 30:
        return False
    return True


def search_command_fallback_reply(query: str, *, no_match_reply: str) -> str:
    clean = re.sub(r"\s+", " ", query or "").strip()
    if not clean:
        return "没搜到特别可靠的结果"
    if len(clean) <= 20 and not re.search(r"(最新|新闻|官宣|辟谣|真的假的|是真的吗|赛果|比分|积分榜|赛程|转会|天气|价格|汇率|股价|开售|发售|售票|发布)", clean):
        return f"没搜到特别需要查证的信息，{clean}"
    return no_match_reply
