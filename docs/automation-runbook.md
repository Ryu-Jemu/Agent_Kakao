# 자동 문서화 설정과 복구

## 사전 조건

이 기능은 검토된 코드가 main에 병합된 후 동작합니다. 병합은 사용자 승인 대상입니다. 기본 브랜치의 CI 완료 이벤트가 기록 워크플로를 실행합니다. 외부 PR의 코드·의존성·캐시·artifact를 Secrets 권한으로 실행하지 않습니다.

| 설정 | 값 | 위치 |
| --- | --- | --- |
| GITHUB_TOKEN | Actions가 제공 | job의 read 권한만 사용 |
| NOTION_TOKEN | 전용 내부 연결 API token | repository Actions Secret |
| NOTION_PARENT_PAGE_ID | 405abd87-fe45-81fe-b786-c55d929dd654 | repository Variable |
| Notion API version | 2026-03-11 | 검토된 코드에 고정 |
| 허용 상위 프로젝트 | 405abd87-fe45-80ab-9dd5-c430c8dce2e1 | 코드에 고정 |

## Notion 연결

1. [Notion 개발자 설정](https://www.notion.so/profile/integrations) → Internal connections → Create a new connection에서 무찌빠용 연결을 만듭니다.
2. Configuration에서 Read/Insert/Update content를 허용합니다.
3. [전용 기록 페이지](https://app.notion.com/p/405abd87fe4581feb786c55d929dd654) → ••• → Connections → Add connection으로 공유합니다. 프로젝트 루트에는 공유하지 않습니다.
4. API token을 [GitHub Actions Secrets](https://github.com/Ryu-Jemu/Agent_Kakao/settings/secrets/actions)에 `NOTION_TOKEN` 이름으로 저장합니다. 채팅·코드·PR·로그에는 붙여 넣지 않습니다.
5. workflow 실행으로 REST 인증과 쓰기·재조회를 별도로 확인합니다. MCP 쓰기 성공으로 이 검증을 대신하지 않습니다.

[Notion 연결·상속 권한](https://developers.notion.com/guides/get-started/internal-connections), [GitHub Secret 설정](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## 정상 실행과 검증

- PR의 CI는 테스트만 수행합니다. 기록 workflow는 기본 브랜치에서 API 수집기를 실행합니다.
- `workflow_run`은 성공·실패·취소 결과 모두 수집합니다. main push CI는 관련된 병합 PR 기록을 갱신합니다. PR이 없는 초기 push는 기록할 PR이 없음을 표시합니다.
- PR/file/commit/run/job 원본을 조회하며 PR 작성자 설명은 테스트 근거로 간주하지 않습니다.
- CI run의 head SHA와 실제 checkout SHA를 혼동하지 않습니다. 확인할 수 없는 테스트 명령·checkout SHA는 미확인으로 둡니다.
- Notion은 허용 컨테이너의 직접 자식만 생성·수정합니다. 관리용 블록 외 수동 내용은 자동으로 지우지 않으며 구조가 달라지면 중단합니다.
- 성공 로그에서 page URL과 `readback_verified`를 확인하고 GitHub 원본 PR 번호·SHA·파일 수·CI 결론과 대조합니다.
- JSON artifact는 Notion 오류가 있어도 수집까지 성공했다면 저장됩니다. 민감정보 마스킹과 명시적 크기 제한을 적용합니다.

## 재실행

Actions → Record PR evidence in Notion → Run workflow에서 `pr_number`와 해당 `run_id`를 입력합니다. `run_id`를 생략하면 현재 head의 CI run을 조회합니다.

```bash
gh workflow run document.yml --repo Ryu-Jemu/Agent_Kakao \
  --ref main -f pr_number=1 -f run_id=실제_CI_RUN_ID
```

같은 저장소/PR/head SHA의 기록을 갱신합니다. 직렬화는 Actions의 공통 concurrency group에서 수행하므로 별도 로컬 writer를 동시에 실행하지 않습니다. `queue: max`는 최대 100개의 pending run을 보존하며 초과·수동 취소된 실행은 재처리합니다. [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 실패 복구

| 증상 | 조치 |
| --- | --- |
| Missing NOTION_TOKEN | GitHub Secret 이름·존재 확인 후 재실행 |
| Notion 401/403/404 | token 유효성, 페이지 공유, Read/Insert/Update 권한 확인 |
| 허용 부모 불일치 | Variable과 페이지 직접 부모 확인. 다른 페이지로 우회하지 않음 |
| stale CI / PR changed | 현재 head에서 CI를 실행하고 그 run ID로 수집. 과거 결과를 최신 결과로 붙이지 않음 |
| API 429/5xx | 제한된 retry 이후에도 실패하면 원인 해소 후 dispatch |
| 생성 timeout/모호한 결과 | 기존 기록 키를 먼저 찾아 성공 여부 확인. 확인 전 새 페이지 수동 생성 금지 |
| 중복 페이지/관리 블록 구조 변경 | 자동 처리를 중지하고 원본 비교 후 관리자가 조정 |
| 문서화 오류 | PR CI와 별도 실패로 취급. artifact·원본 링크로 증거를 보존하고 재실행 |

이 MVP는 단일 writer와 재조회로 중복을 줄입니다. Notion에 원자적 unique 제약이 없어 모든 외부 동시 쓰기까지 exactly-once를 보장하지 않습니다. 불명확한 생성 결과는 자동 재생성 대신 수동 조정을 요구합니다. 오래된 PR revision의 파일을 복원하는 기능은 없으며 안전하게 중단합니다.

## 승인과 중단

GPT의 PASS는 병합·배포 권한이 아닙니다. `docs/review-template.md`에 PR/SHA별 근거를 작성하고 사용자의 명시적 승인을 받습니다. 배포·LLM 자동 호출은 이 workflow에 없습니다.

자동화를 중단할 때는 해당 workflow를 비활성화하고 필요하면 Notion 연결을 해제합니다. Secret 회전 후 같은 run을 재처리할 수 있습니다. 이미 생성한 기록을 자동 삭제하지 않습니다.

## 설계 선택 근거

`workflow_run`은 병합 전 CI 결과도 기록할 수 있어 기본 경로로 사용합니다. main `push` CI는 병합 결과를 보완하며 `workflow_dispatch`는 복구 경로입니다. trusted main 코드만 실행하고 API 입력을 셸 코드로 해석하지 않습니다. [GitHub 이벤트](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [보안 지침](https://docs.github.com/en/actions/reference/security/secure-use), [Notion API 버전](https://developers.notion.com/reference/versioning).
