#!/usr/bin/env python3
"""A5 A/B 실행기 — A4 하네스(tests/run.py)를 조건별 env로 반복 실행하고 평균·표준편차를 낸다.

사용:
  python3 analysis/ab_run.py --exp format --reps 2            # 말풍선 1/2 × 목표 글자 150/250/350
  python3 analysis/ab_run.py --exp thinking --reps 2          # thinking 기본/minimal/low
  python3 analysis/ab_run.py --exp format --summarize-only    # 이미 돈 결과만 집계
  --dry : 실행할 명령만 출력

안전 조건(A4 REQUEST #72):
- 항상 --no-reset --no-record --sim scripted. DATA_RESET 없음(reset은 A4 전용).
- TC는 데이터 비오염 8건만: GET 또는 API-35만 접수(06 응답 규약상 접수가 조회에 남기는 필드는
  orders.refund_ids·orders.change_request_ids·payments.cancellation_request_ids뿐 → 이 8건의 조회 결과는 반복해도 같다).
- 결과는 analysis/runs/ab_<exp>/<cond>_r<k>/ 에 쓴다(run.py --out 지원이 필요하다. 없으면 실행하지 않는다).
- 런 사이 간격 MIN_GAP_S 이상 → 액션 API 분당 20회 미만(런당 ~12회).
판정: 점수 구조상 ②~④는 ⑤로 가중된다(doc:01). 정확도(ok·must_say·required)를 떨어뜨리는 조건은 권고하지 않는다.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFE_TCS = "L-20,Y-24,L-60,L-40,Y-07-b,L-23,L-33,L-32"
MIN_GAP_S = 45
EXPS = {
    "format": {
        "base_b2_t200": {},
        "b1_t200": {"AGENT_MAX_BUBBLES": "1"},
        "b2_t150": {"AGENT_TARGET_CHARS": "150"},
        "b2_t250": {"AGENT_TARGET_CHARS": "250"},
        "b2_t350": {"AGENT_TARGET_CHARS": "350"},
        "b1_t150": {"AGENT_MAX_BUBBLES": "1", "AGENT_TARGET_CHARS": "150"},
    },
    "model": {   # --build 71cad56 기준: AGENT_THINKING_LEVEL 기본 LOW, 빈 문자열이면 모델 기본 thinking
        "m36_low": {"AGENT_MODEL": "gemini-3.6-flash", "AGENT_THINKING_LEVEL": "LOW"},
        "m38_low": {"AGENT_MODEL": "gemini-3.8-flash", "AGENT_THINKING_LEVEL": "LOW"},
        "m36_def": {"AGENT_MODEL": "gemini-3.6-flash", "AGENT_THINKING_LEVEL": ""},
    },
    "thinking": {
        "think_default": {},
        "think_minimal": {"AGENT_THINKING_LEVEL": "minimal"},
        "think_low": {"AGENT_THINKING_LEVEL": "low"},
    },
}
KEYS = ["ok", "partial", "fail", "required_recall", "must_say_rate", "forbidden", "off_target", "premature",
        "avg_bubbles_per_case", "avg_chars_per_bubble", "over_500", "p50_ms", "p95_ms", "p95_turn_ms", "max_ms"]


def run_supports_out():
    try:
        h = subprocess.run(["uv", "run", "--with", "pyyaml", "python", "tests/run.py", "--help"], cwd=ROOT,
                           capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return False
    return "--out" in h


def summarize(exp):
    base = os.path.join(ROOT, "analysis", "runs", "ab_%s" % exp)
    rows = {}
    for cond in EXPS[exp]:
        ms = []
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                if d.startswith(cond + "_r"):
                    # run.py가 --out 아래에 <ts>/ 하위 폴더를 만들 수도 있어 둘 다 찾는다
                    cand = [os.path.join(base, d, "metrics.json")] + [
                        os.path.join(base, d, x, "metrics.json") for x in os.listdir(os.path.join(base, d))
                        if os.path.isdir(os.path.join(base, d, x))]
                    for c in cand:
                        if os.path.exists(c):
                            ms.append(json.load(open(c, encoding="utf-8")))
                            break
        rows[cond] = ms
    L = ["# A/B `%s` — 조건별 평균 ± 표준편차(모집단 sd), 반복 n" % exp, "",
         "> 생성: `python3 analysis/ab_run.py --exp %s --summarize-only` · TC %s · sim=scripted · judge on" % (exp, SAFE_TCS), "",
         "| 조건 | env | n | " + " | ".join(KEYS) + " |", "|---|---|---|" + "---|" * len(KEYS)]
    for cond, ms in rows.items():
        cells = []
        for k in KEYS:
            xs = [m.get(k) for m in ms if isinstance(m.get(k), (int, float))]
            if not xs:
                cells.append("-")
            elif len(xs) == 1:
                cells.append("%s" % round(xs[0], 3))
            else:
                cells.append("%s±%s" % (round(statistics.mean(xs), 3), round(statistics.pstdev(xs), 3)))
        L.append("| %s | `%s` | %d | %s |" % (cond, json.dumps(EXPS[exp][cond], ensure_ascii=False), len(ms), " | ".join(cells)))
    out = os.path.join(ROOT, "analysis", "ab_%s.md" % exp)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", choices=list(EXPS), required=True)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--conds", default="")
    ap.add_argument("--tcs", default=SAFE_TCS)
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--build", default="", help="커밋 sha(run.py --build). 재현성을 위해 지정 권장")
    a = ap.parse_args()
    if a.summarize_only:
        summarize(a.exp)
        return
    bad = set(a.tcs.split(",")) - set(SAFE_TCS.split(","))
    if bad:
        sys.exit("데이터 오염 가능 TC 포함 %s — 금지(--no-reset 반복 시 조회 결과가 바뀜)" % bad)
    if not a.dry and not run_supports_out():
        sys.exit("tests/run.py에 --out 옵션이 없다 → tests/runs/(A4 소유)에 쓰게 되므로 실행하지 않는다. A4 REQUEST #72 대기")
    conds = [c for c in (a.conds.split(",") if a.conds else EXPS[a.exp])]
    last = 0.0
    for rep in range(1, a.reps + 1):          # 반복을 바깥에 둬 시간대 드리프트가 조건 간 고르게 퍼지게 한다
        for cond in conds:
            out = os.path.join("analysis", "runs", "ab_%s" % a.exp, "%s_r%d" % (cond, rep))
            env = dict(os.environ, **EXPS[a.exp][cond])
            env["AGENT_TURN_LOG"] = os.path.join(ROOT, "analysis", "logs", "ab_turns.jsonl")
            cmd = ["uv", "run", "--with", "pyyaml", "python", "tests/run.py", "--set", "public", "--tc", a.tcs,
                   "--no-reset", "--no-record", "--sim", "scripted", "--out", out,
                   "--label", "A5 A/B %s %s r%d" % (a.exp, cond, rep)] + (["--build", a.build] if a.build else [])
            if a.dry:
                print(" ".join("%s=%s" % kv for kv in EXPS[a.exp][cond].items()), " ".join(cmd))
                continue
            wait = MIN_GAP_S - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            t0 = time.monotonic()
            r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
            print("[ab] %s r%d exit=%d %.0fs %s" % (cond, rep, r.returncode, time.monotonic() - t0,
                                                   (r.stdout.strip().splitlines() or [""])[-1][:120]), flush=True)
    if not a.dry:
        summarize(a.exp)


if __name__ == "__main__":
    main()
