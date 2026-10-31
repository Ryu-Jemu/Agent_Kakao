# tests/rubric — 공개 TC 루브릭 (A4-1)

정본은 `tests/tc/public/<ID>.md`의 **기대 대응**이다. `docs/contest/07` B절은 시드로만 썼다(R-013).
대상 주문·배송·승인번호는 R-018 GET 탐침(`tests/logs/customers.json`)으로 확인한 값이다.

## 필드
| 필드 | 뜻 | 채점 |
|---|---|---|
| `source.sha256` | 루브릭을 만든 원문 해시 | run.py가 현재 원문과 다르면 중단 |
| `scope` | 식별자별 허용 값(`re:` 접두는 정규식). 키가 있으면 그 식별자를 쓰는 모든 호출이 이 안이어야 한다 | 밖이면 `off_target` 위반 → fail |
| `confirm_before_call` | 고객이 대화에서 말한 뒤에만 써야 하는 식별자 | 먼저 쓰면 `premature` → partial |
| `calls.required` | 반드시 있어야 하는 호출(파라미터 값 포함) | 하나라도 없으면 partial |
| `calls.alternative` | 택1 그룹. `mode: exactly_one`(둘 다 부르면 불충족) / `at_least_one` | 불충족 → partial |
| `calls.conditional` | 고객 선택 시 필수. 공개 TC 시나리오는 고객이 고르므로 `trigger`가 대화에 나오면 required로 본다 | 불충족 → partial |
| `calls.forbidden` | 금지 호출. `basis: explicit`(원문 명시) / `derived`(원문 상황·정책에서 도출) | 하나라도 있으면 fail |
| (규칙) 기대 목록에 없는 접수(POST) | 필수·택1·조건부 어디에도 맞지 않는 접수 호출(A6 #166). 루브릭 `calls.allowed_writes`로만 예외 | ⚠️ partial |
| `calls.no_call_expected` | 호출이 필요 없는 TC(L-20, Y-24). 조회 → partial, 접수 → fail | |
| `say.must_say` | 필수 안내 요소. `basis: expected`만 판정에 반영, `situation`은 참고(advisory) | LLM 판정, 미충족 → partial |
| `say.must_not_say` | 말하면 안 되는 것. `literal`은 결정적 부분문자열 검사 | 위반 → fail |
| `echo` | 접수 API 응답의 접수번호가 봇 말풍선에 나와야 함 | 미충족 → partial |
| `sim` | 시뮬레이터 사실·행동. 첫 메시지는 원문 '초기 대화' 블록을 그대로 쓴다 | |

match 문법: 스칼라=문자열 일치, `{contains_all: [..]}`, `{contains_any: [..]}`, `{in: [..]}`, `{not_in: [..]}`, `{contains_all: [..], groups: [[a, b], [c]]}`(각 묶음에서 하나 이상), `{present: true}`. `match: {}`는 그 API의 모든 호출.
기타: `after: <G/R id>`(순서 제약), `trigger`(conditional을 켜는 고객 발화 문구), `sim.rules[].once`(한 번만 사용), `sim.max_turns`(고객 발화 상한).
검증(R-030): 15건 파싱·원문 sha256 일치, API 분류가 07 B절과 15/15 일치(정본 대조는 원문 기대 대응 기준).
키는 `path.<이름>`, `query.<이름>`, `body.<이름>`.

## 교차검토 반영(A5 analysis/rubric_review.md v1)
- 반영: R1 echo는 원문이 '이관 접수번호'를 요구하는 L-11·L-32·L-34의 API-35만 / R3 L-23 literal '1104호' / R4 L-11 reason에 조사·안전 / R5 L-32 reason에 인과 / R6 L-33 미출고분 출고일 확정 발언 금지.
- 유지: R2 L-20 조회 — 원문 기대 대응에 호출이 없고 A4 지침이 no_call_expected로 명시 → 조회도 ⚠️(채점 기준을 완화하지 않음).
- A4-4로: R7 Y-07-b 하자 분기 합성 변형.
