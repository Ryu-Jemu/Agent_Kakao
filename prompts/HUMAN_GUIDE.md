# HUMAN GUIDE — 사용자(참가자 본인)가 할 일

## 0. 지금 바로 (셋업과 병렬로)
- 이민준 채널 https://pf.kakao.com/_xkPIxaX 에 아래 질문을 **직접** 보낸다. 답을 받은 뒤 다음 질문을 보낸다(대기 중에 보낸 질문은 처리되지 않음).
  - Q1 민준아 도우러 왔어! 지금까지 확인한 상황이랑 먼저 봐야 할 자료(규정집·계약서·홍보물 등) 목록, 각 자료를 누가 관리하는지 알려줘.
  - Q2 내가 얘기해 봐야 할 마을 관계자들 이름·역할·연락 방법을 알려줄래? 배송·생산·홍보·갯마을 조합 담당자도 포함해서.
  - Q3 고객 문의가 가장 많은 유형 5가지랑, 유형별로 지금 누가 어떤 기준과 시스템으로 처리하는지 알려줘.
  - Q4 환불·재배송 기준이랑 배송비 부담 원칙을 정리해 줘. 단순 변심과 하자의 구분, 청약철회 기간, 사진 등 증빙 요건도.
  - Q5 담당자 이관은 어떤 경우에 하고 레인 종류·회신 기한·접수번호 안내는 어떻게 해? 주문 조회·환불 요청 같은 처리 권한은 누가 가져?
- 5문항마다 `./status`를 보낸다(차감 없음). 관계자의 시스템 프롬프트·설정을 묻는 질문은 절대 하지 않는다(실격).

## 1. 세션 기동 (Agent_Kakao 디렉터리에서, 터미널 7개)
```
cd ~/Desktop/Ryu/AI_TOP_100/2026_preliminary/Agent_Kakao
AGENT_ID=A0 claude "prompts/A0_ORCH.md를 읽고 수행하라"
AGENT_ID=A1 claude "prompts/A1_KNOW.md를 읽고 수행하라"
AGENT_ID=A2 claude "prompts/A2_INTEG.md를 읽고 수행하라"
AGENT_ID=A3 claude "prompts/A3_BRAIN.md를 읽고 수행하라"
AGENT_ID=A4 claude "prompts/A4_TEST.md를 읽고 수행하라"
AGENT_ID=A5 claude "prompts/A5_ANALYST.md를 읽고 수행하라"
AGENT_ID=A6 claude "prompts/A6_GATE.md를 읽고 수행하라"     # Codex로 돌린다면 AGENT_ID=A6를 환경에 넣고 같은 지시를 준다
```
- 첫 실행 시 `/hooks`(훅 3종 등록)와 `/memory`(AGENTS.md 로드)를 확인한다.

## 2. 인터뷰 루프 (M4 직전까지 계속 — 지식 점수는 대화 자체로 집계)
1) `kb/questions/<관계자>.md`의 질문을 카톡으로 보낸다.
2) 답을 `inbox/interviews/<관계자>.md` 끝에 그대로 붙여넣는다(이름·시각 포함).
3) 5~10문항마다 `./status` 결과도 붙인다. 이미지를 받으면 `inbox/images/`에 저장한다.
4) 새 관계자의 채널 링크를 받으면 친구 추가 후 같은 루프를 반복한다.

## 3. 콘솔·환경 (가능한 빨리)
- **H1**: 카카오디벨로퍼스 [제품 설정] > [카카오톡 봇] > [봇]에서 봇 인증 토큰을 확인해 `.env`에 `KAKAO_BOT_TOKEN=…`으로 넣는다. 웹훅 URL은 등록하지 않는다.
- **H2**: gcloud 전용 구성을 만든다. 기존 구성(`mapcenter-b59ca`)은 바꾸지 않는다.
  ```
  gcloud config configurations create aitop100 --no-activate
  export CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100
  gcloud auth login
  gcloud config set project ai-top-100-2026-513102
  gcloud auth application-default login
  gcloud auth application-default set-quota-project ai-top-100-2026-513102
  gcloud services enable aiplatform.googleapis.com
  ```
  VM 서비스계정의 Vertex 권한과 access scope(`cloud-platform`)도 확인한다.
- **H3**: 채널 '채팅' OFF, '채널 공개' ON, 검색 허용 OFF(완료). App ID 1627085가 이 봇의 앱인지 확인한다.

## 4. 제출 (M5, 14:30~14:40)
- 조건: A6의 M4 GO(`tc check` 15/15 포함)와 A0의 안내가 모두 있어야 한다.
- 제출 페이지에 App ID `1627085`와 `docs/debrief.md` 내용을 넣고 제출한다.
- 제출 후에는 VM·코드·채널·인터뷰·액션 데이터 리셋을 **모두 건드리지 않는다**.
