"""저장된 실행(results.json)을 현재 루브릭·채점기로 다시 채점한다(BRAIN·액션 API·LLM 재호출 없음).

    uv run --with pyyaml python tests/rescore.py tests/runs/<ts> [--set synthetic]

- 용도: 루브릭 수정(교차검토 반영)이나 채점기 버그 수정 뒤 같은 대화로 판정만 갱신.
- LLM 판정은 저장된 판정 JSON을 재사용하고, 인용 검증(_quoted)만 다시 한다.
- 결과는 <run>/rescore_<now>/report.md 로 따로 쓴다(원본 보존, TC_MATRIX 기록 안 함).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests import scoring as S  # noqa: E402
from tests.judge import _quoted  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--set", default=None, help="public|synthetic (기본: TC ID로 추정)")
    a = ap.parse_args()
    run = Path(a.run_dir)
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    rows, changed = [], 0
    for r in results:
        set_ = a.set or ("synthetic" if r["tc"].startswith("S-") else "public")
        rub = S.load_rubric(r["tc"], set_)
        bubbles = [b for t in r["turns"] for b in t["bubbles"]]
        bot_text = "\n".join(bubbles)
        jd = r.get("judge")
        if jd and jd.get("status") == "ok":
            for it in jd["must_say"]:
                if it["verdict"] == "unverified" and _quoted(it.get("evidence", ""), bot_text):
                    it["verdict"] = "met"
        cs = S.score_calls(rub, r["calls"], r["sim_turns"])
        v, why = S.verdict(cs, S.score_format(r["turns"]), S.score_echo(rub, r["calls"], bubbles),
                           S.score_literals(rub, bubbles), jd)
        if v != r["verdict"]:
            changed += 1
        rows.append((r["tc"], r["verdict"], v, why))
    out = run / f"rescore_{datetime.now().strftime('%H%M%S')}"
    out.mkdir(exist_ok=True)
    icon = {"ok": "✅", "partial": "⚠️", "fail": "❌"}
    lines = [f"# 재채점 {run.name} ({datetime.now():%H:%M})", "",
             f"- 변경 {changed}건 · 결과 ✅{sum(v == 'ok' for _, _, v, _ in rows)} ⚠️{sum(v == 'partial' for _, _, v, _ in rows)} ❌{sum(v == 'fail' for _, _, v, _ in rows)}",
             "", "| TC | 원판정 | 재판정 | 사유 |", "|---|---|---|---|"]
    for tc, old, new, why in rows:
        lines.append(f"| {tc} | {icon[old]} | {icon[new]} | {'; '.join(why[:3])[:200].replace('|', '¦')} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {out / 'report.md'}")


if __name__ == "__main__":
    main()
