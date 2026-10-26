# GPT 증거 검토 템플릿

복사해 작업별로 작성한다. 빈칸은 확인 결과가 아니며, 필요한 증거가 없으면 `미확인` 또는 `미실행`으로 남긴다. 자동 기록 요약뿐 아니라 GitHub 원본과 Notion 재조회 결과를 대조한다.

## 검토 대상

```yaml
task_id:
repository:
pr_number:
pr_url:
base_branch:
head_sha:
tested_sha:
merge_sha: null
implementation_agent:
reviewer:
reviewed_at: # 시간대가 포함된 ISO 8601
workflow_run_url:
run_id:
run_attempt:
notion_record_url:
```

- `head_sha`: 검토한 PR 최신 소스 커밋.
- `tested_sha`: 해당 CI 실행에서 실제 검사한 커밋. `head_sha`와 다르면 PR 병합 검증 커밋인지 등 관계를 설명한다.
- `merge_sha`: 실제 병합된 경우에만 기록한다. 미병합 PR에는 null을 유지한다.
- 검토 시점에 PR이 새 커밋으로 갱신되었는지: `미확인 / 변경 없음 / 변경됨`.
- 원본 재조회 시각 및 조회 방법:

## 원본 증거 대조

| 항목 | GitHub 원본·실행 근거 | Notion 기록 | 일치 여부·누락 |
| --- | --- | --- | --- |
| PR 번호·저장소·SHA | | | |
| 변경 파일·diff | | | |
| CI 실행 ID·attempt·검증 SHA | | | |
| job/step 및 테스트 결과 | | | |
| 병합 상태·merge SHA | | | |
| 기록 생성·갱신 시각 | | | |

CI 근거에는 실행 URL과 실제 job/step 결론을 포함한다. 필요한 경우 로그·테스트 보고서 artifact URL, 명령, 종료 코드, 통과·실패·건너뜀 수를 기록한다. 작성자가 PR에 적은 테스트 결과는 별도 실행 증거가 없으면 자기 보고로 표시한다. 보안정보나 원시 사용자 데이터는 복사하지 않는다.

## 수용 기준별 검증

| 수용 기준 | 확인 방법·명령 | 실제 결과 | 근거 URL·SHA | 충족 여부 |
| --- | --- | --- | --- | --- |
| | | | | 미확인 |

재현 환경(런타임·의존성·설정 이름):

로컬에서만 확인한 결과와 GitHub Actions에서 확인한 결과:

실행하지 못한 검사와 이유:

## 평가

| 항목 | 확인된 사실·근거 | 해석·위험 | 판정 |
| --- | --- | --- | --- |
| 요구사항 충족 | | | |
| 코드 품질 | | | |
| 기능 정확성 | | | |
| 안정성·오류 복구 | | | |
| 보안·권한 범위 | | | |
| 기존 구조와 통합 | | | |
| 증거 충실도 | | | |

확인된 결함:

검증되지 않은 주장·추정:

Claude Code 독립 검증: `미실행 / 실행 근거 있음`. 실행한 경우 버전·명령·검토 대상 SHA·결과를 기입한다. 이 템플릿 작성 시점에는 Claude Code 검증을 실제 수행한 증거가 없다.

## 최종 판정 및 다음 작업

판정: `PASS / REVISE / BLOCKED / NEEDS_DECISION`

판정 이유와 해당 수용 기준:

- PASS: 충족한 기준과 근거, 남아 있는 비차단 위험을 명시한다.
- REVISE: 결함·영향·수정 범위·재검증 방법을 명시한다.
- BLOCKED: 외부 의존성·권한·환경 문제와 해소 주체·조건을 명시한다.
- NEEDS_DECISION: 결정할 내용·대안·비용 또는 범위 영향을 명시한다.

다음 작업 ID·담당 에이전트·소유 파일·수용 기준:

## 사용자 결정 기록

```yaml
decision: "PENDING" # 사용자의 실제 응답 전에는 변경하지 않음
approved_action: null # 예: 특정 PR 병합, 특정 환경 배포
approved_pr_url: null
approved_head_sha: null
target_environment: null
decided_at: null
decision_evidence: null # 실제 사용자 결정의 위치 또는 기록
conditions: []
execution_result: null # 실행 후 원본 링크와 결과
```

PASS는 병합·배포 승인이 아니다. 승인 없이 자동 병합·배포·중요 설정 변경을 진행하지 않는다. PR 커밋 또는 승인 범위가 달라지면 기존 결정을 새 대상에 적용하지 않는다.

## 변경 이유와 영향

리뷰를 실행 증거와 특정 버전에 연결하고, 자동 기록·평가·사용자 승인을 분리하기 위해 추가했다. 템플릿만으로 검토나 사용자 승인이 완료되지 않으며, 자동 실행 설정은 변경하지 않는다.
