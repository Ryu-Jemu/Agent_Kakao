"""C2 ActionClient — 교동마을 산지직송 액션 API(API-01~40 + reset) 비동기 클라이언트.

근거: actions.json(OpenAPI 3.1, 정본), docs/contest/06_action_api_overview.md.

사용 예::

    from integ.action_client import ActionClient
    trace = []
    ac = ActionClient("L-11", trace=trace)
    order = await ac.get_order("100100003")          # API-07, 없으면 None
    ships = await ac.call("API-11", order_no="100100003")  # 범용 디스패처, 빈 검색은 []

응답 규약(06 '응답 규약'·'오류가 났을 때'):
- 200 → dict(단건) | list(검색). 204(reset) → True.
- 본문 없는 404 → None (POST도 동일: 대상 없음).
- 400 → ActionBadRequest(TC 헤더 오류면 code/message 포함), 401 → ActionUnauthorized,
  403 → ActionForbidden, 429 누적 한도 → ActionQuotaExhausted(재시도 안 함),
  429 시간 창 → Retry-After만큼 대기 후 재시도(대기 상한 초과 시 ActionRateLimited),
  500·503 → 1회 재시도 후 ActionServerError, 네트워크 오류 → 1회 재시도 후 ActionNetworkError.
- 요청 전 로컬 검증 실패(TC ID 형식·필수 필드·타입·enum) → ActionValidationError (호출 안 함 = 한도 소모 없음).

상태(TC 범위, 프로세스 전역 레지스트리):
- 같은 TC의 같은 GET은 캐시(cached=True로 trace).
- POST가 한 번이라도 나가면 GET 캐시를 무효화한다. 접수 데이터는 모든 TC가 공유하므로
  (06 '연습과 평가') 해당 TC뿐 아니라 프로세스 내 모든 TC 캐시를 비운다(요구사항의 상위집합).
- TC당 네트워크 호출 상한 25회(기본) → 초과 시 ActionCallLimitExceeded.
- TC 상태는 30분 미사용 시 자동 초기화(같은 TC 재진행 대비). 명시 초기화: ActionClient.clear_state(tc_id).

호출 속도 제한(클라이언트 측):
- 연습: `.coord/api_rate.json` 파일 잠금으로 여러 프로세스가 60초당 90회를 나눠 쓴다
  (`.coord/`가 있을 때 자동, 또는 ACTION_RATE_FILE 환경변수).
- 그 외(VM 운영): 프로세스 내 60초당 95회.

trace: 호출마다 {api_id, method, path, params, body, status, ms, cached, tc_id, ts}를
`trace` 리스트에 append하고, ACTION_TRACE_FILE 환경변수가 있으면 JSONL로도 남긴다. 토큰은 절대 기록하지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

try:  # 선택: .env 자동 로드
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

BASE_URL = os.environ.get("ACTION_BASE_URL", "https://gyodong-mall-action.aitop100.org")
TC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
QUOTA_MSG = "누적 API 호출 한도"
ROOT = Path(__file__).resolve().parent.parent


# ───────────────────────── 예외 ─────────────────────────
class ActionError(Exception):
    """액션 API 오류의 기반 클래스."""

    def __init__(self, message: str, *, api_id: str = "", status: int | None = None,
                 code: str | None = None, server_message: str | None = None):
        super().__init__(message)
        self.api_id = api_id
        self.status = status
        self.code = code
        self.server_message = server_message


class ActionValidationError(ActionError):
    """요청 전 로컬 검증 실패(호출하지 않음)."""


class ActionBadRequest(ActionError):
    """400. code가 있으면 TC 헤더 오류(MISSING_/INVALID_TEST_CASE_ID), 없으면 파라미터·본문 위반."""


class ActionUnauthorized(ActionError):
    """401: 토큰 오류 또는 API 사용 기간 아님."""


class ActionForbidden(ActionError):
    """403: 접근 권한 없음."""


class ActionConflict(ActionError):
    """409: (reset) 제출 후·평가 시작 후 초기화 불가."""


class ActionRateLimited(ActionError):
    """429 시간 창 한도. retry_after 초 대기가 상한을 넘어 포기."""

    def __init__(self, *a, retry_after: float | None = None, **kw):
        super().__init__(*a, **kw)
        self.retry_after = retry_after


class ActionQuotaExhausted(ActionError):
    """429 평가 누적 한도(3,000회). 기다려도 풀리지 않음 → 재시도 금지."""


class ActionServerError(ActionError):
    """500·503 (1회 재시도 후에도 실패)."""


class ActionNetworkError(ActionError):
    """타임아웃·연결 실패(1회 재시도 후에도 실패)."""


class ActionCallLimitExceeded(ActionError):
    """TC당 호출 상한 초과(클라이언트 안전장치)."""


# ───────────────────────── 스펙 표 (actions.json에서 도출, integ/selfcheck_spec.py로 대조) ─────────────────────────
@dataclass(frozen=True)
class ApiSpec:
    api_id: str
    method: str  # GET | POST
    path: str  # 경로 템플릿. 검색은 '?key=' 포함(actions.json 경로 키 그대로)
    summary: str
    path_params: tuple[str, ...] = ()
    query: str | None = None  # 검색 파라미터 이름
    body: dict[str, str] = field(default_factory=dict)  # 필드 → 'str'|'int'|'date'|'list[str]'|'enum:A|B'
    required: tuple[str, ...] = ()


def _g(api_id, path, summary, path_params=(), query=None):
    return ApiSpec(api_id, "GET", path, summary, tuple(path_params), query)


def _p(api_id, path, summary, path_params=(), body=None, required=()):
    return ApiSpec(api_id, "POST", path, summary, tuple(path_params), None, dict(body or {}), tuple(required))


SPECS: dict[str, ApiSpec] = {s.api_id: s for s in [
    _g("API-01", "/api/products/{sku}", "상품 조회", ["sku"]),
    _g("API-02", "/api/products?item=", "품목별 상품 검색", query="item"),
    _g("API-03", "/api/lots/{lot_id}", "로트 조회", ["lot_id"]),
    _g("API-04", "/api/lots/{lot_id}/investigation", "로트 조사 조회", ["lot_id"]),
    _g("API-05", "/api/tickets?member_id=", "회원별 상담 이력 검색", query="member_id"),
    _g("API-06", "/api/tickets?lot_id=", "로트별 상담 이력 검색", query="lot_id"),
    _g("API-07", "/api/orders/{order_no}", "주문 조회", ["order_no"]),
    _g("API-08", "/api/orders?member_id=", "회원별 주문 검색", query="member_id"),
    _g("API-09", "/api/orders?inflow_tag=", "유입태그별 주문 검색", query="inflow_tag"),
    _g("API-10", "/api/shipments/{shipment_id}", "배송 조회", ["shipment_id"]),
    _g("API-11", "/api/shipments?order_no=", "주문별 배송 검색", query="order_no"),
    _g("API-12", "/api/members/{member_id}", "조합원 조회", ["member_id"]),
    _g("API-13", "/api/members?name=", "이름 조합원 검색", query="name"),
    _g("API-14", "/api/members?referred_by=", "추천인별 조합원 검색", query="referred_by"),
    _g("API-15", "/api/point-entries?member_id=", "적립금 내역 검색", query="member_id"),
    _g("API-16", "/api/coupons?member_id=", "회원별 쿠폰 검색", query="member_id"),
    _g("API-17", "/api/payments/{approval_no}", "결제 조회", ["approval_no"]),
    _g("API-18", "/api/payments?order_no=", "주문별 결제 검색", query="order_no"),
    _g("API-19", "/api/subscriptions/{subscription_id}", "구독 조회", ["subscription_id"]),
    _g("API-20", "/api/promos/{code}", "프로모션 조회", ["code"]),
    _g("API-21", "/api/inventory?sku=", "재고 조회", query="sku"),
    _p("API-22", "/api/orders/{order_no}/restore-requests", "주문 복구 접수", ["order_no"]),
    _p("API-23", "/api/orders/{order_no}/change-requests", "주문 변경 접수", ["order_no"],
       {"requested_items": "list[str]"}, ["requested_items"]),
    _p("API-24", "/api/orders/{order_no}/address-change-requests", "배송지 변경 접수", ["order_no"],
       {"new_address": "str"}, ["new_address"]),
    _p("API-25", "/api/orders/{order_no}/schedule-change-requests", "배송 일정 변경 접수", ["order_no"],
       {"requested_date": "date"}, ["requested_date"]),
    _p("API-26", "/api/orders/{order_no}/memos", "주문 메모 접수", ["order_no"], {"memo": "str"}, ["memo"]),
    _p("API-27", "/api/orders/{order_no}/expedite-requests", "긴급 출고 접수", ["order_no"],
       {"qty": "int", "reason": "str"}, ["qty", "reason"]),
    _p("API-28", "/api/shipments/{shipment_id}/reship-requests", "재배송 접수", ["shipment_id"]),
    _p("API-29", "/api/refunds", "환불 신청", [],
       {"order_no": "str", "amount": "int", "reason": "str"}, ["order_no", "amount", "reason"]),
    _g("API-30", "/api/refunds?order_no=", "주문별 환불 검색", query="order_no"),
    _p("API-31", "/api/payments/{approval_no}/cancellation-requests", "카드 취소 접수", ["approval_no"]),
    _p("API-32", "/api/payments/{approval_no}/cash-receipt-requests", "현금영수증 발행 접수", ["approval_no"],
       {"receipt_number": "str"}, ["receipt_number"]),
    _p("API-33", "/api/members/{member_id}/coupon-issue-requests", "쿠폰 발급 접수", ["member_id"],
       {"promo_code": "str"}, ["promo_code"]),
    _p("API-34", "/api/members/{member_id}/reward-requests", "리워드 지급 접수", ["member_id"]),
    _p("API-35", "/api/escalations", "에스컬레이션", [], {"lane": "str", "reason": "str"}, ["lane", "reason"]),
    _g("API-36", "/api/escalations/{escalation_id}", "에스컬레이션 조회", ["escalation_id"]),
    _p("API-37", "/api/shipments/{shipment_id}/reship-charge-requests", "재배송비 청구 접수", ["shipment_id"],
       {"charge_amount": "int"}, ["charge_amount"]),
    _p("API-38", "/api/orders/{order_no}/pickup-requests", "픽업 접수", ["order_no"],
       {"qty": "int", "trigger": "str", "cost_bearer": "enum:SELLER|CUSTOMER"}, ["qty", "trigger", "cost_bearer"]),
    _p("API-39", "/api/products/{sku}/restock-notification-requests", "재입고 알림 등록", ["sku"]),
    _p("API-40", "/api/subscriptions/{subscription_id}/change-requests", "구독 변경 접수", ["subscription_id"],
       {"kind": "enum:SKIP|CANCEL"}, ["kind"]),
    _p("RESET", "/api/action-data/reset", "내 액션 데이터 전체 초기화"),
]}


# ───────────────────────── 속도 제한기 ─────────────────────────
class _MemoryRate:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window, self.ts = limit, window, []
        self.lock = asyncio.Lock()

    async def acquire(self) -> float:
        waited = 0.0
        while True:
            async with self.lock:
                now = time.time()
                self.ts = [t for t in self.ts if now - t < self.window]
                if len(self.ts) < self.limit:
                    self.ts.append(now)
                    return waited
                wait = self.window - (now - self.ts[0]) + 0.05
            await asyncio.sleep(wait)
            waited += wait


class _FileRate:
    """여러 프로세스 공유: fcntl 잠금 + JSON 타임스탬프 목록."""

    def __init__(self, path: Path, limit: int = 90, window: float = 60.0):
        self.path, self.limit, self.window = path, limit, window

    def _try(self) -> float:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                try:
                    ts = json.loads(raw).get("ts", []) if raw else []
                except Exception:
                    ts = []
                now = time.time()
                ts = [t for t in ts if now - t < self.window]
                if len(ts) < self.limit:
                    ts.append(now)
                    wait = 0.0
                else:
                    wait = self.window - (now - min(ts)) + 0.05
                f.seek(0)
                f.truncate()
                f.write(json.dumps({"ts": ts, "limit": self.limit, "window": self.window}))
                f.flush()
                return wait
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    async def acquire(self) -> float:
        waited = 0.0
        while True:
            wait = await asyncio.to_thread(self._try)
            if wait <= 0:
                return waited
            await asyncio.sleep(wait)
            waited += wait


def _make_rate():
    p = os.environ.get("ACTION_RATE_FILE")
    if p:
        return _FileRate(Path(p), int(os.environ.get("ACTION_RATE_LIMIT", "90")))
    if (ROOT / ".coord").is_dir():
        return _FileRate(ROOT / ".coord" / "api_rate.json", int(os.environ.get("ACTION_RATE_LIMIT", "90")))
    return _MemoryRate(int(os.environ.get("ACTION_RATE_LIMIT", "95")))


_RATE = None


def _rate():
    global _RATE
    if _RATE is None:
        _RATE = _make_rate()
    return _RATE


# ───────────────────────── TC 상태 레지스트리 ─────────────────────────
@dataclass
class _TcState:
    cache: dict[str, Any] = field(default_factory=dict)
    calls: int = 0
    posts: int = 0
    last_used: float = field(default_factory=time.time)


_STATES: dict[str, _TcState] = {}
STATE_IDLE_TTL = float(os.environ.get("ACTION_STATE_TTL", "1800"))


def _state(tc_id: str) -> _TcState:
    st = _STATES.get(tc_id)
    now = time.time()
    if st is None or now - st.last_used > STATE_IDLE_TTL:
        st = _TcState()
        _STATES[tc_id] = st
    st.last_used = now
    return st


def _invalidate_all_caches() -> None:
    for st in _STATES.values():
        st.cache.clear()


# ───────────────────────── HTTP 클라이언트(이벤트 루프별 공유, keep-alive) ─────────────────────────
_HTTP: dict[int, httpx.AsyncClient] = {}


def _http() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    key = id(loop)
    cli = _HTTP.get(key)
    if cli is None or cli.is_closed:
        cli = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(float(os.environ.get("ACTION_TIMEOUT", "10")), connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=120),
            headers={"Accept": "application/json", "User-Agent": "choonsik-cs-agent/0.1"},
        )
        _HTTP[key] = cli
    return cli


async def aclose_all() -> None:
    for cli in list(_HTTP.values()):
        try:
            await cli.aclose()
        except Exception:
            pass
    _HTTP.clear()


_TRACE_FILE = os.environ.get("ACTION_TRACE_FILE")


# ───────────────────────── 본체 ─────────────────────────
class ActionClient:
    """C2. 생성은 가볍다(상태는 tc_id 기준 전역 공유) — 턴마다 새로 만들어도 캐시·호출 수가 이어진다."""

    SPECS = SPECS

    def __init__(self, tc_id: str, *, trace: list | None = None, token: str | None = None,
                 max_calls: int | None = None, allow_reset: bool = False,
                 max_retry_after: float | None = None, on_trace: Callable[[dict], None] | None = None,
                 trace_responses: bool = False):
        if not isinstance(tc_id, str) or not TC_ID_RE.match(tc_id):
            raise ActionValidationError(f"TC ID 형식 오류: {tc_id!r} (패턴 {TC_ID_RE.pattern})")
        self.tc_id = tc_id
        self.trace = trace
        self._token = token or os.environ.get("AI_CS_AGENT", "")
        self.max_calls = max_calls if max_calls is not None else int(os.environ.get("ACTION_MAX_CALLS_PER_TC", "25"))
        self.allow_reset = allow_reset
        self.max_retry_after = (max_retry_after if max_retry_after is not None
                                else float(os.environ.get("ACTION_MAX_RETRY_AFTER", "20")))
        self.on_trace = on_trace
        self.trace_responses = trace_responses

    # ---- 상태 조회/초기화 ----
    @property
    def calls_used(self) -> int:
        return _state(self.tc_id).calls

    @staticmethod
    def clear_state(tc_id: str | None = None) -> None:
        """TC 상태(캐시·호출 수) 초기화. None이면 전체."""
        if tc_id is None:
            _STATES.clear()
        else:
            _STATES.pop(tc_id, None)

    # ---- 경로 조립·검증 ----
    @staticmethod
    def build_path(spec: ApiSpec, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        path = spec.path
        params: dict[str, Any] = {}
        for name in spec.path_params:
            v = args.get(name)
            if v is None or str(v).strip() == "":
                raise ActionValidationError(f"{spec.api_id}: 경로 파라미터 {name} 필요", api_id=spec.api_id)
            sv = str(v).strip()
            params[name] = sv
            path = path.replace("{" + name + "}", quote(sv, safe=""))
        if spec.query:
            v = args.get(spec.query)
            if v is None or str(v).strip() == "":
                raise ActionValidationError(f"{spec.api_id}: 검색 파라미터 {spec.query} 필요", api_id=spec.api_id)
            sv = str(v).strip()
            params[spec.query] = sv
            # 경로 키가 '...?key=' 로 끝나므로 값만 인코딩해 직접 붙인다(06 주의사항)
            path = path + quote(sv, safe="")
        return path, params

    @staticmethod
    def build_body(spec: ApiSpec, args: dict[str, Any]) -> dict[str, Any] | None:
        if spec.method != "POST":
            return None
        allowed = set(spec.body)
        extra = set(args) - allowed - set(spec.path_params)
        if extra:
            raise ActionValidationError(f"{spec.api_id}: 허용되지 않은 필드 {sorted(extra)}", api_id=spec.api_id)
        body: dict[str, Any] = {}
        for k, typ in spec.body.items():
            if k not in args or args[k] is None:
                if k in spec.required:
                    raise ActionValidationError(f"{spec.api_id}: 필수 필드 {k} 누락", api_id=spec.api_id)
                continue
            v = args[k]
            if typ == "int":
                if isinstance(v, bool):
                    raise ActionValidationError(f"{spec.api_id}: {k}는 정수", api_id=spec.api_id)
                if isinstance(v, float) and v.is_integer():
                    v = int(v)
                if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
                    v = int(v.strip())
                if not isinstance(v, int):
                    raise ActionValidationError(f"{spec.api_id}: {k}는 정수", api_id=spec.api_id)
                if not -2**31 <= v < 2**31:
                    raise ActionValidationError(f"{spec.api_id}: {k} int32 범위 초과", api_id=spec.api_id)
            elif typ == "str":
                if not isinstance(v, str):
                    v = str(v)
                if k in spec.required and v.strip() == "":
                    raise ActionValidationError(f"{spec.api_id}: {k} 빈 문자열", api_id=spec.api_id)
            elif typ == "date":
                v = str(v).strip()
                try:
                    date.fromisoformat(v)
                    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
                except Exception:
                    raise ActionValidationError(f"{spec.api_id}: {k}는 YYYY-MM-DD", api_id=spec.api_id)
            elif typ == "list[str]":
                if isinstance(v, str):
                    v = [v]
                if not isinstance(v, (list, tuple)) or not all(isinstance(x, (str, int)) for x in v):
                    raise ActionValidationError(f"{spec.api_id}: {k}는 문자열 배열", api_id=spec.api_id)
                v = [str(x) for x in v]
            elif typ.startswith("enum:"):
                choices = typ[5:].split("|")
                v = str(v).strip().upper()
                if v not in choices:
                    raise ActionValidationError(f"{spec.api_id}: {k}는 {choices} 중 하나", api_id=spec.api_id)
            body[k] = v
        return body

    # ---- 범용 호출 ----
    async def call(self, api_id: str, **args: Any) -> Any:
        api_id = api_id.upper().strip()
        if api_id in ("RESET", "RESETMYACTIONDATA"):
            return await self.reset()
        spec = SPECS.get(api_id)
        if spec is None:
            raise ActionValidationError(f"알 수 없는 API: {api_id}")
        path, params = self.build_path(spec, args)
        if spec.method == "GET":
            extra = set(args) - set(spec.path_params) - ({spec.query} if spec.query else set())
            if extra:
                raise ActionValidationError(f"{api_id}: 지원하지 않는 파라미터 {sorted(extra)}", api_id=api_id)
        body = self.build_body(spec, args)
        return await self._request(spec, path, params, body)

    async def reset(self) -> bool:
        """POST /api/action-data/reset — allow_reset=True(A4 전용)일 때만."""
        if not self.allow_reset:
            raise ActionValidationError("reset은 allow_reset=True(A4 전용)일 때만 허용", api_id="RESET")
        spec = SPECS["RESET"]
        r = await self._request(spec, spec.path, {}, None)
        _STATES.clear()
        return r

    # ---- 내부 요청 ----
    def _emit(self, rec: dict) -> None:
        if self.trace is not None:
            self.trace.append(rec)
        if self.on_trace:
            try:
                self.on_trace(rec)
            except Exception:
                pass
        if _TRACE_FILE:
            try:
                with open(_TRACE_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass

    async def _request(self, spec: ApiSpec, path: str, params: dict, body: dict | None) -> Any:
        st = _state(self.tc_id)
        rec = {"api_id": spec.api_id, "method": spec.method, "path": path, "params": params, "body": body,
               "status": None, "ms": 0, "cached": False, "tc_id": self.tc_id,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if spec.method == "GET" and path in st.cache:
            status, data = st.cache[path]
            rec.update(status=status, cached=True)
            if self.trace_responses:
                rec["resp"] = data
            self._emit(rec)
            return data
        if spec.method == "POST":
            st.posts += 1
            _invalidate_all_caches()  # 접수번호 필드(refund_ids 등) 변경 대비

        t0 = time.perf_counter()
        attempts_5xx = 0
        attempts_net = 0
        try:
            while True:
                if st.calls >= self.max_calls:
                    raise ActionCallLimitExceeded(
                        f"TC {self.tc_id} 호출 상한 {self.max_calls}회 초과", api_id=spec.api_id)
                await _rate().acquire()
                st.calls += 1
                headers = {"Authorization": f"Bearer {self._token}", "X-Aitop100-Test-Case-Id": self.tc_id}
                try:
                    if spec.method == "GET":
                        resp = await _http().get(path, headers=headers)
                    elif body is None:
                        resp = await _http().post(path, headers=headers)
                    else:
                        resp = await _http().post(path, headers=headers, json=body)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    attempts_net += 1
                    if attempts_net <= 1:
                        await asyncio.sleep(0.3)
                        continue
                    rec["status"] = "NETWORK"
                    raise ActionNetworkError(f"{spec.api_id} 네트워크 오류: {type(e).__name__}",
                                             api_id=spec.api_id) from None
                rec["status"] = resp.status_code
                code = resp.status_code
                if code == 200:
                    data = resp.json() if resp.content else None
                    if spec.method == "GET":
                        st.cache[path] = (200, data)
                    if self.trace_responses:
                        rec["resp"] = data
                    return data
                if code == 204:
                    return True
                if code == 404:
                    if spec.method == "GET":
                        st.cache[path] = (404, None)
                    return None
                err_code, err_msg = _err(resp)
                if code == 429:
                    if err_msg and QUOTA_MSG in err_msg:
                        raise ActionQuotaExhausted(f"{spec.api_id} 평가 누적 한도 초과", api_id=spec.api_id,
                                                   status=429, code=err_code, server_message=err_msg)
                    ra = _retry_after(resp)
                    if ra > self.max_retry_after:
                        raise ActionRateLimited(f"{spec.api_id} 429 Retry-After {ra}s > 상한",
                                                api_id=spec.api_id, status=429, code=err_code,
                                                server_message=err_msg, retry_after=ra)
                    await asyncio.sleep(ra)
                    continue
                if code in (500, 502, 503, 504):
                    attempts_5xx += 1
                    if attempts_5xx <= 1:
                        await asyncio.sleep(0.5)
                        continue
                    raise ActionServerError(f"{spec.api_id} 서버 오류 {code}", api_id=spec.api_id, status=code,
                                            code=err_code, server_message=err_msg)
                cls = {400: ActionBadRequest, 401: ActionUnauthorized, 403: ActionForbidden,
                       409: ActionConflict}.get(code, ActionError)
                raise cls(f"{spec.api_id} HTTP {code}" + (f" {err_code}" if err_code else ""),
                          api_id=spec.api_id, status=code, code=err_code, server_message=err_msg)
        finally:
            if spec.method == "POST":
                _invalidate_all_caches()  # 요청 중 동시에 채워진 GET 캐시도 버린다
            rec["ms"] = round((time.perf_counter() - t0) * 1000)
            self._emit(rec)

    # ───────── 명명 메서드 (API-01~40) ─────────
    async def get_product(self, sku): return await self.call("API-01", sku=sku)
    async def search_products(self, item): return await self.call("API-02", item=item)
    async def get_lot(self, lot_id): return await self.call("API-03", lot_id=lot_id)
    async def get_lot_investigation(self, lot_id): return await self.call("API-04", lot_id=lot_id)
    async def search_tickets_by_member(self, member_id): return await self.call("API-05", member_id=member_id)
    async def search_tickets_by_lot(self, lot_id): return await self.call("API-06", lot_id=lot_id)
    async def get_order(self, order_no): return await self.call("API-07", order_no=order_no)
    async def search_orders_by_member(self, member_id): return await self.call("API-08", member_id=member_id)
    async def search_orders_by_inflow_tag(self, inflow_tag): return await self.call("API-09", inflow_tag=inflow_tag)
    async def get_shipment(self, shipment_id): return await self.call("API-10", shipment_id=shipment_id)
    async def search_shipments(self, order_no): return await self.call("API-11", order_no=order_no)
    async def get_member(self, member_id): return await self.call("API-12", member_id=member_id)
    async def search_members_by_name(self, name): return await self.call("API-13", name=name)
    async def search_members_by_referrer(self, referred_by): return await self.call("API-14", referred_by=referred_by)
    async def search_point_entries(self, member_id): return await self.call("API-15", member_id=member_id)
    async def search_coupons(self, member_id): return await self.call("API-16", member_id=member_id)
    async def get_payment(self, approval_no): return await self.call("API-17", approval_no=approval_no)
    async def search_payments(self, order_no): return await self.call("API-18", order_no=order_no)
    async def get_subscription(self, subscription_id): return await self.call("API-19", subscription_id=subscription_id)
    async def get_promo(self, code): return await self.call("API-20", code=code)
    async def get_inventory(self, sku): return await self.call("API-21", sku=sku)
    async def request_restore(self, order_no): return await self.call("API-22", order_no=order_no)
    async def request_order_change(self, order_no, requested_items):
        return await self.call("API-23", order_no=order_no, requested_items=requested_items)
    async def request_address_change(self, order_no, new_address):
        return await self.call("API-24", order_no=order_no, new_address=new_address)
    async def request_schedule_change(self, order_no, requested_date):
        return await self.call("API-25", order_no=order_no, requested_date=requested_date)
    async def add_order_memo(self, order_no, memo): return await self.call("API-26", order_no=order_no, memo=memo)
    async def request_expedite(self, order_no, qty, reason):
        return await self.call("API-27", order_no=order_no, qty=qty, reason=reason)
    async def request_reship(self, shipment_id): return await self.call("API-28", shipment_id=shipment_id)
    async def create_refund(self, order_no, amount, reason):
        return await self.call("API-29", order_no=order_no, amount=amount, reason=reason)
    async def search_refunds(self, order_no): return await self.call("API-30", order_no=order_no)
    async def request_card_cancellation(self, approval_no): return await self.call("API-31", approval_no=approval_no)
    async def request_cash_receipt(self, approval_no, receipt_number):
        return await self.call("API-32", approval_no=approval_no, receipt_number=receipt_number)
    async def request_coupon_issue(self, member_id, promo_code):
        return await self.call("API-33", member_id=member_id, promo_code=promo_code)
    async def request_reward(self, member_id): return await self.call("API-34", member_id=member_id)
    async def create_escalation(self, lane, reason): return await self.call("API-35", lane=lane, reason=reason)
    async def get_escalation(self, escalation_id): return await self.call("API-36", escalation_id=escalation_id)
    async def request_reship_charge(self, shipment_id, charge_amount):
        return await self.call("API-37", shipment_id=shipment_id, charge_amount=charge_amount)
    async def request_pickup(self, order_no, qty, trigger, cost_bearer):
        return await self.call("API-38", order_no=order_no, qty=qty, trigger=trigger, cost_bearer=cost_bearer)
    async def request_restock_notification(self, sku): return await self.call("API-39", sku=sku)
    async def request_subscription_change(self, subscription_id, kind):
        return await self.call("API-40", subscription_id=subscription_id, kind=kind)


def _err(resp: httpx.Response) -> tuple[str | None, str | None]:
    if not resp.content:
        return None, None
    try:
        j = resp.json()
        if isinstance(j, dict):
            return j.get("code"), j.get("message")
    except Exception:
        pass
    return None, None


def _retry_after(resp: httpx.Response) -> float:
    try:
        return max(0.0, float(resp.headers.get("Retry-After", "1")))
    except ValueError:
        return 1.0


def call_sync(tc_id: str, api_id: str, **args: Any) -> Any:
    """동기 편의 함수(스크립트·테스트용)."""

    async def _run():
        try:
            return await ActionClient(tc_id).call(api_id, **args)
        finally:
            await aclose_all()

    return asyncio.run(_run())
