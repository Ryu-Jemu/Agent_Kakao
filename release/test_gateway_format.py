#!/usr/bin/env python3
"""체크리스트 4.1·4.2: 게이트웨이 출력 형식 적대 검사(네트워크 없음). 실행: .venv/bin/python release/test_gateway_format.py"""
import json, os, random, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from integ import gateway as G

bad = []
random.seed(20261031)
ATOMS = ["가", "a", " ", ".", "\n", "😀", "👨‍👩‍👧", "。", "…", "~", "(괄호)", "주문번호 100100033", "\t"]
def rnd_text():
    n = random.choice([0, 1, 5, 80, 300, 449, 450, 499, 500, 501, 700, 1200, 3000])
    return "".join(random.choice(ATOMS) for _ in range(n))
def rnd_outs():
    k = random.choice([0, 1, 2, 3, 4, 7])
    pool = [rnd_text, lambda: None, lambda: 123, lambda: "   ", lambda: {"x": 1}]
    outs = [random.choice(pool)() if random.random() < 0.2 else rnd_text() for _ in range(k)]
    return random.choice([outs, outs, "".join(map(str, outs[:1])) if outs else "", None])
for i in range(2000):
    outs = rnd_outs()
    try:
        texts, issues = G.sanitize_outputs(outs)
    except Exception as e:
        bad.append((i, "예외", repr(e)[:80])); continue
    body = G.build_body(texts)
    if not (1 <= len(texts) <= 3):
        bad.append((i, "개수", len(texts)))
    for t in texts:
        if not isinstance(t, str) or not t.strip():
            bad.append((i, "빈/비문자열", repr(t)[:40]))
        elif G.kakao_len(t) > 500:
            bad.append((i, "500초과", G.kakao_len(t)))
    outs_ = body["skillResponse"]["template"]["outputs"]
    if any(list(o) != ["simpleText"] for o in outs_):
        bad.append((i, "simpleText 외", list(outs_[0])))
print(f"퍼징 2000건 · 위반 {len(bad)}건 · ERROR_TEXT {G.kakao_len(G.ERROR_TEXT)}자")
for b in bad[:10]:
    print("  ✗", b)
# 4.1 코드 grep: simpleText 외 카카오 템플릿
pat = r"basicCard|quickReplies|listCard|carousel|commerceCard|itemCard|simpleImage|textCard"
r = subprocess.run(["grep", "-rnE", pat, "integ", "agent"], cwd=ROOT, capture_output=True, text=True)
hits = [ln for ln in r.stdout.splitlines() if "/logs/" not in ln and "__pycache__" not in ln]
print(f"simpleText 외 템플릿 grep {len(hits)}건"); [print("  ✗", h[:160]) for h in hits[:5]]
sys.exit(1 if bad or hits else 0)
