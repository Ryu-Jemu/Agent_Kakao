# 작업 계약

이 저장소는 사용자 확정 대상 `Ryu-Jemu/Agent_Kakao`입니다.

- 작업 전에 `docs/agent-contract.md`를 읽고 task ID, 소유 파일, 브랜치, 수용 기준을 기록합니다.
- 구현 에이전트는 승인 없이 PR 병합·배포·주요 저장소 설정 변경을 하지 않습니다.
- 테스트: `python -m unittest discover -s tests -v`.
- Notion 쓰기는 `03_GitHub PR 및 CI 기록`의 지정된 자식 기록으로 제한합니다.
- 토큰을 파일·PR·로그에 기록하거나 사용자에게 채팅으로 요청하지 않습니다.
- CI 성공, GPT 평가, 사용자 승인을 서로 구분합니다.
- Claude Code 실행 없이 내부 병렬 에이전트를 Claude 교차검증으로 표기하지 않습니다.
