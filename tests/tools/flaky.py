"""회차별 흔들림 표: 여러 실행(results.json)을 TC×회차 판정으로 비교한다(A0 #207, D-014 근거).

    uv run --with pyyaml python tests/tools/flaky.py tests/runs/<ts1> tests/runs/<ts2> ... [--out tests/runs/flaky_<now>.md]

- 회차마다 빌드 sha·하네스 설정(판정 표 수·pressure 유무)을 함께 적어, BRAIN 편차와 하네스 변경을 구분할 수 있게 한다.
- 바뀐 TC는 회차별 첫 사유 2개를 나란히 보여 준다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ICON = {"ok": "✅", "partial": "⚠️", "fail": "❌"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()
    runs = []
    for r in a.runs:
        d = Path(r).resolve()
        res = {x["tc"]: x for x in json.loads((d / "results.json").read_text(encoding="utf-8"))}
        m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        votes = next((it.get("votes") for x in res.values() if x.get("judge") and x["judge"].get("must_say")
                      for it in x["judge"]["must_say"] if it.get("votes")), None)
        pressure = any("pressure" in str(x.get("sim_log")) for x in res.values())
        runs.append({"name": d.name, "res": res, "m": m, "judge_n": len(votes) if votes else 1, "pressure": pressure})
    tcs = sorted(set().union(*(r["res"] for r in runs)))
    L = [f"# 회차별 흔들림 표 ({datetime.now():%H:%M})", "",
         "| 회차 | 빌드 | 판정 표 수 | pressure | ✅/⚠️/❌ | p95 ms | 말풍선/케이스 |", "|---|---|---|---|---|---|---|"]
    for r in runs:
        m = r["m"]
        L.append(f"| {r['name']} | {m['build']['label'][:7]} | {r['judge_n']} | {'on' if r['pressure'] else 'off'} | "
                 f"{m['ok']}/{m['partial']}/{m['fail']} | {m['p95_ms']} | {m['avg_bubbles_per_case']} |")
    L += ["", "| TC | " + " | ".join(r["name"][-6:] for r in runs) + " | 흔들림 |", "|---|" + "---|" * (len(runs) + 1)]
    changed = []
    for tc in tcs:
        vs = [r["res"].get(tc, {}).get("verdict") for r in runs]
        flip = len({v for v in vs if v}) > 1
        L.append(f"| {tc} | " + " | ".join(ICON.get(v, "-") for v in vs) + f" | {'◆' if flip else ''} |")
        if flip:
            changed.append(tc)
    L += ["", f"흔들린 TC {len(changed)}/{len(tcs)}: {', '.join(changed) or '-'}", ""]
    for tc in changed:
        L.append(f"### {tc}")
        for r in runs:
            x = r["res"].get(tc)
            if x:
                L.append(f"- {r['name'][-6:]} {ICON[x['verdict']]}: {'; '.join(x['why'][:2])[:220] or '-'}")
        L.append("")
    out = Path(a.out) if a.out else ROOT / "tests" / "runs" / f"flaky_{datetime.now():%H%M%S}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
