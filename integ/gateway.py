"""카카오톡 봇 게이트웨이 데몬 — 공식 에코봇(developers.kakao.com/docs/ko/bot/gateway) 구조 확장.

실행:
    uv run python -m integ.gateway --mode echo     # M1 왕복 확인용 (echo: 원문)
    uv run python -m integ.gateway --mode agent    # agent.handle_message(C1) 연결

프로토콜(공식 문서 원문 확인, 2026-10-31 11:1x KST Chrome):
- HELLO(op10, d.heartbeat_interval) → IDENTIFY(op2, d.token) → READY(op3, d.session_id) → HEARTBEAT {"op":1}
  주기 전송 / HEARTBEAT_ACK(op11) → DISPATCH(op0, s,t,d). s는 매번 저장(RESUME의 d.seq).
- 재연결: 1001·네트워크 단절 → RESUME(op6: token, session_id, seq), 실패 시 새 IDENTIFY. 4009 → 세션 초기화 후 IDENTIFY.
  4001(인증)·4003(페이로드)·4004(중복 연결) → 공식 예제는 '중단'.
  ▶ 상시 운영 데몬은 중단하면 심사 중 봇이 죽으므로, 중단 대신 60초 대기 후 새 IDENTIFY로 재시도하고 CRITICAL 로그를 남긴다.
    (동일 호스트 중복 실행은 파일 잠금으로 막는다. 4004가 반복되면 다른 곳에서 같은 봇이 연결 중이라는 뜻.)
- 백오프: 1→2→4…최대 30초(READY 후 60초 이상 유지되면 1초로 초기화).

메시지 처리:
- MESSAGE_CREATE의 d.id로 중복 제거(LRU 20,000). callbackToken 없으면 건너뜀.
- 세션 키 = botGroupKey:botUserKey. 세션 내부는 직렬(큐), 세션끼리는 병렬.
- handle_message 결과(list[str])를 **한 번의 콜백**에 outputs[simpleText]로 담는다(최대 3개).
- 콜백은 메시지당 정확히 1회. 50초 안전 타이머(수신 시각 기준)와 정상 응답이 경합하면 먼저 끝난 쪽만 보낸다:
  타이머가 이기면 handler 태스크를 cancel하고 안전 문구를 보낸다(늦게 끝난 결과는 폐기).
- 송신 직전 각 text 500자(UTF-16 단위로 보수 계산) 검사 → 넘으면 overlength 로그 + 문장 경계 분할(여유 있을 때) 또는 축약.
- 지연 로그: JSON 한 줄 {"ev":"reply", recv_to_cb_ms, handler_ms, tc_id, bubbles, chars, ...} → stdout(journald).
- SIGTERM: 새 메시지 수신 중단 → 처리 중인 메시지 최대 25초 마무리 → 종료.
- 비밀값(봇 토큰·콜백 토큰)은 로그에 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import logging
import os
import re
import signal
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass

GW_URL = os.environ.get("KAKAO_GW_URL", "wss://bot-gateway.kakao.com/gateway")
CALLBACK_URL = os.environ.get("KAKAO_CALLBACK_URL", "https://kapi.kakao.com/v1/bot/callback")
SAFETY_SEC = float(os.environ.get("GATEWAY_SAFETY_SEC", "50"))
MAX_TEXT = 500
MAX_OUTPUTS = 3
STATE_FILE = Path(os.environ.get("GATEWAY_STATE_FILE", str(ROOT / "integ" / "logs" / "gateway_state.json")))
LOCK_FILE = os.environ.get("GATEWAY_LOCK_FILE", "/tmp/choonsik-gateway.lock")

TIMEOUT_TEXT = os.environ.get(
    "GATEWAY_TIMEOUT_TEXT", "확인이 늦어져 죄송합니다. 잠시 후 같은 내용을 한 번 더 보내 주시면 바로 이어서 도와드릴게요.")
ERROR_TEXT = os.environ.get(
    "GATEWAY_ERROR_TEXT", "죄송합니다. 일시적인 오류로 답변을 드리지 못했어요. 잠시 후 한 번 더 말씀해 주세요.")

OP_DISPATCH, OP_HEARTBEAT, OP_IDENTIFY, OP_READY, OP_RESUME, OP_HELLO, OP_HEARTBEAT_ACK = 0, 1, 2, 3, 6, 10, 11
CLOSE_SERVER_RESTART, CLOSE_AUTH_FAILED, CLOSE_INVALID_PAYLOAD, CLOSE_REPLACED, CLOSE_SESSION_TIMEOUT = \
    1001, 4001, 4003, 4004, 4009

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("gateway")
TC_RE = re.compile(r"^\s*-\s*id\s*:\s*([A-Za-z0-9][A-Za-z0-9._-]{0,99})\s*$", re.M)

Handler = Callable[[str, str, str], Awaitable[list[str]]]


def jlog(ev: str, **kw) -> None:
    kw = {"ev": ev, "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **kw}
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def kakao_len(s: str) -> int:
    """보수적 글자 수: UTF-16 코드 유닛(이모지 등 서로게이트는 2). 한글·영문은 len()과 같다."""
    return len(s.encode("utf-16-le")) // 2


def _cut(s: str, limit: int) -> tuple[str, str]:
    """limit(UTF-16) 이하로 문장/줄 경계에서 자른다 → (앞, 나머지)."""
    if kakao_len(s) <= limit:
        return s, ""
    # limit 안에 들어가는 최대 접두사
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if kakao_len(s[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    head = s[:lo]
    ends = [m.end() for m in re.finditer(r"[.!?。…~)\]]\s|\n", head)]
    if ends and ends[-1] >= lo * 0.5:
        cut = ends[-1]
    else:
        sp = head.rfind(" ")
        cut = sp if sp >= lo * 0.5 else lo
    return s[:cut].rstrip(), s[cut:].lstrip()


def sanitize_outputs(outs) -> tuple[list[str], list[dict]]:
    """handle_message 결과를 콜백 가능한 1~3개, 각 500자 이하 문자열로 정리. (texts, issues) 반환."""
    issues: list[dict] = []
    if isinstance(outs, str):
        outs = [outs]
        issues.append({"issue": "not_list"})
    texts = [str(x).strip() for x in (outs or []) if x is not None and str(x).strip()]
    if not texts:
        issues.append({"issue": "empty"})
        texts = [ERROR_TEXT]
    if len(texts) > MAX_OUTPUTS:
        issues.append({"issue": "too_many", "n": len(texts)})
        texts = texts[:MAX_OUTPUTS - 1] + ["\n".join(texts[MAX_OUTPUTS - 1:])]
    fixed: list[str] = []
    for i, t in enumerate(texts):
        if kakao_len(t) <= MAX_TEXT:
            fixed.append(t)
            continue
        issues.append({"issue": "overlength", "idx": i, "len": kakao_len(t)})
        rest = t
        # 남은 칸이 있으면 분할(내용 보존), 없으면 축약
        while rest:
            remaining_slots = MAX_OUTPUTS - len(fixed) - (len(texts) - i - 1)
            if remaining_slots <= 1:
                head, tail = _cut(rest, MAX_TEXT - 1)
                fixed.append(head + ("…" if tail else ""))
                break
            head, rest = _cut(rest, MAX_TEXT)
            fixed.append(head)
    return fixed[:MAX_OUTPUTS], issues


def build_body(texts: list[str]) -> dict:
    return {"skillResponse": {"version": "2.0", "template": {
        "outputs": [{"simpleText": {"text": t}} for t in texts]}}}


# ───────────────────────── 핸들러 ─────────────────────────
async def echo_handler(session_key: str, text: str, received_at: str) -> list[str]:
    return [f"echo: {text}"]


def load_handler(mode: str) -> Handler:
    if mode == "echo":
        return echo_handler
    sys.path.insert(0, str(ROOT))
    from agent import handle_message  # C1 (A3)

    return handle_message


# ───────────────────────── 게이트웨이 ─────────────────────────
class Gateway:
    def __init__(self, token: str, handler: Handler, *, mode: str):
        self.token = token
        self.handler = handler
        self.mode = mode
        self.session_id: str | None = None
        self.last_seq: int = 0
        self.seen: "OrderedDict[str, float]" = OrderedDict()
        self.sessions: dict[str, asyncio.Queue] = {}
        self.workers: dict[str, asyncio.Task] = {}
        self.inflight: set[asyncio.Task] = set()
        self.tc_by_session: dict[str, str] = {}
        self.stopping = asyncio.Event()
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0),
                                      limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=120))
        self.connected = False
        self.last_ack = 0.0
        self.stats = {"msgs": 0, "dups": 0, "cb_ok": 0, "cb_fail": 0, "timeouts": 0, "errors": 0, "reconnects": 0}
        self._load_state()

    # ---- RESUME 상태 영속화(프로세스 재시작 후에도 RESUME 시도) ----
    def _load_state(self) -> None:
        try:
            st = json.loads(STATE_FILE.read_text())
            if time.time() - st.get("saved", 0) < 240 and st.get("session_id"):
                self.session_id, self.last_seq = st["session_id"], int(st.get("seq", 0))
                log.info("이전 세션 상태 로드 — RESUME 시도 예정 (seq=%d)", self.last_seq)
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"session_id": self.session_id, "seq": self.last_seq, "saved": time.time()}))
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def _reset_session(self) -> None:
        self.session_id, self.last_seq = None, 0
        self._save_state()

    # ---- 연결 루프 ----
    async def run(self) -> None:
        backoff = 1.0
        while not self.stopping.is_set():
            t_conn = time.monotonic()
            code, reason = None, ""
            try:
                code, reason = await self._connect_once()
            except ConnectionClosed as e:
                rc = e.rcvd
                code, reason = (rc.code, rc.reason) if rc else (None, "")
            except (OSError, asyncio.TimeoutError, InvalidHandshake, InvalidURI) as e:
                reason = f"{type(e).__name__}: {e}"
            except Exception as e:  # 예상 밖 오류도 재연결
                log.exception("gateway loop error")
                reason = f"{type(e).__name__}: {e}"
            self.connected = False
            if self.stopping.is_set():
                break
            self.stats["reconnects"] += 1
            if time.monotonic() - t_conn > 60:
                backoff = 1.0
            wait = backoff
            if code in (CLOSE_AUTH_FAILED, CLOSE_INVALID_PAYLOAD, CLOSE_REPLACED):
                level = logging.CRITICAL
                self._reset_session()
                wait = 60.0 if code in (CLOSE_AUTH_FAILED, CLOSE_REPLACED) else 5.0
            elif code == CLOSE_SESSION_TIMEOUT:
                level = logging.WARNING
                self._reset_session()
                wait = 1.0
            else:  # 1001·네트워크 단절·기타 → RESUME 유지
                level = logging.WARNING
            log.log(level, "연결 종료 code=%s reason=%s → %.1fs 후 %s", code, reason[:120], wait,
                    "RESUME" if self.session_id else "IDENTIFY")
            jlog("disconnect", code=code, reason=reason[:120], wait=wait, resume=bool(self.session_id))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=wait)
            backoff = min(backoff * 2, 30.0)

    async def _connect_once(self) -> tuple[int | None, str]:
        log.info("connecting %s", GW_URL)
        async with websockets.connect(GW_URL, open_timeout=15, close_timeout=5, max_size=2 ** 22) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if hello.get("op") != OP_HELLO:
                raise RuntimeError(f"HELLO 아님 op={hello.get('op')}")
            interval = float(hello.get("d", {}).get("heartbeat_interval", 41250)) / 1000.0
            resumed = False
            if self.session_id:
                await ws.send(json.dumps({"op": OP_RESUME, "d": {
                    "token": self.token, "session_id": self.session_id, "seq": self.last_seq}}))
                resumed = True
                log.info("RESUME 전송 seq=%d", self.last_seq)
            else:
                await ws.send(json.dumps({"op": OP_IDENTIFY, "d": {"token": self.token}}))
                deadline = time.monotonic() + 20
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(1.0, deadline - time.monotonic()))
                    p = json.loads(raw)
                    if p.get("op") == OP_READY:
                        self.session_id = p["d"]["session_id"]
                        self.last_seq = 0
                        self._save_state()
                        log.info("READY bot=%s", p["d"].get("bot", {}).get("id"))
                        break
                    if p.get("op") == OP_DISPATCH:  # 이론상 READY 전엔 없음
                        await self._on_frame(p)
            self.connected = True
            self.last_ack = time.monotonic()
            jlog("connected", resumed=resumed, hb_ms=int(interval * 1000))
            hb = asyncio.create_task(self._heartbeat(ws, interval))
            try:
                async for raw in ws:
                    try:
                        p = json.loads(raw)
                    except ValueError:
                        log.warning("JSON 아닌 프레임 무시")
                        continue
                    await self._on_frame(p)
            finally:
                hb.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await hb
            # 정상 close(1000/1001)는 예외 없이 반복이 끝나므로 코드를 직접 읽는다
            return getattr(ws, "close_code", None), getattr(ws, "close_reason", "") or ""

    async def _heartbeat(self, ws, interval: float) -> None:
        period = max(1.0, interval * 0.9)  # '약간 짧게'
        while True:
            await asyncio.sleep(period)
            if time.monotonic() - self.last_ack > period * 2 + 15:
                log.warning("HEARTBEAT_ACK 누락 → 재연결")
                await ws.close(code=4000, reason="heartbeat ack timeout")
                return
            await ws.send(json.dumps({"op": OP_HEARTBEAT}))

    async def _on_frame(self, p: dict) -> None:
        op = p.get("op")
        if op == OP_HEARTBEAT_ACK:
            self.last_ack = time.monotonic()
            return
        if op != OP_DISPATCH:
            if op == OP_READY:  # RESUME 후 READY가 올 수도 있음(문서 미기재) → 세션 갱신
                self.session_id = p.get("d", {}).get("session_id", self.session_id)
                self._save_state()
            return
        self.last_ack = time.monotonic()
        if p.get("s") is not None and not self.stopping.is_set():
            # 종료 중 버린 메시지는 seq를 저장하지 않는다 → 재시작 후 RESUME으로 다시 받는다
            self.last_seq = p["s"]
            self._save_state()
        if p.get("t") == "MESSAGE_CREATE":
            self._on_message(p.get("d") or {})

    # ---- 메시지 디스패치 ----
    def _on_message(self, d: dict) -> None:
        recv_mono = time.monotonic()
        mid = str(d.get("id"))
        if mid in self.seen:
            self.stats["dups"] += 1
            jlog("dup", msg_id=mid)
            return
        self.seen[mid] = time.time()
        while len(self.seen) > 20000:
            self.seen.popitem(last=False)
        if self.stopping.is_set():
            jlog("drop_stopping", msg_id=mid)
            return
        if not d.get("callbackToken"):
            jlog("skip_no_callback", msg_id=mid)
            return
        self.stats["msgs"] += 1
        key = f"{d.get('botGroupKey', '')}:{d.get('botUserKey', '')}"
        q = self.sessions.get(key)
        if q is None:
            q = asyncio.Queue()
            self.sessions[key] = q
            self.workers[key] = asyncio.create_task(self._session_worker(key, q))
        q.put_nowait((recv_mono, d))

    async def _session_worker(self, key: str, q: asyncio.Queue) -> None:
        try:
            while True:
                try:
                    recv_mono, d = await asyncio.wait_for(q.get(), timeout=900)
                except asyncio.TimeoutError:
                    if q.empty():
                        return
                    continue
                task = asyncio.create_task(self._process(key, recv_mono, d))
                self.inflight.add(task)
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("process error")
                finally:
                    self.inflight.discard(task)
        finally:
            if self.sessions.get(key) is q:
                self.sessions.pop(key, None)
                self.workers.pop(key, None)

    async def _process(self, key: str, recv_mono: float, d: dict) -> None:
        content = d.get("content") or ""
        mid = str(d.get("id"))
        received_at = d.get("timestamp") or datetime.now(timezone.utc).isoformat()
        m = TC_RE.search(content)
        if m:
            self.tc_by_session[key] = m.group(1)
        tc_id = self.tc_by_session.get(key)
        queued_ms = round((time.monotonic() - recv_mono) * 1000)
        # 수신 시각 기준 50초. 같은 세션 큐에서 오래 기다린 메시지도 최소 3초는 준다
        budget = max(min(3.0, SAFETY_SEC), SAFETY_SEC - (time.monotonic() - recv_mono))
        t_h = time.monotonic()
        status = "ok"
        err = None
        htask = asyncio.create_task(self.handler(key, content, received_at))
        try:
            # 먼저 끝난 쪽만 보낸다: asyncio.wait는 취소 완료를 기다리지 않으므로 타이머가 지연되지 않는다
            done, _ = await asyncio.wait({htask}, timeout=budget)
        except asyncio.CancelledError:
            htask.cancel()
            raise
        if htask in done:
            try:
                outs = htask.result()
            except BaseException as e:  # CancelledError 포함
                status, outs, err = "error", [ERROR_TEXT], f"{type(e).__name__}: {str(e)[:200]}"
                self.stats["errors"] += 1
                log.error("handler error %s", err, exc_info=not isinstance(e, asyncio.CancelledError))
        else:
            htask.cancel()  # 늦게 끝날 결과는 폐기
            status, outs = "timeout", [TIMEOUT_TEXT]
            self.stats["timeouts"] += 1
        handler_ms = round((time.monotonic() - t_h) * 1000)
        texts, issues = sanitize_outputs(outs)
        if any(i.get("issue") == "overlength" for i in issues):
            log.error("A3 포맷터 결함: 500자 초과 말풍선 → 분할/축약 %s", issues)
        cb_status, cb_resp = await self._send_callback(d["callbackToken"], texts, recv_mono)
        jlog("reply", msg_id=mid, session=key[-12:], tc_id=tc_id, status=status, err=err,
             recv_to_cb_ms=round((time.monotonic() - recv_mono) * 1000), handler_ms=handler_ms,
             queued_ms=queued_ms, bubbles=len(texts), chars=[kakao_len(t) for t in texts],
             in_len=len(content), in_head=content[:40].replace("\n", " "), issues=issues or None,
             cb_status=cb_status, cb=cb_resp)

    async def _send_callback(self, cb_token: str, texts: list[str], recv_mono: float):
        body = build_body(texts)
        headers = {"Authorization": f"KakaoAK {self.token}", "X-Bot-Callback-Token": cb_token,
                   "Content-Type": "application/json"}
        last = None
        for attempt in range(2):
            try:
                r = await self.http.post(CALLBACK_URL, json=body, headers=headers)
                try:
                    j = r.json()
                except ValueError:
                    j = {"text": r.text[:200]}
                if r.status_code == 200:
                    self.stats["cb_ok"] += 1
                    return 200, j
                last = (r.status_code, j)
                # 4xx(토큰 만료·중복 등)는 재시도해도 소용없음 → 즉시 포기(중복 전송 방지)
                if r.status_code < 500:
                    break
            except httpx.HTTPError as e:
                last = ("NETWORK", type(e).__name__)
            if time.monotonic() - recv_mono > 55:
                break
            await asyncio.sleep(0.5)
        self.stats["cb_fail"] += 1
        log.error("callback 실패 %s", last)
        return last[0] if last else None, last[1] if last else None

    # ---- 종료·상태 ----
    async def drain(self, timeout: float = 25.0) -> None:
        self.stopping.set()
        if self.inflight:
            log.info("종료 대기: 처리 중 %d건", len(self.inflight))
            await asyncio.wait(list(self.inflight), timeout=timeout)
        await self.http.aclose()

    async def alive_loop(self) -> None:
        while not self.stopping.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=300)
            jlog("alive", connected=self.connected, sessions=len(self.sessions), inflight=len(self.inflight),
                 rss_mb=_rss_mb(), mode=self.mode, **self.stats)


def _rss_mb() -> float | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    try:
        import resource

        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    except Exception:
        return None


def _single_instance():
    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.critical("다른 gateway 프로세스가 이미 실행 중(%s) — 중복 연결(4004) 방지를 위해 종료", LOCK_FILE)
        sys.exit(3)
    f.write(str(os.getpid()))
    f.flush()
    return f


async def amain(mode: str) -> None:
    token = os.environ.get("KAKAO_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        log.critical("KAKAO_BOT_TOKEN 미설정(.env) — 종료")
        sys.exit(2)
    handler = load_handler(mode)
    gw = Gateway(token, handler, mode=mode)
    loop = asyncio.get_running_loop()
    stop_sig = asyncio.Event()
    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, stop_sig.set)
    release = (ROOT / "RELEASE").read_text().strip() if (ROOT / "RELEASE").exists() else "dev"
    jlog("start", mode=mode, release=release, pid=os.getpid(), safety_sec=SAFETY_SEC)
    run_t = asyncio.create_task(gw.run())
    alive_t = asyncio.create_task(gw.alive_loop())
    await stop_sig.wait()
    log.info("종료 신호 수신 — drain")
    await gw.drain()
    for t in (run_t, alive_t):
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    jlog("stop", **gw.stats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["echo", "agent"], default=os.environ.get("GATEWAY_MODE", "agent"))
    a = ap.parse_args()
    _lock = _single_instance()  # noqa: F841 (프로세스 수명 동안 유지)
    asyncio.run(amain(a.mode))


if __name__ == "__main__":
    main()
