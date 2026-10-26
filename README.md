# Agent Kakao · AI TOP 100 2026

AI TOP 100 대회 준비를 위한 개발 및 증거 기록 프로젝트입니다.

GitHub 원본 PR·변경 파일·커밋·CI 결과를 수집하여 지정된 Notion 하위 영역에 기록합니다. 자동화에는 LLM 호출이 없습니다. GPT 평가와 사용자 병합·배포 승인은 별도 단계입니다.

## 시작

Python 3.12 이상에서 추가 패키지 없이 실행합니다.

```bash
python3 -m unittest discover -s tests -v
```

GitHub에서 현재 PR의 증거만 수집하려면 인증된 터미널에서 다음을 실행합니다. 토큰 값은 출력하거나 파일에 저장하지 않습니다.

```bash
export GITHUB_REPOSITORY=Ryu-Jemu/Agent_Kakao
read -rs GITHUB_TOKEN
export GITHUB_TOKEN
python3 -m automation.cli collect --pr 1 --output artifacts/evidence.json
python3 -m automation.cli publish --input artifacts/evidence.json --dry-run
unset GITHUB_TOKEN
```

실제 쓰기는 `NOTION_TOKEN`과 허용된 `NOTION_PARENT_PAGE_ID`가 필요합니다. `publish --dry-run`은 Notion 인증·연결·쓰기 검증을 하지 않습니다.

## 운영 흐름

1. 작업 명세·수용 기준과 파일 소유권을 정합니다.
2. Codex/Claude Code가 브랜치에서 구현하고 PR을 만듭니다.
3. CI가 Python 3.12·3.14에서 테스트합니다.
4. 기본 브랜치의 기록 워크플로가 GitHub API 증거를 수집하여 Notion에 기록합니다.
5. GPT가 원본과 기록을 대조하고 사용자가 다음 행동을 승인합니다.

기록 워크플로는 `main`에 병합된 후 활성화됩니다. 초기 PR의 CI 성공만으로 전체 연동 성공을 주장하지 않습니다. Notion MCP 연결과 Actions용 Notion REST 인증은 서로 별개입니다.

## 문서

- [현재 환경 조사](docs/phase1-audit.md)
- [설정·실행·복구 절차](docs/automation-runbook.md)
- [에이전트 작업 계약](docs/agent-contract.md)
- [GPT 리뷰 템플릿](docs/review-template.md)
- [대회 요구사항과 미확인 항목](docs/contest-requirements.md)
- [Notion 페이지 ID](config/notion-pages.json)

대회 공식 안내: https://aitop100.org/

카카오톡 서버·LLM·배포는 아직 구현하지 않았습니다. 참가자 API 규격과 운영 조건을 확인한 뒤 최소 서버부터 확장합니다.
