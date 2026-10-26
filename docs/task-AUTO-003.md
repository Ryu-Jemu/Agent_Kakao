# AUTO-003 — 병합 증거 API 호환성 수정

- 목적: 실제 main 병합 CI에서 발생한 잘못된 stale SHA 판정을 해결한다.
- 담당/소유: Codex, automation/cli.py, automation/evidence.py, tests/test_automation.py, 이 문서와 운영 가이드.
- 브랜치: codex/fix-github-api-version. 기준: 4b67649d6d634bc9b0a24a97714521863dab209b.
- 원인: GitHub REST 2026-03-10은 merge_commit_sha를 제거했지만 초기 수집기가 해당 필드를 사용했다. 모의 fixture에 필드가 계속 존재하여 초기 테스트가 호환성 문제를 놓쳤다.
- 근거: 실제 PR #1을 두 API 버전으로 조회해 차이를 재현했고 공식 breaking changes와 일치한다.
- 수정: 지원 중인 2022-11-28로 고정, 필드 누락을 schema 오류로 구분하여 불완전한 병합 기록 생성 차단.
- 수용 기준: HTTP 버전별 응답을 재현한 CLI 테스트 통과, 실제 PR #1/main CI 수집에서 정확한 merge SHA 기록, Python 3.12/3.14 CI 통과.
- 영향: API 읽기 호환성만 변경. 권한·Notion 범위·병합 승인 정책은 동일.
- 미검증: NOTION_TOKEN 미등록으로 REST 쓰기 E2E 대기. PR #1 승인은 이 후속 PR의 승인을 대신하지 않는다.
