# kb/ — A1 KNOW 산출물 (계약 C4)
| 파일 | 내용 | 소비자 |
|---|---|---|
| `VERSION` | KB 버전(올릴 때마다 KB_UPDATE 이벤트) | A3·A4·A5 |
| `policy_pack.md` | 프롬프트용 정책 압축본(주제별 규칙·수치·기한·예외·근거 ID, ❓=미확정) | A3 |
| `api_usage.md` | 업무 → API 순서·파라미터·금지 | A3·A4 |
| `facts.jsonl` | 원자 사실 `{id, topic, fact, source_person, quote, as_of, effective_from, effective_until, confidence, conflicts}` | A3·A5 |
| `people.md` | 관계자 지도·채널·발굴률·문서 관리자 | A1·HUMAN |
| `questions/<이름>.md` | HUMAN이 보낼 질문 큐(200자 이하) / `_bank.md` 역할별 질문 은행 | HUMAN |
| `raw/<이름>.md` | 인터뷰 원문 보존본(inbox/interviews 사본) | 감사 |
| `tools/check_kb.py` | 검증기: facts 스키마·인용문 원문 대조, 질문 200자 | 전원 |

- id 규칙: `T-###` = 공개 TC·대회 원문(source_person `tc:<ID>`·`doc:<NN>`), `K-###` = 관계자 진술(source_person = 이름, quote는 kb/raw 원문 그대로).
- confidence: 사실 / 의견 / 추측 / 해석(원문에서 도출한 해석). 추측·의견은 policy_pack에서 사실로 쓰지 않는다.
- 충돌 해소: 공식 문서 > 담당자 진술 > 타인 기억. 미해소는 conflicts에 남기고 질문으로 해결.
