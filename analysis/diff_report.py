#!/usr/bin/env python3
"""A5-2 diff 보고서 — 모범 처리(루브릭=원문 기대 대응)와 실제 trace를 TC별로 비교하고 원인을 분류한다.

사용:
  python3 analysis/diff_report.py tests/runs/<ts>                    → analysis/diff_<ts>.md + analysis/logs/diff_<ts>.json
  python3 analysis/diff_report.py --compare tests/runs/<a> tests/runs/<b> [...]  → 전후 비교 수치표(표준출력)

입력: A4 하네스 산출물(results.json, metrics.json). 루브릭 YAML은 다시 읽지 않는다(results.json의 채점 결과 사용).
원인 분류(A5 프롬프트 기준):
  KB 공백(→A1) / 정책 추론(→A3 프롬프트) / 도구 오용(→A3 가드·A2 클라이언트) / 형식·길이(→A3 포맷터) / 지연(→A2·A3)
분류 규칙(결정적):
  - 금지·대상 외·조기·무호출 위반·API 4xx(인자) → 도구 오용(A3 가드). API 429·5xx·예외 → 도구 오용(A2 클라이언트)
  - 필수/택1/조건부 호출 누락, must_say(expected) 미충족, must_not_say 위반, 접수번호 미안내 → 정책 추론(A3)
    · 단 미충족 must_say가 KB 공백 K(analysis/kb_coverage.py ❌)와 연결돼 있으면 KB 공백(A1)
  - 500자 초과·sanitize 이슈·10말풍선 도달·말풍선당 평균 > LONG_CHARS → 형식·길이(A3 포맷터)
  - 턴 지연 > SLOW_MS, timeout, error → 지연(A2·A3)
  - 조건부 미발동(고객 선택 단계 미도달) → 정책 추론(흐름) — 단 대화가 timeout/10말풍선으로 끊겼으면 해당 원인으로
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOW_MS = 20000      # p95 위험 기준(60초 종료 기준의 1/3). 해석용 임계 — 근거: docs/contest/01 '60초 이상 무응답 종료'
LONG_CHARS = 300     # 말풍선당 평균 글자 상한(해석용). 점수는 '적을수록 높음'(doc:01)이라 절대 기준은 없다

# must_say ↔ KB 지식 단위(analysis/kb_coverage.py). 값이 KB에 없으면 '정책 추론'이 아니라 'KB 공백'으로 분류한다.
MS2K = {
    ("L-11", "S7"): "K10", ("L-34", "S6"): "K10",
    ("Y-24", "S2"): "K35", ("Y-24", "S3"): "K35", ("Y-24", "S4"): "K35",
    ("L-33", "S4"): "K19", ("Y-16", "A1"): "K33", ("L-32", "S8"): "K16",
}
OWNER = {"KB 공백": "A1", "정책 추론": "A3(프롬프트)", "도구 오용": "A3(가드)·A2(클라이언트)",
         "형식·길이": "A3(포맷터)", "지연": "A2·A3"}
ICON = {"ok": "✅", "partial": "⚠️", "fail": "❌"}


def kb_status():
    """kb_coverage.py를 import해 K별 상태를 얻는다(실패하면 빈 dict)."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "analysis"))
        import kb_coverage as kc
        return {k: v["status"] for k, v in kc.evaluate(kc.load_facts()).items()}
    except Exception:
        return {}


def fmt_flat(flat, n=90):
    s = json.dumps(flat or {}, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def analyze_tc(r, kst):
    causes = []  # (분류, 세부, 담당)

    def add(cat, detail, owner=None):
        causes.append((cat, detail, owner or OWNER[cat]))

    cs, f = r["calls_score"], r["format"]
    steps = []
    for x in cs.get("required", []):
        steps.append(("필수", x["id"], x["api"], "일치" if x["ok"] else "누락", x.get("near") or x.get("why") or ""))
        if not x["ok"]:
            if x.get("near"):  # 같은 API를 다른 인자로 불렀다 → 판단은 맞고 인자가 틀림
                add("도구 오용", "필수 %s %s 인자 불일치 (근접: %s)" % (x["id"], x["api"], str(x["near"])[:120]), "A3(가드·인자)")
            else:
                add("정책 추론", "필수 %s %s 누락" % (x["id"], x["api"]))
    for g in cs.get("alternative", []):
        steps.append(("택1", g["id"], g.get("mode"), "일치" if g["ok"] else "누락", "충족 옵션 %s개" % g.get("n_options_hit")))
        if not g["ok"]:
            add("정책 추론", "택1 %s 불충족(mode=%s, 충족 %s개)" % (g["id"], g.get("mode"), g.get("n_options_hit")))
    for c in cs.get("conditional", []):
        st = "미발동" if c["triggered"] is False else ("일치" if c.get("ok") else "누락")
        steps.append(("조건부", c["id"], c["api"], st, c.get("near") or ""))
        if c["triggered"] and not c.get("ok"):
            add("정책 추론", "조건부 %s %s 누락(고객 선택 후)" % (c["id"], c["api"]))
    extra = cs.get("extra", [])
    for x in cs.get("forbidden", []):
        add("도구 오용", "금지 %s %s %s (%s)" % (x["id"], x["api"], fmt_flat(x.get("flat"), 60), x.get("basis")), "A3(가드)")
    for x in cs.get("off_target", []):
        add("도구 오용", "대상 외 %s %s=%s" % (x["api"], x.get("param"), x.get("value")), "A3(가드)")
    for x in cs.get("premature", []):
        add("도구 오용", "조기 %s 턴%s: %s" % (x["api"], x.get("turn"), x.get("why")), "A3(가드)")
    for x in cs.get("no_call", []):
        add("도구 오용", "무호출 TC에서 %s 호출" % x["api"], "A3(가드)")
    for c in r.get("calls", []):
        st = c.get("status")
        # GET 404는 '대상 없음'이라는 정상 의미값일 수 있다(예: API-04 404=로트 조사 미개시, integ/API_SEMANTICS.md ②) → 원인 아님
        if isinstance(st, int) and st >= 400 and not (st == 404 and c.get("method", "GET") == "GET"):
            own = "A2(클라이언트)" if st in (429,) or st >= 500 else "A3(가드)"
            add("도구 오용", "API %s HTTP %s %s" % (c["api_id"], st, fmt_flat(c.get("flat"), 60)), own)
    # 발화
    jd = r.get("judge") or {}
    unmet, viol = [], []
    if jd.get("status") == "ok":
        for it in jd.get("must_say", []):
            if it.get("basis") == "expected" and it["verdict"] in ("unmet", "missing", "unverified"):
                unmet.append(it)
                k = MS2K.get((r["tc"], it["id"]))
                if k and kst.get(k) and kst[k] != "✅":
                    add("KB 공백", "must_say %s 미충족 — %s KB %s: %s" % (it["id"], k, kst[k], it["text"][:60]))
                else:
                    add("정책 추론", "must_say %s %s: %s" % (it["id"], it["verdict"], it["text"][:70]))
        for it in jd.get("must_not_say", []):
            if it["verdict"] == "violated":
                viol.append(it)
                add("정책 추론", "must_not_say %s 위반: %s" % (it["id"], it["text"][:60]))
    for l in r.get("literals", []):
        add("정책 추론", "must_not_say %s 문자열 노출 '%s'" % (l.get("id"), l.get("literal")))
    for e in r.get("echo", []):
        if e.get("ok") is False:
            add("정책 추론", "접수번호 미안내 %s %s" % (e.get("api"), e.get("ids")))
    # 형식·지연
    if f.get("over_500"):
        add("형식·길이", "500자 초과 말풍선 %d개(평가 제외)" % f["over_500"])
    if f.get("reached_10"):
        add("형식·길이", "10말풍선 도달(케이스 강제 종료)")
    if (f.get("avg_chars") or 0) > LONG_CHARS:
        add("형식·길이", "말풍선당 평균 %s자 > %d" % (f["avg_chars"], LONG_CHARS))
    for t in r.get("turns", []):
        if t.get("sanitize"):
            add("형식·길이", "sanitize: %s" % ("; ".join(map(str, t["sanitize"]))[:80]))
        if t.get("status") in ("timeout", "error"):
            add("지연", "턴 %s: %s %s" % (t["status"], t.get("ms"), (t.get("err") or "")[:60]))
        elif (t.get("ms") or 0) > SLOW_MS:
            add("지연", "턴 %dms > %dms" % (t["ms"], SLOW_MS))
    if jd and jd.get("status") != "ok":
        causes.append(("판정 불가", "LLM 판정 %s" % jd.get("status", "off"), "A4"))
    elif not jd:
        causes.append(("판정 불가", "LLM 판정 off(--no-judge) — 발화 비교 생략", "A4"))
    return {"tc": r["tc"], "title": r.get("title"), "verdict": r["verdict"], "steps": steps, "extra": extra,
            "calls": [(c.get("turn"), c["api_id"], fmt_flat(c.get("flat"), 70), c.get("status"), c.get("cached"))
                      for c in r.get("calls", [])],
            "unmet": unmet, "viol": viol, "format": f, "causes": causes}


def render(run, m, rows):
    ts = os.path.basename(run.rstrip("/"))
    L = ["# A5-2 diff 보고서 — run `%s`" % ts, ""]
    L.append("> 생성: `python3 analysis/diff_report.py %s` · 입력: results.json·metrics.json(A4 하네스) · 정본: 원문 기대 대응(루브릭)" % run)
    b = m.get("build", {})
    L.append("> build `%s` · set=%s · sim=%s · judge=%s" % (b.get("label"), m.get("set"), m.get("sim"), m.get("judge")))
    L.append("")
    L.append("## 요약 (사실 — metrics.json)")
    L.append("| ✅ | ⚠️ | ❌ | 필수 재현율 | must_say 충족 | 금지/대상외/조기 | 말풍선/케이스 | 글자/말풍선 | p50 | p95 | 턴 p95 | 액션 호출 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    L.append("| %s | %s | %s | %s | %s | %s/%s/%s | %s | %s | %s | %s | %s | %s |" % (
        m.get("ok"), m.get("partial"), m.get("fail"), m.get("required_recall"), m.get("must_say_rate"),
        m.get("forbidden"), m.get("off_target"), m.get("premature"), m.get("avg_bubbles_per_case"),
        m.get("avg_chars_per_bubble"), m.get("p50_ms"), m.get("p95_ms"), m.get("p95_turn_ms"), m.get("api_calls_net")))
    L.append("")
    agg = {}
    for r in rows:
        for cat, det, own in r["causes"]:
            agg.setdefault(cat, {"n": 0, "tcs": set(), "owner": own})
            agg[cat]["n"] += 1
            agg[cat]["tcs"].add(r["tc"])
    L.append("## 원인 분류 집계")
    L.append("| 원인 | 건수 | TC 수 | TC | 담당 |")
    L.append("|---|---|---|---|---|")
    for cat in ["KB 공백", "정책 추론", "도구 오용", "형식·길이", "지연", "판정 불가"]:
        if cat in agg:
            a = agg[cat]
            L.append("| %s | %d | %d | %s | %s |" % (cat, a["n"], len(a["tcs"]), ", ".join(sorted(a["tcs"])),
                                                  OWNER.get(cat, a["owner"])))
    L.append("")
    L.append("## TC별 비교")
    for r in rows:
        f = r["format"]
        L.append("### %s %s — %s" % (ICON.get(r["verdict"], r["verdict"]), r["tc"], r.get("title") or ""))
        L.append("- 형식: 말풍선 %s · 평균 %s자 · 최대 %s자 · 턴 ms %s" % (f.get("n_bubbles"), f.get("avg_chars"), f.get("max_chars"), f.get("turn_ms")))
        if r["steps"]:
            L.append("- 기대 단계: " + " · ".join("%s %s %s=%s%s" % (k, i, a, s, (" (%s)" % str(n)[:50]) if n and s != "일치" else "")
                                                for k, i, a, s, n in r["steps"]))
        L.append("- 실제 호출(턴·API·인자·상태): " + (" → ".join("t%s %s %s %s%s" % (t, a, p, s, " c" if c else "") for t, a, p, s, c in r["calls"]) or "없음"))
        if r["extra"]:
            L.append("- 초과 호출(기대·금지 외): " + ", ".join("%s %s" % (x["api"], fmt_flat(x.get("flat"), 50)) for x in r["extra"]))
        if r["causes"]:
            L.append("- 원인:")
            for cat, det, own in r["causes"]:
                L.append("  - [%s → %s] %s" % (cat, own, det))
        else:
            L.append("- 원인: 없음")
        L.append("")
    return "\n".join(L) + "\n"


def compare(runs):
    keys = ["ok", "partial", "fail", "required_recall", "must_say_rate", "forbidden", "off_target", "premature",
            "avg_bubbles_per_case", "avg_chars_per_bubble", "over_500", "p50_ms", "p95_ms", "p95_turn_ms", "api_calls_net"]
    ms = []
    for r in runs:
        m = json.load(open(os.path.join(r, "metrics.json"), encoding="utf-8"))
        ms.append((os.path.basename(r.rstrip("/")), m))
    print("| 지표 | " + " | ".join(n for n, _ in ms) + " |")
    print("|---|" + "---|" * len(ms))
    print("| build | " + " | ".join(str(m.get("build", {}).get("label", ""))[:12] for _, m in ms) + " |")
    print("| n | " + " | ".join(str(m.get("n")) for _, m in ms) + " |")
    for k in keys:
        print("| %s | %s |" % (k, " | ".join(str(m.get(k)) for _, m in ms)))
    tcs = sorted({tc for _, m in ms for tc in (m.get("per_tc") or {})})
    print("\n| TC | " + " | ".join(n for n, _ in ms) + " |")
    print("|---|" + "---|" * len(ms))
    for tc in tcs:
        print("| %s | %s |" % (tc, " | ".join(ICON.get((m.get("per_tc") or {}).get(tc, {}).get("verdict"), "-") for _, m in ms)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?")
    ap.add_argument("--compare", nargs="+")
    a = ap.parse_args()
    if a.compare:
        compare(a.compare)
        return
    run = a.run
    res = json.load(open(os.path.join(run, "results.json"), encoding="utf-8"))
    m = json.load(open(os.path.join(run, "metrics.json"), encoding="utf-8"))
    kst = kb_status()
    rows = [analyze_tc(r, kst) for r in res]
    ts = os.path.basename(run.rstrip("/"))
    md = render(run, m, rows)
    out = os.path.join(ROOT, "analysis", "diff_%s.md" % ts)
    open(out, "w", encoding="utf-8").write(md)
    os.makedirs(os.path.join(ROOT, "analysis", "logs"), exist_ok=True)
    json.dump({"run": ts, "metrics": {k: v for k, v in m.items() if k != "per_tc"},
               "causes": {r["tc"]: r["causes"] for r in rows}},
              open(os.path.join(ROOT, "analysis", "logs", "diff_%s.json" % ts), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
