# API_SEMANTICS — 액션 API 응답 필드 의미 (A2-4 실측)

- 실측: 2026-10-31 11:36~11:40 KST, 공개 TC ID로 **GET만** 30건, 각 TC 원문의 대상 식별자(07 B절) 범위 안에서만 조회. 데이터는 reset 전 공유 상태라 다른 세션의 접수가 섞였을 수 있음.
- 원자료: `integ/logs/api_probe_20261031-113633.json`(29건, trace+응답), `integ/logs/api_probe_api02_WTM.json`(1건), `integ/logs/R_api07_L-23.json`. 재현: `uv run python -m integ.api_probe`.
- 지연(연습 서버, 로컬→서버): p50 180ms, 최대 383ms. 같은 TC 같은 GET은 ActionClient가 캐시하므로 0ms.
- 표기: **[사실]** 응답·스키마로 확인 / **[해석]** 사실에서 도출 / **[추정]** 근거 제한, 추가 확인 필요.

## 0. 호출 규약 핵심 (A3 도구 설계용)
| 항목 | 내용 | 근거 |
|---|---|---|
| 단건 없음 | 본문 없는 404 → ActionClient는 `None` 반환 | [사실] API-20 `NOPE-PROBE-0` 404, API-04 404 |
| 검색 없음 | `[]` | [사실] API-30·16·15·05·14 `[]` |
| **API-02 `item`** | **SKU 품목 접두사**다. 한글 품목명 아님. `item=수박` → `[]`, `item=WTM` → 수박 8종 | [사실] actions.json "SKU의 품목 접두사로 검색합니다"(예시 GAL), 실측 |
| SKU 접두사 | `WTM`=수박, `HGL`=하우스 감귤, `MNG`=애플망고 (관찰된 것만) | [사실] API-01·07·10 items |
| API-13 이름 | 한글 이름 그대로(URL 인코딩은 클라이언트가 처리) | [사실] `?name=도현우` → 1건 |
| 접수 후 변화 | 접수번호는 `orders.refund_ids`·`orders.change_request_ids`·`payments.cancellation_request_ids`에만 추가 | [사실] 06 응답 규약 |
| 접수 응답 | 모든 접수 응답 = `{<접수번호 필드>, <대상 식별자>, request_status:"SUBMITTED", requested_at}`. 접수번호 필드명: 대부분 `request_id`, API-26 `memo_id`, API-29 `refund_id`, API-35 `escalation_id` | [사실] actions.json *Receipt 스키마 |
| API-35 응답 | `escalation_id`·`request_status`·`requested_at`뿐 — **회신 기한 필드 없음**(기한은 KB에서) | [사실] EscalationsReceipt |

## 1. 주문 `Orders` (API-07 단건, API-08 회원별)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| `status` | enum `PAID`·`CONFIRMED`·`CANCEL_REQUESTED`·`CANCELED`·`FAILED` [사실] | 관찰 6건 모두 `PAID`(배송 완료 건 포함) |
| `amount` | 결제 총액(원). 상품가 합 + 배송비 등 포함 [해석] | 100100006: items 27,900 → amount 32,900(차 5,000 = 배송비로 **추정**) |
| `items[]` | `{sku, name, qty, unit_price}` — `unit_price`는 **주문 당시 가격** [사실] | L-47: 주문 unit_price 32,000 vs 현재 상품가 27,900 → 가격 인하 차액 근거 |
| `payment_refs[]` | 결제 승인번호 목록 → **API-17 path.approval_no** [사실] | `PAY-3706-0003` |
| `refund_ids[]`·`change_request_ids[]` | 접수 시 번호 추가(접수 이력 확인용) [사실] | 관찰 모두 `[]` |
| `ordered_at`·`status_changed_at` | ISO-8601 +09:00. `status_changed_at` null=최초 상태 유지 [해석] | |
| `ship_scheduled_at` | 출고 예정 시각(null=미정) [해석] | 관찰 모두 null |
| `inflow_tag` | 유입 태그 → API-09 검색 키 [사실]. 인플루언서·공구 코드 유입 판별용 [추정] | 관찰 모두 null |
| `failure_code` | `status=FAILED`일 때 사유 코드 [추정] | 관찰 null |
| `recipient_name`·`shipping_address` | 수령인·배송지(배송지 변경 전 현재값) [해석] | 동·호수까지 포함 |
| `member_id` | 주문 회원 → **인입 계정과 다르면 타 계정 주문**(L-23: 조회 결과 비노출·이관) [해석] | |

## 2. 배송 `Shipments` (API-10 단건, API-11 주문별)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| `status` | enum `READY`·`IN_TRANSIT`·`DELIVERED`·`RETURNED` [사실] | |
| API-11 `[]` | 배송 레코드 없음 = **아직 출고(집하) 전** [해석, A2 프롬프트 예시와 일치] | 이번 실측에선 미관찰 |
| `READY` + `invoice_no` 있음 + `picked_up_at` null | **송장은 발급됐으나 택배 인수(집하) 전** [해석] | Y-16 `SHP-100400017-01`(인입 06-06, 물류 결항 시나리오와 일치) |
| `DELIVERED` + `delivered_at` | 배송 완료 시각 → 수령일 기준 기간 계산(청약철회·하자 신고 기한) [해석] | R-05-a 06-25 14:00 |
| `items[]` | `{sku, qty, lot_id}` — **`lot_id`는 배송 품목에만 있다**(주문 items에는 없음) → API-03/04/06 path·query로 연결 [사실] | `KD-HGL-370624-03` |
| `carrier`·`invoice_no` | 택배사·송장번호 [사실] | `시원배송` |
| `delivered_location`·`item_condition`·`return_reason`·`ship_notice_sent_at` | 배송 위치·도착 상태·반송 사유·출고 알림 발송 시각 [추정: 이름 기반] | 관찰 모두 null |
| 배송 ID 형식 | `SHP-<주문번호>-<순번>` [사실] | 분할 배송이면 순번 증가 [추정] |

## 3. 로트 `Lots`(API-03) · 조사 `LotInvestigations`(API-04) · 상담 이력 `Tickets`(API-05/06)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| Lots `grade` | `PREMIUM`·`STANDARD`·`FAIR`·`IMPERFECT`·`REJECT` [사실] | |
| Lots `status` | `ACTIVE`·`HOLD`(출고 보류)·`DISPOSED`(폐기) [사실/해석] | 관찰 `ACTIVE` |
| Lots `packed_at`·`measured_weight_g`·`measured_brix`·`qty_in_stock`·`sprayed_at` | 포장일·실측 중량·당도·로트 잔여 재고·방제(농약 살포) 일시 [해석] | 수박 8,220g·11.2Brix, 감귤 5,140g·10.8 |
| **API-04 404** | **해당 로트 조사 기록 없음(조사 미개시)** [사실+해석] | L-11 `KD-WTM-370624-03` 404 ↔ 원문 "로트 조사는 열린 적이 없다" |
| LotInvestigations `status`·`symptom`·`liability` | `IN_PROGRESS`·`CLOSED` / `BLACK_HEART`·`MOLD` / `DISTRIBUTION`·`PRODUCTION`·`CARRIER`·null [사실: enum] | 응답 미관찰 |
| API-06 Tickets | 같은 로트의 앞선 상담 `{ticket_id, member_id, lot_id, created_at, content, handler}` → **동일 로트 복수 신고 판단** [사실] | L-11 로트에 `TICKET-00701`(06-26, 곰팡이) 1건 |
| 주의 | Tickets `content`에 **다른 고객 이름·내용**이 들어 있다 → 고객에게 그대로 노출 금지(개인정보) [해석] | "윤재호 고객 접수 — …" |

## 4. 결제 `Payments` (API-17 단건, API-18 주문별)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| `pay_method` | `BANK_TRANSFER`(무통장) 등 — 현금영수증(API-32) 대상 판단 [해석] | L-05 `BANK_TRANSFER` |
| `status` | `APPROVED`·`CANCELED` [사실] | |
| `cancellation_request_ids[]` | 카드 취소 접수번호(API-31 후 추가) [사실] | |
| `card_last4`·`payer_name` | 카드 끝 4자리·입금자명(무통장이면 card null) [해석] | null |

## 5. 상품·재고·프로모션 (API-01·02·21·20)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| Products `price` | **현재** 판매가 [해석] | WTM-STD-8 27,900 (주문 당시 32,000) |
| Products `sale_state` | `ON_SALE`·`PREORDER`·`SOLD_OUT`·`CLOSED` [사실] | WTM-RSV-12 `PREORDER` |
| Products `grade[]`·`listed_weight`·`variety`·`origin` | 출고 등급 범위·표기 중량('이상' 표기)·품종·산지 [해석] | `["STANDARD","FAIR"]`, "8kg 이상" |
| Inventory(API-21) | 배열 `[{sku, total_qty, sale_state}]` [사실] | WTM-STD-8 12개 |
| Promotions `benefit_type`·`benefit_value` | `RATE`(%)·`AMOUNT`(원) [사실] | SUBAK15 RATE 15, CARE5000 AMOUNT 5,000 |
| Promotions `valid_from`·`valid_until` | 유효기간(null=무기한) [해석] | SUBAK15 2037-06-26~07-03 |
| Promotions `target_skus` | 적용 SKU(null=전체) [해석] | SUBAK15 = 수박 8종 |
| Promotions `stackable_with` | 함께 쓸 수 있는 유형 `DISCOUNT_CODE`·`REWARD_COUPON`·`POINTS` — **목록에 없는 유형과는 중복 불가** [해석] | SUBAK15 = REWARD_COUPON·POINTS(→ 다른 할인코드와 중복 불가), CARE5000 = DISCOUNT_CODE·POINTS |

## 6. 회원·쿠폰·적립금 (API-12·13·14·15·16)
| 필드 | 의미 | 관찰값 |
|---|---|---|
| Members `member_type` | `INDIVIDUAL`·`BUSINESS`·`GROUP_BUY_OPERATOR` [사실] | |
| Members `grade` | `MEMBER`·`REGULAR`(단골) [사실/해석] | |
| Members `status` | `ACTIVE`·`WITHDRAWAL_REQUESTED`·`WITHDRAWN` [사실] | |
| Members `phone` | **전체 번호** — 인입 계정의 마스킹 번호(`019-****-7864`) 끝자리와 대조해 본인 확인 [해석]. 고객에게 전체 번호 재노출 금지 | L-40 끝 7864 일치 |
| Members `joined_at`·`referred_by_member_id` | 가입일·추천인 [사실] | L-40 가입 06-17 + 06-19·06-22 대량 주문(45·50통) → 재판매 정황 근거 [해석] |
| API-14 | 이 회원을 추천인으로 가입한 회원 목록 [해석] | `[]` |
| API-15·16 | 적립금 내역·보유 쿠폰 배열 [사실] | 관찰 `[]` |

## 7. 미관찰(추가 확인 필요)
- API-19 구독, API-36 에스컬레이션 조회(접수 후 ID 필요), API-09 유입태그 검색, API-04 조사 존재 응답 본문 — 공개 TC 대상 식별자가 없어 GET 실측 못 함.
- `Orders.status`가 배송 완료 후에도 `PAID`로 남는 것은 관찰 사실이나, `CONFIRMED`(구매확정) 전환 조건은 모름.
- 데이터는 reset 전 공유 상태이므로 `refund_ids` 등은 다른 세션의 접수에 따라 달라질 수 있음(A4 reset 후 재확인 권장).
