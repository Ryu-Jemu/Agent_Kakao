"""brain 루프 배선 검증(가짜 LLM, 실제 C2 GET만): function_call → 가드·실행 → function_response → 최종 텍스트 → 포맷.

실행: .venv/bin/python -m agent.selftest_brain   (exit 0 = 통과). 네트워크 호출: L-23 API-07·API-13 (POST 없음).
"""
from __future__ import annotations

import asyncio
import sys

from google.genai import types

from agent import brain, llm

SCRIPT: list = []
SEEN: list = []


def _resp(parts):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


async def fake_generate(contents, *, system, tools, model=None, timeout=25.0, allow_calls=True, max_tokens=2048):
    SEEN.append({"n_contents": len(contents), "tools": bool(tools), "allow": allow_calls, "system_tail": system[-400:]})
    return SCRIPT.pop(0)


async def main() -> int:
    llm.generate = fake_generate  # type: ignore[assignment]
    brain.llm.generate = fake_generate  # type: ignore[attr-defined]
    fails = []
    SCRIPT[:] = [
        _resp([types.Part(function_call=types.FunctionCall(name="get_order", args={"order_no": "100100033"})),
               types.Part(function_call=types.FunctionCall(name="get_order", args={"order_no": "100100099"}))]),
        _resp([types.Part(text="**확인 결과** 😀 고객님 계정의 주문이 아니라서 배송 상태와 주소는 안내드릴 수 없어요.")]),
    ]
    first = ("case metadata\n- id: L-23\n- 상담 인입 일시: 2037-06-30(화) 17:53\n- 인입창구: 조합몰 1:1 채팅\n"
             "- 인입 계정: 회원 로그인 · 윤재호 · 019-****-8326\n\n저 로그인했어요. 주문번호 100100033 배송 상태랑 받는 사람 주소 확인해주세요.")
    out = await brain.handle_message("selftest-brain", first, "2026-10-31T11:20:00")
    tr = brain.session_trace("selftest-brain")
    if out != ["확인 결과 고객님 계정의 주문이 아니라서 배송 상태와 주소는 안내드릴 수 없어요."]:
        fails.append(f"bubbles {out}")
    if [c["api_id"] for c in tr["calls"]] != ["API-07", "API-13"]:
        fails.append(f"calls {[c['api_id'] for c in tr['calls']]}")
    if [b["why"] for b in tr["blocked"]] != ["NOT_CONFIRMED"]:
        fails.append(f"blocked {tr['blocked']}")
    if "L-23" not in SEEN[0]["system_tail"] or "2037-06-30(화)" not in SEEN[0]["system_tail"]:
        fails.append("case block missing")
    # 2턴: 메타데이터 없음 → 같은 세션 유지, history 누적(user, model(fc), user(fr), model(text), user)
    SCRIPT[:] = [_resp([types.Part(text="죄송하지만 동네 단위로도 안내드릴 수 없어요.")])]
    out2 = await brain.handle_message("selftest-brain", "그럼 동네만이라도요", "2026-10-31T11:21:00")
    if SEEN[-1]["n_contents"] != 5 or not out2:
        fails.append(f"turn2 contents={SEEN[-1]['n_contents']} out={out2}")
    if "100100033" not in SEEN[-1]["system_tail"]:
        fails.append("foreign order not in case block")
    print("brain 배선:", "OK" if not fails else fails, out, out2)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
