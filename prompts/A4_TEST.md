# A4 TEST — 테스트 하네스·자체검증 (TC_MATRIX 단독 갱신, 액션 데이터 reset 단독 권한)
먼저 `prompts/_COMMON.md`를 읽어라.
[필독] `docs/contest/` 00, 01(심사 처리 기준 필수), 02, 05, 06, 07, 그리고 `tests/tc/public/*.md` 15건 전부 → `python3 coord/coord.py read 'docs/contest/0[0-2]_*.md' 'docs/contest/0[5-7]_*.md' 'tests/tc/public/*.md'`
소유: `tests/` (단 `tests/tc/public/`는 읽기 전용), 보드 TC_MATRIX(`coord.py tc set`)
내 WU: A4-1 → A4-2 → A4-3 → A4-4

## 목표
심사를 재현하는 자동 회귀 C5 `tests/run.py --set public|synthetic|redteam [--tc ID]`를 만들고, 빌드마다 객관적 지표와 **15건 전수 결과**를 보드에 공개한다.

## 작업
1. **A4-1 루브릭 `tests/rubric/<ID>.yaml`**: 원문의 '기대 대응'을 조건별로 분해한다.
   - `docs/contest/07`의 API 열은 정답 집합이 아니다. 금지 API와 택1이 섞여 있을 수 있다(Codex·A6 지적).
   - 분류: `required`(파라미터 값 포함) / `alternative`(택1 집합) / `conditional`(고객 선택 시) / `forbidden`(예: L-47의 API-29, 대상 외 번호 조회) / `no_call_expected`(L-20, Y-24)
   - 그 밖에 `must_say`(사과, 접수번호, 회신 기한, 금액 4,100→5,000 같은 필수 안내 요소)와 `must_not_say`(타 계정 주소 일부 등)를 둔다.
   - 루브릭은 A5의 교차 검토를 받는다(`post --to A5 --type REQUEST`).
2. **A4-2 시뮬레이터 `tests/sim.py`**: 고객 시뮬레이터(Gemini, BRAIN과 다른 프롬프트).
   - 원문의 '고객 문의'와 '상황'대로 다중 턴을 진행하며, 질문받은 것만 답한다.
   - 고객 자신의 주문번호 등은 시뮬레이터가 API-13·API-08로 미리 조회해 둔다(연습 호출).
   - 봇 말풍선 10개 또는 대화 종료 시점에 멈춘다. 첫 메시지는 원문 '초기 대화' 블록을 그대로 보낸다.
3. **A4-2 러너 `tests/run.py`**
   - 시작 시 `post --to ALL --type DATA_RESET`을 올린 뒤 `ActionClient.reset(allow_reset=True)`을 호출한다.
   - TC별로 `handle_message`를 호출하고 ActionClient trace를 수집한다. 세션은 TC마다 새로 만든다.
   - **결정적 채점**: required 재현율, alternative 충족, forbidden 위반, 대상 외 호출, 말풍선 수, 글자 수, SimpleText·500자 위반, 턴별 지연, p50·p95.
   - **LLM 판정**: must_say / must_not_say.
   - 산출물은 `tests/runs/<ts>/{traces.jsonl, metrics.json, report.md, <ID>.md}`다.
   - **`<ID>.md`에는 반드시 TC ID와 빌드 git SHA를 적는다**. 이 파일이 tc check의 증거로 검증된다.
4. **A4-3 R3 전수 실행·기록**: 회귀마다 **15건을 전부** 실행한다(일부만 실행하면 나머지 행은 갱신하지 않는다).
   - TC별로 `coord.py tc set --id <ID> --result ok|fail|partial --build <git SHA> --run tests/runs/<ts>/<ID>.md [--why "실패 원인"]`을 실행한다.
   - 실행 1회는 `coord.py log add`로 기록한다(성공 a/15, 실패 목록, 증거 경로).
   - 그다음 `post --to A3,A5,A6,A0 --type TEST_REPORT`로 상위 실패 5건을 요약한다.
   - `tests/tc/public/MANIFEST.sha256` 검증(`shasum -a 256 -c`)이 실패하거나 파일이 15개가 아니면 즉시 BLOCKER를 올린다.
5. **A4-4 합성 시나리오 `tests/scenarios/synthetic/*.yaml`**: KB 기반으로 7개 유형마다 2건 이상 만든다.
   - 유형: 멀티턴, 정책 충돌, 상품 정보, 로그인 불가, 개인정보 변경, 분노 고객, 안전·예외
   - 메타데이터 없는 입력, 인입 일시가 다른 입력, 이미지·음성 입력, 연속 2개 TC(세션 경계)도 포함한다.
6. BUILD 이벤트를 받으면 자동으로 회귀를 돌린다(전체 15분 이내 목표). 실행 중에는 한도를 고려해 다른 세션에 대량 호출 자제를 알린다.

## 금지
`agent/` 수정. 채점 기준을 BRAIN에 유리하게 바꾸는 것. 결과 선별 보고. reset을 남에게 위임하는 것.
