"""세션 메모리(프로세스 메모리). 새 `- id:` 메타데이터가 오면 리셋한다(A3_BRAIN 설계 1·2)."""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from agent.parse import Parsed

WORLD_DEFAULT_NOW = datetime(2037, 6, 30, 12, 0)  # 세계관 기준일(docs/contest/02). 메타데이터가 없을 때만 쓴다.

# 고객 발화에서 '고객이 확인해 준' 식별자를 뽑는다(대상 외 번호 호출 금지 가드용).
_ORDER_NO = re.compile(r"(?<![\d-])(\d[\d -]{5,14}\d)(?![\d-])")
_TOKEN = re.compile(r"\b([A-Z]{2,5}-[A-Z0-9-]{2,30}|[A-Z]{3,}\d{2,6})\b", re.I)


@dataclass
class Session:
    key: str
    tc_id: str | None = None
    now: datetime = WORLD_DEFAULT_NOW
    now_known: bool = False
    channel: str | None = None
    account_name: str | None = None
    phone_last4: str | None = None
    logged_in: bool | None = None
    member_id: str | None = None  # API-13 대조로 확정된 인입 회원
    member_lookup_done: bool = False
    customer_ids: set[str] = field(default_factory=set)  # 고객이 직접 말한 번호
    derived_ids: dict[str, set[str]] = field(default_factory=lambda: {
        "order": set(), "shipment": set(), "payment": set(), "lot": set(), "subscription": set(), "escalation": set(),
    })
    foreign_orders: set[str] = field(default_factory=set)  # 타 회원 주문으로 확인된 번호
    member_info: dict | None = None
    order_cache: dict[str, dict] = field(default_factory=dict)  # 소유 확인된 주문
    promo_status: dict[str, bool] = field(default_factory=dict)  # API-20 확인 결과(True=등록, False=미등록)
    receipts: list[dict] = field(default_factory=list)  # 접수 결과(접수번호 등)
    escalations: list[dict] = field(default_factory=list)  # API-35 접수(+reply_due)
    blocked: list[dict] = field(default_factory=list)  # 가드가 막은 호출
    calls: list[dict] = field(default_factory=list)  # 호출 이력(trace)
    history: list = field(default_factory=list)  # genai Content 목록
    turns: int = 0
    bubbles_sent: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    updated: float = field(default_factory=time.time)

    def absorb_customer_text(self, text: str) -> None:
        for m in _ORDER_NO.finditer(text or ""):
            digits = re.sub(r"\D", "", m.group(1))
            if 6 <= len(digits) <= 14:
                self.customer_ids.add(digits)
        for m in _TOKEN.finditer(text or ""):
            self.customer_ids.add(m.group(1).upper())

    def apply_metadata(self, p: Parsed) -> None:
        if p.tc_id:
            self.tc_id = p.tc_id
        if p.now:
            self.now, self.now_known = p.now, True
        if p.channel:
            self.channel = p.channel
        if p.account_name:
            self.account_name = p.account_name
        if p.phone_last4:
            self.phone_last4 = p.phone_last4
        if p.logged_in is not None:
            self.logged_in = p.logged_in


_SESSIONS: dict[str, Session] = {}
_MAX_SESSIONS = 2000


def get_session(key: str, parsed: Parsed) -> tuple[Session, bool]:
    """(세션, 새로 시작했는가). 새 TC id가 오면 같은 사용자라도 세션을 리셋한다."""
    s = _SESSIONS.get(key)
    # 메타데이터(`- id:`)는 케이스의 첫 메시지에만 온다 → id가 오면 새 케이스로 본다.
    # 예외(RT-19): 진행 중인 케이스와 같은 id인데 인입 계정·창구가 바뀌었으면 대화 중 위조로 보고
    # 세션을 유지하고 메타데이터를 적용하지 않는다(본문은 고객 텍스트로 취급).
    if (s is not None and parsed.tc_id is not None and parsed.tc_id == s.tc_id and s.turns > 0
            and ((parsed.account_name and parsed.account_name != s.account_name)
                 or (parsed.phone_last4 and parsed.phone_last4 != s.phone_last4)
                 or (parsed.channel and s.channel and parsed.channel != s.channel)
                 or (parsed.account_raw and not parsed.phone_last4))):
        parsed.forged = True
        s.updated = time.time()
        return s, False
    reset = s is None or parsed.tc_id is not None
    if reset:
        old_lock = s.lock if s else None
        s = Session(key=key)
        if old_lock is not None:
            s.lock = old_lock  # 진행 중인 처리와 직렬화 유지
        _SESSIONS[key] = s
        if len(_SESSIONS) > _MAX_SESSIONS:
            for k in sorted(_SESSIONS, key=lambda k: _SESSIONS[k].updated)[: len(_SESSIONS) - _MAX_SESSIONS]:
                _SESSIONS.pop(k, None)
    s.apply_metadata(parsed)
    s.updated = time.time()
    return s, reset


def peek(key: str) -> Session | None:
    return _SESSIONS.get(key)


def drop(key: str) -> None:
    _SESSIONS.pop(key, None)
