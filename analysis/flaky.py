#!/usr/bin/env python3
"""회차 간 판정 흔들림 표 — 전수 회귀(15건) 결과를 TC × 회차로 모아 TC별 통과율과 '1회 15/15' 확률을 추정한다.

사용: python3 analysis/flaky.py [run_dir ...]      (생략 시 tests/runs/ 아래 15건 전수 run 전부, 읽기 전용)
      python3 analysis/flaky.py --md analysis/flaky.md tests/runs/a tests/runs/b ...
추정 방법(추정 — 표본이 작다): TC별 ✅ 확률 p_i = (✅ 횟수+1)/(회차+2) (라플라스 보정), P(15/15) = Π p_i (TC 독립 가정).
빌드가 다르면 '흔들림'에 코드·KB 변경 효과가 섞인다 → 빌드 열을 함께 표기하고 같은 빌드끼리 따로 본다.
"""
import argparse
import glob
import json
import os
from math import prod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = {"ok": "✅", "partial": "⚠️", "fail": "❌"}


def load(runs):
    out = []
    for r in runs:
        p = os.path.join(r, "metrics.json")
        if not os.path.exists(p):
            continue
        m = json.load(open(p, encoding="utf-8"))
        if m.get("n") != 15 or not m.get("judge"):
            continue
        out.append((os.path.basename(r.rstrip("/")), m))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--md")
    a = ap.parse_args()
    runs = a.runs or sorted(glob.glob(os.path.join(ROOT, "tests", "runs", "2*")))
    ms = load(runs)
    tcs = sorted({tc for _, m in ms for tc in m["per_tc"]})
    L = ["| TC | " + " | ".join("%s<br>%s" % (n[-6:], str(m["build"].get("label", ""))[:7]) for n, m in ms)
         + " | ✅율 | p̂(라플라스) |", "|---|" + "---|" * len(ms) + "---|---|"]
    ps, flips = [], []
    for tc in tcs:
        vs = [m["per_tc"].get(tc, {}).get("verdict") for _, m in ms]
        k = sum(v == "ok" for v in vs)
        n = sum(v is not None for v in vs)
        p = (k + 1) / (n + 2)
        ps.append(p)
        if len({v for v in vs if v}) > 1:
            flips.append(tc)
        L.append("| %s | %s | %d/%d | %.2f |" % (tc, " | ".join(ICON.get(v, "-") for v in vs), k, n, p))
    L.append("")
    L.append("- 회차 %d개, 흔들린 TC %d개: %s" % (len(ms), len(flips), ", ".join(flips) or "없음"))
    L.append("- 회차별 ✅ 수: %s" % ", ".join("%s=%s" % (n[-6:], m["ok"]) for n, m in ms))
    L.append("- 추정 P(1회 15/15) = Π p̂ = %.3f (TC 독립·라플라스 보정, 표본 %d회 — 추정)" % (prod(ps), len(ms)))
    txt = "\n".join(L)
    print(txt)
    if a.md:
        open(a.md, "w", encoding="utf-8").write("# 회차 간 판정 흔들림 (analysis/flaky.py)\n\n" + txt + "\n")


if __name__ == "__main__":
    main()
