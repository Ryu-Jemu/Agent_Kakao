#!/usr/bin/env python3
"""A5-3 KB 커버리지 매트릭스 — 응대에 필요한 지식 단위(K)를 kb/facts.jsonl 근거와 자동 대조한다.

사용: python3 analysis/kb_coverage.py            → analysis/kb_coverage.md 갱신 + 요약 출력
      python3 analysis/kb_coverage.py --json     → 요약 JSON만 출력

판정 규칙(자동 — 사람이 매칭 fact를 확인할 것)
- K마다 regex 묶음 목록(any-of)을 둔다. 한 묶음의 regex가 '한 fact' 안에서 전부 맞으면 그 fact가 근거다.
- 근거 fact가 있으면 ✅, 없으면 ❌(공백). source_person이 tc:/doc:이면 '원문', 그 밖이면 '인터뷰'.
- 공백 K는 A1 질문 은행(kb/questions/*.md)의 질문 ID와 연결한다. 연결 질문이 없으면 '신규 제안'을 단다.
- K의 근거(need)는 공개 TC 원문 '상황'·'기대 대응' 또는 docs/contest/01 심사 유형이다.
"""
import argparse
import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))

# (id, 영역, 필요한 지식, 필요 근거, 영향, regex 묶음들, 연결 질문, 신규 제안)
# 영향: A=공개 TC 기대 대응이 그 값/규칙을 직접 요구, B=심사 유형(doc:01)·API 사용 규칙, C=보조
K = [
    # ---- 공개 TC 직접 요구
    ("K01", "배송지변경", "배송 건 없음=집하 전 → 배송지 변경 접수 가능", "L-03 상황", "A", [["집하 전", "배송지 변경"]], [], ""),
    ("K02", "배송지변경", "동·호수 상세주소를 받아 접수", "L-03 기대3", "A", [["동·호수|상세주소"]], [], ""),
    ("K03", "배송지변경", "집하 후 배송지 변경 가능 여부·재배송비 부담", "QD4 범위(합성 변형)", "B", [["집하 (후|이후)", "배송지"]], ["QD4", "Q13"], ""),
    ("K04", "현금영수증", "발행 대상(현금·계좌이체)·기한(익월 10일)", "L-05 상황", "A", [["현금영수증", "다음 달 10일|익월 10일"]], [], ""),
    ("K05", "현금영수증", "주문 조회→승인번호→결제 조회로 결제수단 확인", "L-05 상황", "A", [["승인번호", "API-17|결제 조회"]], [], ""),
    ("K06", "현금영수증", "발행 구분(소득공제·지출증빙) 확인", "L-05 기대1", "A", [["소득공제", "지출증빙"]], [], ""),
    ("K07", "환불·하자", "위생 위해 하자: 섭취 중단·폐기·반송 불요·재배송/전액환불", "L-11 상황", "A", [["곰팡이|부패", "반송"]], [], ""),
    ("K08", "환불·하자", "하자 신고 시 사과 + 섭취 여부·몸 상태 확인", "L-11 기대1", "A", [["섭취 여부|먹었는지", "몸"]], [], ""),
    ("K09", "에스컬레이션", "동일 로트 복수 신고·조사 미개시 → LANE2_HANDOFF", "L-11 기대5", "A", [["로트", "LANE2"]], [], ""),
    ("K10", "에스컬레이션", "LANE2_HANDOFF 회신 기한 **값**", "L-11 기대6·L-34 기대6 ('회신 기한을 안내')", "A",
     [["LANE2", r"회신.{0,15}\d+\s*(영업일|시간|일)"], [r"(HANDOFF|담당자 확인).{0,60}회신.{0,15}\d+\s*(영업일|일|시간)"]], ["Q5", "Q7"], ""),
    ("K11", "환불", "전액환불 금액 산정 범위(상품가·배송비·쿠폰·적립금)", "L-11 기대4(amount=34900)", "B",
     [["전액환불", "배송비|쿠폰|적립금", "금액|포함"]], ["Q8"], "N1"),
    ("K12", "프로모션", "쿠폰 발급 권한·범위(임의 생성·무제한 불가)", "L-20 상황", "A", [["임의", "무제한"]], [], ""),
    ("K13", "프로모션", "현행 혜택 목록(신규 3,000·SUBAK15·단골 5%·REFER5000)", "L-20 기대4", "A", [["3,000", "SUBAK15", "5%"]], [], ""),
    ("K14", "개인정보", "타 계정 주문: 귀속 확인 후 안내 거절·LANE2 이관", "L-23 상황·기대", "A", [["계정", "접근권|귀속"]], [], ""),
    ("K15", "배상", "섭취 피해: 원물 보관·촬영, 하자 확인 시 환불, 인과 확인 후 배상", "L-32 상황", "A", [["인과", "배상"]], [], ""),
    ("K16", "에스컬레이션", "배상 이관 회신 기한 영업일 3일", "L-32 상황", "A", [["영업일 3일"]], [], ""),
    ("K17", "배상", "진단서·진료비 영수증 요구", "L-32 기대1", "A", [["진단서", "영수증"]], [], ""),
    ("K18", "배송", "대량 주문 분할 배차·우선배송·LANE2 긴급 이관", "L-33 상황", "A", [["분할", "배차|배송"]], [], ""),
    ("K19", "배송", "정기 출고 요일 **값**", "L-33 기대5 ('정기 출고 요일을 말하더라도' — 언급은 선택)", "B",
     [["정기 출고", "[월화수목금토일]요일"]], ["QD1"], ""),
    ("K20", "배송", "당일배송 불가·익일~모레 도착·도착일 보장 불가", "L-34 상황", "A", [["당일배송", "익일"]], [], ""),
    ("K21", "배송", "출고 마감 시각(몇 시 주문까지 익일 출고)", "L-34 기대3(출고 예정 일정 안내)", "B",
     [["마감", r"\d+\s*시"]], ["QD1"], ""),
    ("K22", "홍보물", "「빠른 배송」 배너 책임=조합, 제작자 홍보라", "L-34 상황", "A", [["빠른 배송", "홍보라"]], [], ""),
    ("K23", "도매·재판매", "도매 판정 기준 **값**(물량·횟수·기간)", "L-40 상황('최근 2주 사이 비슷한 물량 여러 번')", "B",
     [["도매", r"\d+\s*(통|회|건|주|일)"]], ["QC1"], ""),
    ("K24", "도매·재판매", "소매 혜택 제한 + 사업자 도매 절차(단가·세금계산서·거래처 등록)", "L-40 기대3~5", "A",
     [["도매", "세금계산서", "거래처"]], [], ""),
    ("K25", "가격인하보상", "7일 이내 정상가 인하 → 차액 이상 최소 쿠폰·90일", "L-47 상황", "A", [["7일", "90일", "쿠폰"]], [], ""),
    ("K26", "가격인하보상", "CARE 보상 쿠폰 금액 종류(CARE5000 외)", "L-47 변형 대비(L-47 자체는 CARE5000을 명시)", "B",
     [["CARE(?!5000)\\d+"], ["CARE", "종류|단위|3,000|10,000"]], ["Q9"], ""),
    ("K27", "프로모션", "할인 코드 주문당 1개·보상 쿠폰 병용·SUBAK15≠조합원 5%", "L-60 상황", "A", [["주문당 하나|주문당 1", "보상 쿠폰"]], [], ""),
    ("K28", "환불·하자", "당도보장 미달=하자 → 재배송/환불 선택", "R-05-a 상황", "A", [["당도", "재배송"]], [], ""),
    ("K29", "상품", "상품별 당도보장 기준값(감귤 12브릭스 외)", "R-05-a 변형 대비", "B", [["브릭스", "(수박|망고|애플망고|한라봉|천혜향)"]], ["QP1"], ""),
    ("K30", "청약철회", "수령 7일 이내·하자=배송비 무료·변심=왕복 배송비 고객", "Y-07-b 기대5", "A", [["7일", "왕복 배송비"]], [], ""),
    ("K31", "배송비", "기본·반품 왕복 배송비 **금액**, 무료배송 기준", "Y-07-b 기대5(변심 시 비용 안내)", "B",
     [["배송비", r"\d[\d,]*\s*원"]], ["Q4"], "N2"),
    ("K32", "배송", "결항 시: 사유·재개 시점 안내 → 재출고/전액환불 선택·재수확분 교체", "Y-16 상황", "A", [["결항", "재수확"]], [], ""),
    ("K33", "배송", "결항 정보 출처·예상 재개 시점 확인 방법", "Y-16 기대2", "B", [["결항", "재개", "기상|운항|확인"]], ["QD3"], ""),
    ("K34", "판매자정보", "안내 범위=공시 항목, 개인 배경·매입가 제외", "Y-24 상황", "A", [["공시", "제3자"]], [], ""),
    ("K35", "판매자정보", "공시 **값**(상호·대표자·사업자등록번호·통신판매업 번호·주소·전화·이메일)", "Y-24 기대2~4", "A",
     [[r"\d{3}-\d{2}-\d{5}"], ["사업자등록번호", r"\d{3}-?\d{2}-?\d{5}"]], ["Q6", "QC5"], ""),
    # ---- 심사 유형(doc:01)·API 사용 규칙 — 공개 TC에 없음
    ("K40", "에스컬레이션", "레인 체계 전체(LANE2·LANE3 외 레인과 사용 조건)", "doc:06 'lane 자유 문자열' + L-32 택1", "B",
     [["LANE1|LANE4|LANE0"], ["레인", "종류|체계|개"]], ["Q5", "Q7"], ""),
    ("K41", "계정", "회원가입 후 로그인 불가 처리 절차", "doc:01 심사 유형", "B", [["로그인", "안 되|불가|비밀번호|재설정"]], ["Q10"], ""),
    ("K42", "개인정보", "개인정보 변경 요구: 본인확인·변경 가능 항목·채널", "doc:01 심사 유형", "B", [["개인정보|회원정보", "변경", "본인"]], ["Q10"], ""),
    ("K43", "상품", "상품 정보(품종·보관법·섭취 시기·등급)", "doc:01 심사 유형", "B", [["보관(법|방법|요령)|먹기 좋은|섭취 시기|숙성|품종"]], ["QP3", "QS1"], ""),
    ("K44", "응대", "화난 고객 응대 원칙·보상 쿠폰 지급 기준(예: 안내 지연 3,000원)", "doc:01 심사 유형 + L-60 '지난번 안내 지연 보상 쿠폰'", "B",
     [["보상 쿠폰", "지급 기준|지급 조건|지급한다|줄 수 있|한도"], ["화난|분노|욕설|폭언"]], ["Q11"], "N3"),
    ("K45", "안전", "안전/예외(알레르기·이물질·영유아·임산부 등) 1차 안내와 이관", "doc:01 심사 유형", "B",
     [["알레르기|이물|영유아|어린이|임산부"]], [], "N4"),
    ("K46", "수산물", "갯마을 수산물 하자·환불·책임 구분", "doc:02 위탁 공급", "B", [["수산물|갯마을", "환불|하자|책임"]], ["QS2", "QS3"], ""),
    ("K47", "결제", "카드 취소(API-31) 가능 시점·부분취소", "API-31", "B", [["카드 취소|취소 접수", "출고|시점|전"]], ["Q8"], ""),
    ("K48", "환불", "환불 처리 소요 기간", "환불 문의 공통", "B", [["환불", r"\d+\s*(영업일|일)", "입금|소요|걸"]], ["Q8"], ""),
    ("K49", "구독", "정기구독 건너뛰기·해지(API-40 SKIP/CANCEL) 조건", "API-19·40", "B", [["구독", "건너뛰|해지|SKIP|CANCEL"]], ["Q12"], ""),
    ("K50", "회수", "픽업 접수(API-38) trigger·cost_bearer 판단", "API-38", "B", [["픽업|회수", "부담|cost_bearer|SELLER|CUSTOMER"]], ["Q13"], ""),
    ("K51", "재배송비", "재배송비 청구(API-37) 조건·금액", "API-37", "B", [["재배송비", "청구|부담"]], ["Q13", "QD4"], ""),
    ("K52", "주문", "주문 복구(API-22)·품목 변경(API-23) 조건", "API-22·23", "B", [["주문 복구|품목.*변경|수량 변경"]], ["Q12"], ""),
    ("K53", "상품", "재입고 알림(API-39)·재고(API-21) 안내", "API-21·39", "B", [["재입고|재고"]], ["Q12"], ""),
    ("K54", "적립금", "적립금 적립·유효기간·사용 규칙(API-15)", "API-15", "B", [["적립금", "유효기간|소멸|적립률|사용 (조건|규칙|한도)|1원|%"]], ["Q8"], ""),
    ("K55", "체험", "체험 행사 예약·취소·환불", "doc:02 체험 행사 운영", "C", [["체험", "예약|취소|환불"]], ["QH5"], ""),
    ("K56", "운영", "영업일 정의(주말·공휴일)·상담 운영 시간 — 회신 기한 날짜 계산용", "L-32 '영업일 3일'을 날짜로 말할 때(선택)", "B",
     [["영업일", "주말|토요일|공휴일|제외"], ["운영 시간|상담 시간", r"\d+\s*시"]], [], "N5"),
    ("K57", "조합원", "조합원 등급(일반·단골)·가입 조건", "L-20·L-60 '단골 5%·조합원 할인'", "B", [["조합원", "가입 (조건|절차|방법)|등급 기준|등급은|가입하려면"]], ["QC3"], ""),
    ("K58", "유입", "유입태그(API-09)·인플루언서 공구 주문 식별", "API-09 + L-60", "C", [["유입태그|inflow"]], ["QH3"], ""),
]

# 신규 제안 질문(A1 은행에 대응 질문이 없는 공백). 200자 이하, 시스템 프롬프트·설정 질의 아님.
NEW_Q = {
    "N1": ("이민준(정산)", "전액환불할 때 배송비랑 쓴 쿠폰·적립금은 어떻게 돌려줘? 부분환불은 금액을 어떻게 계산하는지도 알려줘."),
    "N2": ("이민준 → 배송 담당", "기본 배송비, 반품 왕복 배송비가 각각 얼마야? 무료배송 기준 금액이나 제주·도서산간 추가비도 있으면 알려줘."),
    "N3": ("이민준", "크게 화난 고객은 어떻게 응대해? 안내 지연 보상 쿠폰 3,000원 같은 보상은 어떤 경우에 얼마까지 줄 수 있고 누가 정해?"),
    "N4": ("이민준 → 생산자", "알레르기·이물질 발견·아이가 먹고 탈 난 경우처럼 안전 문제가 생기면 고객에게 먼저 뭘 안내하고 누구에게 넘겨?"),
    "N5": ("이민준", "회신 기한을 영업일로 셀 때 주말·공휴일은 빼? 상담 운영 시간이랑 6~7월에 쉬는 날이 있으면 알려줘."),
}

# 공개 TC → 필요한 K
TC_NEED = {
    "L-03": ["K01", "K02"], "L-05": ["K04", "K05", "K06"], "L-11": ["K07", "K08", "K09", "K10"],
    "L-20": ["K12", "K13"], "L-23": ["K14"], "L-32": ["K15", "K16", "K17"],
    "L-33": ["K18"], "L-34": ["K20", "K22", "K10"], "L-40": ["K24"], "L-47": ["K25"],
    "L-60": ["K27"], "R-05-a": ["K28"], "Y-07-b": ["K30"], "Y-16": ["K32"], "Y-24": ["K34", "K35"],
}


def load_facts():
    out = []
    for line in open(os.path.join(ROOT, "kb/facts.jsonl"), encoding="utf-8"):
        if line.strip():
            f = json.loads(line)
            f["_text"] = " ".join(str(f.get(x, "")) for x in ("topic", "fact", "quote"))
            out.append(f)
    return out


def bank_ids():
    ids = {}
    for p in glob.glob(os.path.join(ROOT, "kb/questions/*.md")):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"\s*- \[( |x)\] (Q[A-Z]?\d+)", line)
            if m:
                ids[m.group(2)] = (os.path.basename(p), m.group(1) == "x")
    return ids


def evaluate(facts):
    res = {}
    for kid, area, need, why, imp, groups, qs, nq in K:
        hits = []
        for f in facts:
            for g in groups:
                if all(re.search(rx, f["_text"]) for rx in g):
                    hits.append(f)
                    break
        src = sorted({"원문" if str(f.get("source_person", "")).startswith(("tc:", "doc:")) else "인터뷰" for f in hits})
        # 'conflicts'가 있거나 '미확인' 표기 fact만 있으면 부분
        # '모르는 것·미확인·확인해야' 기록은 공백이 확인됐다는 뜻이지 근거가 아니다 → ⚠️
        only_unconfirmed = hits and all(re.search("미확인|모르는|모름|확인해야", f["fact"]) for f in hits)
        st = "❌" if not hits else ("⚠️" if only_unconfirmed else "✅")
        res[kid] = {"status": st, "facts": [f["id"] for f in hits], "src": src}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    facts = load_facts()
    res = evaluate(facts)
    bank = bank_ids()
    kb_ver = open(os.path.join(ROOT, "kb/VERSION")).read().strip() if os.path.exists(os.path.join(ROOT, "kb/VERSION")) else "?"
    n_int = sum(1 for f in facts if not str(f.get("source_person", "")).startswith(("tc:", "doc:")))
    tot = len(K)
    cov = sum(1 for k in K if res[k[0]]["status"] == "✅")
    a_tot = [k for k in K if k[4] == "A"]
    a_cov = sum(1 for k in a_tot if res[k[0]]["status"] == "✅")
    b_tot = [k for k in K if k[4] != "A"]
    b_cov = sum(1 for k in b_tot if res[k[0]]["status"] == "✅")
    tc_full = {tc: all(res[k]["status"] == "✅" for k in ks) for tc, ks in TC_NEED.items()}
    summary = {"at": datetime.now(KST).isoformat(timespec="minutes"), "kb_version": kb_ver, "facts": len(facts),
               "interview_facts": n_int, "K_total": tot, "K_covered": cov, "A_total": len(a_tot), "A_covered": a_cov,
               "B_total": len(b_tot), "B_covered": b_cov,
               "tc_fully_covered": sum(tc_full.values()), "tc_gaps": [tc for tc, ok in tc_full.items() if not ok]}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False))
        return

    L = []
    L.append("# A5-3 KB 커버리지 매트릭스")
    L.append("> 생성: %s · `python3 analysis/kb_coverage.py`(다시 돌리면 갱신) · KB VERSION `%s` · facts %d건(인터뷰 출처 %d건)" % (
        summary["at"], kb_ver, len(facts), n_int))
    L.append("> 판정은 regex 자동 대조다. ✅=근거 fact 있음, ⚠️=근거 fact가 '미확인' 표기뿐, ❌=공백. 매칭 fact ID를 사람이 확인할 것(오탐·누락 가능).")
    L.append("")
    L.append("## 요약")
    L.append("| 지표 | 값 |")
    L.append("|---|---|")
    L.append("| 지식 단위 K 전체 | %d개 중 ✅ %d (%.0f%%) |" % (tot, cov, 100.0 * cov / tot))
    L.append("| A등급(공개 TC 기대 대응이 직접 요구) | %d개 중 ✅ %d |" % (len(a_tot), a_cov))
    L.append("| B·C등급(심사 유형 doc:01·API 사용 규칙·변형 대비) | %d개 중 ✅ %d |" % (len(b_tot), b_cov))
    L.append("| 공개 TC 15건 중 필요 K가 전부 ✅인 TC | %d건 · 공백 TC: %s |" % (summary["tc_fully_covered"], ", ".join(summary["tc_gaps"]) or "없음"))
    L.append("| 인터뷰 출처 fact | %d건 (나머지는 TC·대회 문서 원문 출처) |" % n_int)
    L.append("")
    L.append("**해석**")
    L.append("- 사실: 현재 ✅는 거의 전부 공개 TC '상황' 문장 출처다. 공개 TC는 기대 대응을 이미 알려 주므로 같은 TC에서는 정확도가 높게 나온다.")
    L.append("- 해석: 심사는 약 30개 시나리오다(doc:01). 공개 TC 밖의 유형(로그인·개인정보 변경·상품 정보·화난 고객·안전, B등급)은 인터뷰 근거가 없으면 정책 추론에 맡겨진다. 그래서 공개 TC 점수만으로는 과적합 위험을 판단할 수 없다.")
    L.append("- 추정: TC ID 번호(L-60, Y-24 등)를 보면 비공개 케이스 풀이 공개 15건보다 훨씬 크다. 이것은 근거가 제한된 추정이다.")
    L.append("")
    L.append("## 1. 공개 TC → 필요한 지식 단위")
    L.append("| TC | 필요 K | 상태 |")
    L.append("|---|---|---|")
    for tc, ks in TC_NEED.items():
        L.append("| %s | %s | %s |" % (tc, " ".join("%s%s" % (k, res[k]["status"]) for k in ks), "✅" if tc_full[tc] else "❌ 공백"))
    L.append("")
    L.append("## 2. 지식 단위 매트릭스")
    L.append("| K | 등급 | 영역 | 필요한 지식 | 필요 근거 | 상태 | 근거 fact | 출처 | A1 질문 연결 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for kid, area, need, why, imp, groups, qs, nq in K:
        r = res[kid]
        qtxt = []
        for q in qs:
            if q in bank:
                qtxt.append("%s%s(%s)" % (q, "✔전송" if bank[q][1] else "", bank[q][0].replace(".md", "")))
            else:
                qtxt.append("%s(은행에 없음)" % q)
        if nq:
            qtxt.append("**신규 %s**" % nq)
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            kid, imp, area, need, why, r["status"], ",".join(r["facts"][:4]) + ("…" if len(r["facts"]) > 4 else "") or "-",
            "/".join(r["src"]) or "-", " ".join(qtxt) if r["status"] != "✅" else "-"))
    L.append("")
    gaps = [k for k in K if res[k[0]]["status"] != "✅"]
    L.append("## 3. 공백 우선순위 (A1 REQUEST 대상)")
    L.append("우선순위 = 등급(A > B > C) → 영향을 받는 공개 TC 수. **A등급 공백은 공개 TC 기대 대응 문장이 그 값을 직접 요구하는데 KB에 값이 없는 경우다.**")
    L.append("")
    L.append("| 순위 | K | 등급 | 공백 | 영향 TC | 질문 경로 |")
    L.append("|---|---|---|---|---|---|")
    tc_of = {}
    for tc, ks in TC_NEED.items():
        for k in ks:
            tc_of.setdefault(k, []).append(tc)
    gaps.sort(key=lambda k: ({"A": 0, "B": 1, "C": 2}[k[4]], -len(tc_of.get(k[0], []))))
    for i, (kid, area, need, why, imp, groups, qs, nq) in enumerate(gaps, 1):
        route = " · ".join(qs + (["신규 " + nq] if nq else [])) or "-"
        L.append("| %d | %s | %s | %s | %s | %s |" % (i, kid, imp, need, ",".join(tc_of.get(kid, [])) or "(비공개 유형)", route))
    L.append("")
    L.append("## 4. 신규 질문 제안 (A1 은행에 대응 질문이 없는 공백만)")
    L.append("> A1이 상대 캐릭터에 맞춰 다듬는다. 전송은 HUMAN만 한다. 시스템 프롬프트·설정·지침은 묻지 않는다.")
    L.append("")
    for nid, (who, q) in NEW_Q.items():
        L.append("- **%s** → %s (%d자): %s" % (nid, who, len(q), q))
    L.append("")
    open(os.path.join(ROOT, "analysis/kb_coverage.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    for nid, (who, q) in NEW_Q.items():
        assert len(q) <= 200, nid


if __name__ == "__main__":
    main()
