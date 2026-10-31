#!/usr/bin/env python3
"""A1 KB 검증기 — facts.jsonl 스키마·인용 원문 대조, questions/*.md 200자 검사.

사용: python3 kb/tools/check_kb.py
- facts: 필수 키, confidence ∈ {사실, 의견, 추측, 해석}, id 중복, quote가 출처 원문에 그대로 있는지
  출처 매핑: tc:<ID> → tests/tc/public/<ID>.md, doc:<NN> → docs/contest/<NN>_*.md,
            src:<이름> → inbox/sources/_text/<이름>.txt 또는 kb/raw/sources/_text/<이름>.txt(관계자가 준 문서 원문 추출본),
            그 밖(관계자 이름) → kb/raw/<이름>.md
- questions: '- [ ] Q' 또는 '- [x] Q'로 시작하는 줄의 질문 본문이 200자 이하인지
종료 코드: 문제 없으면 0, 있으면 1.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQ = ["id", "topic", "fact", "source_person", "quote", "as_of",
       "effective_from", "effective_until", "confidence", "conflicts"]
CONF = {"사실", "의견", "추측", "해석"}
# bin/interview_runner.py와 같은 금지 표현(시스템 프롬프트·설정·지침 탈취로 오인 가능) — 실격 방지
FORBIDDEN = re.compile(r"(시스템\s*프롬프트|프롬프트|system\s*prompt|내부\s*설정|설정값|(너|네|당신)의?\s*(지침|규칙|설정|역할)|instruction|ignore|이전\s*지시|무시하고|역할극|너는\s*AI|AI\s*모델)", re.I)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def source_text(src):
    if src.startswith("tc:"):
        p = os.path.join(ROOT, "tests/tc/public", src[3:] + ".md")
    elif src.startswith("src:"):
        p = os.path.join(ROOT, "inbox/sources/_text", src[4:] + ".txt")
        if not os.path.exists(p):
            p = os.path.join(ROOT, "kb/raw/sources/_text", src[4:] + ".txt")
    elif src.startswith("doc:"):
        c = glob.glob(os.path.join(ROOT, "docs/contest", src[4:] + "_*.md"))
        p = c[0] if c else ""
    else:
        p = os.path.join(ROOT, "kb/raw", src + ".md")
    if p and os.path.exists(p):
        return norm(open(p, encoding="utf-8").read())
    return None


def check_facts(errs):
    path = os.path.join(ROOT, "kb/facts.jsonl")
    ids = set()
    n = 0
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.strip():
            continue
        n += 1
        try:
            f = json.loads(line)
        except Exception as e:
            errs.append(f"facts:{i} JSON 오류 {e}")
            continue
        miss = [k for k in REQ if k not in f]
        if miss:
            errs.append(f"facts:{i} {f.get('id')} 키 누락 {miss}")
        if f.get("id") in ids:
            errs.append(f"facts:{i} id 중복 {f.get('id')}")
        ids.add(f.get("id"))
        if f.get("confidence") not in CONF:
            errs.append(f"facts:{i} {f.get('id')} confidence 값 {f.get('confidence')}")
        src = f.get("source_person", "")
        txt = source_text(src)
        if txt is None:
            errs.append(f"facts:{i} {f.get('id')} 출처 파일 없음 {src}")
        else:
            for q in [x for x in str(f.get("quote", "")).split(" … ") if x.strip()]:
                if norm(q) not in txt and re.sub(r"\s+", "", q) not in re.sub(r"\s+", "", txt):
                    errs.append(f"facts:{i} {f.get('id')} 인용 불일치({src}): {q[:50]}…")
    return n


def check_questions(errs):
    n = 0
    for p in sorted(glob.glob(os.path.join(ROOT, "kb/questions/*.md"))):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            m = re.match(r"^- \[[ x]\] (Q[\w.-]+)\s+(.*)$", line.rstrip("\n"))
            if not m:
                continue
            n += 1
            body = m.group(2).strip()
            if len(body) > 200:
                errs.append(f"{os.path.basename(p)}:{i} {m.group(1)} {len(body)}자 > 200")
            if FORBIDDEN.search(body):
                errs.append(f"{os.path.basename(p)}:{i} {m.group(1)} 금지 표현: {FORBIDDEN.search(body).group(0)}")
    return n


if __name__ == "__main__":
    errs = []
    nf = check_facts(errs)
    nq = check_questions(errs)
    print(f"facts {nf}건, 질문 {nq}건 검사")
    for e in errs:
        print("ERR", e)
    print("OK" if not errs else f"FAIL {len(errs)}건")
    sys.exit(1 if errs else 0)
