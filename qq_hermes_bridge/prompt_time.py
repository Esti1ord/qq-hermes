"""Date context helpers for prompt construction."""
from __future__ import annotations

from datetime import datetime, timedelta


def current_date_context(now: datetime | None = None) -> str:
    dt = now or datetime.now().astimezone()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    tz = dt.strftime("%Z") or "本地时区"
    offset = dt.strftime("%z")
    return f"当前日期：{dt:%Y-%m-%d}（{weekday}，{tz}{offset}）。相对时间必须按这个日期解释：今天={dt:%Y-%m-%d}，昨天={(dt - timedelta(days=1)):%Y-%m-%d}，昨晚/昨夜通常指 {(dt - timedelta(days=1)):%Y-%m-%d} 晚间到 {dt:%Y-%m-%d} 凌晨。"
