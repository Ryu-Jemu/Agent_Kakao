"""C3 local_chat — 카카오 없이 agent.handle_message(C1)를 호출하는 REPL / 다중 턴 재생기.

    uv run python -m integ.local_chat --user u1                 # 대화형
    uv run python -m integ.local_chat --tc L-11                 # 공개 TC '초기 대화' 원문을 첫 턴으로 보낸 뒤 대화형
    uv run python -m integ.local_chat --script turns.txt        # 다중 턴 재생(턴 구분: '---' 한 줄), .json이면 문자열 배열
    uv run python -m integ.local_chat --tc L-11 --script t.txt  # TC 첫 턴 + 스크립트 턴
    옵션: --echo (agent 없이 echo), --json (턴별 결과를 JSON 한 줄로 출력), --session <키>

대화형 입력: 여러 줄은 줄 끝에 '\\'를 붙이거나 '\"\"\"'로 감싼다. /quit 종료, /new 새 세션.
게이트웨이와 동일하게 sanitize_outputs(1~3개, 500자)와 50초 안전 타이머를 적용해 실제 카톡 출력과 같게 보여 준다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integ.gateway import SAFETY_SEC, TIMEOUT_TEXT, ERROR_TEXT, kakao_len, load_handler, sanitize_outputs  # noqa: E402


def tc_first_turn(tc_id: str) -> str:
    """tests/tc/public/<ID>.md 의 '#### 초기 대화' ~ 다음 '#### ' 사이 원문."""
    p = ROOT / "tests" / "tc" / "public" / f"{tc_id}.md"
    s = p.read_text(encoding="utf-8")
    m = re.search(r"^####\s*초기 대화\s*\n(.*?)(?=^####\s)", s, re.S | re.M)
    if not m:
        raise SystemExit(f"{p}: '#### 초기 대화' 블록 없음")
    return m.group(1).strip("\n")


def load_script(path: str) -> list[str]:
    s = Path(path).read_text(encoding="utf-8")
    if path.endswith(".json"):
        turns = json.loads(s)
        assert isinstance(turns, list)
        return [str(t) for t in turns]
    return [t.strip("\n") for t in re.split(r"^---\s*$", s, flags=re.M) if t.strip()]


async def one_turn(handler, session_key: str, text: str) -> dict:
    t0 = time.monotonic()
    received_at = datetime.now(timezone.utc).isoformat()
    task = asyncio.create_task(handler(session_key, text, received_at))
    done, _ = await asyncio.wait({task}, timeout=SAFETY_SEC)
    status, err = "ok", None
    if task in done:
        try:
            outs = task.result()
        except BaseException as e:
            status, outs, err = "error", [ERROR_TEXT], f"{type(e).__name__}: {e}"
    else:
        task.cancel()
        status, outs = "timeout", [TIMEOUT_TEXT]
    texts, issues = sanitize_outputs(outs)
    return {"status": status, "err": err, "ms": round((time.monotonic() - t0) * 1000), "texts": texts,
            "chars": [kakao_len(t) for t in texts], "issues": issues or None, "raw_n": len(outs or [])}


def show(res: dict, as_json: bool, turn_text: str) -> None:
    if as_json:
        print(json.dumps({"in": turn_text, **res}, ensure_ascii=False), flush=True)
        return
    for i, t in enumerate(res["texts"], 1):
        print(f"\n🤖[{i}/{len(res['texts'])} · {res['chars'][i - 1]}자]\n{t}")
    meta = f"⏱ {res['ms']}ms · {res['status']}"
    if res["err"]:
        meta += f" · {res['err']}"
    if res["issues"]:
        meta += f" · issues={res['issues']}"
    print(f"\n{meta}\n", flush=True)


def read_user() -> str | None:
    try:
        line = input("🙂> ")
    except EOFError:
        return None
    if line.strip() == '"""':
        buf = []
        while True:
            try:
                ln = input("... ")
            except EOFError:
                break
            if ln.strip() == '"""':
                break
            buf.append(ln)
        return "\n".join(buf)
    buf = [line]
    while buf[-1].endswith("\\"):
        buf[-1] = buf[-1][:-1]
        try:
            buf.append(input("... "))
        except EOFError:
            break
    return "\n".join(buf)


async def amain(a) -> int:
    handler = load_handler("echo" if a.echo else "agent")
    session = a.session or f"local:{a.user}:{uuid.uuid4().hex[:6]}"
    turns: list[str] = []
    if a.tc:
        turns.append(tc_first_turn(a.tc))
    if a.script:
        turns += load_script(a.script)
    for t in turns:
        if not a.json:
            print(f"🙂> {t}")
        show(await one_turn(handler, session, t), a.json, t)
    if a.script and not a.interactive:
        return 0
    if not sys.stdin.isatty() and not turns:
        # 파이프 입력: 전체를 한 턴으로
        t = sys.stdin.read().strip()
        if t:
            show(await one_turn(handler, session, t), a.json, t)
        return 0
    while True:
        t = await asyncio.to_thread(read_user)
        if t is None or t.strip() == "/quit":
            return 0
        if t.strip() == "/new":
            session = f"local:{a.user}:{uuid.uuid4().hex[:6]}"
            print(f"(새 세션 {session})")
            continue
        if not t.strip():
            continue
        show(await one_turn(handler, session, t), a.json, t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="u1")
    ap.add_argument("--session")
    ap.add_argument("--tc", help="공개 TC ID — 초기 대화 원문을 첫 턴으로")
    ap.add_argument("--script", help="턴 파일('---' 구분 또는 .json 배열)")
    ap.add_argument("--interactive", action="store_true", help="--script 후에도 대화형 계속")
    ap.add_argument("--echo", action="store_true")
    ap.add_argument("--json", action="store_true")
    sys.exit(asyncio.run(amain(ap.parse_args())))


if __name__ == "__main__":
    main()
