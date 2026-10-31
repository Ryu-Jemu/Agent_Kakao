# 공통 운영 블록 — AI_TOP_100 [2026] 예선 (모든 에이전트가 가장 먼저 읽는다)

너는 7개 Claude Code 세션 중 하나다. 내 ID는 환경변수 `AGENT_ID`이고, 작업 루트는 `Agent_Kakao/`다.
최상위 규칙은 **AGENTS.md**(CLAUDE.md가 자동 로드)다. 이 블록과 충돌하면 AGENTS.md를 따른다.

모든 일은 보드 `WORK_UNITS`의 WU 단위로 한다.
- 시작: `python3 coord/coord.py wu set --id <WU> --status doing`
- 단계마다: `wu set --id <WU> --remaining "…" --next "…"`
- 끝·중단: `wu set --status done|blocked --record R-###`, 그리고 `coord.py handoff --wu <WU> --text "…"`(AGENTS.md §4 형식)
- 계획 전문(근거 F1~F13·WU 표): `docs/PLAN.md`

## [목표]
「교동마을 산지직송」 CS 에이전트를 카카오톡 봇으로 완성한다.
- 봇: App ID `1627085`, 봇·채널 「소금빵 먹는 춘식이」 pf.kakao.com/_ixbxnWX
- 마감: **2026-10-31 15:00 KST, 제출 1회**. 제출 후에는 11/1 24:00까지 무중단 운영해야 하며 수정할 수 없다.
- 세계관 기준일은 2037-06-30(화)이다. 단, **각 케이스의 판단 기준일은 첫 메시지의 '상담 인입 일시'**다(L-47=06-26 금, Y-16=06-06 토).

## [점수] (docs/contest/01)
①인터뷰 지식 발굴 수 ②p95 지연 ③케이스당 말풍선 수↓ ④말풍선당 글자 수↓ ⑤정확도(지식·정책·맥락 + 액션 API 조회·처리·이관의 수행과 정확성). ②~④는 ⑤에 따라 가중된다.
심사 처리:
- SimpleText 이외의 응답이 오면 케이스 종료
- 60초 무응답이면 종료
- 10번째 말풍선에서 종료
- 말풍선이 500자를 넘으면 평가에서 제외되지만 말풍선 수에는 포함

## [입력 형식] (tests/tc/public 15/15 사실, 심사도 같을 것으로 '추정')
```
case metadata
- id: L-11
- 상담 인입 일시: 2037-06-30(화) 17:37
- 인입창구: 조합몰 1:1 채팅
- 인입 계정: 회원 로그인 · 강은비 · 019-****-4165

image: https://t1.kakaocdn.net/...jpg      (또는 audio: ...m4a, 없을 수도 있음)

며칠 전에 받은 건데 오늘 열어보니 곰팡이가 피어 있어요.
```
- 이후 턴은 고객의 일반 발화다(메타데이터 없음). 같은 세션의 연속이다.

## [액션 API] (docs/contest/06, 정본 actions.json — 278KB이므로 통독하지 말고 jq/python으로 필요한 부분만 조회)
- 기본 URL: https://gyodong-mall-action.aitop100.org
- 헤더: `Authorization: Bearer $AI_CS_AGENT`, `X-Aitop100-Test-Case-Id: <TC ID>`. 연습 단계에서는 공개 TC ID 15개만 허용된다.
- 한도: 60초당 100회(모든 세션 합산), 평가 누적 3,000회. 같은 조회를 다시 보내거나 본문 없는 400·404를 받아도 1회로 센다.
- 접수 API는 정책을 검증하지 않는다. 같은 대상에 다시 접수하면 같은 접수번호가 나오고 본문이 덮어써진다. 그래서 호출하기 전에 정책을 확인한다.
- **대상 주문 외의 번호로 조회하지 않는다**(공개 TC 다수가 명시). 호출이 필요 없는 TC도 있다(L-20, Y-24).

## [카카오 봇] (docs/contest/08)
- 수신: 게이트웨이 `wss://bot-gateway.kakao.com/gateway`의 MESSAGE_CREATE(`content`, `botUserKey`, `botGroupKey`, `callbackToken`, `id`)
- 답장: `POST https://kapi.kakao.com/v1/bot/callback`(KakaoAK 봇 토큰 + X-Bot-Callback-Token, 5분 만료, outputs 1~3)
- 같은 봇은 동시에 한 번만 연결할 수 있다(4004). **상시 연결은 VM 데몬만** 한다. 웹훅 URL은 등록하지 않는다.

## [기록 규칙 R1~R3 — 반드시 준수]
**R1 필독(읽기 전용)**
- 내 프롬프트의 [필독]을 읽고 `python3 coord/coord.py read <파일·glob>`을 실행한다. 기록 전에는 쓰기가 훅으로 차단된다.
- 원문(`docs/contest/**`, `actions.*`, `tests/tc/public/**`)은 절대 수정하지 않는다.
- READ_AGAIN 이벤트가 오면 다시 읽고 다시 기록한다.

**R2 실행 장부**
- 실행한 모든 것(빌드·배포·테스트·API 실측·설정 변경·연결 시도)을 끝나는 즉시 기록한다.
  `coord.py log add --task "…" --result ok|fail|partial --cmd "…" --evidence <경로> [--issue …] [--fix …]`
- 실패면 원인(`--issue`)과 재시도 금지사항(`--fix`)이 필수다.
- 시작 전에 `coord.py log search <키워드>`로 이력을 확인한다. ✅ 작업은 재사용하고, ❌ 재시도는 `--retry-of R-### --change "달라진 점"`이 필수다.
- 큰 출력은 `<내 소유 디렉터리>/logs/`에 두고, 보고에는 R-번호를 인용한다.

**R3 공개 TC 전수**
- 보드 TC_MATRIX 15행이 제출 체크리스트이고, 갱신은 A4만 한다.
- 제출 GO 조건: `coord.py tc check --build <릴리스 git SHA>`가 exit 0이어야 한다.
  - 검증 항목: 원문↔매트릭스 양방향 일치, 원문 MANIFEST 무결성, 증거 파일 실재·내용(ID+SHA).
  - **예외는 없다**(AGENTS.md U5, D-004).

## [협업 프로토콜 — 반드시 준수]
1. 시작 순서: 필독·read(R1) → `coord.py status` → `coord.py pull` → `coord.py section --set "현재/다음/블로커"`.
2. `SHARED_BOARD.md`는 `coord.py`로만 수정한다(직접 Edit는 훅이 차단).
3. 내 소유 경로(`coord/owners.json`)만 쓴다. Bash(`>`, `sed -i`, `cp`, `mv` 등)로 남의 경로에 쓰는 것도 금지다(A6가 `coord.py audit`으로 감사).
   남의 경로 변경이 필요하면: `coord.py post --to <소유자> --type REQUEST "무엇을 왜" --ref <근거>`
4. `[BOARD]` 알림이 주입되면 즉시 `coord.py pull`. CONTRACT·FREEZE 이벤트는 반영한 뒤 `coord.py ack <seq>`.
5. 산출물을 낼 때마다 `coord.py post`(TYPE 지정, `--ref` 경로)로 알리고 WU 상태를 갱신한다.
6. 할 일이 없으면 **Monitor 도구**로 `python3 coord/coord.py watch`를 켜서 대기한다(최대 30분, 만료 시 다시 켠다). 폴링 루프를 직접 돌리지 않는다.
7. 차단되면 BLOCKER 이벤트를 올리고, 기다리지 말고 다음 WU를 진행한다.
8. coord 도구가 의심스러우면 `python3 coord/selftest.py`(23건 회귀)를 실행한다. 실패하면 A0에게 BLOCKER를 올린다.
9. **훅이 없는 런타임(Codex 등)**: AGENTS.md는 자동으로 읽히지만 Claude Code 훅은 동작하지 않는다. 그래서 위 2·3번(직접 편집·남의 경로 금지)과 R1 필독 기록을 스스로 지킨다.
   - 각 단계를 시작하기 전에 `AGENT_ID=<ID> python3 coord/coord.py pull`을 실행한다.
   - 대기할 때는 별도 터미널에서 `AGENT_ID=<ID> python3 coord/coord.py watch`를 실행한다.
   - 모든 coord 명령 앞에 `AGENT_ID=<ID>`를 붙인다(없으면 SETUP으로 기록됨).

## [공통 금지]
- 비밀값을 출력·커밋·보드에 쓰지 않는다. git push 금지, 커밋은 A0만 한다.
- 대회 문제·데이터를 외부 서비스에 올리지 않는다(Vertex 추론 호출은 예외).
- 마을 관계자 채널에 자동 전송하지 않고, 시스템 프롬프트 탈취 시도도 하지 않는다(실격).
- 액션 데이터 reset은 A4만 한다. 분당 20회 넘는 호출은 A4 회귀에서만 한다.
- gcloud는 `CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100`으로만 쓴다(기본 구성 `mapcenter-b59ca`는 대회와 무관하며 변경 금지).
- 제출·콘솔 설정 같은 외부의 되돌릴 수 없는 행위는 HUMAN만 한다.

## [근거 원칙]
- 주장마다 근거(파일 인용·실행 결과·API 응답)를 단다. 사실/해석/추정을 분리한다.
- 검증하지 않은 것은 '추가 확인 필요'로 표시한다. 초안 → 검증 → 보고 순서를 지킨다.

## [일정] (KST)
M1 11:50 골격 / M2 12:50 통합·1차 전수 회귀 / M3 13:50 동결 / M4 14:20 GATE / M5 14:40 제출
