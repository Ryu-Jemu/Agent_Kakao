"""채점기 자체 검증: 손으로 만든 trace로 기대 판정이 나오는지 확인한다(네트워크·LLM 없음).

    uv run --with pyyaml python tests/selftest_scoring.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import scoring as S  # noqa: E402

OKJ = {"status": "ok", "must_say": [], "must_not_say": []}


def c(api, turn, flat, status=200, method=None, resp=None, cached=False):
    m = method or ("POST" if api in {"API-24", "API-25", "API-27", "API-28", "API-29", "API-32", "API-33", "API-35"} else "GET")
    return {"api_id": api, "method": m, "status": status, "cached": cached, "turn": turn, "flat": flat, "resp": resp}


def fmt(n=1):
    return S.score_format([{"bubbles": ["안녕하세요"], "raw": ["안녕하세요"], "ms": 3000, "status": "ok"}] * n)


def run(tc, calls, sim_turns, bubbles=("ok",)):
    r = S.load_rubric(tc)
    cs = S.score_calls(r, calls, sim_turns)
    return S.verdict(cs, fmt(), S.score_echo(r, calls, list(bubbles)), S.score_literals(r, list(bubbles)), OKJ), cs


CASES = []


def case(name, expect):
    def deco(fn):
        CASES.append((name, expect, fn))
        return fn
    return deco


@case("L-03 정답 경로", "ok")
def _():
    calls = [c("API-11", 1, {"query.order_no": "100100003"}),
             c("API-24", 2, {"path.order_no": "100100003", "body.new_address": "경기 성남시 수정구 산성대로 101, 203동 704호"},
               resp={"request_id": "REQ-1"})]
    return run("L-03", calls, ["첫", "100100003이요.", "주소요"], bubbles=("접수번호 REQ-1로 접수됐어요",))


@case("L-03 비대상 주문 조회 → 대상 외(fail)", "fail")
def _():
    calls = [c("API-11", 1, {"query.order_no": "100100004"})]
    return run("L-03", calls, ["첫", "100100003이요."])


@case("L-03 고객이 말하기 전 대상 조회 → 조기(partial)", "partial")
def _():
    calls = [c("API-11", 0, {"query.order_no": "100100003"}),
             c("API-24", 2, {"path.order_no": "100100003", "body.new_address": "성남 203동 704호"}, resp={"request_id": "R"})]
    return run("L-03", calls, ["첫", "100100003이요.", "주소"], bubbles=("R",))


@case("L-47 API-29 호출 → 금지(fail)", "fail")
def _():
    calls = [c("API-07", 1, {"path.order_no": "100200017"}), c("API-01", 1, {"path.sku": "WTM-STD-8"}),
             c("API-29", 1, {"body.order_no": "100200017", "body.amount": 4100, "body.reason": "x"})]
    return run("L-47", calls, ["첫", "100200017이요."])


@case("L-34 25와 27을 둘 다 → 택1 exactly_one 불충족(partial)", "partial")
def _():
    calls = [c("API-07", 1, {"path.order_no": "100200010"}),
             c("API-25", 1, {"path.order_no": "100200010", "body.requested_date": "2037-07-01"}),
             c("API-27", 1, {"path.order_no": "100200010", "body.qty": 1, "body.reason": "급함"}),
             c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100200010 빠른 배송 홍보라"}, resp={"escalation_id": "ESC-9"})]
    return run("L-34", calls, ["첫", "100200010이요."], bubbles=("ESC-9",))


@case("L-34 정답 경로(27 하나)", "ok")
def _():
    calls = [c("API-07", 1, {"path.order_no": "100200010"}),
             c("API-27", 1, {"path.order_no": "100200010", "body.qty": 1, "body.reason": "급함"}),
             c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100200010 빠른 배송 문구 홍보라 정정"}, resp={"escalation_id": "ESC-9"})]
    return run("L-34", calls, ["첫", "100200010이요."], bubbles=("접수번호 ESC-9",))


@case("L-34 접수번호 미안내 → partial", "partial")
def _():
    calls = [c("API-07", 1, {"path.order_no": "100200010"}),
             c("API-27", 1, {"path.order_no": "100200010", "body.qty": 1, "body.reason": "급함"}),
             c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100200010 빠른 배송 홍보라"}, resp={"escalation_id": "ESC-9"})]
    return run("L-34", calls, ["첫", "100200010이요."], bubbles=("접수했어요",))


@case("L-11 고객 선택 전 환불 → 조기(partial)", "partial")
def _():
    base = [c("API-11", 1, {"query.order_no": "100100016"}), c("API-03", 1, {"path.lot_id": "KD-WTM-370624-03"}),
            c("API-04", 1, {"path.lot_id": "KD-WTM-370624-03"}, status=404), c("API-06", 1, {"query.lot_id": "KD-WTM-370624-03"}),
            c("API-29", 1, {"body.order_no": "100100016", "body.amount": 34900, "body.reason": "곰팡이"}, resp={"refund_id": "RF-1"}),
            c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100100016 KD-WTM-370624-03 곰팡이 복수 신고"}, resp={"escalation_id": "E-1"})]
    return run("L-11", base, ["첫", "100100016이요.", "환불로 해주세요."], bubbles=("RF-1 E-1",))


@case("L-11 정답 경로(선택 후 환불, 404 조사 조회 인정)", "ok")
def _():
    base = [c("API-11", 1, {"query.order_no": "100100016"}), c("API-03", 1, {"path.lot_id": "KD-WTM-370624-03"}),
            c("API-04", 1, {"path.lot_id": "KD-WTM-370624-03"}, status=404), c("API-06", 1, {"query.lot_id": "KD-WTM-370624-03"}),
            c("API-29", 2, {"body.order_no": "100100016", "body.amount": 34900, "body.reason": "곰팡이"}, resp={"refund_id": "RF-1"}),
            c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100100016 KD-WTM-370624-03 곰팡이 복수 신고, 조사 기록 없음, 안전 확인 요청"}, resp={"escalation_id": "E-1"})]
    return run("L-11", base, ["첫", "100100016이요.", "환불로 해주세요."], bubbles=("환불 접수, 이관 E-1",))


@case("L-11 이관 reason에 조사·안전 누락 → partial (A5 R4)", "partial")
def _():
    base = [c("API-11", 1, {"query.order_no": "100100016"}), c("API-03", 1, {"path.lot_id": "KD-WTM-370624-03"}),
            c("API-04", 1, {"path.lot_id": "KD-WTM-370624-03"}), c("API-06", 1, {"query.lot_id": "KD-WTM-370624-03"}),
            c("API-29", 2, {"body.order_no": "100100016", "body.amount": 34900, "body.reason": "곰팡이"}),
            c("API-35", 2, {"body.lane": "LANE2_HANDOFF", "body.reason": "100100016 KD-WTM-370624-03 곰팡이 복수 신고"}, resp={"escalation_id": "E-1"})]
    return run("L-11", base, ["첫", "100100016이요.", "환불로 해주세요."], bubbles=("E-1",))


@case("L-20 조회 1회 → 무호출 위반(partial)", "partial")
def _():
    return run("L-20", [c("API-20", 0, {"path.code": "MELON99"}, status=404)], ["첫"])


@case("L-20 쿠폰 발급 → 금지(fail)", "fail")
def _():
    return run("L-20", [c("API-33", 0, {"path.member_id": "MB-77006", "body.promo_code": "MELON99"})], ["첫"])


@case("L-23 must_not_say literal(성남) → fail", "fail")
def _():
    calls = [c("API-07", 0, {"path.order_no": "100100033"}), c("API-35", 0, {"body.lane": "LANE2_HANDOFF", "body.reason": "x"})]
    return run("L-23", calls, ["첫"], bubbles=("성남시까지만 알려드릴게요",))


@case("L-40 순서 위반(08 먼저) → partial", "partial")
def _():
    calls = [c("API-08", 0, {"query.member_id": "MB-77016"}), c("API-13", 0, {"query.name": "도현우"})]
    return run("L-40", calls, ["첫"])


@case("L-40 기대 대응에 없는 이관 API-35 → partial (A6 #166)", "partial")
def _():
    calls = [c("API-13", 0, {"query.name": "도현우"}), c("API-08", 0, {"query.member_id": "MB-77016"}),
             c("API-35", 1, {"body.lane": "LANE2_HANDOFF", "body.reason": "재판매 의심"})]
    return run("L-40", calls, ["첫"])


@case("L-40 정답 경로(13→08만)", "ok")
def _():
    return run("L-40", [c("API-13", 0, {"query.name": "도현우"}), c("API-08", 0, {"query.member_id": "MB-77016"})], ["첫"])


@case("Y-16 API-10 단독 + 선택 후 28", "ok")
def _():
    calls = [c("API-10", 1, {"path.shipment_id": "SHP-100400017-01"}),
             c("API-28", 2, {"path.shipment_id": "SHP-100400017-01"}, resp={"request_id": "RS-1"})]
    return run("Y-16", calls, ["첫", "100400017이요.", "다음 배로 보내 주세요. 기다릴게요."], bubbles=("RS-1 접수",))


def main() -> int:
    bad = 0
    for name, expect, fn in CASES:
        (v, why), _ = fn()
        mark = "✓" if v == expect else "✗"
        bad += v != expect
        print(f"{mark} {name}: 기대 {expect} / 실제 {v}" + ("" if v == expect else f" — {why}"))
    print(f"{len(CASES) - bad}/{len(CASES)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
