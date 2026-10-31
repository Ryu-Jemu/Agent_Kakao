"""C5 회귀 러너 (A4-2). 심사 처리 기준(docs/contest/01)을 로컬에서 재현한다.

    uv run --with pyyaml python tests/run.py --set public                 # 15건 전수 + TC_MATRIX 기록
    uv run --with pyyaml python tests/run.py --set public --tc L-03,L-11  # 일부(매트릭스 갱신 안 함)
    옵션: --sim llm|scripted  --jobs 3  --no-reset  --no-judge  --no-record  --label "메모"

흐름: MANIFEST 검증 → (DATA_RESET 이벤트 → ActionClient.reset) → TC별 새 세션으로 handle_message 다중 턴
→ 게이트웨이와 같은 sanitize_outputs/50초 안전 타이머 → trace 수집(ActionClient 생성자 래핑, agent/ 무수정)
→ 결정적 채점 + LLM 판정 → tests/runs/<ts>/{traces.jsonl, metrics.json, report.md, <ID>.md}
→ (전수일 때) coord tc set ×15, log add, TEST_REPORT.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LOG_LEVEL", "WARNING")

try:  # 토큰 등 비밀값은 환경으로만 넘긴다(출력 금지). 커밋 추출본에는 .env가 없다
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from tests import scoring as S  # noqa: E402
from tests.sim import Simulator  # noqa: E402

BOT_PATHS = ["agent", "integ", "kb", "deploy", "pyproject.toml", "uv.lock"]
COORD = [sys.executable if False else "python3", str(ROOT / "coord" / "coord.py")]


# ───────────────────────── 보조 ─────────────────────────
CALLER = os.environ.get("AGENT_ID") or "A4"  # A6 #320: 기록 담당 = 실제 호출자(없으면 A4)


def coord(*args: str, check: bool = False) -> str:
    env = dict(os.environ, AGENT_ID=CALLER)
    r = subprocess.run(COORD + list(args), capture_output=True, text=True, env=env, cwd=ROOT)
    if check and r.returncode != 0:
        raise RuntimeError(f"coord {args[:2]} 실패: {r.stderr.strip()}")
    return (r.stdout + r.stderr).strip()


def export_build(sha: str) -> Path:
    """D-009: 커밋된 sha의 봇 경로만 git archive로 풀어 그 코드로 실행한다(작업 트리의 미커밋 수정 배제, .git 무변경)."""
    full = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", f"{sha}^{{commit}}"],
                          capture_output=True, text=True).stdout.strip()
    if not full:
        raise SystemExit(f"--build {sha}: 이 저장소의 커밋이 아님")
    d = ROOT / "tests" / "runs" / "_builds" / full
    if not (d / "agent").exists():
        d.mkdir(parents=True, exist_ok=True)
        arc = subprocess.run(["git", "-C", str(ROOT), "archive", full, "--", *BOT_PATHS], capture_output=True)
        if arc.returncode != 0:
            raise SystemExit(f"git archive 실패: {arc.stderr.decode()[:200]}")
        subprocess.run(["tar", "-x", "-C", str(d)], input=arc.stdout, check=True)
    (d / "agent" / "logs").mkdir(parents=True, exist_ok=True)
    return d


def build_info(bot_root: Path | None = None, sha_full: str | None = None) -> dict:
    if bot_root is not None:  # 커밋 추출본: 정의상 clean
        h = hashlib.sha256()
        for top in ("agent", "kb"):
            for p in sorted((bot_root / top).rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and "logs" not in p.parts:
                    h.update(str(p.relative_to(bot_root)).encode()); h.update(p.read_bytes())
        return {"sha": sha_full, "dirty": False, "label": sha_full, "content_fp": h.hexdigest()[:16],
                "dirty_files": [], "bot_root": str(bot_root.relative_to(ROOT))}
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    st = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *BOT_PATHS],
                        capture_output=True, text=True).stdout.strip()
    h = hashlib.sha256()
    for top in ("agent", "kb"):
        for p in sorted((ROOT / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and "logs" not in p.parts:
                h.update(str(p.relative_to(ROOT)).encode()); h.update(p.read_bytes())
    dirty = bool(st)
    return {"sha": sha, "dirty": dirty, "label": sha + ("-dirty" if dirty else ""),
            "content_fp": h.hexdigest()[:16], "dirty_files": st.splitlines()[:20]}


def manifest_check() -> list[str]:
    pub = ROOT / "tests" / "tc" / "public"
    probs = []
    r = subprocess.run(["shasum", "-a", "256", "-c", "MANIFEST.sha256"], cwd=pub, capture_output=True, text=True)
    if r.returncode != 0:
        probs.append("shasum -c 실패: " + (r.stdout + r.stderr).strip().replace("\n", " / ")[:300])
    n = len(list(pub.glob("*.md")))
    if n != 15:
        probs.append(f"원문 TC {n}건 ≠ 15")
    return probs


def pct(xs: list[int], p: float) -> int | None:
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))  # nearest-rank
    return s[k]


# ───────────────────────── trace 수집 ─────────────────────────
TRACES: dict[str, list[dict]] = {}
CUR_TURN: dict[str, int] = {}


def install_trace_hook():
    import integ.action_client as acm

    if getattr(acm.ActionClient, "_a4_hooked", False):
        return acm
    orig = acm.ActionClient.__init__

    def _init(self, tc_id, *a, **kw):
        user_cb = kw.get("on_trace")

        def cb(rec, _u=user_cb, _tc=tc_id):
            r = dict(rec)
            r["turn"] = CUR_TURN.get(_tc, -1)
            TRACES.setdefault(_tc, []).append(r)
            if _u:
                _u(rec)

        kw["on_trace"] = cb
        kw["trace_responses"] = True  # 접수번호 전달(echo) 판정용. 동작에는 영향 없음(trace에만 resp 추가)
        orig(self, tc_id, *a, **kw)

    acm.ActionClient.__init__ = _init
    acm.ActionClient._a4_hooked = True
    return acm


# ───────────────────────── TC 1건 ─────────────────────────
HEADER_LOCKS: dict[str, asyncio.Lock] = {}


async def run_tc(sid: str, handler, args, ts: str, gw, session_key: str | None = None) -> dict:
    """sid = 공개 TC ID 또는 합성 시나리오 ID. 같은 TC 헤더를 쓰는 실행은 직렬화(trace 라우팅이 TC 헤더 기준)."""
    rub = S.load_rubric(sid, args.set)
    tc = sid if args.set == "public" else (rub.get("tc_header") or "-")
    lock = HEADER_LOCKS.setdefault(tc, asyncio.Lock())
    async with lock:
        r = await _run_tc(sid, tc, rub, handler, args, ts, gw, session_key or f"a4test:{ts}:{sid}")
    return r


async def _run_tc(sid: str, tc: str, rub: dict, handler, args, ts: str, gw, key: str) -> dict:
    acm = install_trace_hook()
    if tc != "-":
        acm.ActionClient.clear_state(tc)
    TRACES[tc] = []
    sim = Simulator(tc, rub, mode=args.sim)
    history: list[tuple[str, str]] = []
    turns: list[dict] = []
    text = sim.first()
    total = 0
    while text is not None:
        CUR_TURN[tc] = len(sim.turns) - 1
        history.append(("user", text))
        t0 = time.monotonic()
        task = asyncio.create_task(handler(key, text, datetime.now(timezone.utc).isoformat()))
        done, _ = await asyncio.wait({task}, timeout=gw.SAFETY_SEC)
        status, err, raw = "ok", None, None
        if task in done:
            try:
                raw = task.result()
            except BaseException as e:
                status, err, raw = "error", f"{type(e).__name__}: {e}", [gw.ERROR_TEXT]
        else:
            task.cancel()
            status, raw = "timeout", [gw.TIMEOUT_TEXT]
        ms = int((time.monotonic() - t0) * 1000)
        bubbles, issues = gw.sanitize_outputs(raw)
        if total + len(bubbles) > S.MAX_BUBBLES:
            bubbles = bubbles[: S.MAX_BUBBLES - total]
        total += len(bubbles)
        turns.append({"user": text, "raw": raw if isinstance(raw, list) else [raw], "bubbles": bubbles, "ms": ms,
                      "status": status, "err": err, "sanitize": issues})
        for b in bubbles:
            history.append(("bot", b))
        if total >= S.MAX_BUBBLES or status != "ok":
            break
        text = await sim.next(bubbles, history)
    CUR_TURN[tc] = 999
    calls = []
    for r in TRACES.get(tc, []):
        calls.append({"api_id": r.get("api_id"), "method": r.get("method"), "status": r.get("status"),
                      "cached": r.get("cached"), "turn": r.get("turn"), "resp": r.get("resp"),
                      "flat": S.flatten_call(r, acm.SPECS), "ms": r.get("ms")})
    bot_bubbles = [b for t in turns for b in t["bubbles"]]
    calls_sc = S.score_calls(rub, calls, sim.turns)
    fmt = S.score_format(turns)
    echo = S.score_echo(rub, calls, bot_bubbles)
    lits = S.score_literals(rub, bot_bubbles)
    jd = None
    if args.judge:
        from tests.judge import judge_votes
        jd = await judge_votes(tc, rub, history, kb_hint=kb_hint(tc), n=args.judge_n)
        # 판정 정답 근거는 '현재 최신 KB'(빌드 KB가 아님) — 진실은 빌드와 무관. 어떤 KB로 판정했는지 남긴다
        jd["kb_truth"] = (ROOT / "kb" / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "kb" / "VERSION").exists() else "-"
    v, why = S.verdict(calls_sc, fmt, echo, lits, jd)
    return {"tc": sid, "header": tc, "type": rub.get("type"), "title": rub.get("title"), "verdict": v, "why": why, "turns": turns, "calls": calls,
            "calls_score": calls_sc, "format": fmt, "echo": echo, "literals": lits, "judge": jd,
            "sim_log": sim.log, "sim_turns": sim.turns}


def kb_hint(tc: str) -> str:
    p = ROOT / "kb" / "policy_pack.md"
    if tc != "Y-24" or not p.exists():
        return ""
    keys = ("사업자", "상호", "대표", "통신판매", "주소", "이메일", "연락처")
    return "\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if any(k in l for k in keys))[:2000]


# ───────────────────────── 산출물 ─────────────────────────
def write_tc_md(out: Path, r: dict, build: dict, ts: str, args) -> Path:
    cs = r["calls_score"]
    req_ok = sum(1 for x in cs["required"] if x["ok"])
    lines = [f"# {r['tc']} — {r['title']}", "",
             f"- TC ID: {r['tc']}", f"- build git SHA: {build['label']} (HEAD {build['sha']}, content_fp {build['content_fp']}, agent {build.get('agent_file', '-')})",
             f"- run: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}/ ({ts}) · sim={args.sim} · judge={'on×' + str(args.judge_n) if args.judge else 'off'}",
             f"- 결과: **{r['verdict']}**", ""]
    if r["why"]:
        lines += ["## 사유"] + [f"- {w}" for w in r["why"]] + [""]
    f = r["format"]
    lines += ["## 지표",
              f"- 필수 {req_ok}/{len(cs['required'])} · 택1 {sum(1 for g in cs['alternative'] if g['ok'])}/{len(cs['alternative'])}"
              f" · 조건부 {[(c['id'], c['ok']) for c in cs['conditional']]} · 금지 {len(cs['forbidden'])} · 대상 외 {len(cs['off_target'])}"
              f" · 조기 {len(cs['premature'])} · 무호출위반 {len(cs['no_call'])} · 추가호출 {len(cs['extra'])}",
              f"- 말풍선 {f['n_bubbles']}개 · 평균 {f['avg_chars']}자 · 최대 {f['max_chars']}자 · 500자 초과 {f['over_500']} · 턴 지연(ms) {f['turn_ms']}",
              f"- echo {r['echo']}", ""]
    lines += ["## 대화"]
    for i, t in enumerate(r["turns"]):
        u = t["user"].replace("\n", "  \n")
        lines.append(f"**고객[{i}]** {u}")
        for b in t["bubbles"]:
            q = b.replace("\n", "\n> ")
            lines.append(f"> **봇** ({S.kakao_len(b)}자, {t['ms']}ms) {q}")
        if t["status"] != "ok":
            lines.append(f"> ⚠️ {t['status']} {t['err'] or ''}")
        lines.append("")
    lines += ["## 액션 호출(trace)", "| # | 턴 | API | 파라미터 | status | cached |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(r["calls"]):
        lines.append(f"| {i} | {c['turn']} | {c['api_id']} | {json.dumps(c['flat'], ensure_ascii=False)[:160]} | {c['status']} | {c['cached']} |")
    lines.append("")
    if r["judge"]:
        lines += ["## LLM 판정", f"- 상태: {r['judge'].get('status')} {r['judge'].get('error', '')} · 정답 근거 KB(작업 트리 최신) v{r['judge'].get('kb_truth', '-')}"]
        for it in r["judge"].get("must_say", []):
            lines.append(f"- must_say {it['id']}[{it['basis']}] **{it['verdict']}** {it.get('votes', '')} — {it['text']} | 인용: {it['evidence']}")
        for it in r["judge"].get("must_not_say", []):
            lines.append(f"- must_not_say {it['id']} **{it['verdict']}** {it.get('votes', '')} — {it['text']} | 인용: {it['evidence']}")
    lines += ["", f"- 시뮬레이터 경로: {r['sim_log']}"]
    p = out / f"{r['tc']}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def summarize(results: list[dict], build: dict, ts: str, args, wall: float) -> tuple[dict, str]:
    bub_ms = [m for r in results for m in r["format"]["bubble_ms"]]
    turn_ms = [m for r in results for m in r["format"]["turn_ms"]]
    nb = [r["format"]["n_bubbles"] for r in results]
    chars = [c for r in results for c in r["format"]["chars"]]
    req = [x["ok"] for r in results for x in r["calls_score"]["required"]]
    met = [it["verdict"] == "met" for r in results if r["judge"] and r["judge"].get("status") == "ok"
           for it in r["judge"]["must_say"] if it["basis"] == "expected"]
    m = {"ts": ts, "build": build, "set": args.set, "sim": args.sim, "judge": args.judge, "n": len(results),
         "ok": sum(r["verdict"] == "ok" for r in results), "partial": sum(r["verdict"] == "partial" for r in results),
         "fail": sum(r["verdict"] == "fail" for r in results),
         "required_recall": round(sum(req) / len(req), 3) if req else None,
         "must_say_rate": round(sum(met) / len(met), 3) if met else None,
         "forbidden": sum(len(r["calls_score"]["forbidden"]) for r in results),
         "off_target": sum(len(r["calls_score"]["off_target"]) for r in results),
         "premature": sum(len(r["calls_score"]["premature"]) for r in results),
         "avg_bubbles_per_case": round(sum(nb) / len(nb), 2) if nb else None,
         "avg_chars_per_bubble": round(sum(chars) / len(chars), 1) if chars else None,
         "over_500": sum(r["format"]["over_500"] for r in results),
         "p50_ms": pct(bub_ms, 50), "p95_ms": pct(bub_ms, 95), "p95_turn_ms": pct(turn_ms, 95),
         "max_ms": max(turn_ms) if turn_ms else None,
         "api_calls_net": sum(1 for r in results for c in r["calls"] if not c["cached"]),
         "wall_sec": round(wall, 1),
         "per_tc": {r["tc"]: {"verdict": r["verdict"], "why": r["why"][:6], "bubbles": r["format"]["n_bubbles"],
                              "avg_chars": r["format"]["avg_chars"], "turn_ms": r["format"]["turn_ms"]} for r in results}}
    L = [f"# 회귀 리포트 {ts}", "",
         f"- build: `{build['label']}` (content_fp {build['content_fp']}) · set={args.set} · sim={args.sim} · judge={'on' if args.judge else 'off'} · {args.label or ''}",
         f"- 결과: ✅ {m['ok']} / ⚠️ {m['partial']} / ❌ {m['fail']} (총 {m['n']}) · 소요 {m['wall_sec']}s",
         f"- 필수 호출 재현율 {m['required_recall']} · must_say(expected) 충족률 {m['must_say_rate']} · 금지 {m['forbidden']} · 대상 외 {m['off_target']} · 조기 {m['premature']}",
         f"- 말풍선/케이스 {m['avg_bubbles_per_case']} · 글자/말풍선 {m['avg_chars_per_bubble']} · 500자 초과 {m['over_500']} · p50 {m['p50_ms']}ms · p95 {m['p95_ms']}ms (턴 p95 {m['p95_turn_ms']}, 최대 {m['max_ms']}) · 액션 호출 {m['api_calls_net']}회",
         "", "| TC | 결과 | 필수 | 금지/대상외/조기 | 말풍선 | 평균자 | 최대 턴ms | 주요 사유 |", "|---|---|---|---|---|---|---|---|"]
    icon = {"ok": "✅", "partial": "⚠️", "fail": "❌"}
    for r in results:
        cs, f = r["calls_score"], r["format"]
        L.append(f"| {r['tc']} | {icon[r['verdict']]} | {sum(1 for x in cs['required'] if x['ok'])}/{len(cs['required'])} | "
                 f"{len(cs['forbidden'])}/{len(cs['off_target'])}/{len(cs['premature'])} | {f['n_bubbles']} | {f['avg_chars']} | "
                 f"{max(f['turn_ms']) if f['turn_ms'] else '-'} | {'; '.join(r['why'][:2])[:160].replace('|', '¦')} |")
    L += ["", "증거: 각 TC는 `<ID>.md`(TC ID·빌드 SHA·대화·trace·판정). 원 trace는 traces.jsonl."]
    return m, "\n".join(L) + "\n"


# ───────────────────────── main ─────────────────────────
async def amain(args) -> int:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out).resolve() if args.out else ROOT / "tests" / "runs" / ts
    out.mkdir(parents=True, exist_ok=True)
    all_ids = S.tc_ids() if args.set == "public" else S.scenario_ids(args.set)
    if not all_ids:
        print(f"세트 {args.set}에 시나리오 없음" + (" — redteam은 A6 러너 release/redteam_run.py 사용" if args.set == "redteam" else ""))
        return 2
    ids = [x.strip() for x in args.tc.split(",")] if args.tc else all_ids
    full = args.set == "public" and set(ids) == set(all_ids) and args.handler == "agent" and not args.out
    if CALLER != "A4" and (args.reset or (args.record and full)):
        print(f"[run] 거부: reset·TC_MATRIX 기록은 A4 전용(호출자 {CALLER}) — --no-reset 와 --out(또는 --no-record)로 실행")
        return 2
    probs = manifest_check()
    if probs:
        coord("post", "--to", "ALL", "--type", "BLOCKER", f"A4 회귀 중단: 공개 TC 원문 무결성 실패 — {'; '.join(probs)}",
              "--ref", "tests/tc/public/MANIFEST.sha256")
        print("BLOCKER:", probs)
        return 2
    if args.build:
        bot_root = export_build(args.build)
        sys.path.insert(0, str(bot_root))  # agent·integ를 커밋 추출본에서 import
        os.environ.setdefault("ACTION_RATE_FILE", str(ROOT / ".coord" / "api_rate.json"))  # 세션 간 레이트리밋 공유
        build = build_info(bot_root, bot_root.name)
    else:
        build = build_info()
    print(f"[run] {ts} build={build['label']} tc={len(ids)} sim={args.sim} judge={args.judge}")
    acm = install_trace_hook()
    if args.reset:
        coord("post", "--to", "ALL", "--type", "DATA_RESET",
              f"A4 회귀 시작({ts}, {len(ids)}건, 약 {max(3, len(ids))}분): 액션 데이터 reset 후 실행. 실행 중 액션 API 대량 호출 자제(60초당 100회 공유)",
              "--ref", f"tests/runs/{ts}/")
        ok = await acm.ActionClient(S.tc_ids()[0], allow_reset=True).reset()
        print(f"[run] reset → {ok}")
        acm.ActionClient.clear_state()
    import integ.gateway as gw
    handler = gw.load_handler(args.handler)
    if args.handler == "agent":
        build["agent_file"] = str(Path(sys.modules["agent"].__file__).resolve().relative_to(ROOT))
        build["integ_file"] = str(Path(gw.__file__).resolve().relative_to(ROOT))
        print(f"[run] agent={build['agent_file']} integ={build['integ_file']}")
    t0 = time.monotonic()
    sem = asyncio.Semaphore(args.jobs)

    groups: dict[str, list[str]] = {}
    if args.set != "public":
        for sid in ids:
            g = S.load_rubric(sid, args.set).get("session_group")
            if g:
                groups.setdefault(g, []).append(sid)
        for g in groups.values():
            g.sort(key=lambda s: S.load_rubric(s, args.set).get("session_order", 0))
    in_group = {s: g for g, ss in groups.items() for s in ss}
    group_done: dict[str, asyncio.Event] = {}

    async def one(tc):
        g = in_group.get(tc)
        if g:  # 세션 경계 묶음: 같은 세션 키로 순서대로
            seq = groups[g]
            if seq.index(tc) > 0:
                await group_done.setdefault(f"{g}:{seq.index(tc) - 1}", asyncio.Event()).wait()
        async with sem:
            try:
                r = await run_tc(tc, handler, args, ts, gw, session_key=f"a4test:{ts}:{g}" if g else None)
            except Exception as e:  # 러너 예외도 결과로 남긴다(선별 보고 금지)
                r = {"tc": tc, "title": "", "verdict": "fail", "why": [f"러너 예외 {type(e).__name__}: {e}"],
                     "turns": [], "calls": [], "calls_score": {k: [] for k in ("required", "alternative", "conditional",
                     "forbidden", "off_target", "premature", "no_call", "extra")}, "format": S.score_format([]),
                     "echo": [], "literals": [], "judge": None, "sim_log": [], "sim_turns": []}
            print(f"[run] {tc} → {r['verdict']} {('; '.join(r['why'][:2]))[:140]}")
        if g:
            group_done.setdefault(f"{g}:{groups[g].index(tc)}", asyncio.Event()).set()
        return r

    results = await asyncio.gather(*(one(tc) for tc in ids))
    results.sort(key=lambda r: ids.index(r["tc"]))
    wall = time.monotonic() - t0
    with open(out / "traces.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            for c in r["calls"]:
                f.write(json.dumps({"tc": r["tc"], **{k: v for k, v in c.items()}}, ensure_ascii=False) + "\n")
    paths = {r["tc"]: write_tc_md(out, r, build, ts, args) for r in results}
    m, rep = summarize(results, build, ts, args, wall)
    (out / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "report.md").write_text(rep, encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, default=str), encoding="utf-8")
    print(rep)
    rel = str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out)
    if args.record and full:
        for r in results:
            why = "; ".join(r["why"][:3])[:200]
            cmd = ["tc", "set", "--id", r["tc"], "--result", r["verdict"], "--build", build["label"],
                   "--run", f"{rel}/{r['tc']}.md"] + (["--why", why] if r["verdict"] != "ok" else [])
            print(coord(*cmd))
        fails = [r["tc"] for r in results if r["verdict"] != "ok"]
        rid = coord("log", "add", "--task", f"A4-3 공개 TC 15건 전수 회귀 {ts} (build {build['label']})",
                    "--result", "ok" if not fails else ("partial" if m["ok"] else "fail"),
                    "--cmd", f"uv run --with pyyaml python tests/run.py --set public --sim {args.sim}",
                    "--evidence", f"{rel}/report.md",
                    "--issue", f"성공 {m['ok']}/15, 미통과 {','.join(fails) or '-'}; p95 {m['p95_ms']}ms; 말풍선/케이스 {m['avg_bubbles_per_case']}",
                    "--fix", "TC별 사유는 report.md·<ID>.md 참조(재시도는 빌드 변경 후)")
        print("[run] RUNLOG", rid)
        top = sorted([r for r in results if r["verdict"] != "ok"], key=lambda r: (r["verdict"] != "fail", r["tc"]))[:5]
        msg = (f"회귀 {ts} build {build['label']}: ✅{m['ok']}/15 ⚠️{m['partial']} ❌{m['fail']}, 필수재현 {m['required_recall']}, "
               f"must_say {m['must_say_rate']}, 금지 {m['forbidden']}, 대상외 {m['off_target']}, p95 {m['p95_ms']}ms, 말풍선 {m['avg_bubbles_per_case']}, 글자 {m['avg_chars_per_bubble']}. "
               f"상위 실패: " + " | ".join(f"{r['tc']}: {'; '.join(r['why'][:2])[:110]}" for r in top) + f" ({rid})")
        print(coord("post", "--to", "A3,A5,A6,A0", "--type", "TEST_REPORT", msg[:1500], "--ref", f"{rel}/report.md"))
    elif args.record and args.handler == "agent":
        rid = coord("log", "add", "--task", f"A4 {'부분' if args.set == 'public' else args.set} 회귀 {ts} ({len(ids)}건, build {build['label']})",
                    "--result", "ok" if m["ok"] == m["n"] else "partial",
                    "--cmd", f"uv run --with pyyaml python tests/run.py --set {args.set} --tc {args.tc or ''} --sim {args.sim}",
                    "--evidence", f"{rel}/report.md",
                    "--issue", f"성공 {m['ok']}/{m['n']} (부분 실행 → TC_MATRIX 미갱신)", "--fix", "-")
        print("[run] RUNLOG", rid, "(부분 실행: TC_MATRIX 갱신 안 함)")
    try:
        import integ.action_client as acm2
        await acm2.aclose_all()
    except Exception:
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default="public", choices=["public", "synthetic", "redteam"])
    ap.add_argument("--tc", help="쉼표 구분 TC ID(지정 시 부분 실행)")
    ap.add_argument("--sim", default="llm", choices=["llm", "scripted"])
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--no-reset", dest="reset", action="store_false")
    ap.add_argument("--no-judge", dest="judge", action="store_false")
    ap.add_argument("--no-record", dest="record", action="store_false")
    ap.add_argument("--build", help="커밋 sha(D-009). 지정 시 그 커밋의 봇 경로를 추출해 실행·기록(미지정=작업 트리, 수정 있으면 -dirty)")
    ap.add_argument("--judge-n", type=int, default=3, help="LLM 판정 다수결 횟수(동률은 엄격 쪽)")
    ap.add_argument("--label", default="")
    ap.add_argument("--out", help="산출 디렉터리(기본 tests/runs/<ts>). 다른 소유자는 자기 경로로(A5: analysis/runs/…). 지정 시 TC_MATRIX 기록 안 함")
    ap.add_argument("--handler", default="agent", choices=["agent", "echo"], help="echo = 파이프라인 건식 점검(채점 무의미)")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # 파일로 리다이렉트해도 진행 로그가 바로 보이게
    sys.exit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
