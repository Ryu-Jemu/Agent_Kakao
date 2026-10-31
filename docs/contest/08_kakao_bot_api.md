# 08 카카오톡 봇 연동 요약 (원문 아님 — 요약, 출처 URL 명시)
> 읽기 전용(R1). 2026-10-31 10:2x KST Chrome으로 확인. 원문: https://developers.kakao.com/docs/ko/bot/gateway · /bot/webhook · /bot/rest-api · /bot/common

## 수신: 게이트웨이(채택, D-001)
- `wss://bot-gateway.kakao.com/gateway` 연결 → HELLO(op10, `d.heartbeat_interval` 기본 41250ms) → IDENTIFY(op2, `d.token`=봇 인증 토큰) → READY(op3, `d.session_id`) → HEARTBEAT(op1) 주기 전송/HEARTBEAT_ACK(op11) → DISPATCH(op0, `s`,`t`,`d`).
- 마지막 HEARTBEAT 후 90초 이상 없으면 close 4009. 재연결: 1001/네트워크 단절 → RESUME(op6: token, session_id, seq=마지막 s), 4009 → 새 IDENTIFY, 4001(인증)/4003(페이로드)/4004(다른 연결로 대체=중복 연결) → 중단.
- 연결별 최근 100개 이벤트만 보관. 재시도는 지수 백오프(1→2→4…최대 30초).
- **웹훅 URL이 등록돼 있으면 게이트웨이 연결 불가.**
- `t=MESSAGE_CREATE` 의 `d`: `id`(Long, 메시지 구분키), `content`(String, 본문), `timestamp`(ISO-8601), `isChannelChatroom`(Boolean), `botGroupKey`(채팅방), `botUserKey`(발화자), `callbackToken`(선택).
- 기타 이벤트: ENTRANCE, CHAT_JOIN, LEAVE, AD_REWARD. 이미지·음성 전용 필드는 문서에 없음 → 평가 입력은 `content` 텍스트 안의 `image:`/`audio:` URL로 올 것으로 **추정**(공개 TC 원문 형식, docs/PLAN.md F2).

## 응답: 메시지 콜백 API
- `POST https://kapi.kakao.com/v1/bot/callback` 헤더 `Authorization: KakaoAK ${BOT_TOKEN}`, `X-Bot-Callback-Token: ${callbackToken}` (일회성, **5분 후 만료**).
- 본문 `{"skillResponse":{"version":"2.0","template":{"outputs":[{"simpleText":{"text":"..."}}]}}}` — outputs 최소 1·최대 3개. 응답 `{totalCount, sendCount, errorCount}`.
- SimpleText `text` 최대 1,000자(500자 초과 시 '전체 보기'로 접힘). **대회 규정은 말풍선당 500자 이내, SimpleText 이외 응답은 케이스 종료**(01 참조).
- 웹훅 방식일 경우 1초 내 2xx 응답 후 비동기 콜백(참고용, 미채택).
- 쿼터: 메시지 콜백 API 초당 200건, 일 18,000,000건.
- 봇 인증 토큰 위치: 앱 관리 페이지 [제품 설정] > [카카오톡 봇] > [봇].
