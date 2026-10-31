# 06 액션 API 서술부 원문 + 엔드포인트 표
> 읽기 전용(R1). 원문: `actions.json`의 `info.description` 그대로 (sha256 20082b8f76e41f5d…). `actions.json`=`actions.yaml`=대회정보 [9] 동일(F10). 스키마 세부는 `actions.json`을 jq/python으로 필요한 부분만 조회한다(전체 278KB, 통독 금지).
> 서버: https://gyodong-mall-action.aitop100.org · 인증: `Authorization: Bearer $AI_CS_AGENT` · 필수 헤더: `X-Aitop100-Test-Case-Id` (패턴 `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`)
> 주의: 검색 API 경로 키에 쿼리가 포함됨(예: `/api/products?item=`) → URL을 직접 조립한다.

## 서술부 원문
에이전트가 고객 문의를 처리하면서 주문·배송·결제·상품·프로모션·조합원 정보를 조회하고, 환불 신청이나 배송지 변경 같은 요청을 접수하는 API입니다.

## 시작하기

처음이라면 공개 TC 하나를 골라 조회 API부터 호출해 보세요.

1. 액션 토큰을 준비합니다. 참가 동의 후 받은 토큰으로, `aitop100_`로 시작합니다. 홈페이지에서 다시 조회할 수 있습니다.
2. 상단 공개 TC 탭에서 고객 문의 사례(TC)를 하나 고르고 TC ID를 확인합니다. 사례마다 고객 질문과 모범 처리 과정이 있어, 어떤 API를 어떤 순서로 부르는지 참고할 수 있습니다. 평가가 시작되기 전에는 공개 TC의 ID만 쓸 수 있습니다.
3. 헤더 두 개를 붙여 호출합니다. 이 화면에서는 인증 입력란에 `Bearer ` 없이 토큰만 넣고, TC ID는 각 API의 `X-Aitop100-Test-Case-Id` 입력란에 넣습니다. 공개 TC 사례 화면에서 사례에 나온 액션의 링크로 열면 TC ID가 미리 채워져 있습니다.

```http
GET /api/orders/{order_no}
Authorization: Bearer <액션 토큰>
X-Aitop100-Test-Case-Id: <TC ID>
```

호출은 API 사용 기간에만 할 수 있습니다. 평가 때는 공개·비공개 TC 모두 대화에서 전달받은 TC ID를 넣고, 한 TC를 처리하는 동안에는 같은 ID를 유지합니다.

조회 API에 미리 채운 예시 값은 처음 상태의 데이터에서 가져온 값입니다. 그대로 보내 응답 형식부터 확인해 보세요.

## 연습과 평가

최종 제출 전이거나 평가가 시작되기 전의 호출은 연습 호출입니다. 연습 호출은 평가에 반영되지 않으며, 데이터와 응답 형식은 평가 때와 같습니다. 최종 제출 뒤 평가가 시작되면 그때부터의 호출을 평가 호출로 셉니다. 토큰은 연습과 평가에 같은 것을 씁니다.

- 호출 한도: 연습 호출에도 평가와 같은 시간 창 호출 한도가 적용되며, 평가 호출과 따로 셉니다. 평가 호출에는 누적 호출 한도도 적용됩니다.
- 데이터: 본인 데이터는 모든 TC가 함께 씁니다. 한 TC에서 접수한 요청은 초기화하기 전까지 남아, 다른 TC를 연습할 때 조회 결과에도 나타납니다.
- 초기화: 처음 상태에서 다시 연습하려면 `POST /api/action-data/reset`을 호출하세요. 최종 제출 후나 평가 시작 시각부터는 초기화할 수 없습니다.
- 평가 시작: 첫 평가 호출 전에 본인 데이터가 자동으로 처음 상태로 돌아갑니다. 따로 초기화하지 않아도 됩니다.

## 호출 한도

### 대회 진행 중

최종 제출 전이거나, 제출했어도 평가가 시작되기 전의 연습 호출입니다.

- 60초마다 최대 100번 호출할 수 있습니다.
- 누적 한도는 없습니다.

### 대회 제출 후

최종 제출 뒤 평가가 시작되면 평가 호출로 셉니다.

- 60초마다 최대 100번 호출할 수 있습니다. 대회 진행 중 호출과 따로 셉니다.
- 평가 호출은 모두 합쳐 최대 3,000번입니다. 넘으면 기다려도 풀리지 않습니다.

한도를 넘으면 `429`를 받습니다. 시간 창 한도는 `Retry-After` 헤더의 초만큼 기다리면 풀리므로, 에이전트가 그만큼 기다린 뒤 다시 보내게 하세요. 본문 없는 `400`·`404`를 받은 호출과 같은 조회를 다시 보낸 호출도 한 번씩 호출 한도에 들어갑니다. 적힌 값은 이 문서를 내려받은 시점의 한도이며, 대회 진행 중 바뀔 수 있습니다.

## 응답 규약

### 조회

- 단건 조회는 객체, 검색은 배열을 반환합니다. 단건이 없으면 본문 없는 `404`, 검색 결과가 없으면 `[]`입니다.
- `/api` 아래에서 문서에 없는 경로나 메서드도 본문 없는 `404`입니다. 대상이 없다고 판단하기 전에 경로와 메서드를 확인하세요.
- 지원하지 않는 검색 파라미터와 요청 본문의 필드·필수값·타입·허용값 위반은 본문 없는 `400`입니다.

### 접수

- 접수 API는 요청을 기록만 합니다. 정책을 적용하거나 주문·결제 등 데이터의 상태·금액을 바꾸지 않으므로, 정책에 어긋나는 요청도 그대로 접수됩니다. 호출 전에 정책을 확인하세요.
- 같은 접수 API로 같은 대상에 다시 접수하면 본문이 달라도 같은 접수번호를 반환하고, 접수 내용은 마지막 요청 본문으로 바뀝니다.
  - 대상이 없는 에스컬레이션은 본문으로 접수번호를 정합니다. 같은 본문을 다시 보내면 같은 접수번호를 반환합니다.
- 접수 후 다시 조회하면 아래 필드에만 접수번호가 추가됩니다.
  - `orders.refund_ids`
  - `orders.change_request_ids`
  - `payments.cancellation_request_ids`

## 오류가 났을 때

오류 응답은 대부분 `{code, message}` 본문으로 원인을 알려 줍니다. TC 헤더 오류를 뺀 `400`과 `404`는 본문이 없습니다. 상태 코드별 원인과 대처는 각 API의 응답 항목에도 있습니다.

- `400`과 `{code, message}`: TC 헤더 문제라 액션을 실행하지 않았습니다. 메시지는 코드마다 고정입니다.
  - `MISSING_TEST_CASE_ID`: 헤더가 없습니다.
  - `INVALID_TEST_CASE_ID`: 값이 비었거나, 헤더가 중복되거나, 형식이 틀리거나, 목록에 없는 ID입니다. 평가가 시작되기 전에는 공개 TC가 아닌 ID도 이 코드입니다.
- `401`: 토큰이 없거나 올바르지 않거나(`UNAUTHORIZED`), API 사용 기간이 아닙니다.
- `429`: 호출 한도를 넘었습니다. 메시지가 `누적 API 호출 한도를 초과했습니다.`이면 평가 누적 한도라 기다려도 풀리지 않습니다. 그 밖에는 `Retry-After` 헤더의 초만큼 기다린 뒤 다시 보내세요.
- `500`·`503`: 잠시 뒤 다시 요청하세요. 다시 보낸 접수 요청은 같은 접수번호를 반환합니다.

## 엔드포인트 41개
| operationId | 메서드 | 경로 | 요약 |
|---|---|---|---|
| API-01 | GET | `/api/products/{sku}` | 상품 조회 |
| API-02 | GET | `/api/products?item=` | 품목별 상품 검색 |
| API-03 | GET | `/api/lots/{lot_id}` | 로트 조회 |
| API-04 | GET | `/api/lots/{lot_id}/investigation` | 로트 조사 조회 |
| API-05 | GET | `/api/tickets?member_id=` | 회원별 상담 이력 검색 |
| API-06 | GET | `/api/tickets?lot_id=` | 로트별 상담 이력 검색 |
| API-07 | GET | `/api/orders/{order_no}` | 주문 조회 |
| API-08 | GET | `/api/orders?member_id=` | 회원별 주문 검색 |
| API-09 | GET | `/api/orders?inflow_tag=` | 유입태그별 주문 검색 |
| API-10 | GET | `/api/shipments/{shipment_id}` | 배송 조회 |
| API-11 | GET | `/api/shipments?order_no=` | 주문별 배송 검색 |
| API-12 | GET | `/api/members/{member_id}` | 조합원 조회 |
| API-13 | GET | `/api/members?name=` | 이름 조합원 검색 |
| API-14 | GET | `/api/members?referred_by=` | 추천인별 조합원 검색 |
| API-15 | GET | `/api/point-entries?member_id=` | 적립금 내역 검색 |
| API-16 | GET | `/api/coupons?member_id=` | 회원별 쿠폰 검색 |
| API-17 | GET | `/api/payments/{approval_no}` | 결제 조회 |
| API-18 | GET | `/api/payments?order_no=` | 주문별 결제 검색 |
| API-19 | GET | `/api/subscriptions/{subscription_id}` | 구독 조회 |
| API-20 | GET | `/api/promos/{code}` | 프로모션 조회 |
| API-21 | GET | `/api/inventory?sku=` | 재고 조회 |
| API-22 | POST | `/api/orders/{order_no}/restore-requests` | 주문 복구 접수 |
| API-23 | POST | `/api/orders/{order_no}/change-requests` | 주문 변경 접수 |
| API-24 | POST | `/api/orders/{order_no}/address-change-requests` | 배송지 변경 접수 |
| API-25 | POST | `/api/orders/{order_no}/schedule-change-requests` | 배송 일정 변경 접수 |
| API-26 | POST | `/api/orders/{order_no}/memos` | 주문 메모 접수 |
| API-27 | POST | `/api/orders/{order_no}/expedite-requests` | 긴급 출고 접수 |
| API-28 | POST | `/api/shipments/{shipment_id}/reship-requests` | 재배송 접수 |
| API-29 | POST | `/api/refunds` | 환불 신청 |
| API-30 | GET | `/api/refunds?order_no=` | 주문별 환불 검색 |
| API-31 | POST | `/api/payments/{approval_no}/cancellation-requests` | 카드 취소 접수 |
| API-32 | POST | `/api/payments/{approval_no}/cash-receipt-requests` | 현금영수증 발행 접수 |
| API-33 | POST | `/api/members/{member_id}/coupon-issue-requests` | 쿠폰 발급 접수 |
| API-34 | POST | `/api/members/{member_id}/reward-requests` | 리워드 지급 접수 |
| API-35 | POST | `/api/escalations` | 에스컬레이션 |
| API-36 | GET | `/api/escalations/{escalation_id}` | 에스컬레이션 조회 |
| API-37 | POST | `/api/shipments/{shipment_id}/reship-charge-requests` | 재배송비 청구 접수 |
| API-38 | POST | `/api/orders/{order_no}/pickup-requests` | 픽업 접수 |
| API-39 | POST | `/api/products/{sku}/restock-notification-requests` | 재입고 알림 등록 |
| API-40 | POST | `/api/subscriptions/{subscription_id}/change-requests` | 구독 변경 접수 |
| resetMyActionData | POST | `/api/action-data/reset` | 내 액션 데이터 전체 초기화 |
