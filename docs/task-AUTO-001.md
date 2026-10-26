# AUTO-001 — PR 증거 자동 기록

- 목적: 실제 GitHub API의 PR·파일·커밋·CI 증거를 전용 Notion 자식 기록에 저장.
- 대상: 사용자 확정 `Ryu-Jemu/Agent_Kakao`.
- 브랜치: `codex/documentation-automation`.
- 시작 기준: `9744cda` (README 초기 커밋).
- 담당: Codex. 내부 병렬 구현·문서·독립 리뷰를 사용했으며 Claude Code 실행으로 간주하지 않음.
- 파일 소유: 구현 담당 `automation/**`, `tests/**`; 문서 담당 대회·계약·리뷰 템플릿; 주 에이전트 workflows·설정·나머지 문서. 커밋·push는 주 에이전트만 수행.

## 수용 기준

- 실제 PR 파일·커밋·CI를 API로 수집하며 source revision 변경 시 잘못된 결과를 게시하지 않는다.
- Notion 쓰기는 고정 컨테이너의 관리 페이지로 제한하고 원본 부모와 readback을 검증한다.
- 같은 PR/head의 반복 실행·CI attempt 이력 보존·제목 변경·API 오류·모호한 생성 결과를 테스트한다.
- 외부 PR code/artifact 실행, 자동 LLM 호출, 자동 PASS·병합·배포가 없다.
- 실제 PR CI와 REST→Notion E2E를 별도로 검증하고 미실행은 완료로 표기하지 않는다.

## 로컬 검증

2026-10-26: `python3 -m unittest discover -s tests -v` — 27 tests, OK, Python 3.14.7.
독립 리뷰에서 발견한 CI 이력 덮어쓰기와 제목 변경 후 중복 생성 문제를 수정하고 회귀 테스트로 확인했다.
대기 이벤트의 run attempt도 정확한 API endpoint에 고정한다.

## 미검증·범위 밖

이 기록 작성 시 실제 PR CI·Notion REST E2E는 아직 미실행이다. 결과는 PR 및 Notion 검증 기록에 추가한다.
실제 checkout SHA·개별 테스트 명령은 GitHub job 이름만으로 추정하지 않으며 수집 결과에서 미확인으로 둔다.
카카오톡 서버·배포·유료 LLM·Rulesets 변경은 별도 작업이다. 병합은 사용자 승인 후 수행한다.
