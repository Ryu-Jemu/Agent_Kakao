"""gateway 자체 검증(카카오 미접속): 로컬 모의 게이트웨이(websockets 서버) + 모의 콜백(httpx MockTransport).

실행: uv run python -m integ.selftest_gateway
검증: IDENTIFY/READY, HEARTBEAT {"op":1}, 콜백 형식·헤더, id 중복 제거, 50초 타이머 경합(1회만 전송),
      500자 분할, 세션 내부 직렬/세션 간 병렬, callbackToken 없음 건너뜀, 1001→RESUME(seq), 4009→IDENTIFY,
      handler 예외 → 안전 문구, sanitize_outputs 경계.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

from integ import gateway as ig

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))


class MockGW:
    def __init__(self):
        self.frames: list[dict] = []  # 클라이언트→서버
        self.conns = 0
        self.ws = None
        self.seq = 0
        self.connected = asyncio.Event()

    async def handler(self, ws):
        self.conns += 1
        self.ws = ws
        await ws.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 1000}}))
        try:
            async for raw in ws:
                p = json.loads(raw)
                self.frames.append(p)
                if p["op"] == 2:
                    self.seq = 0
                    await ws.send(json.dumps({"op": 3, "d": {"session_id": "sess_T", "bot": {"id": "b1"}}}))
                    self.connected.set()
                elif p["op"] == 6:
                    self.connected.set()
                elif p["op"] == 1:
                    await ws.send(json.dumps({"op": 11}))
        except websockets.ConnectionClosed:
            pass

    async def dispatch(self, d: dict):
        self.seq += 1
        await self.ws.send(json.dumps({"op": 0, "s": self.seq, "t": "MESSAGE_CREATE", "d": d}))


def msg(mid, content, user="u1", group="g1", cb="cbtok"):
    d = {"id": mid, "content": content, "timestamp": "2026-10-31T02:00:00Z", "isChannelChatroom": False,
         "botGroupKey": group, "botUserKey": user}
    if cb:
        d["callbackToken"] = cb
    return d


async def run_tests():
    tmp = tempfile.mkdtemp()
    ig.STATE_FILE = Path(tmp) / "state.json"
    ig.SAFETY_SEC = 1.5
    mock = MockGW()
    server = await websockets.serve(mock.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    ig.GW_URL = f"ws://127.0.0.1:{port}"

    callbacks: list[httpx.Request] = []

    def cb_handler(req: httpx.Request):
        callbacks.append(req)
        return httpx.Response(200, json={"totalCount": 1, "sendCount": 1, "errorCount": 0})

    timeline: list[tuple] = []

    async def handler(key, text, received_at):
        timeline.append(("start", key, text, time.monotonic()))
        try:
            if text == "slow":
                await asyncio.sleep(3)
                return ["늦은 결과(폐기돼야 함)"]
            if text.startswith("ser"):
                await asyncio.sleep(0.4)
            if text == "long":
                return [("가나다라마바사아자차. " * 120).strip()]
            if text == "boom":
                raise RuntimeError("x")
            return [f"R:{text}"]
        finally:
            timeline.append(("end", key, text, time.monotonic()))

    gw = ig.Gateway("BOT_TOKEN_X", handler, mode="test")
    await gw.http.aclose()
    gw.http = httpx.AsyncClient(transport=httpx.MockTransport(cb_handler))
    run_t = asyncio.create_task(gw.run())

    await asyncio.wait_for(mock.connected.wait(), 5)
    ident = [f for f in mock.frames if f["op"] == 2]
    check("identify", ident and ident[0]["d"]["token"] == "BOT_TOKEN_X")
    await asyncio.sleep(0.2)
    check("ready:session", gw.session_id == "sess_T")

    await asyncio.sleep(1.2)
    check("heartbeat", any(f == {"op": 1} for f in mock.frames), [f for f in mock.frames if f["op"] == 1][:1])

    big_id = 558185822630215770
    await mock.dispatch(msg(big_id, "hi"))
    await asyncio.sleep(0.3)
    check("callback:once", len(callbacks) == 1)
    if callbacks:
        r = callbacks[0]
        body = json.loads(r.content)
        check("callback:body", body == {"skillResponse": {"version": "2.0", "template": {
            "outputs": [{"simpleText": {"text": "R:hi"}}]}}}, body)
        check("callback:headers", r.headers.get("Authorization") == "KakaoAK BOT_TOKEN_X"
              and r.headers.get("X-Bot-Callback-Token") == "cbtok")
    await mock.dispatch(msg(big_id, "hi"))
    await asyncio.sleep(0.3)
    check("dedup", len(callbacks) == 1 and gw.stats["dups"] == 1)

    n = len(callbacks)
    await mock.dispatch(msg(2, "slow", user="u2"))
    await asyncio.sleep(2.0)
    check("timer:fires", len(callbacks) == n + 1 and ig.TIMEOUT_TEXT in callbacks[-1].content.decode())
    await asyncio.sleep(2.0)
    check("timer:once", len(callbacks) == n + 1, len(callbacks) - n)

    n = len(callbacks)
    await mock.dispatch(msg(3, "long", user="u3"))
    await asyncio.sleep(0.3)
    outs = json.loads(callbacks[-1].content)["skillResponse"]["template"]["outputs"] if len(callbacks) > n else []
    lens = [ig.kakao_len(o["simpleText"]["text"]) for o in outs]
    check("long:split", 1 < len(outs) <= 3 and all(x <= 500 for x in lens), lens)

    n = len(callbacks)
    await mock.dispatch(msg(4, "boom", user="u4"))
    await asyncio.sleep(0.3)
    check("error:safe", len(callbacks) == n + 1 and ig.ERROR_TEXT in callbacks[-1].content.decode())

    n = len(callbacks)
    await mock.dispatch(msg(5, "nocb", user="u5", cb=None))
    await asyncio.sleep(0.3)
    check("skip:no-cb", len(callbacks) == n)

    timeline.clear()
    await mock.dispatch(msg(6, "ser1", user="s1"))
    await mock.dispatch(msg(7, "ser2", user="s1"))
    await mock.dispatch(msg(8, "ser3", user="s2"))
    await asyncio.sleep(1.2)
    ev = {(e[0], e[2]): e[3] for e in timeline}
    check("serial:same-session", ev.get(("start", "ser2"), 0) >= ev.get(("end", "ser1"), 9e9) - 1e-3)
    check("parallel:diff-session", ev.get(("start", "ser3"), 9e9) < ev.get(("end", "ser1"), 0))

    # 1001 → RESUME(seq)
    last_seq = mock.seq
    mock.connected.clear()
    await mock.ws.close(code=1001, reason="restart")
    await asyncio.wait_for(mock.connected.wait(), 6)
    res = [f for f in mock.frames if f["op"] == 6]
    check("1001:resume", res and res[-1]["d"] == {"token": "BOT_TOKEN_X", "session_id": "sess_T", "seq": last_seq},
          res[-1] if res else None)

    # 4009 → IDENTIFY
    n_ident = len([f for f in mock.frames if f["op"] == 2])
    mock.connected.clear()
    await mock.ws.close(code=4009, reason="session timeout")
    await asyncio.wait_for(mock.connected.wait(), 6)
    await asyncio.sleep(0.3)
    check("4009:identify", len([f for f in mock.frames if f["op"] == 2]) == n_ident + 1)
    check("state:persist", json.loads(ig.STATE_FILE.read_text())["session_id"] == "sess_T")

    print("stage: drain", flush=True)
    await asyncio.wait_for(gw.drain(2), 5)
    print("stage: cancel run", flush=True)
    run_t.cancel()
    done, _ = await asyncio.wait({run_t}, timeout=8)
    check("shutdown:run-cancel", run_t in done)
    if run_t not in done:
        for t in asyncio.all_tasks():
            t.print_stack(limit=6)
    print("stage: server close", flush=True)
    server.close()
    await asyncio.wait_for(server.wait_closed(), 8)
    print("stage: done", flush=True)


def unit_sanitize():
    t, i = ig.sanitize_outputs(["a", "b", "c", "d"])
    check("san:max3", len(t) == 3 and t[2] == "c\nd")
    t, i = ig.sanitize_outputs([])
    check("san:empty", t == [ig.ERROR_TEXT])
    t, i = ig.sanitize_outputs(["x" * 600, "y", "z"])
    check("san:truncate", len(t) == 3 and ig.kakao_len(t[0]) <= 500 and t[1] == "y")
    t, i = ig.sanitize_outputs(["😀" * 300])  # UTF-16 600
    check("san:utf16", all(ig.kakao_len(x) <= 500 for x in t), [ig.kakao_len(x) for x in t])
    t, i = ig.sanitize_outputs("문자열")
    check("san:str", t == ["문자열"])


def main():
    unit_sanitize()
    asyncio.run(run_tests())
    bad = [r for r in results if not r[1]]
    for n, ok, d in results:
        print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {d}"))
    print(f"{len(results) - len(bad)}/{len(results)} PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
