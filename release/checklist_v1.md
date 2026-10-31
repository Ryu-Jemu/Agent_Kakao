# A6 GATE 체크리스트 v1 — 2026-10-31 11:24 KST (coord v2 0e9b8620 반영)

용도: M2(12:50)·M3(13:50)·M4(14:20) 판정에서 항목별로 **명령을 다시 실행**하고 출력·파일·R-번호를 `release/gate_Mx.md`에 붙인다.
- 다른 에이전트의 보고는 재실행 또는 원본 대조로 검증한 뒤에만 인용한다.
- 실행하지 않은 항목은 "미실행"으로 적는다. 통과로 적지 않는다.
- **GO 규칙**: 모든 [필수] 항목이 실측으로 충족돼야 GO다.
  - 특히 `tc check --build <release SHA>`가 exit 0이 아니면 예외 없이 NO-GO다(AGENTS.md U5·D-004).
  - [HUMAN] 항목은 HUMAN의 확인 기록(보드 이벤트 또는 inbox 메모와 시각)이 있어야 충족이다.

표기: ✅ 실측 충족 · ❌ 실측 미충족 · ⬜ 미실행 · ⛔ 선행 대기

주의: `release/logs/` 파일명의 숫자 접미사(예: selftest_1112)는 라벨이며 실행 시각이 아니다. 실행 시각은 각 파일 첫 줄 또는 RUNLOG(R-번호)를 따른다. 11:24 이후 파일명은 `date +%H%M`으로 만든다.

## 1. 게이트 도구 [필수]
| # | 검사 | 명령·방법 | 기준 | 기준선(시각은 RUNLOG 기준) |
|---|---|---|---|---|
| 1.1 | coord 회귀 | `python3 coord/selftest.py` | exit 0, 실패 0 | ✅ 50/50, exit 0 (coord 0e9b8620, R-050, `release/logs/selftest_1132.txt`). 이력: b84538c7 28/28(R-023), 579c3b90 26/28 실패(S8 작업 중간) |
| 1.2 | 적대 감사 | `python3 release/test_gate_audit.py` | N·P 회귀 0, 사유 문자열까지 일치 (exit 0) | ✅ 37건: N·P 31 PASS, W1~W6 모두 의도한 사유로 NO-GO (R-050, `release/logs/gate_audit_v3_run2.txt`). b84538c7에서는 W1~W6이 GO였음(R-025) → S8 v2에서 해소 |
| 1.3 | 판정에 쓰는 coord.py 고정 | `shasum -a 256 coord/coord.py`를 gate 보고에 기록하고, 1.1·1.2와 같은 해시인지 확인 | 해시 일치 | 기준선 0e9b8620… (S8 진행 중이라 바뀌면 1.1·1.2 재실행) |
| 1.4 | `--interim` 금지 | gate 판정에는 `--interim`을 쓰지 않는다. `--interim`은 exit 0이어도 "제출 판정 아님"이다(P4로 확인) | 보고서의 tc check 명령에 `--interim` 없음 | - |

## 2. R3 전수 [필수]
coord v2(0e9b8620)는 아래 2.2~2.6을 도구 안에서 강제한다. A6는 원칙 4(복수 경로)에 따라 도구와 별개의 명령으로 다시 확인한다.

| # | 검사 | 명령·방법 | 기준 |
|---|---|---|---|
| 2.1 | 게이트 | 릴리스 커밋을 체크아웃한 작업트리에서 `python3 coord/coord.py tc check --build <release SHA>` | exit 0, 15/15. coord v2는 `release` 태그=빌드=HEAD를 요구하므로 태그가 먼저 있어야 한다(D-009 순서 충돌 → A0 DECISION 요청 #101) |
| 2.2 | 증거 고유성 | 증거 칸 `경로#해시16` 15개에서 경로·inode·sha256이 서로 다른지 확인 | 중복 0 |
| 2.3 | 증거 위치·고정 | realpath가 `<ROOT>/tests/runs/` 아래이고, 현재 sha256 앞 16자가 칸의 해시와 같은지 확인 | 15/15 |
| 2.4 | 원문 고정 | `git diff --quiet originals-baseline -- docs/contest tests/tc/public actions.json actions.yaml` + MANIFEST 2종 `shasum -c` | 둘 다 rc 0 (11:23 ✅ baseline=676126b, MANIFEST 해시 동일) |
| 2.5 | 릴리스 일치 | `git rev-parse release^{commit}` = `--build`의 전체 SHA = HEAD = VM RELEASE 파일 | 넷 다 같음 |
| 2.5b | 동결 이후 봇 경로 불변(D-034) | `git diff --stat m3 release -- agent integ deploy pyproject.toml uv.lock kb/policy_pack.md kb/api_usage.md kb/VERSION` (FREEZE #456 범위. kb/raw·facts 등은 런타임 미사용) | 비어 있음, 또는 agent/DESIGN.md(#449)·A6가 승인한 HOTFIX만 |
| 2.6 | ID 정확 일치 | 증거 본문에서 `(?<![A-Za-z0-9-])<ID>(?![A-Za-z0-9-])` 검색 | 15/15 |
| 2.7 | 증거 내용 표본 | 무작위 3건(`python3 -c "import random;…"` 시드를 보고에 기록)의 증거와 `tests/runs/<ts>/traces.jsonl`을 대조. 호출 API·파라미터·TC 헤더·말풍선이 일치하는지 본다 | 3/3 일치 |

## 3. 기능 [필수]
| # | 검사 | 방법 | 기준 |
|---|---|---|---|
| 3.1 | 최신 A4 리포트 | `tests/runs/<최신>/report.md`·`metrics.json`·`traces.jsonl`을 직접 읽고 trace로 재계산한다 | forbidden 위반 0, 대상 외 호출 0 |
| 3.2 | required 재현율·must_say 충족률 | 3.1과 같은 파일에서 재계산(A4 수치와 대조) | 15건 모두 required 충족, must_say 미달은 TC별 사유 기록 |
| 3.3 | 직접 재실행 3건 | `tests/run.py --set public --tc <ID>` 3건. 무작위 2건 + 쓰기 포함 1건(L-11·L-47·R-05-a 중). A4와 시간을 조정하고 reset은 A4만 한다 | 판정이 A4 결과와 같음 |
| 3.0 | 실행 유효성 | 판정에 쓰는 run의 빌드가 `<sha>`(dirty 아님, D-009)이고, `agent/logs/turns.jsonl`의 해당 세션에 `llm:` 오류·FALLBACK 응답이 없는지 확인(R-067: us-central1 404로 전 턴 FALLBACK) | dirty 0, LLM 오류 0 |
| 3.4 | 금지 호출 점검 | trace에서 L-47 API-29 0회, L-20·Y-24 호출 0회, 고객이 확인하지 않은 번호로 조회 0회, Y-07-b의 '끝 33' 추측 조회 0회 | 모두 0 |

## 4. 형식·성능 [필수]
| # | 검사 | 방법 | 기준 |
|---|---|---|---|
| 4.1 | 코드: simpleText만 | `integ/gateway.py` `build_body`가 `simpleText`만 만드는지, 다른 템플릿 경로가 없는지(grep `basicCard\|quickReplies\|listCard\|carousel`) | 다른 템플릿 0 |
| 4.2 | 코드: 500자·1~3개 | `sanitize_outputs` 적대 단위 검사(빈 문자열·비문자열·5개·1,200자·이모지 서로게이트) | 출력 1~3개, 각 `kakao_len`≤500, 빈 말풍선 0 |
| 4.3 | 실측: 500자 | 15건 trace와 레드팀의 모든 말풍선 길이 | 최대 ≤500(목표 ≤450) |
| 4.4 | 평균 말풍선 수 | 15건 trace에서 (총 말풍선 ÷ 총 봇 턴) | ≤1.3 |
| 4.5 | p95 지연 | 턴별 지연의 p95(로컬 15건 + VM 카톡 스모크 3건 따로) | 60초 미만 필수, 값 기록 |
| 4.6 | 콜백 중복 0 | VM journald에서 msg_id별 `cb_ok` 수 집계, `stats.dups` 확인 | msg_id당 콜백 정확히 1회 |

## 5. 레드팀 [필수] — `release/redteam/RT-01~25.yaml` (21개 분류)
| # | 검사 | 명령 | 기준 |
|---|---|---|---|
| 5.1 | 시나리오 스키마 | `.venv/bin/python release/redteam_run.py --validate` | 20건 이상, 오류 0 (현재 25건) |
| 5.2 | 러너 판정 자체 검증 | `.venv/bin/python release/test_redteam_runner.py` | exit 0 (현재 13/13, R-037) |
| 5.3 | 실행 | `VERTEX_LOCATION=global .venv/bin/python release/redteam_run.py` → `release/redteam/runs/<ts>/report.md` | **실행 유효성 '유효'** + **누출(LEAK_*) 0, 무단 쓰기(WRITE_UNAUTHORIZED) 0**. 무효 실행(exit 2)은 판정 불가 |
| 5.4 | 부수 신호 | 같은 보고의 CALL_OUT_OF_SCOPE·FORMAT·LATENCY·CRASH·MUST_NOT | 0이 아니면 담당(A3·A2)에 사유와 재현 명령을 첨부 |

- 경로 메모: 러너는 local_chat과 같은 진입점인 C1 `agent.handle_message`를 직접 호출한다. local_chat은 REPL이라 다줄 메타데이터와 자동 판정에 맞지 않는다.
  - 수동 탐색: `.venv/bin/python release/rt_local_chat.py --user rt1`
  - 이 방식은 프롬프트의 "local_chat으로 실행"과 다르므로 gate 보고에 명시한다.
- POST는 모두 서버로 보내지 않고 기록만 한다(공유 액션 데이터 오염 방지). GET은 공개 TC ID로 실서버를 조회한다.

## 6. 인프라 [필수]
| # | 검사 | 방법 | 기준 |
|---|---|---|---|
| 6.0 | VM 환경값 | VM `.env`의 `VERTEX_LOCATION=global`(D-008), 키 이름 목록, `stat -c %a .env`=600. 값은 출력하지 않는다(VERTEX_LOCATION 제외) | global, 600 |
| 6.1 | 서비스·버전 | `CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100 gcloud compute ssh ai-top-100-choonsik --zone us-central1-a -- 'systemctl is-active <svc>; cat <app>/RELEASE'` | active, RELEASE = `git rev-parse release` |
| 6.2 | kill 후 재기동 | `sudo systemctl kill -s KILL <svc>` → 30초 안에 active, journald에서 재연결 확인 | 자동 복구 |
| 6.3 | 재부팅 자동 시작 | `systemctl is-enabled <svc>`. 실제 재부팅은 A0·A2와 시간을 합의한 뒤 1회 | enabled, 재부팅 뒤 active·READY |
| 6.4 | 게이트웨이 재연결 | journald `reconnects`·RESUME·READY 로그 | 끊긴 뒤 재연결 기록 존재 |
| 6.5 | 메모리 여유 | `free -m`, `ps -o rss` (e2-micro 1GB) | 가용 ≥150MB, 스왑 폭주 없음 |
| 6.5b | 자동 업데이트 중지(D-020) | VM `systemctl list-timers apt-daily*`·`is-enabled apt-daily.timer apt-daily-upgrade.timer` | 둘 다 disabled·inactive(11/2까지) |
| 6.5c | LLM 백엔드·warmup(D-029·D-032) | VM `/etc/default/choonsik`·`.env` 키 이름(값 미출력), journald `warmup` 이벤트의 backend·ok, Vertex 폴백 OFF | backend=gemini-api-key만, AGENT_VERTEX_FALLBACK=0, warmup 270s·연속 오류 2회 시 중지, 403·429 반복 없음 |
| 6.5d | 지출 한도(H12b) | 제출 직전 키 프로젝트 사용액·한도(40,000원) 화면 확인(HUMAN), 제출 후 우리 쪽 테스트 호출 0 | 남은 한도로 심사+warmup 충분 |
| 6.6 | 로컬 게이트웨이 0 | 로컬 `pgrep -fl 'integ.gateway'` | 0개(중복 연결 4004 방지) |
| 6.7 | [HUMAN] 웹훅 미등록 | 콘솔 확인 기록 | HUMAN 확인 |
| 6.8 | [HUMAN] 카톡 스모크 3건 | 실기기에서 L-20·Y-24·L-23 첫 메시지 → 응답 수신·체감 지연 기록 | 3/3 수신, 각 60초 미만 |

## 7. 보안·규정 [필수]
| # | 검사 | 방법 | 기준 | 11:19 기준선 |
|---|---|---|---|---|
| 7.1 | 비밀값 미노출 | `.env` 값으로 `git log --all -p`, 작업트리(.git·.venv·.env 제외), 보드를 grep하고 키 이름별 건수만 기록 | 0 | ✅ AI_CS_AGENT·KAKAO_BOT_TOKEN 모두 0 (`release/logs/security_baseline_1120.txt`) |
| 7.2 | 토큰 패턴 | `grep -rIlE 'aitop100_[A-Za-z0-9]{8,}'` (작업트리), VM journald 동일 | 0 | ✅ 0. A6 테스트 픽스처 1건은 문자열 분리로 해소 |
| 7.3 | coord audit | `python3 coord/coord.py audit` | 위반 0 | ❌ exit 1. 문제 1건 = SHARED_BOARD.md 'READONLY 변경!'. A0 #24에서 이미 보고된 audit 오탐. 소유권 위반은 0 |
| 7.4 | push 없음 | `git reflog show --all \| grep push`, 원격 ref 변화 | 규칙 시행(10:37) 이후 push 0 | ✅ 마지막 push는 10:33:43 KST, origin/main 0ac4fd9(.gitignore·README만) |
| 7.5 | `.env` 권한 | 로컬 `ls -l .env`, VM `stat -c %a` | VM 600 필수, 로컬 600 권장 | ⚠️ 로컬 644(HUMAN 소유). VM ⬜ |
| 7.6 | .gitignore | `.env`·`.coord/`·`**/logs/`·`tests/runs/` 포함 | 포함 | ✅ 포함. 단 `**/logs/`·`tests/runs/`가 ignore되므로 증거는 커밋되지 않는다 → gate 보고에 핵심 출력을 인라인한다 |

## 8. 기록 규칙 R1~R3 [필수]
| # | 검사 | 방법 | 기준 |
|---|---|---|---|
| 8.1 | READ 최신성 | 에이전트별 `.coord/read/<ID>.json` 해시와 owners `required_reading` 파일의 현재 sha256 비교(`coord.missing_reading`) | 전원 미기록·변경 0 |
| 8.2 | 원문 무결성 | MANIFEST 2종 `shasum -c` + `git diff --quiet HEAD -- <원문>` | 모두 rc 0 (11:11 ✅ R-026) |
| 8.3 | 미기록 실행 없음 | `tests/runs/*`·`release/redteam/runs/*`·`integ/logs`·`agent/logs`의 산출물 시각과 RUNLOG 시각·증거 경로 대조 | 대응하는 R-번호 없는 실행 0 |
| 8.4 | ❌ 반복 | RUNLOG에서 같은 task가 ❌ 뒤 다시 나온 행에 `--retry-of`·`--change`가 있는지 | 위반 0 |
| 8.5 | 이벤트 ref 무결성 | WU 이벤트의 ref R-번호가 RUNLOG에서 그 WU 담당자의 기록인지 | 불일치 0 |

## 9. 제출 준비 [필수]
| # | 검사 | 방법 | 기준 |
|---|---|---|---|
| 9.1 | [HUMAN] App ID | 콘솔에서 App ID 1627085의 봇이 게이트웨이 연결 봇(「소금빵 먹는 춘식이」)인지 | HUMAN 확인 |
| 9.2 | [HUMAN] 채널 설정 | 채널 공개 ON·검색 허용 OFF·채팅 OFF | HUMAN 확인 |
| 9.3 | 디브리프 사실 | `docs/debrief.md`의 수치·주장을 보드 R-번호·trace와 하나씩 대조 | 근거 없는 주장 0 |
| 9.4 | 디브리프 길이 | `python3 -c "print(len(open('docs/debrief.md',encoding='utf-8').read()))"` | ≤16,000자 |

## 10. HOTFIX(M3 이후)
- 요청마다 다음을 기록하고 승인·거부한다.
  - 변경 파일과 diff 줄 수
  - 영향 TC(15건 중), 회귀 범위(전수 또는 영향 TC 재실행 결과의 R-번호)
  - 레드팀 재실행 여부
  - 되돌리기 방법
- 거부 기준: 영향 범위를 특정할 수 없음, 회귀 증거 없음, 프롬프트·KB 대량 변경, 14:30 이후 비긴급 변경.

## 자동 수집
- `python3 release/gate_collect.py --build <sha> --seed <N>` → 1·2·4·7·8을 다시 실행하고 `release/logs/gate_collect_<HHMM>.md`에 모은다. gate 보고에 인라인한다.
- 판정 문구는 사람이(A6) 쓴다. 수집기 rc는 판정이 아니다. 예: 7.3 audit의 SHARED_BOARD 오탐은 행별로 해석한다.

## 현재 외부 의존(11:24)
- **A3**: `agent/brain.py`가 아직 없어 레드팀(5.3)과 기능(3.x)을 실행할 수 없다.
- **A2**: `integ/local_chat.py`, VM 배포, RELEASE 파일이 아직 없다.
- **A4**: `tests/run.py`, 1차 전수(A4-3)가 아직 없다.
- **A0**: `release` 태그가 없다(`originals-baseline`=676126b는 있음). coord 약점 W1~W6 REQUEST(#31)는 S8 v2에서 해소됐다(R-050).
- **HUMAN**: H2(Vertex)는 미확인이다. `.env`에는 KAKAO_BOT_TOKEN이 있고, GCP_PROJECT·VERTEX_LOCATION은 없다.
