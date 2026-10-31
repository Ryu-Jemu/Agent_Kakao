"""저장된 실행(results.json)을 현재 루브릭·채점기로 다시 채점한다(BRAIN·액션 API·LLM 재호출 없음).

    uv run --with pyyaml python tests/rescore.py tests/runs/<ts> [--set synthetic]

- 용도: 루브릭 수정(교차검토 반영)이나 채점기 버그 수정 뒤 같은 대화로 판정만 갱신.
- LLM 판정은 저장된 판정 JSON을 재사용하고, 인용 검증(_quoted)만 다시 한다.
- 결과는 <run>/rescore_<now>/report.md 로 따로 쓴다(원본 보존).
- --record(공개 15건 전수 실행일 때만): TC별 증거 <ID>.md(TC ID·빌드 SHA·재채점 근거+원 증거 전문)를 쓰고 tc set ×15.
  같은 대화에 채점 규칙 수정만 반영하는 것이므로 빌드 SHA는 원 실행 그대로다.
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
    ap.add_argument("--record", action="store_true", help="공개 15건 전수 실행이면 TC_MATRIX 재기록")
    ap.add_argument("--why", default="", help="재채점 사유(증거·장부에 기록)")
    ap.add_argument("--rejudge", type=int, default=0, help="N>0이면 저장된 대화로 LLM 판정을 N회 다수결로 다시 함(BRAIN 재호출 없음)")
    a = ap.parse_args()
    run = Path(a.run_dir).resolve()
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    rows, changed = [], 0
    for r in results:
        set_ = a.set or ("synthetic" if r["tc"].startswith("S-") else "public")
        rub = S.load_rubric(r["tc"], set_)
        bubbles = [b for t in r["turns"] for b in t["bubbles"]]
        bot_text = "\n".join(bubbles)
        jd = r.get("judge")
        if a.rejudge:
            import asyncio
            from tests.judge import judge_votes
            from tests.run import kb_hint
            hist = []
            for t in r["turns"]:
                hist.append(("user", t["user"]))
                hist += [("bot", b) for b in t["bubbles"]]
            jd = asyncio.run(judge_votes(r.get("header") or r["tc"], rub, hist, kb_hint=kb_hint(r.get("header") or r["tc"]), n=a.rejudge))
            r["judge"] = jd
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
    if a.record:
        record(run, out, rows, a.why)


def record(run: Path, out: Path, rows: list, why: str) -> None:
    import os
    import subprocess

    m = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    ids = sorted(tc for tc, *_ in rows)
    if m.get("set") != "public" or ids != S.tc_ids() or m["build"].get("dirty"):
        sys.exit("--record는 공개 15건 전수·clean 빌드 실행에만 쓸 수 있음")
    sha = m["build"]["label"]
    env = dict(os.environ, AGENT_ID="A4")
    coord = ["python3", str(ROOT / "coord" / "coord.py")]
    rel = out.relative_to(ROOT)
    for tc, old, new, reasons in rows:
        body = (f"# {tc} — 재채점\n\n- TC ID: {tc}\n- build git SHA: {sha}\n- 원 실행: {run.relative_to(ROOT)}/{tc}.md (원판정 {old})\n"
                f"- 재채점 결과: **{new}** · 사유: {why or '채점 규칙 수정'}\n"
                + "".join(f"- {w}\n" for w in reasons) + "\n---\n\n" + (run / f"{tc}.md").read_text(encoding="utf-8"))
        (out / f"{tc}.md").write_text(body, encoding="utf-8")
        cmd = coord + ["tc", "set", "--id", tc, "--result", new, "--build", sha, "--run", f"{rel}/{tc}.md"]
        if new != "ok":
            cmd += ["--why", "; ".join(reasons[:3])[:200]]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
        print((r.stdout + r.stderr).strip())
    n_ok = sum(new == "ok" for _, _, new, _ in rows)
    r = subprocess.run(coord + ["log", "add", "--task", f"A4 재채점 기록 {run.name} (build {sha}): {why or '채점 규칙 수정'}",
                                "--result", "ok" if n_ok == 15 else "partial",
                                "--cmd", f"uv run --with pyyaml python tests/rescore.py {run.relative_to(ROOT)} --record",
                                "--evidence", f"{rel}/report.md",
                                "--issue", f"재채점 후 성공 {n_ok}/15, 변경 " + ",".join(f"{tc}:{old}→{new}" for tc, old, new, _ in rows if old != new),
                                "--fix", "-"], capture_output=True, text=True, env=env, cwd=ROOT)
    print("[rescore] RUNLOG", (r.stdout + r.stderr).strip())


if __name__ == "__main__":
    main()
