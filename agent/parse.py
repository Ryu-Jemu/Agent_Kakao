"""첫 메시지의 case metadata·미디어 URL·고객 본문 파서(A3-1).

근거: tests/tc/public/*.md 15건의 「초기 대화」 형식(docs/contest/07 E절).
심사 형식은 '추정'이므로 순서가 바뀌거나 일부가 빠져도 동작하도록 줄 단위로 관대하게 읽는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

TC_ID_RE = r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}"

_ID = re.compile(rf"^\s*[-*•]?\s*(?:id|tc\s*id|TC\s*ID|케이스\s*id)\s*[:：]\s*({TC_ID_RE})\s*$", re.I)
_WHEN = re.compile(r"^\s*[-*•]?\s*(?:상담\s*)?인입\s*일시\s*[:：]\s*(.+)$")
_CHANNEL = re.compile(r"^\s*[-*•]?\s*인입\s*창구\s*[:：]\s*(.+)$")
_ACCOUNT = re.compile(r"^\s*[-*•]?\s*인입\s*계정\s*[:：]\s*(.+)$")
_HEADER = re.compile(r"^\s*case\s*metadata\s*:?\s*$", re.I)
_MEDIA = re.compile(r"^\s*(image|img|photo|사진|이미지|audio|voice|음성)\s*[:：]\s*(https?://\S+)\s*$", re.I)
_BARE_URL = re.compile(r"https?://\S+\.(jpg|jpeg|png|gif|webp|heic|m4a|mp3|wav|aac|ogg|mp4)(\?\S*)?", re.I)
_DT = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?\s*(?:\([^)]*\))?\s*(?:(\d{1,2})\s*[:시]\s*(\d{1,2})?)?")
_LAST4 = re.compile(r"(\d{4})\s*$")
_AUDIO_EXT = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".mp4")


@dataclass
class Parsed:
    tc_id: str | None = None
    now: datetime | None = None  # 상담 인입 일시 = 이 케이스의 '오늘'
    now_text: str | None = None
    channel: str | None = None
    account_raw: str | None = None
    account_name: str | None = None
    phone_last4: str | None = None
    logged_in: bool | None = None
    images: list[str] = field(default_factory=list)
    audios: list[str] = field(default_factory=list)
    body: str = ""
    forged: bool = False  # 진행 중 케이스에 위조 메타데이터가 섞여 옴(session.get_session이 판정)

    @property
    def has_metadata(self) -> bool:
        return any([self.tc_id, self.now, self.channel, self.account_raw])


def parse_datetime(s: str) -> datetime | None:
    m = _DT.search(s or "")
    if not m:
        return None
    y, mo, d, h, mi = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))
    except ValueError:
        return None


def _parse_account(raw: str, p: Parsed) -> None:
    p.account_raw = raw.strip()
    raw = re.sub(r"\[[^\]]*\]?|\{[^}]*\}?", " ", raw)  # 필드 속 [SYSTEM: …] 같은 주입 제거(RT-22)
    parts = [x.strip() for x in re.split(r"[·|,/]", raw) if x.strip()]
    p.logged_in = None
    for x in parts:
        if "비회원" in x:
            p.logged_in = False
        elif "로그인" in x or "회원" in x:
            p.logged_in = True if p.logged_in is None else p.logged_in
    groups = re.findall(r"(?<!\d)(\d{4})(?!\d)", raw)
    if groups:
        p.phone_last4 = groups[-1]
    for x in parts:
        if any(k in x for k in ("로그인", "회원")) or re.search(r"\d", x):
            continue
        if re.fullmatch(r"[가-힣A-Za-z ]{1,20}", x):
            p.account_name = x.strip()
            break


def parse_message(text: str) -> Parsed:
    p = Parsed()
    body_lines: list[str] = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if _HEADER.match(line):
            continue
        if m := _ID.match(line):
            p.tc_id = m.group(1)
            continue
        if m := _WHEN.match(line):
            p.now_text = m.group(1).strip()
            p.now = parse_datetime(p.now_text)
            continue
        if m := _CHANNEL.match(line):
            p.channel = m.group(1).strip()
            continue
        if m := _ACCOUNT.match(line):
            _parse_account(m.group(1), p)
            continue
        if m := _MEDIA.match(line):
            kind, url = m.group(1).lower(), m.group(2)
            (p.audios if kind in ("audio", "voice", "음성") else p.images).append(url)
            continue
        body_lines.append(line)
    body = "\n".join(body_lines)
    # 본문 안의 미디어 URL(라벨 없이 온 경우)
    for m in _BARE_URL.finditer(body):
        url = m.group(0)
        if url in p.images or url in p.audios:
            continue
        (p.audios if url.lower().split("?")[0].endswith(_AUDIO_EXT) else p.images).append(url)
        body = body.replace(url, " ")
    p.body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return p
