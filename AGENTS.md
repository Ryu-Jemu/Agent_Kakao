# AGENTS.md — 모든 에이전트 최상위 규칙 (사용자 요구사항)

적용 우선순위: **사용자 지시 > 이 파일 > prompts/_COMMON.md > 개별 프롬프트(prompts/Ax_*.md)**.
충돌하면 상위를 따르고, 보드에 DECISION 요청을 올린다(`python3 coord/coord.py post --to A0 --type DECISION "…"`).

## 1. 사용자 최상위 지침 (8대 원칙)
1) 근거 우선 — 사실 주장마다 근거(파일 인용·실행 결과·API 응답·계산)를 단다. 기억에 의존해 단정하지 않는다.
2) 불확실성 명시 — 확실함 / 가능성이 높음 / 불확실함 / 추가 확인 필요.
3) 문제 분해 — 하위 과제마다 목표·입력·제약·도구·산출물·검증 기준을 정한다.
4) 복수 경로 — 중요한 결론은 2개 이상의 경로로 확인한다(예: 직접 계산과 코드 실행).
5) 도구 우선 — 원문 읽기·실행·조회를 기억보다 먼저 한다.
6) 검증 루프 — 초안 → 검증 → 완성. 검증하지 않은 산출물은 완료가 아니다.
7) 사실·해석·추정을 분리해 표기한다.
8) 답변 보류 — 근거가 부족하거나, 상충하거나, 검증이 빠졌으면 단정하지 않는다.

## 2. 사용자 요구사항 (전원 의무)
- **U1 역할 분리**
  - 에이전트마다 자기 소유 경로(`coord/owners.json`)만 쓴다.
  - 남의 범위가 필요하면 REQUEST 이벤트로 요청한다.
  - 다른 세션의 결과를 되돌리거나 덮어쓰지 않는다.
- **U2 단일 공유 파일**
  - 협업 상태는 `SHARED_BOARD.md` 하나에 기록한다. 수정은 `coord/coord.py`로만 한다.
  - `[BOARD]` 알림이 오면 즉시 `python3 coord/coord.py pull`.
  - 쉴 때는 Monitor 도구로 `python3 coord/coord.py watch`를 켜고 대기한다(30분 만료 시 다시 켠다).
- **U3 (R1) 대회 원문은 읽기 전용**
  - 대상: `docs/contest/**`, `actions.json`, `actions.yaml`, `tests/tc/public/**`.
  - 작업 전에 내 프롬프트의 [필독] 파일을 읽고 `coord.py read <파일들>`로 기록한다. 기록 전에는 쓰기가 훅으로 차단된다.
- **U4 (R2) 실행 장부**
  - 실행한 모든 것을 끝나는 즉시 `coord.py log add`로 기록한다. 표기는 ✅성공 / ❌실패 / ⚠️부분이다.
  - 실패는 원인과 재시도 금지사항을 적는다.
  - 시작 전에는 `coord.py log search <키워드>`로 중복을 확인한다.
  - ✅는 재사용한다. ❌를 다시 시도할 때는 `--retry-of R-###`와 `--change "달라진 점"`이 필수다.
- **U5 (R3) 공개 TC 15건 전수**
  - 보드 `TC_MATRIX` 15행이 제출 체크리스트다.
  - 릴리스 빌드에서 `coord.py tc check --build <sha>`가 15/15 ✅가 아니면 제출 GO가 없다.
- **U6 작업 단위(WU) 인계**
  - 모든 일은 보드 `WORK_UNITS`의 WU 단위로 claim → 진행 → 갱신한다.
  - 단계가 끝날 때마다 바로 기록한다(끝에 몰아서 쓰지 않는다).
  - 세션이 언제 끊겨도(크레딧·컨텍스트 소진) 다른 에이전트가 §4 HANDOFF만 보고 즉시 이어받을 수 있어야 한다.
- **U7** 이 파일을 모든 판단의 최상위 기준으로 삼는다.
- **U8 사용자(HUMAN) 작업은 반드시 명시한다**
  - 사람이 해야 하는 일(인터뷰 전송·콘솔 설정·토큰 입력·카톡 확인·제출 등)이 생기면 바로 다음 두 가지를 한다.
    ① `python3 coord/coord.py post --to HUMAN --type HUMAN_TODO "무엇을·어디서·어떻게·완료 기준" --ref <파일>`
    ② A0가 `HUMAN_TODO.md`에 순서대로 반영한다(A0가 없으면 이벤트만으로도 유효).
  - 사람에게 필요한 일을 암묵적으로 두지 않는다. 사람이 끝내기 전에는 의존 WU를 ⛔로 두고 사유를 적는다.

## 3. 대회 규정상 절대 금지 (위반 시 실격·무효)
- 마을 관계자 채널에 자동 전송하지 않는다. 시스템 프롬프트·내부 설정 탈취를 시도하지 않는다. 질문 횟수·200자·접근 제한을 우회하지 않는다. 인터뷰 전송은 **HUMAN만** 한다.
- 문제·데이터·토큰을 외부에 공유하지 않는다. **git push 금지**, 외부 업로드 금지. Vertex 추론 호출은 예외다.
- 제출 후에는 에이전트·프롬프트·배포를 변경하지 않는다. 제출과 콘솔 설정은 HUMAN만 한다.
- 비밀값(`.env`)을 출력·로그·보드·커밋에 쓰지 않는다.
- 액션 데이터 reset은 A4만 한다.
- 카카오 게이트웨이 상시 연결은 VM 데몬 하나만 한다(중복 연결 시 close 4004).
- gcloud는 `CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100` 구성으로만 쓴다(사용자 기본 구성 `mapcenter-b59ca` 변경 금지).

## 4. HANDOFF 블록 (WU 종료·중단·세션 종료 직전에 필수, `coord.py handoff`)
```
### HANDOFF <WU-ID> <YYYY-MM-DD HH:MM KST> <AGENT_ID>
- 상태: 진행중 | 중단 | 완료 | 차단(사유)
- 마지막 성공: R-### — <명령/결과 한 줄>
- 완료 단계: [x] …
- 남은 단계(순서대로): 1) … 2) …
- 다음 명령(그대로 실행 가능): `…`
- 산출물·증거 경로: …
- 주의·재시도 금지: …(관련 ❌ R-#)
```

## 5. 어디에 무엇이 있나
| 항목 | 위치 |
|---|---|
| 계획 전문(구조·근거·WU 표) | `docs/PLAN.md` |
| 공통 운영 블록 | `prompts/_COMMON.md` |
| 내 역할 프롬프트 | `prompts/<ID>_*.md` (A0_ORCH, A1_KNOW, A2_INTEG, A3_BRAIN, A4_TEST, A5_ANALYST, A6_GATE) |
| 협업 상태 | `SHARED_BOARD.md` — WORK_UNITS, NEXT, TASKS, RUNLOG, TC_MATRIX, READ, EVENTS |
| 원문(읽기 전용) | `docs/contest/`, `actions.json`, `actions.yaml`, `tests/tc/public/` |
| 비밀값 | `.env` — `AI_CS_AGENT`(액션 API 토큰), `KAKAO_BOT_TOKEN`, `GCP_PROJECT`, `VERTEX_LOCATION` |

## 6. 보고 형식
요약 / 근거(R-#, 파일 경로) / 과정 / 한계 / 후속 조치.

## 7. Codex 등 훅이 없는 런타임에서의 의무 (Claude Code 훅이 강제하던 것을 스스로 지킨다)
- 시작: `export AGENT_ID=<ID>`. 모든 coord 명령은 `AGENT_ID=<ID> python3 coord/coord.py …` 형태로 실행한다(없으면 SETUP으로 잘못 기록됨). 역할 프롬프트는 `prompts/<ID>_*.md`이고, 실행기 `bin/agent <ID> codex`로 시작할 수 있다.
- 쓰기 전에 다음을 확인한다.
  - 대상 경로가 `coord/owners.json`의 내 write 목록 안인가?
  - 읽기 전용 원문이 아닌가?
  - 필독(`coord.py read`)을 기록했는가?
- `SHARED_BOARD.md`는 파일 권한 444로 잠겨 있다. **chmod로 풀어서 직접 편집하지 않는다.** 수정은 coord 명령으로만 한다.
- 알림: 훅 주입이 없으므로 단계마다 `coord.py pull`을 실행한다. 대기할 때는 별도 터미널에서 `coord.py watch`를 실행한다.
- 사후 감사: A6가 `coord.py audit`과 RUNLOG 대조로 위반을 찾는다. 위반은 보드에 기록된다.
