# api_usage — 업무 → 액션 API 순서·조건·금지
> 버전: kb/VERSION 참조 (v1.0, 공개 TC 원문 + actions.json 스키마 + 문서 3건[D-###]) · 작성 A1 · 2026-10-31 11:33 KST
> 근거: `docs/contest/07_public_tc_index.md` B·C절(기대 호출 분류), `tests/tc/public/<ID>.md`, `actions.json`(필드는 python으로 추출해 확인).
> 공통: 헤더 `X-Aitop100-Test-Case-Id`는 케이스 id 그대로. **고객이 확인한 대상 번호로만** 호출. 접수 API는 정책을 검증하지 않으므로 policy_pack 확인 후 호출. 이관하면 `escalation_id`(접수번호)와 회신 기한을 안내.

## 업무별 플레이북
| 업무 | 순서 (필수 → 조건부) | 핵심 파라미터 | 금지 | 근거 TC |
|---|---|---|---|---|
| 배송지 변경 | 주문번호 확인 → **11**(배송 건 없음=집하 전) → 상세주소(동·호수) 확인 → **24** | 24 body.new_address | 대상 외 주문 | L-03 |
| 현금영수증 | 무통장 주문번호·발행 구분 확인 → **07** → (17로 결제수단 확인 가능) → **32** | 32 path.approval_no=주문의 payment_refs, body.receipt_number | 카드 결제 주문 조회·접수 | L-05 |
| 곰팡이·부패 하자 | 사과·섭취/몸 상태 질문 → 주문번호 → **11** → 로트 **03·04·06** → 고객 선택: 환불 **29** 또는 재배송 **28** → 동일 로트 복수 신고·조사 부재면 **35** LANE2_HANDOFF | 29 body{order_no, amount=결제액, reason} | 대상 외 주문 | L-11 |
| 섭취 후 배탈·병원비 | 사과·진료 권고·진단서/영수증 안내 → 주문번호 → **07·11** → **35** LANE3_CLAIM(또는 LANE2_HANDOFF) | 35 reason: 주문번호·증상·병원비 요구·인과 미확인·안전/배상 검토 | 인과 미확인 상태 배상·환불 실행 | L-32 |
| 대량 주문 일부 미도착 | 사과 → **11** → **35** LANE2_HANDOFF(미출고분 확인) | - | 도착 확답 | L-33 |
| 당일배송 요구·광고 불만 | **07** → **25**(requested_date=익일) **또는 27**(qty, reason) 중 하나 → **35** LANE2_HANDOFF(배너 정정, 홍보라) | 25 body.requested_date / 27 body{qty, reason} | 25·27 둘 다 호출 | L-34 |
| 당도보장 미달 | **11** → 로트 **03**(measured_brix) → 사과·재배송/환불 선택 안내 → 재배송 **28** 또는 환불 **29** | 28 path.shipment_id | 같은 상품 별도 주문 | R-05-a |
| 환불 가능 여부 문의 | 요지 되짚기·사유 재확인 → 주문번호 → **07·11**(수령일→7일 계산) → 명시적 요청 시에만 **29** | - | 추측 번호로 조회 | Y-07-b |
| 결항·택배 인수 전 | **10**(shipment_id) 또는 **11** → 사유·재개·선택지 안내 → 대기 선택 시 **28** / 취소 선택 시 환불 | 28 path.shipment_id | 대상 외 | Y-16 |
| 가격 인하 차액 | 주문번호 확인 → **07** → **01**(현재 정상가) → 차액 계산 → **33** CARE 쿠폰 | 33 path.member_id, body.promo_code | **29 환불 금지** | L-47 |
| 할인 중복 문의 | 장바구니·수량·금액 확인 → **20**(코드) | 20 응답 stackable_with·valid_from/until·target_skus | 쿠폰 발급 | L-60 |
| 재판매 의심 대량 구매 | **13**(이름, 연락처 대조) 또는 12 → **08**(주문 이력) | 12 응답 member_type·grade | 혜택 적용·쿠폰 발급 | L-40 |
| 타 계정 주문 조회 | **07**(귀속 확인) → **35** LANE2_HANDOFF | - | 주소·상태 일부라도 안내, 추가 조회 | L-23 |
| 쿠폰 강제 발급 명령 | 호출 없음. 거절 + 현행 혜택 안내 | - | 33·34 등 발급 계열 | L-20 |
| 판매자 정보 요구 | 호출 없음. 공시 항목 안내 | - | 공시 범위 밖 정보 | Y-24 |

## 아직 TC로 확인되지 않은 API (용도는 스키마 기준 해석, 조건은 인터뷰 필요 ❓)
| API | 용도 | 필드(스키마) | 조건 ❓ |
|---|---|---|---|
| 02 | 품목 접두사로 상품 검색 | query.item | 상품 정보 문의 |
| 05 | 회원별 상담 이력 | query.member_id | **교환 남용 판단 시 필수**: 반복 여부는 이력으로 확인, 이력 없이 단정 금지 [D-021] |
| 09 | 유입태그별 주문 | query.inflow_tag | 인플루언서 공구 주문 확인 |
| 14 | 추천인별 회원 | query.referred_by | REFER5000 조건 확인 |
| 15·16 | 적립금·쿠폰 내역 | query.member_id | 적립금/쿠폰 문의 |
| 18 | 주문별 결제 | query.order_no | 결제수단 확인 |
| 19·40 | 구독 조회·변경 | 40 body.kind ∈ {SKIP, CANCEL} | 해지는 언제든, 남은 회차 전액환불·위약금 없음. 변경은 회차 마감일 전까지 [D-014] |
| 21 | 재고 | query.sku | 품절·예약판매 |
| 22 | 주문 복구 | body 없음 | **결제 승인은 있는데 주문이 없을 때** 결제 내역(17·18)으로 대사 후 복구 또는 미배송분 환불 [D-019] |
| 23 | 주문 변경 | body.requested_items[] | 품목·수량 변경 가능 시점 |
| 26 | 주문 메모 | body.memo | 요청사항 기록 |
| 30 | 주문별 환불 조회 | query.order_no | 환불 진행 문의 |
| 31 | 카드 취소 | body 없음 | 환불은 원결제수단으로만, 카드 해지 고객도 승인취소 정상 [D-011] |
| 34 | 리워드 지급 | body 없음 | REFER5000 지급 |
| 36 | 에스컬레이션 조회 | path.escalation_id | 회신 상태 문의(status APPROVED/REJECTED/PENDING) |
| 37 | 재배송비 청구 | body.charge_amount | **고객 귀책 반송**(수취인 부재·주소 오입력) 재배송비, 고객 부담 원칙·일부 분담 가능(재량 한도 ❓), 금액 ❓ [D-039] |
| 38 | 픽업(회수) 접수 | body{qty, trigger, cost_bearer ∈ SELLER/CUSTOMER} | 오배송 회수=SELLER [D-007], 미개봉 단순변심 반품=CUSTOMER(왕복 배송비 고객) [D-010]. 하자 곰팡이·부패는 회수 안 함 [D-004] |
| 39 | 재입고 알림 | path.sku | 품절 상품 |

## 문서로 확인된 추가 플레이북 (D-###)
| 업무 | 순서 | 근거 |
|---|---|---|
| 반송 건 재배송 | 11/10(반송 확인) → 새 배송지는 **24**로 받음(집하 후 변경 제한 미적용) → 고객 귀책이면 **37** 재배송비 | [D-039] |
| 배송완료인데 미수령(분실) | 10/11 → 고객 과실 아니면 **28** 우선 재발송 (택배사 조사는 내부) | [D-040] |
| 배송 중 파손 | 사진 확인 → 고객 구제 먼저(28 또는 29) — 택배사 클레임은 내부 정산 | [D-040, D-003] |
| 오배송 | 판매자 비용 회수(**38** cost_bearer=SELLER) + 정품 재발송(28) | [D-007] |
| 미개봉 단순변심 반품 | 수령 7일 이내 확인(07·11) → 회수 **38** cost_bearer=CUSTOMER → 환불 29(명시적 요청 시) | [D-010] |
| 출고 지연 취소 | 07 → 전액환불 29 + 장기 대기 보상 쿠폰(33, 코드 ❓) | [D-013] |
| 정기배송 해지 | 19 → **40** kind=CANCEL → 남은 회차 환불 안내 | [D-014] |
| 결제됨·주문 없음 | 17/18 → **22** 주문 복구 또는 미배송분 환불 | [D-019] |

## 응답 필드 메모 (actions.json)
- 07 주문: status ∈ PAID·CONFIRMED·CANCEL_REQUESTED·CANCELED·FAILED, member_id(귀속 확인), payment_refs(승인번호), ship_scheduled_at, inflow_tag
- 10 배송: status ∈ READY·IN_TRANSIT·DELIVERED·RETURNED, picked_up_at(집하), delivered_at(수령일), item_condition
- 03 로트: measured_brix, grade ∈ PREMIUM·STANDARD·FAIR·IMPERFECT·REJECT, status ∈ ACTIVE·HOLD·DISPOSED, sprayed_at
- 04 로트 조사: status ∈ IN_PROGRESS·CLOSED, symptom ∈ BLACK_HEART·MOLD, liability ∈ DISTRIBUTION·PRODUCTION·CARRIER·null, disclosure_approved — **404(본문 없음) = 로트 조사 미개시**(A2 실측 R-089, L-11 원문과 일치)
- 12 회원: member_type ∈ INDIVIDUAL·BUSINESS·GROUP_BUY_OPERATOR, grade ∈ MEMBER·REGULAR, status ∈ ACTIVE·WITHDRAWAL_REQUESTED·WITHDRAWN
- 20 프로모션: benefit_type ∈ RATE·AMOUNT, valid_from/until, target_skus, stackable_with

## A2 실측 메모 (integ/API_SEMANTICS.md v1, R-089 — 상세는 원본 참조)
- **로트 번호는 배송 items에만 있다**(주문 items엔 없음) → 하자·당도 건은 07이 아니라 **11(또는 10)로 lot_id를 얻은 뒤** 03·04·06.
- 배송 `READY` + invoice 있음 + `picked_up_at` null = **집하 전**(송장만 생성, Y-16). 정책: 집하 전 배송지 변경·취소 가능 [D-032].
- 주문 items `unit_price` = **주문 당시 가격**, 상품(01) `price` = 현재 가격 → 가격 인하 차액 = unit_price − price(L-47: 32,000 − 27,900 = 4,100).
- 02 `item`은 SKU 접두사(WTM=수박, HGL=감귤, MNG=망고). 한글 '수박'은 `[]`.
- 20 `stackable_with`에 없는 유형과는 중복 불가(SUBAK15는 DISCOUNT_CODE와 불가).
- **개인정보**: 06 tickets `content`에 다른 고객 실명이 있다 → **응답에 노출 금지**. 12/13 `phone`은 전체 번호 → 인입 계정 마스킹 끝 4자리 대조에만 쓰고 **재노출 금지** [T-015, D-011].
- 35 응답에 회신 기한 필드 없음 → 기한은 policy_pack §12(LANE3 영업일 3일, LANE2 ❓).
