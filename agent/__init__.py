"""교동마을 산지직송 CS 에이전트 두뇌(A3). 계약 C1: handle_message."""
from __future__ import annotations


async def handle_message(session_key: str, text: str, received_at: str) -> list[str]:
    """C1. 말풍선 1~3개(각 450자 이하, 기본 1개)를 반환한다."""
    from agent.brain import handle_message as _impl

    return await _impl(session_key, text, received_at)


async def warmup() -> bool:
    """콜드 스타트 제거(액션 API 호출 없음). 데몬 기동 직후 1회 + 4~5분마다 호출 권장."""
    from agent.brain import warmup as _w

    return await _w()


__all__ = ["handle_message", "warmup"]
