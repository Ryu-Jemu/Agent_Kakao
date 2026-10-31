# tests/ — A4 테스트 하네스 (C5)

## 실행
```
uv run --with pyyaml python tests/run.py --set public                  # 15건 전수: reset → 실행 → TC_MATRIX·RUNLOG·TEST_REPORT
uv run --with pyyaml python tests/run.py --set public --tc L-03 --no-reset   # 부분(매트릭스 미갱신)
uv run --with pyyaml python tests/run.py --set synthetic --no-reset    # 합성 16건
옵션: --sim llm|scripted  --jobs 3  --no-judge  --no-record  --out <dir>  --handler echo(건식)
      --build <sha>(커밋 추출 실행, D-009)  --exclude S-SF-02,…(민감 입력 제외)  --lite(시뮬 규칙 기반+판정 1회, D-027 저부하)
```
- reset·15건 전수 기록은 A4만 한다. 다른 세션은 `--no-reset --no-record --out <자기 경로>`.
- redteam은 A6 러너 `release/redteam_run.py`를 쓴다(중복 구현 안 함).

## 구성
| 파일 | 역할 |
|---|---|
| `rubric/<ID>.yaml` | 공개 TC 루브릭(정본=원문 기대 대응). 필드·판정 규칙은 `rubric/README.md` |
| `scenarios/synthetic/*.yaml` | 합성 시나리오(7유형×2+, 메타 없음·인입일 변형·이미지·음성·세션 경계) |
| `run.py` | 러너. 게이트웨이와 같은 sanitize_outputs·50초 안전 타이머, ActionClient 생성자 래핑으로 trace 수집(agent/ 무수정) |
| `sim.py` | 고객 시뮬레이터(LLM gemini-3.6-flash, 실패 시 규칙 기반). 정답(기대 대응)은 보지 않음 |
| `judge.py` | must_say/must_not_say LLM 판정(gemini-3.7-flash). 인용이 봇 발화에 없으면 unverified(미충족) |
| `scoring.py` | 결정적 채점(필수·택1·조건부·금지·대상 외·조기 호출·무호출·접수번호·형식·지연) |
| `selftest_scoring.py` | 채점기 자체 검증(가짜 trace) |
| `tools/probe*.py` | GET 탐침(대상 식별자 확인용, R-018·R-052) |

## 판정
- ❌ fail: 금지 호출, 대상 외 번호 호출, 무호출 TC에서 접수, must_not_say 위반, 500자 초과, 60초 이상
- ⚠️ partial: 필수·택1·조건부 미충족, 고객 확인 전 호출, 접수번호 미안내(원문 요구 시), must_say(expected) 미충족, LLM 판정 불가
- ✅ ok: 위 항목 전부 없음
- 빌드: 봇 경로(agent·integ·kb·deploy·pyproject·uv.lock)에 미커밋 변경이 있으면 `<HEAD>-dirty`로 기록 → `tc check` 통과 불가(릴리스 커밋에서 다시 돌려야 함)

## 환경
- 하네스 LLM 위치는 `A4_VERTEX_LOCATION`(기본 global, D-008). 모델은 `SIM_MODEL`·`JUDGE_MODEL`.
- 산출물 `tests/runs/<ts>/{traces.jsonl, metrics.json, report.md, results.json, <ID>.md}` (gitignore 대상).
