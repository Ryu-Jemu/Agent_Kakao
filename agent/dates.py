"""날짜·영업일·기간 계산(LLM 암산 금지 — A3_BRAIN 설계 5).

기준일은 케이스의 '상담 인입 일시'다(docs/contest/05 FAQ: 시나리오의 문의 접수 날짜 기준).
공휴일: 2037년은 세계관 정본 「영업일·공휴일 달력」의 공휴일 표를 그대로 쓴다(HOLIDAYS_2037).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKDAY_KO = "월화수목금토일"
# 정본: 「영업일·공휴일 달력」(kb/raw/sources/_text/영업일공휴일달력.txt '공휴일 표', 2037-03 개장 이후, KB D-120~123).
# 주의: 이 세계관에서 2037-05-05(화)는 영업일이고 05-06(수)이 공휴일이다. 대체공휴일 포함.
HOLIDAYS_2037 = {date(2037, 3, 1), date(2037, 5, 6), date(2037, 5, 25), date(2037, 6, 6), date(2037, 8, 15),
                 date(2037, 8, 17), date(2037, 9, 23), date(2037, 9, 24), date(2037, 9, 25), date(2037, 10, 3),
                 date(2037, 10, 5), date(2037, 10, 9), date(2037, 12, 25)}
FIXED_HOLIDAYS = {(1, 1), (3, 1), (5, 5), (6, 6), (8, 15), (10, 3), (10, 9), (12, 25)}  # 2037 외 연도용(추정)
SHIP_WEEKDAYS = (0, 2, 4)  # 산지 정기 출고 월·수·금, 휴무일이면 그 회차 건너뜀(달력 §1, D-120)


def to_date(x) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if d.year == 2037:
        return d not in HOLIDAYS_2037
    return (d.month, d.day) not in FIXED_HOLIDAYS


def next_ship_day(d) -> date:
    """d 다음 날부터 가장 빠른 정기 출고일(월·수·금 중 영업일). 개별 주문의 출고 확정이 아니다."""
    cur = to_date(d) + timedelta(days=1)
    while not (cur.weekday() in SHIP_WEEKDAYS and is_business_day(cur)):
        cur += timedelta(days=1)
    return cur


def add_business_days(d, n: int) -> date:
    """영업일 n일 후의 마감일(그날 24:00까지).

    규칙(inbox/interviews/이민준.md Q5 원문): 기준일은 세지 않고 다음 영업일부터 1일차로 센다.
    토·일·공휴일은 건너뛴다. 기준일 자체가 휴무일이면 다음 영업일을 기준일로 바꾼 뒤 센다.
    예: 월(휴일 없음)+3 → 목, 금+3 → 다음 주 수, 토+3 → (기준 월) → 목.
    """
    cur = to_date(d)
    if n > 0:
        while not is_business_day(cur):
            cur += timedelta(days=1)
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        cur += timedelta(days=step)
        if is_business_day(cur):
            left -= 1
    return cur


def days_between(a, b) -> int:
    """b - a (달력일)."""
    return (to_date(b) - to_date(a)).days


def ko(d) -> str:
    d = to_date(d)
    return f"{d.month}월 {d.day}일({WEEKDAY_KO[d.weekday()]})"


def iso_ko(d) -> str:
    d = to_date(d)
    return f"{d.isoformat()}({WEEKDAY_KO[d.weekday()]})"


def case_calendar(now: datetime) -> dict:
    """시스템 프롬프트에 넣을 케이스 기준 달력(미리 계산해 LLM 왕복을 줄인다)."""
    today = now.date()
    return {
        "today": iso_ko(today),
        "now_time": now.strftime("%H:%M"),
        "yesterday": iso_ko(today - timedelta(days=1)),
        "tomorrow": iso_ko(today + timedelta(days=1)),
        "day_after_tomorrow": iso_ko(today + timedelta(days=2)),
        "reply_due_3bd": iso_ko(add_business_days(today, 3)),
        "next_business_day": iso_ko(add_business_days(today, 1)),
        "minus_7d": iso_ko(today - timedelta(days=7)),
        "next_regular_ship": iso_ko(next_ship_day(today)),
    }


def elapsed_note(event_at, now: datetime, label: str) -> str | None:
    d = to_date(event_at)
    if not d:
        return None
    n = days_between(d, now.date())
    return f"{label} {ko(d)} → 상담일({ko(now)}) 기준 {label.split()[-1]} 후 {n}일째"
