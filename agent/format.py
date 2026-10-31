"""응답 포맷터(A3-4): 마크다운·이모지 제거, 말풍선 1개(필요 시 2개), 말풍선당 450자 상한(대회 500자 하드캡).

길이 초과 처리 순서(A6 지적 반영): ① LLM 1회 축약(brain에서 수행, 핵심 보존) → ② 문장 경계로 2개 말풍선 분할
→ ③ 그래도 넘으면 문장 단위 절단. 어떤 경우에도 말풍선은 500자를 넘지 않는다.
"""
from __future__ import annotations

import re

TARGET = 350
SOFT_MAX = 450
HARD_MAX = 500

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D\U000020E3\U0001F1E6-\U0001F1FF]+"
)


def clean(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    t = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t, flags=re.S)
    t = re.sub(r"__(.+?)__", r"\1", t, flags=re.S)
    t = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "· ", t, flags=re.M)
    t = re.sub(r"^\s*\|?\s*:?-{3,}.*$", "", t, flags=re.M)  # 표 구분선
    t = t.replace("|", " ")
    t = _EMOJI.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _sentences(t: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|(?<=[요다죠까])\.?\s*\n+|\n{2,}", t)
    return [p.strip() for p in parts if p and p.strip()]


def _pack(sents: list[str], limit: int) -> tuple[str, list[str]]:
    out = ""
    for i, s in enumerate(sents):
        cand = (out + (" " if out else "") + s) if not out.endswith("\n") else out + s
        if len(cand) > limit:
            return out, sents[i:]
        out = cand
    return out, []


def _cut(t: str, limit: int) -> str:
    if len(t) <= limit:
        return t
    head, _ = _pack(_sentences(t), limit)
    if head:
        return head
    return t[: limit - 1].rstrip() + "…"


def to_bubbles(text: str, max_bubbles: int = 2) -> list[str]:
    t = clean(text)
    if not t:
        return []
    if len(t) <= SOFT_MAX:
        return [t]
    sents = _sentences(t)
    first, rest = _pack(sents, SOFT_MAX)
    if not first:
        return [_cut(t, SOFT_MAX)]
    if max_bubbles < 2 or not rest:
        return [first]
    second = _cut(" ".join(rest), SOFT_MAX)
    return [first, second]


def needs_shortening(text: str) -> bool:
    return len(clean(text)) > SOFT_MAX
