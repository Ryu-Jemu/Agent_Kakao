#!/usr/bin/env python3
"""인터뷰 질문 초안 기계 점검(D-043) — 읽기 전용, 전송·LLM 호출 없음.

사용: python3 analysis/question_check.py [docs/interview_support/*.md ...]  (생략 시 전부)
점검:
  - 길이: python len ≤ 200 (doc:03·05 FAQ '메시지 한 건당 200자 이하')
  - 표기 글자수 = 실측 len 인지('글자수: NN')
  - 금지(실격 위험): 관계자의 시스템 프롬프트·내부 설정·지침·AI/봇 정체 질의(AGENTS.md §3)
  - 단일 주제: 물음표 개수 ≤ 2 (민준이 묶음 질문 거부 — K-015). 3개 이상이면 경고
  - 중복: 이미 보낸 질문(kb/raw/<이름>.md '나:' 줄, inbox/interviews/<이름>.md 원문)과 문자 bigram Jaccard ≥ 0.5
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBID = re.compile(r"시스템\s*프롬프트|프롬프트|내부\s*설정|설정\s*(값|된)|지침\s*(원문|전문)|너의\s*(규칙|지시)|당신의\s*(규칙|지시|설정)|(AI|인공지능|챗봇|봇)\s*(이세요|인가요|이죠|맞나요)|어떤\s*모델|instruction|system\s*prompt", re.I)
ALIAS = {"보라": ["보라", "홍보라"], "홍보라": ["보라", "홍보라"]}


def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jacc(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / max(1, len(A | B))


def asked(name):
    out = []
    for n in ALIAS.get(name, [name]):
        p = os.path.join(ROOT, "kb/raw/%s.md" % n)
        if os.path.exists(p):
            out += [m.group(1) for m in re.finditer(r"^(?:나|Q\d+)\s*[:：]\s*(.+)$", open(p, encoding="utf-8").read(), re.M)]
        p = os.path.join(ROOT, "inbox/interviews/%s.md" % n)
        if os.path.exists(p):
            out += [l.strip("-> ").strip() for l in open(p, encoding="utf-8") if "?" in l and len(l) < 260]
        # A1 질문 큐: 보낸 것([x])과 대기 중([ ]) 모두 — inbox 파일은 답변만 담고 있어 질문 원문은 여기서 얻는다
        p = os.path.join(ROOT, "kb/questions/%s.md" % n)
        if os.path.exists(p):
            out += [m.group(1) for m in re.finditer(r"^\s*- \[[ x]\]\s*Q[A-Z]?\d+\s+(.+)$", open(p, encoding="utf-8").read(), re.M)]
    return out


# D-044 '기록상 단서' 휴리스틱: 날짜·시각·수치·코드·진술 인용이 하나도 없으면 경고(자동 판정 한계 — 사람이 최종 확인)
CLUE = re.compile(r"\d|[A-Z]{2,}-|Q\d+|K-\d+|['\"「『“]|[라다]고\s*(하셨|했|들었)|(하셨|했)다던데|기록|일지|스캔|문자|장부|대장|시트")


def v1_questions(name):
    p = os.path.join(ROOT, "docs/interview_support/%s.md" % name)
    if not os.path.exists(p):
        return []
    return [m.group(1) for m in re.finditer(r"^\s*- \[ \]\s*N\d+\s+(.+)$", open(p, encoding="utf-8").read(), re.M)]


def main():
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "docs/interview_support/*.md")))
    tot = bad = 0
    for f in files:
        base = os.path.basename(f)[:-3]
        name = re.sub(r"_v\d+$", "", base)
        prev = asked(name) + (v1_questions(name) if base != name else [])
        lines = open(f, encoding="utf-8").read().splitlines()
        print("## %s (기존 질문%s %d건과 중복 대조)" % (base, "+v1 초안" if base != name else "", len(prev)))
        for i, l in enumerate(lines):
            m = re.match(r"\s*- \[ \]\s*([ND]\d+)\s+(.+)$", l)
            if not m:
                continue
            qid, q = m.group(1), m.group(2).strip()
            tot += 1
            issues = []
            n = len(q)
            if n > 200:
                issues.append("200자 초과(%d)" % n)
            meta = " ".join(lines[i + 1:i + 3])
            mm = re.search(r"글자수\s*[:：]\s*(\d+)", meta)
            if mm and int(mm.group(1)) != n:
                issues.append("표기 글자수 %s ≠ 실측 %d" % (mm.group(1), n))
            if FORBID.search(q):
                issues.append("금지 표현 '%s'" % FORBID.search(q).group(0))
            if q.count("?") >= 3:
                issues.append("물음표 %d개(묶음 질문 위험)" % q.count("?"))
            if base != name and not CLUE.search(q):
                issues.append("기록상 단서 약함(날짜·수치·코드·인용 없음)")
            dup = max(((jacc(q, p), p) for p in prev), default=(0, ""))
            if dup[0] >= 0.5:
                issues.append("기존 질문과 유사 %.2f: %s" % (dup[0], dup[1][:50]))
            bad += bool(issues)
            print("- %s %s (%d자) %s" % (qid, "⚠️" if issues else "✅", n, "; ".join(issues)))
    print("\n합계: %d문항, 문제 %d문항" % (tot, bad))


if __name__ == "__main__":
    main()
