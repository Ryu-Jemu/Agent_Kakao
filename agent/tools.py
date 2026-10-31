"""C2(ActionClient)를 감싼 Gemini function declarations + 가드(A3_BRAIN 설계 4).

가드(코드로 강제, 프롬프트와 이중화):
- 대상 확인: 주문번호는 고객이 대화에서 직접 말한 것만. 배송·결제·로트 ID는 고객이 말했거나 허용된 주문의 조회 결과에서 나온 것만.
- 회원: member_id 계열은 인입 계정(API-13 이름 검색 + 전화 끝 4자리 대조)으로 확정한 회원만. API-13은 인입 이름으로만.
- 소유: API-07 결과의 member_id가 인입 회원과 다르면 내용을 숨기고 NOT_OWNER만 돌려준다(L-23).
- 이관(API-35): 세션당 같은 이슈 1회. 별개 이슈일 때만 separate_issue=true로 1회 더.
- 쿠폰(API-33): 고객이 제시한 코드는 API-20으로 등록 확인된 경우에만.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from agent import dates
from agent.session import Session

try:
    from integ.action_client import SPECS, ActionClient, ActionError
except Exception:  # pragma: no cover - integ 미배포 환경
    SPECS, ActionClient, ActionError = {}, None, Exception

# api_id → (함수 이름, 설명)
TOOL_INFO: dict[str, tuple[str, str]] = {
    "API-01": ("get_product", "상품 조회: 상품명·원산지·품종·중량·등급·현재 판매가(price)·판매상태."),
    "API-02": ("search_products", "SKU 접두사로 상품 목록 검색: item=WTM(수박)·HGL(감귤)·MNG(망고) 등. 한글 품목명은 결과가 비어 있다(integ/API_SEMANTICS ①)."),
    "API-03": ("get_lot", "로트(출고 묶음) 조회: 포장일·측정 중량·측정 당도(measured_brix)·등급·상태·방제일. lot_id는 배송 조회 결과 items[].lot_id."),
    "API-04": ("get_lot_investigation", "로트 조사 기록 조회(상태·증상·책임·결론). found=false면 조사 기록이 없는 것."),
    "API-05": ("search_tickets_by_member", "인입 회원의 과거 상담 이력 검색(과거 약속·보상 이력 확인용)."),
    "API-06": ("search_tickets_by_lot", "같은 로트에 대한 상담·신고 이력 건수 확인(동일 로트 복수 신고 여부). 다른 고객 정보는 비공개로 건수·날짜만 돌려준다."),
    "API-07": ("get_order", "주문 조회: 회원·주문상태·주문일·결제금액(amount)·수령인·배송지·결제승인번호(payment_refs)·품목(sku·단가)·출고예정일."),
    "API-08": ("search_orders_by_member", "인입 회원의 주문 이력 검색. 반복 구매 등 이력 판단이 정책상 필요할 때만 쓴다. 대상 주문을 찾으려고 쓰지 말고 주문번호는 고객에게 묻는다."),
    "API-09": ("search_orders_by_inflow_tag", "유입태그(인플루언서·제휴 코드 등)별 주문 검색."),
    "API-10": ("get_shipment", "배송 건 조회(shipment_id): 상태 READY/IN_TRANSIT/DELIVERED/RETURNED·택배사·송장·집하/배송완료 시각·물품 상태·로트."),
    "API-11": ("search_shipments_by_order", "주문의 배송 건 목록 조회. 빈 목록이면 배송 건이 아직 없는 것(집하 전)."),
    "API-12": ("get_member", "조합원 조회(인입 회원 본인만). 회원 유형·등급 판단이 필요할 때만."),
    "API-13": ("search_members_by_name", "이름으로 조합원 검색 — 인입 계정 이름으로만 가능, 전화 끝 4자리로 본인 회원ID를 확정한다. 회원별 판단(반복 구매·도매 여부, 회원 보유 혜택)이 필요할 때만 쓴다."),
    "API-14": ("search_members_by_referrer", "인입 회원이 추천한 조합원 목록(추천 리워드 확인용)."),
    "API-15": ("search_point_entries", "인입 회원의 적립금 내역."),
    "API-16": ("search_coupons", "인입 회원이 보유한 쿠폰 목록(발급·만료·사용 여부). 고객이 자기 보유 쿠폰을 물을 때만."),
    "API-17": ("get_payment", "결제 조회(approval_no): 결제수단(pay_method)·금액·결제일·상태·카드 끝자리."),
    "API-18": ("search_payments_by_order", "주문의 결제 목록 조회."),
    "API-19": ("get_subscription", "구독 조회."),
    "API-20": ("get_promo", "프로모션 코드 조회: 혜택(정률/정액)·유효기간·대상 SKU·함께 쓸 수 있는 코드(stackable_with). found=false면 등록되지 않은 코드. 고객이 특정 코드의 적용 조건·기간·중복을 물을 때만 쓴다(혜택 목록 안내·쿠폰 요구 거절에는 쓰지 않는다)."),
    "API-21": ("get_inventory", "SKU 재고·판매상태 조회."),
    "API-22": ("request_order_restore", "[접수] 주문 복구 요청."),
    "API-23": ("request_order_change", "[접수] 주문 품목 변경 요청. requested_items 예: ['WTM-STD-8 x1']."),
    "API-24": ("request_address_change", "[접수] 배송지 변경. new_address는 고객이 확인해 준 동·호수까지의 상세주소."),
    "API-25": ("request_schedule_change", "[접수] 출고/배송 일정 변경. requested_date=YYYY-MM-DD."),
    "API-26": ("add_order_memo", "[접수] 주문 메모 등록(배송 요청사항 등)."),
    "API-27": ("request_expedite", "[접수] 긴급 출고(출고 독촉) 요청. qty=수량, reason=사유."),
    "API-28": ("request_reship", "[접수] 배송 건 재배송(재출고) 요청. 하자 재배송·결항 후 차기 운송편 재출고 등."),
    "API-29": ("request_refund", "[접수] 환불 신청. order_no·amount(정책상 환불액, 원)·reason 필수. 고객이 환불을 명시적으로 선택했을 때만."),
    "API-30": ("search_refunds_by_order", "주문의 환불 신청 내역."),
    "API-31": ("request_card_cancellation", "[접수] 카드 결제 취소 요청(approval_no)."),
    "API-32": ("request_cash_receipt", "[접수] 현금영수증 발행 요청. approval_no=현금·계좌이체 결제의 승인번호, receipt_number=고객이 지정한 발행 번호."),
    "API-33": ("request_coupon_issue", "[접수] 인입 회원에게 등록된 프로모션/보상 쿠폰 발급 요청(promo_code). 임의·미등록 코드 금지."),
    "API-34": ("request_reward", "[접수] 인입 회원에게 리워드(추천 리워드 등) 지급 요청."),
    "API-35": ("escalate", "[접수] 담당자 이관(에스컬레이션). lane: LANE2_HANDOFF=담당자 확인·처리 이관(기본), LANE3_CLAIM=손해배상·클레임 정식 검토. 같은 이슈는 한 번만. "
               "reason은 다음 5요소를 모두 채운 한두 문장: [대상] 주문번호(관련 로트·배송 건 ID) / [사실] 조회 결과와 고객 진술 — 고객이 쓴 핵심 표현을 그대로(예: 곰팡이, 배탈, 병원비, 광고 문구 \"…\") / "
               "[고객 요청] 고객이 요구한 것(환불·배상·병원비·정정 등) / [미확인] 아직 확인 안 된 것(예: 하자와 증상의 인과관계 미확인, 조사 기록 없음) / [요청] 담당자(지식베이스의 담당자 이름)에게 확인·조치 요청 사항. 섭취 후 건강 이상 건은 '병원비(진료비) 배상 검토'와 '하자와 증상의 인과관계 미확인'을 반드시 넣는다."),
    "API-36": ("get_escalation", "이관 접수 건 조회(처리 상태)."),
    "API-37": ("request_reship_charge", "[접수] 재배송비 청구(charge_amount, 원)."),
    "API-38": ("request_pickup", "[접수] 회수(픽업) 요청. qty·trigger(사유)·cost_bearer(SELLER|CUSTOMER)."),
    "API-39": ("request_restock_notification", "[접수] 상품 재입고 알림 등록(sku)."),
    "API-40": ("request_subscription_change", "[접수] 구독 변경. kind=SKIP(이번 회차 건너뛰기)|CANCEL(해지)."),
}
NAME_TO_API = {v[0]: k for k, v in TOOL_INFO.items()}

# 이관 회신 기한(영업일). 근거: L-32 원문 "접수번호와 회신 기한(영업일 3일)"(kb T-010·T-012).
# LANE2_HANDOFF 값은 KB ❓(이민준 Q7 대기) → 확인 전에는 같은 3일을 쓴다(추정).
DEFAULT_REPLY_BUSINESS_DAYS = 3
LANE_REPLY_BUSINESS_DAYS = {"LANE3_CLAIM": 3, "LANE2_HANDOFF": 3}

ORDER_PARAM_APIS = {"API-07", "API-11", "API-18", "API-22", "API-23", "API-24", "API-25", "API-26", "API-27",
                    "API-29", "API-30", "API-38"}
MEMBER_PARAM = {"API-05": "member_id", "API-08": "member_id", "API-12": "member_id", "API-14": "referred_by",
                "API-15": "member_id", "API-16": "member_id", "API-33": "member_id", "API-34": "member_id"}
SHIPMENT_APIS = {"API-10", "API-28", "API-37"}
PAYMENT_APIS = {"API-17", "API-31", "API-32"}
LOT_APIS = {"API-03", "API-04", "API-06"}
SUB_APIS = {"API-19", "API-40"}

_EXTRA_PARAM_DESC = {
    "order_no": "고객이 확인해 준 주문번호(숫자)",
    "shipment_id": "배송 건 ID(예: SHP-...)",
    "approval_no": "결제 승인번호(예: PAY-...)",
    "lot_id": "로트 ID",
    "member_id": "인입 회원 ID(MB-...). 모르면 생략 가능 — 시스템이 인입 계정으로 채운다",
    "referred_by": "추천인 회원 ID(인입 회원). 모르면 생략 가능",
    "name": "인입 계정 이름",
    "requested_date": "YYYY-MM-DD",
    "amount": "환불 금액(원, 정수)",
    "reason": "사유(구체적으로)",
    "lane": "LANE2_HANDOFF 또는 LANE3_CLAIM",
    "receipt_number": "고객이 지정한 발행 번호 — 고객이 적은 형식 그대로(하이픈 포함, 예: 019-2314-9701)",
    "new_address": "고객이 확인해 준 상세주소 — 고객이 말한 표기 그대로",
}


def _schema_for(spec) -> dict:
    props: dict[str, Any] = {}
    req: list[str] = []
    for n in spec.path_params:
        props[n] = {"type": "string", "description": _EXTRA_PARAM_DESC.get(n, n)}
        req.append(n)
    if spec.query:
        props[spec.query] = {"type": "string", "description": _EXTRA_PARAM_DESC.get(spec.query, spec.query)}
        req.append(spec.query)
    for k, typ in spec.body.items():
        d = _EXTRA_PARAM_DESC.get(k, k)
        if typ == "int":
            props[k] = {"type": "integer", "description": d}
        elif typ == "list[str]":
            props[k] = {"type": "array", "items": {"type": "string"}, "description": d}
        elif typ.startswith("enum:"):
            props[k] = {"type": "string", "enum": typ[5:].split("|"), "description": d}
        else:
            props[k] = {"type": "string", "description": d}
        if k in spec.required:
            req.append(k)
    if spec.api_id in MEMBER_PARAM:  # 시스템이 채운다
        req = [r for r in req if r != MEMBER_PARAM[spec.api_id]]
    if spec.api_id == "API-35":
        props["separate_issue"] = {"type": "boolean",
                                   "description": "이미 이관한 건과 전혀 다른 별개 이슈일 때만 true"}
    return {"type": "object", "properties": props, "required": req}


def function_declarations() -> list[dict]:
    out = []
    for api_id, (fname, desc) in TOOL_INFO.items():
        spec = SPECS.get(api_id)
        if spec is None:
            continue
        out.append({"name": fname, "description": f"{api_id} {desc}", "parameters_json_schema": _schema_for(spec)})
    return out


def _digits(x: Any) -> str:
    return re.sub(r"\D", "", str(x or ""))


def _norm(x: Any) -> str:
    return str(x or "").strip().upper()


def _err(code: str, msg: str) -> dict:
    return {"ok": False, "error": code, "message": msg}


class ToolRunner:
    def __init__(self, s: Session, trace: list | None = None):
        self.s = s
        self.ac = None
        if ActionClient and s.tc_id:
            try:
                self.ac = ActionClient(s.tc_id, trace=trace if trace is not None else s.calls)
            except Exception:  # noqa: BLE001 — TC id 형식 오류 등 → 조회 없이 응대
                self.ac = None
        self._member_lock = asyncio.Lock()

    # ---- 인입 회원 확정(API-13 + 전화 끝 4자리) ----
    async def resolve_member(self) -> str | None:
        s = self.s
        async with self._member_lock:
            if s.member_lookup_done:
                return s.member_id
            s.member_lookup_done = True
            if not s.account_name:
                return None
            try:
                res = await self.ac.call("API-13", name=s.account_name) or []
            except ActionError:
                s.member_lookup_done = False
                return None
            cands = [m for m in res if isinstance(m, dict)]
            if s.phone_last4:
                cands = [m for m in cands if _digits(m.get("phone")).endswith(s.phone_last4)]
            if len(cands) == 1:
                s.member_id = cands[0].get("member_id")
                s.member_info = cands[0]
            return s.member_id

    # ---- 가드 ----
    def _allowed(self, kind: str, value: Any) -> bool:
        s = self.s
        v = _norm(value)
        if kind == "order":
            return _digits(v) in s.customer_ids or v in s.customer_ids
        return v in s.customer_ids or v in s.derived_ids.get(kind, set())

    async def _guard(self, api_id: str, args: dict) -> dict | None:
        s = self.s
        if api_id in ORDER_PARAM_APIS:
            o = args.get("order_no")
            if not self._allowed("order", o):
                return _err("NOT_CONFIRMED", f"주문번호 {o}는 고객이 대화에서 직접 확인해 준 번호가 아니다. 고객에게 대상 주문번호를 물어 확인받은 뒤 호출하라(추측·다른 주문 조회 금지).")
            if _digits(o) in s.foreign_orders:
                return _err("NOT_OWNER", "인입 계정의 주문이 아니다. 이 주문에 대해 더 조회·접수·안내하지 말라.")
        if api_id in SHIPMENT_APIS and not self._allowed("shipment", args.get("shipment_id")):
            return _err("NOT_CONFIRMED", "이 배송 건은 확인된 대상 주문의 배송 조회 결과에 없다. 먼저 고객이 확인해 준 주문으로 search_shipments_by_order를 조회하라.")
        if api_id in PAYMENT_APIS and not self._allowed("payment", args.get("approval_no")):
            return _err("NOT_CONFIRMED", "이 결제 승인번호는 확인된 대상 주문의 payment_refs에 없다. 먼저 대상 주문을 get_order로 조회하라.")
        if api_id in LOT_APIS and not self._allowed("lot", args.get("lot_id")):
            return _err("NOT_CONFIRMED", "이 로트는 확인된 대상 주문의 배송 조회 결과(items[].lot_id)에 없다. 먼저 대상 주문의 배송을 조회하라.")
        if api_id in SUB_APIS and not self._allowed("subscription", args.get("subscription_id")):
            return _err("NOT_CONFIRMED", "고객이 확인해 준 구독 ID가 아니다. 고객에게 확인받아라.")
        if api_id == "API-36" and not self._allowed("escalation", args.get("escalation_id")):
            return _err("NOT_CONFIRMED", "이 세션에서 접수한 이관 번호가 아니다.")
        if api_id == "API-13":
            if (args.get("name") or "").strip() != (s.account_name or ""):
                return _err("FORBIDDEN", "회원 검색은 인입 계정 본인 이름으로만 할 수 있다. 타인 정보는 조회·안내하지 않는다.")
        if api_id in MEMBER_PARAM:
            key = MEMBER_PARAM[api_id]
            mid = await self.resolve_member()
            if not mid:
                return _err("MEMBER_UNVERIFIED", "인입 계정(이름·전화 끝 4자리)으로 회원을 특정하지 못했다. 회원 정보 조회·접수를 하지 말고 필요하면 이관하라.")
            if args.get(key) and _norm(args.get(key)) != _norm(mid):
                return _err("FORBIDDEN", "인입 회원 본인이 아닌 회원ID다. 타인 정보는 조회·접수하지 않는다.")
            args[key] = mid
        if api_id == "API-33":
            code = _norm(args.get("promo_code"))
            st = s.promo_status.get(code)
            if st is False:
                return _err("UNREGISTERED_CODE", f"{code}는 등록되지 않은 코드다. 발급할 수 없다.")
            if code in s.customer_ids and st is not True:
                return _err("REFUSE", f"고객이 요구한 코드 {code}는 발급할 수 없다(봇은 진행 중 이벤트의 등록 코드를 정책 조건에 맞을 때만 발급). 조회·발급을 더 시도하지 말고 거절한 뒤 실제 받을 수 있는 혜택을 안내하라.")
        if api_id in ("API-24", "API-25", "API-27"):
            # 상태 전제 가드(T-003): 집하 후에는 배송지·출고일 변경·긴급 출고 불가(KB §6, 택배 계약서).
            ono = _digits(args.get("order_no"))
            ships = s.shipments_by_order.get(ono)
            if ships is None:
                return _err("CHECK_SHIPMENT_FIRST", "접수 전에 search_shipments_by_order로 이 주문의 집하 여부를 먼저 확인하라.")
            picked = [r for r in ships if isinstance(r, dict) and (r.get("picked_up_at") or r.get("status") in ("IN_TRANSIT", "DELIVERED", "RETURNED"))]
            if picked:
                return _err("ALREADY_PICKED_UP", "이 주문은 이미 택배사가 집하(인수)했다. 배송지·출고 일정 변경이나 긴급 출고를 접수할 수 없다. 접수하지 말고, 집하 후에는 변경이 불가하다는 점과 지식베이스의 대안을 안내하라.")
        # 식별자 원문 보존(D-012④, L-05): 고객이 쓴 번호를 모델이 정규화해 넘기면 고객 표기로 되돌린다.
        for key in ("receipt_number",):
            if args.get(key):
                raw = s.customer_raw.get(_digits(args[key]))
                if raw and raw != args[key]:
                    args[key] = raw
        if api_id == "API-32":
            pay = s.payment_cache.get(_norm(args.get("approval_no")))
            if pay and "카드" in str(pay.get("pay_method", "")) or (pay and "CARD" in str(pay.get("pay_method", "")).upper()):
                return _err("NOT_ELIGIBLE", "카드 결제는 현금영수증 발행 대상이 아니다. 접수하지 말고 현금·계좌이체 결제 주문인지 확인하라.")
        if api_id == "API-29":
            amt = args.get("amount")
            o = s.order_cache.get(_digits(args.get("order_no")))
            if isinstance(amt, (int, float)) and o and isinstance(o.get("amount"), int) and amt > o["amount"]:
                return _err("AMOUNT_EXCEEDS", f"환불액 {amt}원이 주문 결제금액 {o['amount']}원을 넘는다.")
        if api_id == "API-35":
            sep = bool(args.pop("separate_issue", False))
            if s.escalations and (not sep or len(s.escalations) >= 2):
                first = s.escalations[0]
                return {"ok": True, "already_escalated": True, "escalation_id": first.get("escalation_id"),
                        "reply_due": first.get("reply_due"),
                        "message": "이 상담에서 이미 담당자 이관이 접수돼 있다(같은 이슈 재접수 금지). 기존 접수번호로 안내하라."}
        return None

    # ---- 실행 ----
    async def run(self, fname: str, args: dict) -> dict:
        s = self.s
        api_id = NAME_TO_API.get(fname)
        if not api_id:
            return _err("UNKNOWN_TOOL", fname)
        if not self.ac:
            return _err("NO_CASE", "케이스 정보(TC id)가 없어 조회·접수를 할 수 없다. 고객에게 필요한 정보만 묻고 조회 없이 응대하라.")
        args = {k: v for k, v in (args or {}).items() if v is not None}
        if "order_no" in args:
            args["order_no"] = _digits(args["order_no"]) or args["order_no"]
        blocked = await self._guard(api_id, args)
        if blocked is not None:
            s.blocked.append({"api_id": api_id, "args": args, "why": blocked.get("error")})
            return blocked
        try:
            data = await self.ac.call(api_id, **args)
        except ActionError as e:
            return _err(type(e).__name__, str(e)[:200])
        except Exception as e:  # noqa: BLE001
            return _err("CALL_FAILED", f"{type(e).__name__}")
        return await self._post(api_id, args, data)

    async def _post(self, api_id: str, args: dict, data: Any) -> dict:
        s = self.s
        now = s.now
        if data is None:
            if api_id == "API-20":
                s.promo_status[_norm(args.get("code"))] = False
            return {"ok": True, "found": False, "note": "대상 없음(404). 번호를 고객에게 다시 확인하라." if api_id in ORDER_PARAM_APIS else "기록 없음"}
        out: dict[str, Any] = {"ok": True}
        if api_id == "API-07" and isinstance(data, dict):
            ono = _digits(data.get("order_no"))
            owner = data.get("member_id")
            mine = None
            if s.member_id:
                mine = owner == s.member_id
            elif s.account_name and data.get("recipient_name") == s.account_name:
                mine = True
            else:
                mid = await self.resolve_member()
                mine = (owner == mid) if mid else None
            if mine is False:
                s.foreign_orders.add(ono)
                return {"ok": True, "ownership": "NOT_OWNER",
                        "message": "이 주문은 인입 계정이 아닌 다른 회원의 주문이다. 주문 내용(배송 상태·수령인·주소 일부 포함)을 절대 안내하지 말고, 본인 주문만 안내 가능하다고 설명한 뒤 escalate(LANE2_HANDOFF)로 담당자 확인을 접수하라."}
            s.order_cache[ono] = data
            for ref in data.get("payment_refs") or []:
                s.derived_ids["payment"].add(_norm(ref))
            out["ownership"] = "OWNER" if mine else "UNVERIFIED"
            notes = [dates.elapsed_note(data.get("ordered_at"), now, "주문일")]
            if data.get("ship_scheduled_at"):
                notes.append(f"출고예정일 {dates.iso_ko(data['ship_scheduled_at'])}")
            out["date_notes"] = [n for n in notes if n]
        if api_id in ("API-11", "API-10"):
            rows = data if isinstance(data, list) else [data]
            if api_id == "API-11":
                s.shipments_by_order[_digits(args.get("order_no"))] = [r for r in rows if isinstance(r, dict)]
            else:
                for r in rows:
                    if isinstance(r, dict) and r.get("order_no"):
                        cur = [x for x in s.shipments_by_order.get(_digits(r["order_no"]), []) if x.get("shipment_id") != r.get("shipment_id")]
                        s.shipments_by_order[_digits(r["order_no"])] = cur + [r]
            notes = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                s.derived_ids["shipment"].add(_norm(r.get("shipment_id")))
                for it in r.get("items") or []:
                    if it.get("lot_id"):
                        s.derived_ids["lot"].add(_norm(it["lot_id"]))
                for k, label in (("picked_up_at", "집하"), ("delivered_at", "배송완료(수령)"), ("ship_notice_sent_at", "송장 알림")):
                    n = dates.elapsed_note(r.get(k), now, f"{r.get('shipment_id')} {label}")
                    if n:
                        notes.append(n)
            if not rows:
                out["note"] = "이 주문에 배송 건이 아직 없다 = 택배사 집하 전."
            if notes:
                out["date_notes"] = notes
        if api_id == "API-18" and isinstance(data, list):
            for r in data:
                if isinstance(r, dict) and r.get("approval_no"):
                    s.derived_ids["payment"].add(_norm(r["approval_no"]))
                    s.payment_cache[_norm(r["approval_no"])] = r
        if api_id == "API-17" and isinstance(data, dict) and data.get("approval_no"):
            s.payment_cache[_norm(data["approval_no"])] = data
        if api_id == "API-03" and isinstance(data, dict) and data.get("packed_at"):
            out["date_notes"] = [dates.elapsed_note(data["packed_at"], now, "포장일")]
        if api_id == "API-01" and isinstance(data, dict) and isinstance(data.get("price"), int):
            cmp = []
            for ono, o in s.order_cache.items():
                for it in o.get("items") or []:
                    if it.get("sku") == data.get("sku") and isinstance(it.get("unit_price"), int):
                        cmp.append({"order_no": ono, "paid_unit_price": it["unit_price"], "current_price": data["price"],
                                    "diff_per_unit": it["unit_price"] - data["price"], "qty": it.get("qty"),
                                    "ordered": dates.elapsed_note(o.get("ordered_at"), now, "주문일")})
            if cmp:
                out["price_compare"] = cmp
        if api_id == "API-06" and isinstance(data, list):
            # tickets.content에 타 고객 실명이 들어 있다(API_SEMANTICS ③) → 건수·날짜·본인 여부만 넘긴다.
            mine = [r for r in data if isinstance(r, dict) and s.member_id and r.get("member_id") == s.member_id]
            return {"ok": True, "lot_id": args.get("lot_id"), "ticket_count": len(data),
                    "others_count": len(data) - len(mine),
                    "created_dates": sorted({str(r.get("created_at", ""))[:10] for r in data if isinstance(r, dict)}),
                    "note": "다른 고객의 신원·연락처·신고 내용은 고객에게 절대 말하지 않는다(건수 수준으로만)."}
        if api_id in ("API-12", "API-14") and data:
            rows = data if isinstance(data, list) else [data]
            for r in rows:
                if isinstance(r, dict) and r.get("phone"):
                    r["phone"] = "***-****-" + _digits(r["phone"])[-4:]
        if api_id == "API-20":
            s.promo_status[_norm(args.get("code"))] = True
        if api_id == "API-13":
            return {"ok": True, "member_id": s.member_id,
                    "verified": bool(s.member_id), "note": "인입 계정(이름+전화 끝 4자리)과 일치하는 회원만 표시"}
        if api_id == "API-35" and isinstance(data, dict):
            rec = dict(data)
            bd = LANE_REPLY_BUSINESS_DAYS.get(_norm(args.get("lane")), DEFAULT_REPLY_BUSINESS_DAYS)
            rec["reply_due"] = dates.ko(dates.add_business_days(now, bd))
            s.escalations.append(rec)
            s.derived_ids["escalation"].add(_norm(data.get("escalation_id")))
            out["reply_due"] = f"영업일 {bd}일 이내, {rec['reply_due']}까지"
        if TOOL_INFO.get(api_id, ("", ""))[1].startswith("[접수]") and isinstance(data, dict):
            s.receipts.append({"api_id": api_id, **data})
        out["data"] = data
        return out
