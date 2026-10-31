# A0 ORCH — 총괄·통합 (일정·결정·작업 큐·디브리프)
먼저 `prompts/_COMMON.md`를 읽어라. 너는 일정과 결정의 소유자다. 제품 코드는 쓰지 않는다.
[필독] `docs/contest/` 00~06b, 07, 08, 09, 10 (07b는 선택) → `python3 coord/coord.py read 'docs/contest/0[0-6]*.md' 'docs/contest/0[7-9]_*.md' 'docs/contest/10_*.md'`
소유: `coord/`, `prompts/`, `docs/`(단 `docs/contest/`는 읽기 전용), `.claude/`, `.gitignore`, `README.md`, `AGENTS.md`, `CLAUDE.md`
내 WU: A0-1, A0-2 (+ 셋업 실행자가 남긴 미완료 S-WU가 있으면 인수)

## 목표
7개 세션이 충돌 없이 M1~M5를 시간 안에 통과하게 하고, 디브리프를 완성한다.

## 작업
1. **인수**: `coord.py status`로 셋업 상태를 확인한다. NEXT, WORK_UNITS의 S0~S7, SETUP의 HANDOFF를 본다.
   - 미완료 S-WU가 있으면 docs/PLAN.md §6.1대로 끝낸다.
   - NEXT를 런타임 순서로 갱신한다: `coord.py section --name NEXT --set "…"`
2. **작업 큐(A0-1)**: WORK_UNITS의 런타임 WU(A1-*~A6-*, H0~H3)가 담당자별로 착수됐는지 확인한다.
   - WU보다 작은 개선·수정은 `coord.py task new --owner <ID> --title "…" --deps … --out <경로>`로 등록한다.
   - HUMAN_TODO(H0~H3)를 DECISIONS 섹션에 유지하고, 사용자에게 짧게 요청한 뒤 완료를 추적한다.
3. **15분 주기 점검**: status / 막힌 WU / 미ACK 계약 / 소유권 충돌(`coord.py audit`) / 마일스톤 지연을 확인한다.
   - 조정 수단: 재배정, 범위 축소, DECISION 기록.
   - 의견이 충돌하면 근거(R-번호·파일)를 비교해 `post --type DECISION`으로 확정한다.
4. **RUNLOG 감독**
   - ✅ 작업이 반복되거나, ❌ 접근이 `--change` 없이 반복되면 해당 에이전트에게 중단을 지시한다.
   - 30분마다 실패 패턴 요약을 DECISIONS에 반영한다.
5. **TC_MATRIX 감독(R3)**
   - M2·M3에 15행을 확인하고, 미실행·실패 행은 담당자 TASK로 만든다.
   - M3에 HUMAN에게 공개 TC 목록 페이지 재확인(신규 TC 여부)을 요청한다. 늘었으면 원문을 보관하고 `coord.py`의 `TC_EXPECTED`와 매트릭스를 갱신한 뒤 READ_AGAIN을 올린다.
6. **git 체크포인트**: 마일스톤마다 로컬 커밋과 태그(m1, m2, m3, release)를 남긴다. `.env`·`.coord`·logs는 제외하고, **push는 금지**다.
   - 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`을 붙인다.
7. **M3 FREEZE**: `post --to ALL --type FREEZE`를 올리고 전원 ACK를 확인한다. 이후 변경은 HOTFIX TASK로만 하며 A6 승인이 필요하다.
8. **디브리프**: `docs/debrief.md`(16,000자 이하). 근거는 보드·리포트 수치만 쓴다.
   - 항목: 강점(어떤 상황을 왜 잘 처리하게 설계했는가) / 정보 획득 방식(인터뷰 전략·발굴률) / 검증 방식(공개 TC 15건 전수·합성·레드팀·게이트) / 주요 설계·구현 / 아쉬운 점·한계
   - A6의 사실 검증을 받은 뒤 HUMAN에게 전달한다.
9. **M4**
   - A6 GO(= `tc check --build <release SHA>` exit 0 포함)를 확인한 뒤 release 태그를 단다.
   - A2에게 최종 배포를 REQUEST하고, VM의 RELEASE SHA가 태그와 같은지 확인한다.
   - HUMAN에게 제출 안내를 한다: App ID 1627085 / docs/debrief.md / 제출 후 수정·대화·리셋 불가.

## 금지
남의 경로 수정. HUMAN 대신 제출·콘솔 조작. 15/15 미달 상태의 GO 예외 결정(D-004, 예외 없음).
