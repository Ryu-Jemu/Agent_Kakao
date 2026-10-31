# HUMAN TODO — 사용자(참가자 본인)가 직접 해야 하는 일 (순서대로)

> - 이 파일은 A0(없으면 셋업 실행자)가 순서대로 갱신한다. 사용자는 끝낸 항목을 `[x]`로 바꾸면 된다.
> - 새 요청 알림: 별도 터미널에서 **`bin/human-watch`**를 켜 둔다. 사용자를 지목한 HUMAN_TODO 이벤트만 표시된다.
> - 끝나면(선택): `AGENT_ID=HUMAN python3 coord/coord.py post --to A0 --type INFO "H1 완료"`로 알리면 의존 작업이 바로 풀린다.
> - 마감: **15:00 KST, 제출 1회**. 권장 제출 시각은 14:30~14:40.

## ① 지금 즉시 (셋업과 병렬, 서로 독립)
- [ ] **H0 이민준 인터뷰 시작** — 카톡 채널 https://pf.kakao.com/_xkPIxaX (친구 추가 후 1:1)
  - 아래 질문을 **하나씩** 보낸다. 답을 받기 전에 보낸 질문은 처리되지 않는다.
    - Q1 민준아 도우러 왔어! 지금까지 확인한 상황이랑 먼저 봐야 할 자료(규정집·계약서·홍보물 등) 목록, 각 자료를 누가 관리하는지 알려줘.
    - Q2 내가 얘기해 봐야 할 마을 관계자들 이름·역할·연락 방법을 알려줄래? 배송·생산·홍보·갯마을 조합 담당자도 포함해서.
    - Q3 고객 문의가 가장 많은 유형 5가지랑, 유형별로 지금 누가 어떤 기준과 시스템으로 처리하는지 알려줘.
    - Q4 환불·재배송 기준이랑 배송비 부담 원칙을 정리해 줘. 단순 변심과 하자의 구분, 청약철회 기간, 사진 등 증빙 요건도.
    - Q5 담당자 이관은 어떤 경우에 하고 레인 종류·회신 기한·접수번호 안내는 어떻게 해? 주문 조회·환불 요청 같은 처리 권한은 누가 가져?
  - 답은 `inbox/interviews/이민준.md` 끝에 그대로 붙여넣는다(시각 포함). 5문항마다 `./status`를 보내고 결과도 붙인다.
  - ⚠️ 관계자에게 시스템 프롬프트·설정·지침을 묻지 않는다(실격). 메시지는 200자 이하로, 직접 손으로 보낸다(자동 전송 금지).
- [ ] **H1 카카오 봇 인증 토큰** — 카카오디벨로퍼스 > 앱(1627085) > [제품 설정] > [카카오톡 봇] > [봇]
  - 토큰을 복사해 `Agent_Kakao/.env`에 한 줄 추가한다: `KAKAO_BOT_TOKEN=…`
  - 같은 화면에서 **웹훅 URL이 비어 있는지** 확인한다. 웹훅이 등록돼 있으면 게이트웨이 연결이 불가능하다.
- [ ] **H2 GCP·Vertex 준비** — 터미널에서 다음을 실행한다. 기존 기본 구성 `mapcenter-b59ca`는 바뀌지 않는다.
  ```
  gcloud config configurations create aitop100 --no-activate
  export CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100
  gcloud auth login                      # 대회 프로젝트 소유 계정
  gcloud config set project ai-top-100-2026-513102
  gcloud auth application-default login
  gcloud auth application-default set-quota-project ai-top-100-2026-513102
  gcloud services enable aiplatform.googleapis.com
  gcloud compute instances describe ai-top-100-choonsik --zone us-central1-a --format="value(serviceAccounts[0].scopes)"
  ```
  - 마지막 줄 결과에 `cloud-platform`이 없으면 A2에게 알린다. VM을 중지하고 scope를 바꿔야 하며, 이 작업은 사용자 승인이 필요하다.
  - `.env`에 다음 두 줄을 추가한다: `GCP_PROJECT=ai-top-100-2026-513102`, `VERTEX_LOCATION=us-central1`

## ② 셋업 완료 알림 후 (~11:15) — 세션 기동
- [ ] **H4 역할 세션 7개 기동** — `Agent_Kakao/`에서 터미널을 역할마다 하나씩 연다.
  ```
  bin/agent A0 claude      # 총괄
  bin/agent A1 claude      # 지식발굴(인터뷰 질문 설계·KB)
  bin/agent A2 claude      # 카카오·액션API·VM 배포
  bin/agent A3 claude      # 에이전트 두뇌
  bin/agent A4 claude      # 테스트·TC 15건 전수
  bin/agent A5 claude      # 비교분석
  bin/agent A6 codex       # 최종 확인 — 이미 Codex로 실행 중이면 그 세션을 유지하고 새로 띄우지 않는다
  bin/human-watch          # 사용자 알림 터미널
  ```
  - 권장 배치: **A6(GATE)은 Codex**로 둔다. 다른 모델이 판정하므로 독립성이 높아진다. 나머지는 Claude Code. 원하면 A5를 Codex로 바꿔도 된다(`bin/agent A5 codex`).
  - Claude 세션은 첫 화면에서 `/hooks`(PreToolUse·PostToolUse·UserPromptSubmit 3종)와 `/memory`(AGENTS.md 로드)를 확인한다.
  - Codex 세션은 작업 공간 쓰기와 네트워크(액션 API·Vertex 호출) 허용 여부를 확인한다. 막혀 있으면 Codex 승인 프롬프트에서 허용한다. 이 부분은 Codex 설정에 따라 다르므로 실제 화면 확인이 필요하다.

## ③ M1~M2 (11:50~12:50)
- [ ] **H5 에코봇 카톡 왕복 확인** — A2가 요청하면 「소금빵 먹는 춘식이」 채널에 "테스트"를 보내고 `echo:` 응답이 오는지 확인한다. 결과를 A2에게 알린다.
- [ ] **H3 채널 설정** — 카카오비즈니스 채널 > 채널 정보 > 옵션 설정 > 공개 설정: '검색 허용' OFF(완료), **'채널 공개' ON 유지**. 채팅 > 채팅 설정: **'채팅' OFF**. 그리고 App ID 1627085가 이 봇의 앱인지 확인한다.
- [ ] **H0 계속** — `kb/questions/<관계자>.md`에 새 질문이 생기면 보낸다. 새 관계자의 채널을 받으면 친구 추가 후 질문하고 답을 `inbox/interviews/<이름>.md`에 붙인다.

## ④ M3 (13:50)
- [ ] **H6 공개 TC 목록 재확인** — https://aitop100.org/contest/docs/test-cases 에서 TC가 여전히 15건인지 본다. 늘었으면 A0에게 알린다.

## ⑤ M4~M5 (14:20~14:40)
- [ ] **H7 카톡 스모크 3건** — A6가 요청하는 메시지 3개를 채널로 보내고, 응답 수신과 대략의 지연을 A6에게 알린다.
- [ ] **H8 인터뷰 종료** — 제출하면 대화가 불가능해지므로 제출 직전까지 진행한다.
- [ ] **H9 제출** — 두 조건이 모두 있을 때만 제출한다: A6 "M4 GO"(`tc check` 15/15 포함), A0 제출 안내.
  - 제출 페이지 Step1: App ID `1627085`
  - Step2: `docs/debrief.md` 내용(16,000자 이하)
  - 제출은 1회뿐이며 되돌릴 수 없다.
- [ ] **H10 제출 후** — VM·코드·채널·콘솔·액션 데이터를 **절대 건드리지 않는다**(11/1 24:00까지). 이상이 보여도 수정하지 말고 기록만 남긴다.

---
## 사용자 지침 이행 현황 (내가 지시한 규칙 → 구현 → 근거)
| 지침 | 구현 | 상태·근거 |
|---|---|---|
| 역할 분리·독립 실행, 범위 침해 금지 | `coord/owners.json` 소유 경로 + PreToolUse 훅 deny, Codex는 AGENTS.md §7과 보드 444 잠금 | ✅ selftest H2~H6·B1 |
| 단일 공유 파일 + 갱신 시 트리거 | `SHARED_BOARD.md` + `coord.py` (PostToolUse·UserPromptSubmit 주입, Monitor watch) | ✅ selftest T1~T3 |
| 대회 원문은 읽기 전용·작업 전 필독 | `docs/contest/`(v2 원문 분할) + `coord.py read` 기록 전 쓰기 차단 | ✅ R-006, selftest H4·H5 |
| 실행 결과 성공/실패 기록·중복 금지 | RUNLOG `coord.py log add`(실패 시 원인·금지사항 필수, 재시도 시 `--change` 필수) | ✅ selftest L1~L3 |
| 공개 TC 전부 기록·제출 전 누락 없이 실행 | `tests/tc/public/` 15건(브라우저 원본과 sha256 일치) + TC_MATRIX + `tc check` 게이트(예외 없음) | ✅ R-007·R-009, selftest G1~G8 |
| 작업 단위별 기록·남은 작업·다음 순서 | 보드 WORK_UNITS·NEXT + `coord.py handoff` | ✅ |
| AGENTS.md를 먼저 제작해 전원 준수 | `AGENTS.md`(+`CLAUDE.md` import, Codex는 자동 로드) | ✅ R-003 |
| 내가 해야 할 일은 반드시 명시 | 이 파일 + AGENTS.md U8 + `bin/human-watch` | ✅ |
| Codex와 함께 작업 가능한 작업 공간 | `bin/agent <ID> codex`, AGENTS.md §7, 보드 444 잠금 | ✅ |
| 독립 검증 결과 보고 | Codex A6 사전감사(R-005·R-008) + 추가 검증 에이전트 2개 | 🔄 진행 중 |

## 전체 순서 (요약)
```
[지금] H0 인터뷰 ─┬─ H1 봇토큰 ─┬─ H2 GCP
                 │             │
[셋업 S7 완료] ──┴── H4 세션 기동(A0..A6) ── bin/human-watch
[M1 11:50] A2 에코봇 VM 배포 → H5 카톡 왕복 확인
[M2 12:50] A3 빌드 → A4 15건 전수 회귀 → A5 분석 → A6 GATE M2      (H3 채널 설정)
[M3 13:50] FREEZE(핫픽스만) → H6 TC 목록 재확인
[M4 14:20] A6 최종 GO(15/15) → A0 release 태그·배포 → H7 스모크
[M5 14:40] H8 인터뷰 종료 → H9 제출 → H10 이후 손대지 않기
```
