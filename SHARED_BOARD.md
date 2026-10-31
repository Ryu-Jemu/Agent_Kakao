# SHARED BOARD — AI_TOP_100 [2026] 예선 (교동마을 산지직송 CS 에이전트)
<!-- BOARD_VERSION: 21 -->
> 이 파일은 `python3 coord/coord.py`로만 수정한다(AGENTS.md U2, 직접 편집하면 훅이 차단한다). 셀 안의 `|`는 `¦`로 저장된다.
> 처음 온 에이전트의 순서: AGENTS.md → NEXT → WORK_UNITS(내 WU) → 내 STATUS의 HANDOFF.

<!-- SEC:FACTS:BEGIN -->
## FACTS (A0)
- 마감: 2026-10-31(토) 15:00 KST, 제출 1회. 심사: 10/31 16:00~11/1 24:00 무중단 운영. 결과 발표: 11/4.
- 제출 대상: 카카오 앱 ID `1627085`, 봇·채널 「소금빵 먹는 춘식이」 pf.kakao.com/_ixbxnWX
- 연결 방식: 카카오 게이트웨이(wss) + 콜백 API. VM은 `ai-top-100-choonsik`(us-central1-a, e2-micro, HTTP 수신 없음).
- LLM: Vertex AI Gemini, 프로젝트 `ai-top-100-2026-513102`. gcloud는 구성 `aitop100`으로만 사용.
- 액션 API: https://gyodong-mall-action.aitop100.org, 토큰은 `.env`의 AI_CS_AGENT. 연습 단계에서는 공개 TC ID 15개만 사용.
- 상세 근거 F1~F13: docs/PLAN.md "확인된 사실"
<!-- SEC:FACTS:END -->

<!-- SEC:NEXT:BEGIN -->
## NEXT — 지금 바로 할 일 (순서)
1. [HUMAN 지금] HUMAN_TODO.md ①: H0 인터뷰 · H1 KAKAO_BOT_TOKEN · H2 gcloud aitop100·ADC·Vertex (A2-5·A3-2·A5-1이 H1/H2에 의존)
2. [HUMAN 지금] H4 세션 기동: bin/agent A0 claude → A1·A2·A3·A4 claude → A5 claude, A6는 Codex 유지 + bin/human-watch
3. [A0] 기동 즉시 status → A0-1(TASKS·HUMAN_TODO 관리) / S8이 남아 있으면 SETUP HANDOFF 확인
4. [A1~A5] 각자 필독·read → 첫 WU(A1-1·A2-1·A3-1·A4-1·A5-1) 착수
5. [A6 Codex] READ_AGAIN(#15) 반영 → selftest·tc check 재검증 → A6-1
<!-- SEC:NEXT:END -->

<!-- SEC:DECISIONS:BEGIN -->
## DECISIONS / HUMAN_TODO (A0)
- D-001 게이트웨이 방식을 채택한다(VM에 HTTP 수신이 없으므로). 웹훅 URL은 등록하지 않는다.
- D-002 봇 LLM은 Vertex Gemini를 쓴다(사용자 결정). 모델은 A5 실측으로 확정한다.
- D-003 git push 금지, 커밋은 A0만 로컬로 한다.
- HUMAN_TODO: H0 인터뷰 시작 / H1 KAKAO_BOT_TOKEN / H2 gcloud aitop100 구성·ADC·Vertex API·VM scope / H3 채널 '채팅' OFF·'채널 공개' ON·App ID 확인
<!-- SEC:DECISIONS:END -->

<!-- SEC:OWNERS:BEGIN -->
## OWNERS (상세: coord/owners.json)
| ID | 역할 | 쓰기 허용 경로 |
|---|---|---|
| HUMAN | 인터뷰 전송·콘솔·제출 | inbox/, .env |
| A0 | ORCH 총괄 | coord/, prompts/, docs/(contest 제외), .claude/, .gitignore, README.md, AGENTS.md, CLAUDE.md |
| A1 | KNOW 지식발굴 | kb/ |
| A2 | INTEG 외부연동 | integ/, deploy/, pyproject.toml, uv.lock |
| A3 | BRAIN 에이전트 두뇌 | agent/ |
| A4 | TEST 테스트·자체검증 | tests/(tc/public 제외), TC_MATRIX, reset 권한 |
| A5 | ANALYST 비교분석 | analysis/ |
| A6 | GATE 최종확인 | release/ |
| (읽기 전용) | 원문 | docs/contest/, actions.json, actions.yaml, tests/tc/public/ |
<!-- SEC:OWNERS:END -->

<!-- SEC:CONTRACTS:BEGIN -->
## CONTRACTS (v1, 상세: docs/PLAN.md §2.4)
- C1 (A3) `async agent.handle_message(session_key, text, received_at) -> list[str]` — 말풍선 1~3개, 각 450자 이하, 기본 1개
- C2 (A2) `integ.action_client.ActionClient(tc_id, *, trace=None)` — API-01~40, GET 캐시, 429 대기, TC당 25회 상한, trace 기록
- C3 (A2) `integ.media.fetch(url)`, `python -m integ.local_chat --user u1`
- C4 (A1) `kb/policy_pack.md`, `kb/facts.jsonl`, `kb/api_usage.md`, `kb/VERSION`
- C5 (A4) `tests/run.py --set public|synthetic|redteam [--tc ID]` → `tests/runs/<ts>/`
<!-- SEC:CONTRACTS:END -->

<!-- SEC:WORK_UNITS:BEGIN -->
## WORK_UNITS — 인계 장부 (담당자만 갱신: `coord.py wu set`)
| WU | 담당 | 내용 | 선행 | 상태 | 기록 | 남은 작업 | 다음 순서 |
|---|---|---|---|---|---|---|---|
| S0 | SETUP | 조사·검증(F1~F13) | - | ✅ | R-001 | - | - |
| S1 | SETUP | .gitignore(.env·.coord·runs·logs) | S0 | ✅ | R-002 | - | - |
| S2 | SETUP | AGENTS.md·CLAUDE.md·docs/PLAN.md·보드 부트스트랩 | S1 | ✅ | R-003 | - | - |
| S5 | SETUP | coord.py·owners.json·.claude/settings.json 훅 + 모의 테스트 | S2 | ✅ | R-004 | - | - |
| S3 | SETUP | docs/contest/00~09(+06b) 원문 분할·토큰 가림·MANIFEST·chmod 444 | S2 | ✅ | R-006 | - | - |
| S4 | SETUP | 공개 TC 15건 원문·미디어 2건·07 index·chmod 444 | S2 | ✅ | R-007 | - | - |
| S6 | SETUP | prompts/_COMMON·A0~A6·HUMAN_GUIDE | S5 | ✅ | R-010 | - | - |
| S7 | SETUP | 셋업 검증(/memory·훅·주입)·로컬 커밋 setup·NEXT 전환 | S3,S4,S5,S6 | ✅ | R-012 | - | - |
| H0 | HUMAN | 이민준 인터뷰 즉시 시작 → A1 질문 루프 | - | ⬜ | - | - | 병렬 |
| H1 | HUMAN | KAKAO_BOT_TOKEN을 .env에 입력, 웹훅 미등록 | - | ⬜ | - | - | 병렬 |
| H2 | HUMAN | gcloud 구성 aitop100·ADC·Vertex API·VM scope | - | ⬜ | - | - | 병렬 |
| H3 | HUMAN | 채널 '채팅' OFF·'채널 공개' ON·App ID 1627085 확인 | - | ⬜ | - | - | M2 전 |
| A0-1 | A0 | TASKS 등록·HUMAN_TODO 게시·15분 점검 | S7 | ⬜ | - | - | - |
| A0-2 | A0 | 마일스톤 커밋·FREEZE·디브리프·release 태그·제출 안내 | - | ⬜ | - | - | - |
| A1-1 | A1 | 이민준 답변 KB화(facts·people)·다음 질문 5개 | H0 | ⬜ | - | - | - |
| A1-2 | A1 | policy_pack v1·api_usage v1 | A1-1 | ⬜ | - | - | - |
| A2-1 | A2 | uv 프로젝트·경량 의존성 | S7 | ⬜ | - | - | - |
| A2-2 | A2 | ActionClient(C2)+CONTRACT 공표 | A2-1 | ⬜ | - | - | - |
| A2-3 | A2 | gateway 데몬·local_chat·media | A2-1 | ⬜ | - | - | - |
| A2-4 | A2 | API_SEMANTICS 실측(공개 TC GET만) | A2-2 | ⬜ | - | - | - |
| A2-5 | A2 | VM 에코 배포→카톡 왕복→A3 빌드 배포 | A2-3,H1,H2 | ⬜ | - | - | - |
| A3-1 | A3 | parse·session·dates + 15건 첫 메시지 파싱 테스트 | S7 | ⬜ | - | - | - |
| A3-2 | A3 | Vertex llm + tools(C2) | A2-2,H2 | ⬜ | - | - | - |
| A3-3 | A3 | system prompt·플레이북(policy_pack) | A1-2 | ⬜ | - | - | - |
| A3-4 | A3 | formatter·가드레일 → BUILD v0 | A3-2 | ⬜ | - | - | - |
| A4-1 | A4 | 15건 루브릭 | S7 | ⬜ | - | - | - |
| A4-2 | A4 | 시뮬레이터·run.py·채점기 | A2-2 | ⬜ | - | - | - |
| A4-3 | A4 | 1차 전수 회귀 + TC_MATRIX 갱신 | A3-4 | ⬜ | - | - | - |
| A4-4 | A4 | 합성 시나리오 7개 유형 | A1-2 | ⬜ | - | - | - |
| A5-1 | A5 | Vertex 가용 모델·지연 실측 | H2 | ⬜ | - | - | - |
| A5-2 | A5 | diff 보고서 #1·개선 작업 등록 | A4-3 | ⬜ | - | - | - |
| A5-3 | A5 | KB 커버리지 매트릭스 → A1 공백 요청 | A1-2 | ⬜ | - | - | - |
| A6-1 | A6 | 체크리스트 v1·레드팀 20건 | S7 | ⬜ | - | - | - |
| A6-2 | A6 | GATE M2 | A4-3 | ⬜ | - | - | - |
| A6-3 | A6 | GATE M3 | M3 | ⬜ | - | - | - |
| A6-4 | A6 | GATE M4 (tc check 15/15 필수) | M4 | ⬜ | - | - | - |
| S8 | SETUP | coord 하드닝: 검증 에이전트 A(적대 감사) 결과 반영 → 패치·selftest·커밋 (SETUP 부재 시 A0 인수) | S7 | 🔄 | - | 검증 A 보고 대기→확인된 구멍만 패치 | 1 |
<!-- SEC:WORK_UNITS:END -->

<!-- SEC:TASKS:BEGIN -->
## TASKS (WU보다 작은 단위·개선 요청, owner만 상태 변경)
| ID | owner | 상태 | 선행 | 제목 | 산출물 | 생성자 |
|---|---|---|---|---|---|---|
<!-- SEC:TASKS:END -->

<!-- SEC:TC_MATRIX:BEGIN -->
## TC_MATRIX — 공개 TC 15건 (A4만 갱신: `coord.py tc set`) · 제출 게이트: `coord.py tc check --build <sha>`
| TC | 제목 | 주요 API | 결과 | 빌드 | 실행 시각 | 실패 원인 | 증거 |
|---|---|---|---|---|---|---|---|
| L-03 | 배송지 변경 요청 | API-11, API-24 | ⬜미실행 | - | - | - | - |
| L-05 | 현금영수증 요청 | API-07, API-32 | ⬜미실행 | - | - | - | - |
| L-11 | 곰팡이 핀 수박 사진과 함께 온 하자 신고 | API-11, 03, 04, 06, 29, 35 | ⬜미실행 | - | - | - | - |
| L-20 | 명령문으로 쿠폰 강제 발급 요구 | (호출 없음) | ⬜미실행 | - | - | - | - |
| L-23 | 타 계정 주문 조회 | API-07, 35 | ⬜미실행 | - | - | - | - |
| L-32 | 상한 상품 주장 뒤 병원비 요구와 여론 압박 | API-07, 11, 35 | ⬜미실행 | - | - | - | - |
| L-33 | 대량 주문 일부만 도착, 잔여분 독촉 | API-11, 35 | ⬜미실행 | - | - | - | - |
| L-34 | 당일배송 불가 안내와 광고 문구 불만 | API-07, 25/27, 35 | ⬜미실행 | - | - | - | - |
| L-40 | 재판매 정황 반복 구매 | API-13(12), 08 | ⬜미실행 | - | - | - | - |
| L-47 | 구매 후 가격 인하 차액 요구 | API-07, 01, 33 (29 금지) | ⬜미실행 | - | - | - | - |
| L-60 | 인플루언서 코드와 다른 할인 중복 요구 | API-20 | ⬜미실행 | - | - | - | - |
| R-05-a | 당도보장 표기 감귤의 신맛 불만 | API-11, 03, 28 | ⬜미실행 | - | - | - | - |
| Y-07-b | 음성으로 온 환불 문의 | API-07, 11 | ⬜미실행 | - | - | - | - |
| Y-16 | 수확·포장 완료 뒤 제주 물류 결항 | API-10/11, 28 | ⬜미실행 | - | - | - | - |
| Y-24 | 판매자 사업자정보 전수 요구 | (호출 없음) | ⬜미실행 | - | - | - | - |
<!-- SEC:TC_MATRIX:END -->

<!-- SEC:RUNLOG:BEGIN -->
## RUNLOG — 실행 장부 (append-only: `coord.py log add`)
| R | 시각 | 에이전트 | 작업 | 결과 | 명령·빌드 | 증거 | 문제·원인 | 조치·재시도 금지 | retry-of |
|---|---|---|---|---|---|---|---|---|---|
| R-001 | 10:31 | SETUP | S0 조사·검증 | ✅성공 | Chrome(TC md·docs·카카오 문서), python 비교, gcloud/date 확인 | docs/PLAN.md 확인된 사실 F1~F13 | gcloud 활성 프로젝트가 다름(F12) | 전용 구성 aitop100만 사용, 기본 구성 변경 금지 | - |
| R-002 | 10:35 | SETUP | S1 .gitignore | ✅성공 | `git check-ignore -v .env` → .gitignore:2 매칭 | .gitignore | HEAD 0ac4fd9에 사용자 .gitignore(.env)가 이미 있음 | 사용자 항목을 포함한 상위 집합으로 작성 | - |
| R-003 | 10:41 | SETUP | S2 AGENTS.md·CLAUDE.md·docs/PLAN.md·보드 부트스트랩 | ✅성공 | Write ×4, cp plan | AGENTS.md, CLAUDE.md, docs/PLAN.md, SHARED_BOARD.md | - | - | - |
| R-004 | 10:41 | SETUP | S5 coord.py·owners.json·훅 모의 테스트 T1~T15 | ✅성공 | scratch/coordtest에서 hook-pre/post, 동시 post 40건, log/tc/wu/handoff/watch | scratch coordtest(일회성) | log add의 --cmd가 서브커맨드 dest와 충돌(KeyError) → dest=command로 수정 후 재검증 | argparse에서 서브커맨드 인자 이름에 cmd를 쓰지 않는다 | - |
| R-005 | 10:46 | A6 | 사전 검증 및 게이트 결함 재현 | ⚠️부분 | Chrome 읽기 전용 확인; python3 release/test_gate_audit.py | release/preflight_audit_20261031.md; release/test_gate_audit.py | 실제 TC 미실행; 모의 보드에서 원문 및 증거 없는 15/15 오통과; 전체 웹 상세 및 음성은 미검증 | A0에 게이트 수정 요청; 독립 전수 확인 필요 | - |
| R-006 | 10:46 | SETUP | S3 docs/contest 원문 분할(v2 기준, 13개 파일) | ✅성공 | python 줄범위 분할(00=1–78,01=79–161,02=162–168+265–330,03=169–183+331–450,04=184–264+451–503,05=504–715,07b=716–1483,10=8928–8962), 06=actions.json, chmod 444 | docs/contest/MANIFEST.sha256 | v1→v2 원본 교체(이미지 내 텍스트 [10] 추가, 줄번호 변경) | 정본은 v2(~/Downloads/aitop100_contest_info_v2.txt). 토큰 줄 195 가림 확인(grep 0건) | - |
| R-007 | 10:46 | SETUP | S4 공개 TC 15건 원문·미디어 2건 저장 | ✅성공 | Chrome fetch /api/contest/test-cases/<ID>/md ×15 → get_page_text → 분할, curl 미디어 2건 | tests/tc/public/MANIFEST.sha256, docs/contest/07_public_tc_index.md | 1차 저장 시 끝 개행(\n\n) 1자 누락 → 길이 불일치 발견 | 원본 끝이 \n\n임을 확인 후 재작성 → 15건 길이·sha256 브라우저 원본과 일치. 재수집 불필요 | - |
| R-008 | 10:47 | A6 | 사전감사 매니페스트 및 장부 대조 | ✅성공 | shasum -a 256 -c docs/contest/MANIFEST.sha256 및 tests/tc/public/MANIFEST.sha256 (각 디렉터리) | release/preflight_audit_20261031.md | 이벤트 #5·#6의 RUNLOG 참조가 동시 기록으로 빗나감; TC 인덱스에 금지·대체 API 혼재 | A0에 이벤트 #7로 정정 요청; 원문 의미별 루브릭 필요 | - |
| R-009 | 10:48 | SETUP | A6 BLOCKER #4 수정: tc check 강화 + 훅 realpath + 영구 selftest | ✅성공 | python3 coord/selftest.py (23건) | coord/selftest_result.txt | tc check가 가짜 15행/원문0/없는 증거에 통과(A6 R-005 재현). selftest 중 /var→/private/var 심볼릭 링크로 훅 경로 비교가 우회되는 결함 추가 발견 | 게이트: git 커밋 SHA·원문↔매트릭스 양방향·중복·MANIFEST 무결성·증거 파일 실재와 내용(ID+SHA) 검증, 예외 없음(U5). 훅: realpath 정규화. 수정 후 selftest 23/23 통과 | - |
| R-010 | 10:56 | SETUP | S6 prompts(_COMMON·A0~A6·HUMAN_GUIDE)+Codex 작업공간(bin/agent·bin/human-watch·AGENTS.md U8·§7)+HUMAN_TODO.md+보드 444 잠금 | ✅성공 | Write prompts/*.md, bin/*, HUMAN_TODO.md; coord.py save()에 chmod 444; relevant()에 HUMAN 필터; selftest 24/24 | prompts/, bin/, HUMAN_TODO.md, coord/selftest_result.txt | - | - | - |
| R-011 | 10:57 | SETUP | S7 훅 deny 실증(claude -p, AGENT_ID=A5) | ❌실패 | claude -p --max-turns 3 --allowedTools Write "<prompt>" | 터미널 출력: Input must be provided… | --allowedTools가 가변 인자라 뒤의 프롬프트까지 도구 이름으로 소비됨 | 프롬프트를 먼저 쓰고 --allowedTools=Write 형식 사용. 같은 인자 순서로 재시도 금지 | - |
| R-012 | 10:57 | SETUP | S7 셋업 실증: AGENTS.md 자동 로드·R1 필독 전 쓰기 deny·보드 직접 편집 deny | ✅성공 | AGENT_ID=A5 claude -p "…" --max-turns 3 --allowedTools=Write,Edit (3회) | 응답: 'U5 (R3) 공개 TC 15건 전수' / 'PreToolUse:Write hook error: 필독 기록 전…' / 'PreToolUse:Edit hook error: SHARED_BOARD.md는 직접 편집 금지…', 파일 미생성·보드 무변경 | - | - | R-011 (프롬프트-옵션 순서 변경(--allowedTools=)) |
| R-013 | 10:58 | SETUP | 07 인덱스 v2: 기대 호출 분류(필수/택1/조건부/금지)·스키마 사실·Y-07-b 음성 전사 반영 | ✅성공 | 검증 에이전트 B 보고(A·B·C) + 원문 직접 대조 → 07 재생성, MANIFEST 재작성(13/13 OK), chmod 444 | docs/contest/07_public_tc_index.md, docs/contest/MANIFEST.sha256 | 구 07의 '기대 API' 열은 정규식 수집이라 L-47 금지 API-29, L-34·L-40·Y-16 택1이 정답처럼 보임(Codex A6·검증 B 동일 지적) | 채점·루브릭은 원문 기대 대응을 정본으로 하고 07 B절 분류를 시드로만 사용. 정규식으로 API 집합을 정답화하지 말 것 | - |
| R-014 | 10:59 | SETUP | A6 BLOCKER #7 재발 방지: wu --record는 존재+본인 R-번호만 허용(--foreign 예외) | ✅성공 | python3 coord/selftest.py (27건) | coord/selftest_result.txt | - | - | - |
<!-- SEC:RUNLOG:END -->

<!-- SEC:READ:BEGIN -->
## READ — 필독 확인 기록 (`coord.py read`)
| 에이전트 | 시각 | 파일(해시 앞 8자리) |
|---|---|---|
| A6 | 10:46 | 00_schedule_overview.md:96af7038, 01_guide_judging.md:e1919f38, 02_story_problem.md:653ee1e4, 03_villager_interview.md:2a3c4407, 04_build_bot_submit.md:380a8418, 05_rules_faq.md:3324b608, 06_action_api_overview.md:82ca82b4, 06b_docs_introduction_page.md:d4f09988, 07_public_tc_index.md:a416798f, 07b_public_tc_rendered.md:56f2a69a, 08_kakao_bot_api.md:d8d49b44, 09_environment.md:4282d543, 10_image_text.md:a2ecd5bf, L-03.md:55d3fa13, L-05.md:48095af3, L-11.md:9a52bdb0, L-20.md:d17d3a8d, L-23.md:0ca798c4, L-32.md:aa8d4ad0, L-33.md:45dae878, L-34.md:d3c8fb55, L-40.md:23a8f7d0, L-47.md:8194bbbc, L-60.md:8a59d6b1, R-05-a.md:1487b555, Y-07-b.md:779e16da, Y-16.md:740351df, Y-24.md:781745b5 |
<!-- SEC:READ:END -->

<!-- SEC:STATUS:A0:BEGIN -->
## STATUS A0 ORCH
(미기동)
<!-- SEC:STATUS:A0:END -->
<!-- SEC:STATUS:A1:BEGIN -->
## STATUS A1 KNOW
(미기동)
<!-- SEC:STATUS:A1:END -->
<!-- SEC:STATUS:A2:BEGIN -->
## STATUS A2 INTEG
(미기동)
<!-- SEC:STATUS:A2:END -->
<!-- SEC:STATUS:A3:BEGIN -->
## STATUS A3 BRAIN
(미기동)
<!-- SEC:STATUS:A3:END -->
<!-- SEC:STATUS:A4:BEGIN -->
## STATUS A4 TEST
(미기동)
<!-- SEC:STATUS:A4:END -->
<!-- SEC:STATUS:A5:BEGIN -->
## STATUS A5 ANALYST
(미기동)
<!-- SEC:STATUS:A5:END -->
<!-- SEC:STATUS:A6:BEGIN -->
## STATUS A6 GATE
(미기동)

### HANDOFF A6-1 2026-10-31 10:47 KST A6
- 상태: 중단(사전 감사 완료, 본격 게이트는 S7과 구현·실행 증거 대기)
- 마지막 성공: R-008 — 원문 13개 및 TC 15개·미디어 2개 매니페스트 해시 검증
- 완료 단계: [x] 사전 조사·게이트 결함 재현·A0 BLOCKER 통보 #4, #7
- 남은 단계(순서대로): 1) S7 완료 및 필독 해시 갱신 2) A0의 게이트 결함 수정 검증 3) A4 실제 TC 15개 결과와 증거 및 릴리스 SHA 감사 4) 레드팀·카카오·인프라 실측과 M2/M3/M4 독립 판정
- 다음 명령(그대로 실행 가능): `AGENT_ID=A6 python3 coord/coord.py status`
- 산출물·증거 경로: release/preflight_audit_20261031.md, release/test_gate_audit.py, R-005, R-008
- 주의·재시도 금지: 사이트는 읽기 전용, 실제 데이터 reset은 A4만; 제출 후 변경 금지; tc check 단독 GO 금지; 공개 TC는 관찰 당시 전부 미실행
<!-- SEC:STATUS:A6:END -->
<!-- SEC:STATUS:SETUP:BEGIN -->
## STATUS SETUP (셋업 실행자 — AGENT_ID 없음)

### HANDOFF S7 2026-10-31 10:59 KST SETUP
- 상태: 진행중
- 마지막 성공: R-013 — 07 인덱스 v2(기대 호출 분류) 반영, READ_AGAIN #15
- 완료 단계: [x] S7-1 AGENTS.md 자동 로드 실증 [x] S7-2·S7-3 훅 deny 실증(R-012) [x] 로컬 커밋 4ae18b7(브랜치 contest/prelim-2026) [x] 검증 B 반영(R-013)
- 남은 단계(순서대로): 1) 검증 에이전트 A(coord 적대 감사) 결과 확인 2) 확인된 구멍 패치 + python3 coord/selftest.py 3) 2차 커밋 4) wu set S7 done + post ALL '셋업 완료' + NEXT를 런타임 순서로 전환
- 다음 명령(그대로 실행 가능): `python3 coord/selftest.py && git -C . status --short`
- 산출물·증거 경로: coord/selftest_result.txt, docs/contest/07_public_tc_index.md, HUMAN_TODO.md, prompts/
- 주의·재시도 금지: claude -p에서 --allowedTools 뒤에 프롬프트를 두지 말 것(R-011). 보드는 444 — chmod로 풀지 말 것

### HANDOFF S2 2026-10-31 10:37 KST SETUP
- 상태: 진행중
- 마지막 성공: R-002 — .gitignore 작성·검증
- 완료 단계: [x] AGENTS.md [x] CLAUDE.md(@AGENTS.md) [x] docs/PLAN.md 복사 [x] 디렉터리 골격 [x] 보드 부트스트랩
- 남은 단계(순서대로): 1) S5 coord.py 2) S3 3) S4 4) S6 5) S7
- 다음 명령: docs/PLAN.md §6.1의 S5 행대로 coord/coord.py를 작성한다
- 산출물·증거 경로: AGENTS.md, CLAUDE.md, docs/PLAN.md, SHARED_BOARD.md
- 주의·재시도 금지: 원문 파일(actions.*)은 수정하지 않는다
<!-- SEC:STATUS:SETUP:END -->

<!-- SEC:EVENTS:BEGIN -->
## EVENTS (append-only: `coord.py post`)
| # | 시각 | from→to | TYPE | 요약 | ref | ack |
|---|---|---|---|---|---|---|
| 1 | 10:37 | SETUP→ALL | DECISION | 보드 부트스트랩. AGENTS.md가 최상위 규칙이다 | AGENTS.md | - |
| 2 | 10:41 | SETUP→ALL | WU | WU S2 ✅ AGENTS.md·CLAUDE.md·docs/PLAN.md·보드 부트스트랩 | R-003 | - |
| 3 | 10:41 | SETUP→ALL | WU | WU S5 ✅ coord.py·owners.json·.claude/settings.json 훅 + 모의 테스트 | R-004 | - |
| 4 | 10:46 | A6→A0 | BLOCKER | tc check가 가상 15개 성공 행에서 원문 0건과 존재하지 않는 증거에도 통과함. 양방향 ID·중복·증거·릴리스 SHA 검증 필요. 실제 TC는 전부 미실행. R-005 | release/test_gate_audit.py | SETUP |
| 5 | 10:46 | SETUP→ALL | WU | WU S3 ✅ docs/contest/00~09(+06b) 원문 분할·토큰 가림·MANIFEST·chmod 444 | R-005 | - |
| 6 | 10:46 | SETUP→ALL | WU | WU S4 ✅ 공개 TC 15건 원문·미디어 2건·07 index·chmod 444 | R-006 | - |
| 7 | 10:47 | A6→A0 | BLOCKER | 보드 이벤트 #5의 S3 ref R-005는 실제 R-006, #6의 S4 ref R-006은 실제 R-007로 불일치. 동시 RUNLOG 추가 시 고정 예상번호 사용 금지. 정정 이벤트 요청. 07 index 기대 API 열에는 L-47 금지 API-29와 대체 API가 섞여 있어 루브릭 주의. | release/preflight_audit_20261031.md | SETUP |
| 8 | 10:48 | SETUP→A6 | INFO | BLOCKER #4 수정 완료(R-009). release/test_gate_audit.py TEST2는 이제 거부됨(스크립트의 assert는 결함 존재를 가정하므로 갱신 필요). coord/selftest.py로 독립 재검증 요청. 계획 충돌 지적 반영: 15/15 예외 없음(U5), A6 프롬프트·PLAN에서 DECISION 예외 삭제 예정 | coord/selftest_result.txt | - |
| 9 | 10:48 | SETUP→ALL | DECISION | D-004 R3 게이트는 예외 없음: tc check 15/15 ✅(릴리스 git SHA·증거 파일 내용 포함)가 아니면 제출 GO 불가 (AGENTS.md U5 우선, A6 지적 반영) | AGENTS.md | - |
| 10 | 10:56 | SETUP→ALL | WU | WU S6 ✅ prompts/_COMMON·A0~A6·HUMAN_GUIDE | R-010 | - |
| 11 | 10:56 | SETUP→HUMAN | HUMAN_TODO | H0 이민준 인터뷰 시작(질문 Q1~Q5, 답은 inbox/interviews/이민준.md) | HUMAN_TODO.md | - |
| 12 | 10:56 | SETUP→HUMAN | HUMAN_TODO | H1 KAKAO_BOT_TOKEN을 .env에 추가 + 웹훅 URL 미등록 확인 | HUMAN_TODO.md | - |
| 13 | 10:56 | SETUP→HUMAN | HUMAN_TODO | H2 gcloud 구성 aitop100·ADC·Vertex API·VM scope 확인 + .env에 GCP_PROJECT·VERTEX_LOCATION | HUMAN_TODO.md | - |
| 14 | 10:57 | SETUP→A0 | INFO | R-011 실패: S7 훅 deny 실증(claude -p, AGENT_ID=A5) | 터미널 출력: Input must be provided… | - |
| 15 | 10:58 | SETUP→ALL | READ_AGAIN | docs/contest/07_public_tc_index.md 갱신(v2: 기대 호출 필수/택1/조건부/금지 분류, 스키마 사실, Y-07-b 전사). 필독 대상자는 다시 읽고 coord.py read 할 것 — 해시 변경으로 쓰기 차단됨 | R-013 | - |
| 16 | 10:58 | SETUP→A6 | INFO | 검증 에이전트 결과: (A) 07 인덱스 오분류 확인→v2로 수정 (B) docs/contest 원문 커버리지 누락 0·actions.json=원문[9] (C) Y-07-b whisper base 전사 확보(07 D절). 독립 재검증 요청 | docs/contest/07_public_tc_index.md | - |
| 17 | 10:59 | SETUP→ALL | DECISION | 정정: 이벤트 #5(S3)의 ref R-005→R-006, #6(S4)의 ref R-006→R-007 (WU 행은 이미 정정됨). 원인: 예상 R-번호를 --record에 사용. 재발 방지: log add가 반환한 번호만 사용 + coord가 타인 소유 R-번호를 --record로 거부하도록 패치 예정. A6 BLOCKER #4·#7 접수·처리 | R-006,R-007 | - |
| 18 | 10:59 | SETUP→A6 | INFO | BLOCKER #7 처리: 정정 이벤트 #17 + coord 패치(wu --record 검증), selftest 27/27 | coord/selftest_result.txt | - |
| 19 | 11:00 | SETUP→ALL | WU | WU S7 ✅ 셋업 검증(/memory·훅·주입)·로컬 커밋 setup·NEXT 전환 | R-012 | - |
| 20 | 11:00 | SETUP→ALL | DECISION | 셋업 완료(S0~S7 ✅). 역할 세션 기동 가능: bin/agent <ID> claude¦codex. 런타임 WU 착수. coord 보강은 S8로 병행(선택적 패치, selftest로 보호) | HUMAN_TODO.md | - |
| 21 | 11:00 | SETUP→HUMAN | HUMAN_TODO | H4 세션 기동 시작 가능: bin/agent A0 claude 부터 (HUMAN_TODO.md ②) | HUMAN_TODO.md | - |
<!-- SEC:EVENTS:END -->
