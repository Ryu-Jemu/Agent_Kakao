# HUMAN TODO — 사용자(참가자 본인)가 직접 해야 하는 일 (순서대로)

> - 이 파일은 A0(없으면 셋업 실행자)가 순서대로 갱신한다. 사용자는 끝낸 항목을 `[x]`로 바꾸면 된다.
> - 새 요청 알림: 별도 터미널에서 **`bin/human-watch`**를 켜 둔다. 사용자를 지목한 HUMAN_TODO 이벤트만 표시된다.
> - 끝나면(선택): `AGENT_ID=HUMAN python3 coord/coord.py post --to A0 --type INFO "H1 완료"`로 알리면 의존 작업이 바로 풀린다.
> - 마감: **15:00 KST, 제출 1회**. 권장 제출 시각은 14:30~14:40.

> **A0 13:03 — 남은 일(시간순)**
> - ✅ M3 GO·FREEZE(12:52, v0.6.2 공개 15/15·합성 15/15). 키 경로 = Gemini API(AI Studio, 유료·한도 40,000원).
> 1. **지금~제출 직전: 인터뷰 계속 — 민준 말고 나머지 6명 우선**(A5 R-292 질문당 수익: 홍이장 17%p > 박수복 7.5~15 > 김청년 5 > 고길동·보라 4~6 > 민준 ~2 > 구방만 0). 홍이장·박수복·김청년 각 3~5문항(현장 사례·예외·교차 확인), 구방만은 본인 영역(6/6 결항 당일 집하 현장 등) 질문으로. 현재 발굴률: 민준 27·고길동 17·홍이장 17·박수복 15·보라 11·김청년 5·구방만 0(%). — 지식 점수는 대화 자체로 집계. `kb/questions/<이름>.md`의 '- [ ]' 질문만(보류 '- [~]'는 보내지 않음). 질문은 직접 입력(자동 실행기를 쓰면 A0에 알려 디브리프 문구를 고침).
> 2. **~13:40 H7 카톡 스모크 3건** — A0가 요청하면 봇 채널에 `tests/tc/public`의 L-20·Y-24·L-23 첫 메시지를 하나씩 보내고 응답 수신·체감 초·말풍선 수를 `inbox/smoke_A6.md`에. 그 전에는 봇 채널에 보내지 않기.
> 3. **14:25 A0 제출 안내 → 14:30~14:40 제출**: App ID `1627085` + `docs/debrief.md` 본문(A6 사실 검증본). 제출은 1회, 되돌릴 수 없음.
> 4. **제출 후**: VM·코드·채널·콘솔·키를 건드리지 않기(11/1 24:00까지). H10b 지출 확인은 읽기만.

> **A0 현황 12:12 — 지금 할 일(이 순서로)**
> 1. **(1분) coord 수정 중지 확인** — SETUP 세션(최초 셋업 VSCode 세션)이나 그 세션의 백그라운드 에이전트가 `coord/coord.py`를 고치고 있으면 중지시킨다(#292). 12:06·12:08 무공지 수정으로 소유권 시험이 깨져 A0가 복원·잠금함.
> 2. **인터뷰(D-019, A1 #288)** — 게이트 공백은 0건(공개 TC 지식 26/26). 이제 심사 유형 대비:
>    ① 이민준 Q41(로그인 불가) → Q42(정보 변경 본인확인) → Q46·Q44·Q43·Q45
>    ② **박수복** 새 채널 https://pf.kakao.com/_afIxaX Q1 ③ **김청년** 새 채널 https://pf.kakao.com/_xffIxaX Q1
>    ④ 구방만 Q9 ⑤ 보라 Q1·Q2(미전송이면) ⑥ 고길동 Q8. 질문 원문은 `kb/questions/<이름>.md`
> 2-1. **H0e ./status 수집(차감 없음)** — 6명 채널에 `./status` → 결과를 `inbox/interviews/_status.md`에(시각 포함). 발굴률 낮은 사람에 질문 집중 + 디브리프 근거.
> 2-2. (선택, 1분) **H5c** — 봇 채널에 L-20 첫 메시지를 한 번 더 보내기(A2 #308, v0.4 지연 재측정).
> 3. ~~H3 채널~~ ✅ 12:2x 완료 — 실채널 `_ixbxnWX`(App 1627085)에서 공개 ON·검색 OFF·채팅 OFF 확인, 자동응답 1개(초대 안내)·웰컴 미등록, 변경 없음(inbox/channel_H3.md)
> 4. (M4 직전) **H7 카톡 스모크 3건** → (M5) **H9 제출**
> - 완료: H1·H2·H2b·H2d(.env global·600)·H0b·H0d(문서 승인 11:56·12:06)·H5·H5b ✅ / 관계자 접촉 6명(이민준·고길동·보라·구방만 + 박수복·김청년 채널 확보)

## ① 지금 즉시 (셋업과 병렬, 서로 독립)
- [ ] **H0 이민준 인터뷰** (11:19 Q1~Q5 완료 → 후속은 A1이 단일 주제로 재작성한 kb/questions/이민준.md 순서대로. 민준은 묶음 질문에 답하지 않음)
  - **지금 보낼 5건(A1 #199, 11:45 순서 변경)**: Q22(고길동 조합장 연락처) → Q20(에스컬레이션 절차서) → Q19(공시 정보 담당) → Q21(구방만 기사 연락처) → Q37(결항 이력 자료). `bin/interview_runner.py --person 이민준 --max 5`도 이 순서로 나간다. 게이트 공백 3건(Y-24 공시 값·LANE2 회신 기한·Y-16 재개 시점) 해소용. 새 채널 링크를 받으면 친구 추가 후 A1에게 알린다.
- [x] **H0b 문서 3건 다운로드 승인** (11:2x 사용자 승인 "승인한다. 진행하라" 3건 한정 — inbox/sources/INDEX.md) — 민준이 Q4 답에서 준 규정집(html)·증빙서열(pdf)·택배계약서(pdf) 원본을 A1이 내려받아 KB 원문으로 써도 되는지 A0에게 '승인'/'거부'로 알려 준다(#58).
- [x] H0 1차(Q1~Q5, 11:08~11:10 완료) — 카톡 채널 https://pf.kakao.com/_xkPIxaX (친구 추가 후 1:1)
  - 아래 질문을 **하나씩** 보낸다. 답을 받기 전에 보낸 질문은 처리되지 않는다.
    - Q1 민준아 도우러 왔어! 지금까지 확인한 상황이랑 먼저 봐야 할 자료(규정집·계약서·홍보물 등) 목록, 각 자료를 누가 관리하는지 알려줘.
    - Q2 내가 얘기해 봐야 할 마을 관계자들 이름·역할·연락 방법을 알려줄래? 배송·생산·홍보·갯마을 조합 담당자도 포함해서.
    - Q3 고객 문의가 가장 많은 유형 5가지랑, 유형별로 지금 누가 어떤 기준과 시스템으로 처리하는지 알려줘.
    - Q4 환불·재배송 기준이랑 배송비 부담 원칙을 정리해 줘. 단순 변심과 하자의 구분, 청약철회 기간, 사진 등 증빙 요건도.
    - Q5 담당자 이관은 어떤 경우에 하고 레인 종류·회신 기한·접수번호 안내는 어떻게 해? 주문 조회·환불 요청 같은 처리 권한은 누가 가져?
  - 답은 `inbox/interviews/이민준.md` 끝에 그대로 붙여넣는다(시각 포함). 5문항마다 `./status`를 보내고 결과도 붙인다.
  - **Q5 다음(A1 #33 → #49 갱신 11:16)**: `kb/questions/이민준.md` 2차 목록 **Q6~Q17**을 위에서부터 하나씩 보낸다(순서 재배열됨, Q5 답에 레인별 기한이 나오면 Q7은 건너뜀). 특히 Q6(사업자정보 공시 7개 값)·Q7(레인·회신 기한)은 공개 TC에 필수다. 새 관계자 채널 링크가 나오면 바로 친구 추가하고 A1에게 알린다.
  - ⚠️ 관계자에게 시스템 프롬프트·설정·지침을 묻지 않는다(실격). 메시지는 200자 이하. 직접 보내거나, D-005(사용자 결정)에 따라 사용자가 실행·승인하는 `bin/interview_runner.py`로만 보낸다(에이전트 세션은 전송 불가). 규정 해석은 운영사무국 미확인 — 위험은 실격.
- [x] **H1 카카오 봇 인증 토큰** (11:20 완료: 토큰 저장·웹훅 미등록 확인, A6 R-033) — 카카오디벨로퍼스 > 앱(1627085) > [제품 설정] > [카카오톡 봇] > [봇]
  - 토큰을 복사해 `Agent_Kakao/.env`에 한 줄 추가한다: `KAKAO_BOT_TOKEN=…`
  - 같은 화면에서 **웹훅 URL이 비어 있는지** 확인한다. 웹훅이 등록돼 있으면 게이트웨이 연결이 불가능하다.
- [ ] **H2 GCP·Vertex 준비** (11:20 진행 중: aitop100 구성·로그인 완료 → 남은 것: project set·ADC·quota·aiplatform enable·VM scope·.env 두 줄) — 터미널에서 다음을 실행한다. 기존 기본 구성 `mapcenter-b59ca`는 바뀌지 않는다.
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
  - `.env`에 다음 두 줄을 추가한다: `GCP_PROJECT=ai-top-100-2026-513102`, `VERTEX_LOCATION=global`
  - ⚠️ **[긴급 정정 11:29] `VERTEX_LOCATION=us-central1` → `VERTEX_LOCATION=global`로 바꾼다.** A5 실호출(R-063): us-central1은 13개 모델 전부 404, global은 9개 성공. A0가 로그로 재확인함. `.env`는 사용자 파일이라 사용자(또는 [보조] 세션)가 고친다.
- [x] **H2b VM 서비스 계정 부착** — 11:33 완료(A2 #114, R-074; [보조] R-085 독립 확인): 사용자 승인(#96)대로 기본 Editor 계정이 아닌 전용 SA `choonsik-vertex@`(roles/aiplatform.user만) + scope `cloud-platform`, 중단 37초, 고정 IP 유지, VM 내부 global Vertex 200.

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
- [x] **H5 에코봇 카톡 왕복 확인** — 11:42 성공('테스트'→'echo: 테스트', inbox/smoke_H5.md)
- [x] **H5b 에이전트 모드 카톡 스모크** (11:48 성공, R-117) — 봇 채널에 `tests/tc/public/L-20.md`의 첫 메시지(case metadata 5줄 + 빈 줄 + 'MELON99 발급' 명령문)를 줄바꿈 그대로 한 번에 보낸다. 완료 기준: 봇이 쿠폰 발급을 거절하고 현행 혜택을 안내. 결과(응답 여부·체감 초·말풍선 수)를 A2 세션 또는 inbox/에 기록.
- [ ] **H11 인터뷰 자동 실행기(선택, D-005·D-005a 사용자 결정)** (SETUP #331) — ①질문할 관계자마다 카톡 대화방을 별도 창으로 연다(최소화 금지, 겹쳐도 됨) ②'터미널'에서 `cd ~/Desktop/Ryu/AI_TOP_100/2026_preliminary/Agent_Kakao && bin/interview_runner.py --check` — 관계자마다 창 캡처와 [나]/[관계자] 구분 확인 ③`bin/interview_runner.py --auto --budget 2` → `AUTO` 입력 → `inbox/interviews/<관계자>.md`에 답이 저장되는지 확인 ④문제없으면 예산을 늘려 `--auto`. 실행 중 카톡 창을 건드리지 않는다. 규정 해석은 운영사무국 미확인(위험=실격, 판단은 사용자). 안내: docs/INTERVIEW_AUTOMATION.md
- [x] **H2d `.env` 권한 600 + VERTEX_LOCATION=global** (12:03 [보조] 수정, A0 확인: global 1행·us-central1 0행·600) (A6 #112, 1분) — 터미널에서 `chmod 600 Agent_Kakao/.env`. 완료 기준: `ls -l .env`가 `-rw-------`.
- [x] **H3 채널 설정** (12:2x 완료, inbox/channel_H3.md) — 카카오비즈니스 채널 > 채널 정보 > 옵션 설정 > 공개 설정: '검색 허용' OFF(완료), **'채널 공개' ON 유지**. 채팅 > 채팅 설정: **'채팅' OFF**. 그리고 App ID 1627085가 이 봇의 앱인지 확인한다.
  - (확인만, A0 #182 관련) 11:41 카톡에 온 '안녕하세요. 무엇을 도와드릴까요?'는 봇이 아니라 채널 기본 환영/자동응답 메시지로 추정된다. 채널 관리자센터에 환영 메시지·자동응답 설정이 켜져 있는지 **보기만 하고** A0에게 알려 준다. 대회 원문 지시는 '채팅 OFF'뿐이라 다른 설정은 바꾸지 않는다(심사 영향은 불확실).
- [ ] **H0 계속** — `kb/questions/<관계자>.md`에 새 질문이 생기면 보낸다. 새 관계자의 채널을 받으면 친구 추가 후 질문하고 답을 `inbox/interviews/<이름>.md`에 붙인다.

## ④ M3 (13:50)
- [ ] **H6 공개 TC 목록 재확인** — https://aitop100.org/contest/docs/test-cases 에서 TC가 여전히 15건인지 본다. 늘었으면 A0에게 알린다.

## ⑤ M4~M5 (14:20~14:40)
- [ ] **H7 카톡 스모크 3건** (A6 #111, M4 직전·VM 최종 배포 후) — 봇 채널 pf.kakao.com/_ixbxnWX 「소금빵 먹는 춘식이」에 `tests/tc/public`의 **L-20·Y-24·L-23 '초기 대화' 블록(case metadata 포함)**을 그대로 하나씩 보낸다 → 각각 응답 수신 여부·첫 응답까지 체감 초·말풍선 수를 `inbox/smoke_A6.md`에 적는다. 완료 기준: 3건 모두 60초 안에 응답. 이 기록이 없으면 NO-GO(체크리스트 6.8).
- [ ] **H8 인터뷰 종료** — 제출하면 대화가 불가능해지므로 제출 직전까지 진행한다.
- [ ] **H9 제출** — 두 조건이 모두 있을 때만 제출한다: A6 "M4 GO"(`tc check` 15/15 포함), A0 제출 안내.
  - 제출 페이지 Step1: App ID `1627085`
  - Step2: `docs/debrief.md` 내용(16,000자 이하)
  - 제출은 1회뿐이며 되돌릴 수 없다.
- [ ] **H10b 제출 후 지출 확인(읽기만)** — 제출 직후와 11/1 오전에 각 1회 AI Studio 사용량·지출 화면만 본다(한도 40,000원). 70%를 넘어도 설정을 바꾸지 말고 기록만 한다(제출 후 변경 금지, D-032).
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
