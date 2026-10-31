"""ActionClient 자체 검증(네트워크 없음): 스펙↔actions.json 대조 + MockTransport 동작 검증.

실행: uv run python -m integ.selftest_action_client
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

from integ import action_client as ac

ROOT = Path(__file__).resolve().parent.parent
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def spec_vs_openapi() -> None:
    d = json.loads((ROOT / "actions.json").read_text())
    comps = d["components"]["schemas"]
    seen = set()
    for path, ops in d["paths"].items():
        for m, op in ops.items():
            if m not in ("get", "post"):
                continue
            oid = op["operationId"]
            key = "RESET" if oid == "resetMyActionData" else oid
            seen.add(key)
            s = ac.SPECS.get(key)
            if not s:
                check(f"spec:{oid}", False, "누락")
                continue
            ok = s.method == m.upper() and s.path == path
            pp = tuple(p["name"] for p in op.get("parameters", []) if p.get("in") == "path")
            qp = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"]
            ok &= pp == s.path_params and (qp[0] if qp else None) == s.query
            rb = op.get("requestBody")
            if rb:
                sch = rb["content"]["application/json"]["schema"]
                if "$ref" in sch:
                    sch = comps[sch["$ref"].split("/")[-1]]
                ok &= set(sch.get("properties", {})) == set(s.body)
                ok &= set(sch.get("required", [])) == set(s.required)
                for k, v in sch.get("properties", {}).items():
                    if "enum" in v:
                        ok &= s.body[k] == "enum:" + "|".join(v["enum"])
            else:
                ok &= not s.body
            check(f"spec:{oid}", ok, f"{s.method} {s.path}")
    check("spec:count", seen == set(ac.SPECS), f"openapi={len(seen)} specs={len(ac.SPECS)}")


def mock_handler_factory(log: list):
    def handler(req: httpx.Request) -> httpx.Response:
        log.append(req)
        p = req.url.raw_path.decode()
        if req.headers.get("X-Aitop100-Test-Case-Id") is None:
            return httpx.Response(400, json={"code": "MISSING_TEST_CASE_ID", "message": "x"})
        if p.startswith("/api/orders/NOPE"):
            return httpx.Response(404)
        if p.startswith("/api/orders/100"):
            return httpx.Response(200, json={"order_no": "100", "refund_ids": []})
        if p.startswith("/api/shipments?order_no="):
            return httpx.Response(200, json=[])
        if p.startswith("/api/members?name="):
            return httpx.Response(200, json=[{"name": "강은비"}])
        if p == "/api/refunds" and req.method == "POST":
            return httpx.Response(200, json={"refund_id": "RF-1"})
        if p.startswith("/api/flaky"):
            return httpx.Response(503)
        if p.startswith("/api/products/RATE"):
            n = sum(1 for r in log if r.url.raw_path.decode().startswith("/api/products/RATE"))
            if n == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={"code": "RATE_LIMIT_EXCEEDED", "message": "시간 창"})
            return httpx.Response(200, json={"sku": "RATE"})
        if p.startswith("/api/products/QUOTA"):
            return httpx.Response(429, json={"code": "RATE_LIMIT_EXCEEDED", "message": "누적 API 호출 한도를 초과했습니다."})
        if p.startswith("/api/products/S500"):
            n = sum(1 for r in log if r.url.raw_path.decode().startswith("/api/products/S500"))
            return httpx.Response(500) if n == 1 else httpx.Response(200, json={"sku": "S500"})
        if p.startswith("/api/products/S503"):
            return httpx.Response(503)
        if p.startswith("/api/products/BAD"):
            return httpx.Response(400)
        if p.startswith("/api/products/AUTH"):
            return httpx.Response(401, json={"code": "UNAUTHORIZED", "message": "x"})
        return httpx.Response(404)
    return handler


async def mock_behaviour() -> None:
    log: list[httpx.Request] = []
    loop = asyncio.get_running_loop()
    ac._HTTP[id(loop)] = httpx.AsyncClient(base_url="https://mock", transport=httpx.MockTransport(mock_handler_factory(log)))
    ac._RATE = ac._MemoryRate(1000)
    ac.ActionClient.clear_state()
    tr: list = []
    c = ac.ActionClient("L-11", trace=tr, token="t")

    # TC ID 사전 검증
    for bad in ["", "-x", "a" * 101, "가나", "L 11"]:
        try:
            ac.ActionClient(bad)
            check(f"tcid:{bad[:5]!r}", False)
        except ac.ActionValidationError:
            check(f"tcid:{bad[:5]!r}", True)
    check("tcid:ok", ac.ActionClient("Y-07-b") is not None)

    r = await c.get_order("100")
    check("get:200", r == {"order_no": "100", "refund_ids": []})
    hdr = log[-1].headers
    check("hdr:auth", hdr.get("Authorization") == "Bearer t" and hdr.get("X-Aitop100-Test-Case-Id") == "L-11")
    n = len(log)
    r2 = await c.get_order("100")
    check("cache:hit", r2 == r and len(log) == n and tr[-1]["cached"] is True)
    check("trace:keys", {"api_id", "method", "path", "params", "body", "status", "ms", "cached"} <= set(tr[-1]))
    check("404:None", await c.get_order("NOPE") is None)
    check("search:[]", await c.search_shipments("100") == [])
    await c.search_members_by_name("강은비")
    check("query:encoded", "%EA%B0%95" in log[-1].url.raw_path.decode())

    # 다른 인스턴스(같은 TC)도 캐시 공유, 다른 TC는 분리
    n = len(log)
    await ac.ActionClient("L-11", token="t").get_order("100")
    check("cache:shared-same-tc", len(log) == n)
    await ac.ActionClient("L-20", token="t").get_order("100")
    check("cache:separate-tc", len(log) == n + 1)

    # POST → 캐시 무효화
    rr = await c.create_refund("100", 1000, "곰팡이")
    check("post:200", rr == {"refund_id": "RF-1"} and log[-1].method == "POST"
          and json.loads(log[-1].content) == {"order_no": "100", "amount": 1000, "reason": "곰팡이"})
    n = len(log)
    await c.get_order("100")
    check("post:invalidate", len(log) == n + 1 and tr[-1]["cached"] is False)

    # 로컬 검증(호출 안 함)
    n = len(log)
    for name, coro in [
        ("val:missing", c.call("API-29", order_no="1", amount=1)),
        ("val:int", c.call("API-29", order_no="1", amount="천원", reason="r")),
        ("val:extra", c.call("API-35", lane="L", reason="r", foo=1)),
        ("val:enum", c.call("API-40", subscription_id="S", kind="PAUSE")),
        ("val:date", c.call("API-25", order_no="1", requested_date="7/1")),
        ("val:path", c.call("API-07", order_no="")),
        ("val:unknown", c.call("API-99")),
        ("val:reset", c.reset()),
    ]:
        try:
            await coro
            check(name, False, "예외 없음")
        except ac.ActionValidationError:
            check(name, True)
    check("val:no-network", len(log) == n)
    b = ac.ActionClient.build_body(ac.SPECS["API-38"], {"order_no": "1", "qty": "2", "trigger": "t", "cost_bearer": "seller"})
    check("val:coerce", b == {"qty": 2, "trigger": "t", "cost_bearer": "SELLER"})

    # 429 시간창 → 재시도 성공
    check("429:retry", await c.get_product("RATE") == {"sku": "RATE"})
    # 429 누적 → 재시도 없음
    n = len(log)
    try:
        await c.get_product("QUOTA")
        check("429:quota", False)
    except ac.ActionQuotaExhausted:
        check("429:quota", len(log) == n + 1)
    # 500 → 1회 재시도 성공, 503 지속 → 2회 후 예외
    check("500:retry", await c.get_product("S500") == {"sku": "S500"})
    n = len(log)
    try:
        await c.get_product("S503")
        check("503:raise", False)
    except ac.ActionServerError:
        check("503:raise", len(log) == n + 2)
    for name, sku, exc in [("400:raise", "BAD", ac.ActionBadRequest), ("401:raise", "AUTH", ac.ActionUnauthorized)]:
        try:
            await c.get_product(sku)
            check(name, False)
        except exc as e:
            check(name, True, f"code={e.code}")

    # 호출 상한
    ac.ActionClient.clear_state("CAP")
    cap = ac.ActionClient("CAP", token="t", max_calls=3)
    for i in range(3):
        await cap.get_product(f"P{i}")
    try:
        await cap.get_product("P9")
        check("cap:25", False)
    except ac.ActionCallLimitExceeded:
        check("cap:25", True)
    check("trace:no-token", all("t" != v for rec in tr for v in rec.values() if isinstance(v, str)) and
          not any("Bearer" in json.dumps(rec, ensure_ascii=False) for rec in tr))
    await ac.aclose_all()


async def file_rate() -> None:
    import tempfile
    import time as _t

    with tempfile.TemporaryDirectory() as d:
        fr = ac._FileRate(Path(d) / "r.json", limit=3, window=1.0)
        t0 = _t.time()
        for _ in range(4):
            await fr.acquire()
        el = _t.time() - t0
        check("filerate:waits", 0.8 < el < 2.0, f"{el:.2f}s")


def main() -> int:
    spec_vs_openapi()
    asyncio.run(mock_behaviour())
    asyncio.run(file_rate())
    bad = [r for r in results if not r[1]]
    for n, ok, d in results:
        if not ok:
            print("FAIL", n, d)
    print(f"{len(results) - len(bad)}/{len(results)} PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
