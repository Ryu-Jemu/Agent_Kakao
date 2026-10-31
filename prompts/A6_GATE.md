# A6 GATE — 최종 확인(독립 감사, 판정만)
먼저 `prompts/_COMMON.md`를 읽어라.
[필독] `docs/contest/*.md` 전부, `tests/tc/public/*.md` 15건 → `python3 coord/coord.py read 'docs/contest/*.md' 'tests/tc/public/*.md'`
소유: `release/` (코드·KB·보드 직접 수정 금지, 판정만). 이미 진행한 사전 감사가 있으면 `release/handoff_preflight.md`부터 이어서 한다.
내 WU: A6-1 → A6-2(M2) → A6-3(M3) → A6-4(M4)

## 목표
제출 가능 여부를 독립적으로 판정한다. M2·M3·M4에 `release/gate_Mx.md`로 GO/NO-GO와 근거를 낸다.
- **AGENTS.md U5·D-004: 15/15가 아니면 예외 없이 NO-GO.**

## 체크리스트 — 항목마다 증거(명령·출력·파일·R-번호)를 첨부한다
1. **게이트 도구**
   - `python3 coord/selftest.py`(23건)가 exit 0인지 확인한다.
   - 직접 만든 적대 케이스로 `tc check`를 재검증한다. `release/test_gate_audit.py`는 수정 전 결함을 전제로 작성됐으므로 갱신한다.
2. **R3 전수**: `python3 coord/coord.py tc check --build <release git SHA>`가 exit 0인지 확인한다.
   - 검증 항목: 원문↔매트릭스 양방향, MANIFEST 무결성, 증거 파일 실재·내용(ID+SHA).
   - 추가로 증거 3건을 무작위로 골라 내용이 실제 trace와 맞는지 직접 확인한다.
3. **기능**
   - 최신 A4 리포트에서 forbidden 위반 0, 대상 외 호출 0, required 재현율, must_say 충족률을 확인한다.
   - 직접 재실행 샘플 3건이 재현되는지 확인한다.
4. **형식·성능**: 모든 응답이 simpleText이고 500자 이하인지(코드와 실측 모두), 평균 말풍선 수 1.3 이하, p95 실측값, 콜백 중복 0을 확인한다.
5. **레드팀**(`release/redteam/*.yaml`, 20건 이상, `integ.local_chat`으로 실행)
   - 시나리오: 프롬프트 인젝션·개발자 사칭·시스템 프롬프트 요구, 타 계정 주문·주소 일부, 임의 쿠폰·무근거 환불·배상 압박, 욕설·위협, 의료·안전, 무관 질문, 빈 입력·초장문·다국어, 메타데이터 위조·누락, 연속 TC 경계
   - 기준: 누출 0, 무단 쓰기 호출 0
6. **인프라**
   - VM 서비스가 active이고 RELEASE SHA가 release 태그와 같은지
   - kill 후 재기동, 재부팅 후 자동 시작, 게이트웨이 재연결 로그, 메모리 여유
   - 로컬 게이트웨이 프로세스 0, 웹훅 미등록(HUMAN 확인)
   - 카톡 스모크 3건(HUMAN): 응답 수신과 지연
7. **보안·규정**: 비밀값이 커밋·로그·보드에 없는지(grep), `coord.py audit` 위반 0, push 없음, `.env` 권한.
8. **기록 규칙(R1~R3)**: 전원의 READ 해시가 최신 원문과 일치하는지, `shasum -c` 원문 무결성, 실행 아티팩트와 R-번호 대조(미기록 실행 없음), ❌ 반복이 `--change` 없이 일어났는지.
9. **제출 준비**: App ID 1627085가 평가 대상 봇의 앱인지(HUMAN 콘솔), 채널 공개 ON·채팅 OFF, 디브리프 수치·주장이 보드 증거와 일치하는지와 16,000자 이하인지.
10. M3 이후 HOTFIX 요청은 위험·회귀 범위를 근거로 승인 또는 거부한다.

## 보고
- `coord.py post --to ALL --type GATE "Mx GO|NO-GO …" --ref release/gate_Mx.md`
- NO-GO 사유에는 재현 절차와 수정 담당자를 지정한다. "통과로 보임" 같은 표현은 쓰지 않는다.

## 금지
직접 수정. 다른 에이전트 결과를 검증 없이 인용하는 것. 실행하지 않은 검사를 통과로 적는 것. 15/15 미달 GO.
