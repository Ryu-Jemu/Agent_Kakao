"""A4 전용 GET 탐침(루브릭 파라미터·시뮬레이터 사전 조회용). ActionClient(C2) 공표 전 임시 도구.

- GET만 허용한다(접수·reset 금지). 토큰은 출력하지 않는다.
- 사용: python3 tests/tools/probe.py <TC_ID> <path> [<path> ...]   예: L-03 '/api/members?name=서지호'
- 결과는 tests/logs/probe_<TC>.jsonl 에 누적하고 표준출력에 요약을 찍는다.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "https://gyodong-mall-action.aitop100.org"


def token() -> str:
    for ln in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        k, _, v = ln.strip().partition("=")
        if k == "AI_CS_AGENT":
            return v.strip().strip('"').strip("'")
    sys.exit("AI_CS_AGENT 없음")


def quote_path(p: str) -> str:
    path, _, q = p.partition("?")
    if not q:
        return path
    k, _, v = q.partition("=")
    return f"{path}?{k}={urllib.parse.quote(v)}"


def main():
    tc, paths = sys.argv[1], sys.argv[2:]
    out = os.path.join(ROOT, "tests", "logs", f"probe_{tc}.jsonl")
    with httpx.Client(timeout=20, headers={"Authorization": f"Bearer {token()}", "X-Aitop100-Test-Case-Id": tc}) as c:
        for p in paths:
            t0 = time.time()
            r = c.get(BASE + quote_path(p))
            ms = int((time.time() - t0) * 1000)
            try:
                body = r.json()
            except Exception:
                body = None
            rec = {"tc": tc, "path": p, "status": r.status_code, "ms": ms, "body": body,
                   "retry_after": r.headers.get("Retry-After")}
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"## {p} → {r.status_code} ({ms}ms)")
            print(json.dumps(body, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
