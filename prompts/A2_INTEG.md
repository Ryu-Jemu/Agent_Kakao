# A2 INTEG — 카카오 게이트웨이·액션 API·VM 배포
먼저 `prompts/_COMMON.md`를 읽어라.
[필독] `docs/contest/` 00, 01, 02, 04, 05, 06, 06b, 08, 09 → `python3 coord/coord.py read 'docs/contest/0[0-2]_*.md' 'docs/contest/0[4-6]_*.md' 'docs/contest/06b_*.md' 'docs/contest/0[89]_*.md'`
(`actions.json`은 통독하지 말고 `jq`/python으로 필요한 경로·스키마만 조회한다.)
소유: `integ/`, `deploy/`, `pyproject.toml`, `uv.lock`, `.python-version`
내 WU: A2-1 → A2-2 → A2-3 → A2-4 → A2-5 (선행은 보드 WORK_UNITS 참조)

## 목표
외부 I/O를 빠르고 끊기지 않게 만든다.
- 계약 C2(ActionClient)와 C3(media·local_chat)를 제공한다.
- VM에서 상시 운영(11/1 24:00까지)을 책임진다.

## 작업
1. **A2-1 프로젝트**: uv, Python 3.11 이상. 의존성은 `httpx`, `websockets`, `google-genai`, `python-dotenv` 정도로 최소화한다(e2-micro 1GB).
2. **A2-2 `integ/action_client.py`(C2)**
   - API-01~40과 reset(`reset()`은 `allow_reset=True` 플래그가 있을 때만 = A4 전용)
   - 검색 API는 경로 키에 쿼리가 들어 있으므로 URL을 직접 조립한다(예: `/api/shipments?order_no=…`).
   - 헤더: `Authorization: Bearer $AI_CS_AGENT`, `X-Aitop100-Test-Case-Id`(형식 `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`를 사전 검증).
   - 응답 처리: 본문 없는 404는 None, 빈 검색은 [], 400·401·5xx는 typed 예외. 429면 `Retry-After`만큼 대기하고, 메시지가 '누적 API 호출 한도'면 재시도하지 않는다. 500·503은 1회 재시도한다.
   - **GET 캐시는 TC 범위로만** 둔다. **같은 TC에서 POST(접수)가 한 번이라도 일어나면 그 TC의 GET 캐시를 전부 무효화한다**(접수번호 필드 `refund_ids`·`change_request_ids`·`cancellation_request_ids`가 바뀌기 때문, A6 지적).
   - TC당 호출 상한은 25회(초과하면 예외). 연습 중에는 `.coord/api_rate.json` 파일 잠금으로 여러 프로세스가 60초당 90회를 나눠 쓴다.
   - trace 훅: 호출마다 `{api_id, method, path, params, body, status, ms, cached}`를 남긴다.
   - 완료하면 `coord.py contract --id C2 --text "<시그니처 요약>"`을 실행한다(소비자 ACK 필요).
3. **A2-3 `integ/gateway.py`**: 공식 에코봇 구조(docs/contest/08)를 확장한다.
   - HELLO→IDENTIFY→READY, heartbeat, RESUME, 지수 백오프(최대 30초), close 코드별 처리를 넣는다.
   - MESSAGE_CREATE의 `id`로 중복을 제거한다. 세션 키는 `botGroupKey:botUserKey`이며, 세션 내부는 직렬, 세션끼리는 병렬로 처리한다.
   - `agent.handle_message`(C1) 결과를 **한 번의 callback**에 outputs[simpleText]로 담는다.
   - **콜백은 메시지당 정확히 1회**만 보낸다. 50초 안전 타이머와 정상 응답이 경합하면 먼저 끝난 쪽만 보내고, 나머지는 취소·폐기한다(A6 지적).
   - 각 text는 500자 이하인지 송신 직전에 최종 검사한다. 넘으면 A3 포맷터 결함이므로 로그를 남기고 안전 축약한다.
   - 지연 로그: 수신→콜백 완료 ms, TC id, 말풍선 수·글자 수를 JSON 한 줄로 남긴다(A5 분석용).
   - `integ/media.py`: image·audio URL을 받는다(크기 상한 5MB, timeout 10s, mime 판별: jpg/png, m4a=audio/mp4).
   - `integ/local_chat.py`(C3): 카카오 없이 `handle_message`를 호출하는 REPL이다. `--script <파일>`로 다중 턴 재생도 지원한다.
4. **A2-4 `integ/API_SEMANTICS.md`**: 공개 TC ID로 **GET만** 실측해 필드 의미를 정리한다.
   - 예: shipments `[]`이면 집하 전, READY+invoice면 인수 전, `items[].lot_id`, `payment_refs`→API-17.
   - 실측마다 RUNLOG에 남긴다.
5. **A2-5 배포(`deploy/`)**
   - 대상 VM: `ai-top-100-choonsik`(136.65.54.161, us-central1-a). `CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100 gcloud compute ssh …` 또는 ssh/rsync로 접근한다.
   - 설치: `/opt/choonsik`에 rsync, uv sync. systemd 유닛(`Restart=always`, `RestartSec=2`), journald, `.env` 권한 600, `RELEASE` 파일(git SHA)을 둔다.
   - Vertex 인증은 VM 메타데이터 ADC로 한다. scope·권한이 실패하면 BLOCKER와 HUMAN_TODO(H2)를 올린다.
   - 배포 전에 로컬 게이트웨이 프로세스가 0개인지 확인한다(4004 방지). 웹훅 URL 미등록은 HUMAN이 확인한다.
   - 순서: 에코봇 배포 → HUMAN이 카톡으로 왕복 확인(M1) → A3 빌드 배포(DEPLOY 이벤트, SHA 명시).
6. **내구성 실측**: kill 후 재기동, 네트워크 단절 후 RESUME, VM 재부팅 후 자동 시작, 메모리 사용량. 각각 RUNLOG에 남긴다.

## 금지
웹훅 URL 등록, 로컬 상시 게이트웨이 연결, `agent/` 수정(REQUEST로), 비밀값 로그 출력, M3 이후 HOTFIX 승인 없는 배포, 제출 후 어떤 변경도.
