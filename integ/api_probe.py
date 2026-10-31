"""A2-4 API 의미 실측 — 공개 TC ID로 **GET만**, 각 TC의 원문 대상 식별자(07 B절) 범위에서만 조회한다.

실행: uv run python -m integ.api_probe  → integ/logs/api_probe_<ts>.json (trace + 응답 원문)
연쇄 조회(앞 응답에서 얻은 번호)는 같은 TC 대상의 연결 번호일 때만 한다(예: 배송 ID의 주문, 결제의 주문).
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from integ.action_client import ActionClient, ActionError, aclose_all

OUT = Path(__file__).resolve().parent / "logs"


async def probe() -> dict:
    out: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tcs": {}}
    allt: list = []

    async def run(tc: str, steps):
        tr: list = []
        ac = ActionClient(tc, trace=tr, trace_responses=True)
        res = {}
        ctx: dict = {}
        for label, fn in steps:
            try:
                r = await fn(ac, ctx)
                res[label] = r
            except ActionError as e:
                res[label] = {"__error__": type(e).__name__, "status": e.status, "code": e.code}
        out["tcs"][tc] = {"results": res, "trace": [{k: v for k, v in t.items() if k != "resp"} for t in tr]}
        allt.extend(tr)

    async def s_pay(ac, c):
        r = await ac.get_payment("PAY-3706-0003")
        c["order"] = (r or {}).get("order_no")
        return r

    async def s_pay_order(ac, c):
        return await ac.get_order(c["order"]) if c.get("order") else None

    async def s_pay_search(ac, c):
        return await ac.search_payments(c["order"]) if c.get("order") else None

    async def s_refunds(ac, c):
        return await ac.search_refunds(c["order"]) if c.get("order") else None

    await run("L-05", [("API-17 PAY-3706-0003", s_pay), ("API-07 결제의 주문", s_pay_order),
                       ("API-18 결제의 주문", s_pay_search), ("API-30 결제의 주문", s_refunds)])

    lot = "KD-WTM-370624-03"
    await run("L-11", [("API-03 " + lot, lambda ac, c: ac.get_lot(lot)),
                       ("API-04 " + lot, lambda ac, c: ac.get_lot_investigation(lot)),
                       ("API-06 " + lot, lambda ac, c: ac.search_tickets_by_lot(lot))])

    shp, odr, lot2 = "SHP-100300009-01", "100300009", "KD-HGL-370624-03"
    await run("R-05-a", [("API-10 " + shp, lambda ac, c: ac.get_shipment(shp)),
                         ("API-11 " + odr, lambda ac, c: ac.search_shipments(odr)),
                         ("API-07 " + odr, lambda ac, c: ac.get_order(odr)),
                         ("API-03 " + lot2, lambda ac, c: ac.get_lot(lot2))])

    shp3, odr3 = "SHP-100400017-01", "100400017"
    await run("Y-16", [("API-10 " + shp3, lambda ac, c: ac.get_shipment(shp3)),
                       ("API-11 " + odr3, lambda ac, c: ac.search_shipments(odr3)),
                       ("API-07 " + odr3, lambda ac, c: ac.get_order(odr3))])

    mb, sku = "MB-77017", "WTM-STD-8"
    await run("L-47", [("API-01 " + sku, lambda ac, c: ac.get_product(sku)),
                       ("API-21 " + sku, lambda ac, c: ac.get_inventory(sku)),
                       ("API-12 " + mb, lambda ac, c: ac.get_member(mb)),
                       ("API-16 " + mb, lambda ac, c: ac.search_coupons(mb)),
                       ("API-20 CARE5000", lambda ac, c: ac.get_promo("CARE5000")),
                       ("API-08 " + mb, lambda ac, c: ac.search_orders_by_member(mb))])

    mb2 = "MB-77016"
    await run("L-40", [("API-13 도현우", lambda ac, c: ac.search_members_by_name("도현우")),
                       ("API-12 " + mb2, lambda ac, c: ac.get_member(mb2)),
                       ("API-08 " + mb2, lambda ac, c: ac.search_orders_by_member(mb2)),
                       ("API-15 " + mb2, lambda ac, c: ac.search_point_entries(mb2)),
                       ("API-05 " + mb2, lambda ac, c: ac.search_tickets_by_member(mb2)),
                       ("API-14 " + mb2, lambda ac, c: ac.search_members_by_referrer(mb2))])

    await run("L-60", [("API-20 SUBAK15", lambda ac, c: ac.get_promo("SUBAK15")),
                       ("API-02 수박", lambda ac, c: ac.search_products("수박")),
                       ("API-20 없는코드(404 확인)", lambda ac, c: ac.get_promo("NOPE-PROBE-0"))])
    await aclose_all()
    out["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out["calls"] = sum(1 for t in allt if not t["cached"])
    out["ms"] = [t["ms"] for t in allt if not t["cached"]]
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res = asyncio.run(probe())
    p = OUT / f"api_probe_{time.strftime('%Y%m%d-%H%M%S')}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    ms = sorted(res["ms"])
    print(f"saved {p} calls={res['calls']} p50={ms[len(ms)//2]}ms max={ms[-1]}ms")
    for tc, v in res["tcs"].items():
        for t in v["trace"]:
            print(tc, t["api_id"], t["path"], t["status"], f"{t['ms']}ms")


if __name__ == "__main__":
    main()
