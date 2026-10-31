"""A3 개발용 대화 실행기(정식 회귀는 A4의 tests/run.py).

예)
  .venv/bin/python -m agent.devchat L-11 "주문번호는 100100003이고 안 먹었어요" "환불할게요"
  .venv/bin/python -m agent.devchat L-20 -i        # 첫 메시지 후 표준입력으로 대화
첫 메시지는 tests/tc/public/<ID>.md 「초기 대화」 원문을 그대로 보낸다.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time

from agent import handle_message
from agent.brain import session_trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def first_message(tc: str) -> str:
    md = open(os.path.join(ROOT, "tests/tc/public", f"{tc}.md"), encoding="utf-8").read()
    return re.search(r"#### 초기 대화\s*\n(.*?)\n#### ", md, re.S).group(1).strip()


async def turn(key: str, text: str) -> None:
    t0 = time.monotonic()
    bubbles = await handle_message(key, text, time.strftime("%Y-%m-%dT%H:%M:%S"))
    ms = (time.monotonic() - t0) * 1000
    tr = session_trace(key)
    print(f"\n고객> {text[-160:]}")
    for b in bubbles:
        print(f"봇[{len(b)}자]> {b}")
    print(f"   ({ms:.0f}ms, 누적 API {len(tr.get('calls', []))}, 차단 {len(tr.get('blocked', []))})")


async def main(argv: list[str]) -> None:
    tc = argv[0]
    interactive = "-i" in argv
    turns = [a for a in argv[1:] if a != "-i"]
    key = f"dev-{tc}-{int(time.time())}"
    await turn(key, first_message(tc))
    for t in turns:
        await turn(key, t)
    while interactive:
        try:
            t = input("\n> ").strip()
        except EOFError:
            break
        if not t:
            break
        await turn(key, t)
    tr = session_trace(key)
    print("\n== API 호출:")
    for c in tr.get("calls", []):
        print(f"  {c.get('api_id')} {c.get('params')} {c.get('body') or ''} → {c.get('status')}{' (cache)' if c.get('cached') else ''}")
    for b in tr.get("blocked", []):
        print(f"  [차단] {b}")
    for r in tr.get("receipts", []):
        print(f"  [접수] {r}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
