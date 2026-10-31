#!/usr/bin/env python3
"""레드팀 수동 탐색용: POST(접수·이관)를 서버로 보내지 않고 기록만 하는 상태로 integ.local_chat(C3)을 실행한다.
실행: .venv/bin/python release/rt_local_chat.py --user rt1 [local_chat 인자…]
종료 시 차단·기록된 호출 목록을 stderr로 출력한다(비밀값 없음)."""
import atexit, json, os, runpy, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import redteam_run as R

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(R.ROOT, ".env"))
except Exception:
    pass
R.install_patch(live_get="--stub-get" not in sys.argv)
sys.argv = [a for a in sys.argv if a != "--stub-get"]
atexit.register(lambda: print("\n[rt] 호출 기록:\n" + "\n".join(
    json.dumps({k: c.get(k) for k in ("tc_id", "api_id", "method", "params", "blocked")}, ensure_ascii=False) for c in R.CALLS),
    file=sys.stderr))
runpy.run_module("integ.local_chat", run_name="__main__", alter_sys=True)
