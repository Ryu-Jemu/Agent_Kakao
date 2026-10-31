"""A4 결정적 채점기 — 루브릭(tests/rubric/<ID>.yaml) × 액션 trace × 대화 기록.

정본은 원문 '기대 대응'이고 루브릭이 그것을 조건별로 분해한 것이다(tests/rubric/README.md).
여기서는 LLM 없이 판정 가능한 것만 본다: 호출(필수·택1·조건부·금지·대상 외·조기 호출·무호출),
접수번호 전달(echo), 형식(말풍선 수·글자 수·500자·지연), must_not_say의 literal.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUBRIC_DIR = ROOT / "tests" / "rubric"
ID_KEYS = {"order_no", "shipment_id", "approval_no", "lot_id", "member_id", "sku", "code",
           "subscription_id", "escalation_id"}
RECEIPT_KEYS = ("request_id", "refund_id", "escalation_id", "memo_id")
MAX_BUBBLES = 10      # 01 심사 처리 기준: 10번째 메시지까지 평가
MAX_CHARS = 500       # 01: 말풍선당 500자 초과는 평가 제외
TIMEOUT_MS = 60_000   # 01: 60초 무응답이면 종료


SCEN_DIR = ROOT / "tests" / "scenarios"


def load_rubric(tc_id: str, set_: str = "public") -> dict:
    d = RUBRIC_DIR if set_ == "public" else SCEN_DIR / set_
    return yaml.safe_load((d / f"{tc_id}.yaml").read_text(encoding="utf-8"))


def scenario_ids(set_: str) -> list[str]:
    return sorted(p.stem for p in (SCEN_DIR / set_).glob("*.yaml"))


def kakao_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


# ───────────────────────── trace 정규화 ─────────────────────────
def flatten_call(rec: dict, specs: dict) -> dict:
    """trace 레코드 → {'path.x': v, 'query.y': v, 'body.z': v}."""
    spec = specs.get(rec.get("api_id"))
    flat: dict[str, Any] = {}
    params = rec.get("params") or {}
    if spec is not None:
        for n in getattr(spec, "path_params", ()) or ():
            if n in params:
                flat[f"path.{n}"] = params[n]
        q = getattr(spec, "query", None)
        if q and q in params:
            flat[f"query.{q}"] = params[q]
    else:  # 스펙을 모르면 params를 path로 취급
        for k, v in params.items():
            flat[f"path.{k}"] = v
    for k, v in (rec.get("body") or {}).items():
        flat[f"body.{k}"] = v
    return flat


def is_success(rec: dict) -> bool:
    st = rec.get("status")
    if rec.get("method") == "GET":
        return st in (200, 404)  # 본문 없는 404도 '조회는 수행'(예: 조사 기록 없음)
    return isinstance(st, int) and 200 <= st < 300


# ───────────────────────── match ─────────────────────────
def _val_ok(actual: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        if "present" in cond:
            return (actual is not None and str(actual).strip() != "") == bool(cond["present"])
        if actual is None:
            return "not_in" in cond  # 값이 없으면 not_in만 참
        s = str(actual)
        if "contains_all" in cond or "groups" in cond:  # groups: 각 묶음에서 하나 이상
            return (all(str(x) in s for x in cond.get("contains_all") or [])
                    and all(any(str(x) in s for x in g) for g in cond.get("groups") or []))
        if "contains_any" in cond:
            return any(str(x) in s for x in cond["contains_any"])
        if "in" in cond:
            return s in [str(x) for x in cond["in"]]
        if "not_in" in cond:
            return s not in [str(x) for x in cond["not_in"]]
        raise ValueError(f"알 수 없는 match 조건: {cond}")
    return actual is not None and str(actual) == str(cond)


def call_matches(call: dict, api: str, match: dict) -> bool:
    if call["api_id"] != api:
        return False
    for k, cond in (match or {}).items():
        if not _val_ok(call["flat"].get(k), cond):
            return False
    return True


def _scope_ok(value: str, allowed: list) -> bool:
    for a in allowed:
        a = str(a)
        if a.startswith("re:"):
            if re.fullmatch(a[3:], value):
                return True
        elif value == a:
            return True
    return False


# ───────────────────────── 채점 ─────────────────────────
def score_calls(rub: dict, calls: list[dict], sim_turns: list[str]) -> dict:
    """calls: [{api_id, method, flat, status, cached, turn, resp?}] (turn = 이 호출을 일으킨 고객 발화 번호)."""
    c = rub.get("calls") or {}
    out: dict[str, Any] = {"required": [], "alternative": [], "conditional": [], "forbidden": [],
                           "off_target": [], "premature": [], "no_call": [], "extra": []}
    used_idx: set[int] = set()

    def first_hit(api, match, min_turn=None):
        for i, cl in enumerate(calls):
            if call_matches(cl, api, match) and is_success(cl) and (min_turn is None or cl["turn"] >= min_turn):
                return i
        return None

    hit_index: dict[str, int | None] = {}
    # 택1
    for g in c.get("alternative") or []:
        hits = []
        for opt in g["options"]:
            i = first_hit(opt["api"], opt.get("match"))
            if i is not None:
                hits.append(i)
        n_opt = sum(1 for opt in g["options"]
                    if any(call_matches(cl, opt["api"], opt.get("match")) and is_success(cl) for cl in calls))
        ok = n_opt == 1 if g.get("mode") == "exactly_one" else n_opt >= 1
        hit_index[g["id"]] = min(hits) if hits else None
        used_idx.update(hits)
        out["alternative"].append({"id": g["id"], "ok": ok, "n_options_hit": n_opt, "mode": g.get("mode"),
                                   "ref": g.get("ref")})
    # 필수
    for r in c.get("required") or []:
        i = first_hit(r["api"], r.get("match"))
        ok = i is not None
        why = None
        if ok and r.get("after"):
            j = hit_index.get(r["after"])
            if j is None or j > i:
                ok, why = False, f"순서 위반: {r['after']} 이후여야 함"
        hit_index[r["id"]] = i
        if i is not None:
            used_idx.add(i)
        out["required"].append({"id": r["id"], "api": r["api"], "ok": ok, "why": why, "ref": r.get("ref"),
                                "near": None if ok else _near(calls, r["api"])})
    # 조건부: 고객 발화에 trigger가 나온 뒤의 호출만 인정
    for r in c.get("conditional") or []:
        tturn = next((t for t, u in enumerate(sim_turns) if any(x in u for x in r.get("trigger") or [])), None)
        if tturn is None:
            out["conditional"].append({"id": r["id"], "api": r["api"], "triggered": False, "ok": None})
            continue
        i = first_hit(r["api"], r.get("match"), min_turn=tturn)
        early = [k for k, cl in enumerate(calls) if call_matches(cl, r["api"], r.get("match")) and cl["turn"] < tturn]
        for k in early:
            out["premature"].append({"api": r["api"], "turn": calls[k]["turn"], "why": f"{r['id']} 고객 선택 전 호출"})
        if i is not None:
            used_idx.add(i)
        out["conditional"].append({"id": r["id"], "api": r["api"], "triggered": True, "ok": i is not None,
                                   "ref": r.get("ref"), "near": None if i is not None else _near(calls, r["api"])})
    # 금지
    for f in c.get("forbidden") or []:
        for k, cl in enumerate(calls):
            if call_matches(cl, f["api"], f.get("match")):
                out["forbidden"].append({"id": f["id"], "api": f["api"], "basis": f.get("basis"), "turn": cl["turn"],
                                         "flat": cl["flat"], "ref": f.get("ref")})
    # 대상 외(scope)
    scope = rub.get("scope") or {}
    for cl in calls:
        for k, v in cl["flat"].items():
            key = k.split(".", 1)[1]
            if key in scope and key in ID_KEYS and not _scope_ok(str(v), scope[key] or []):
                out["off_target"].append({"api": cl["api_id"], "param": k, "value": v, "turn": cl["turn"]})
    # 고객 확인 전 호출(confirm_before_call)
    for ident in rub.get("confirm_before_call") or []:
        reveal = next((t for t, u in enumerate(sim_turns) if ident in u), None)
        for cl in calls:
            if any(str(v) == ident for v in cl["flat"].values()) and (reveal is None or cl["turn"] < reveal):
                out["premature"].append({"api": cl["api_id"], "turn": cl["turn"], "why": f"고객이 {ident}를 말하기 전 호출"})
    # 무호출 TC
    if c.get("no_call_expected"):
        for cl in calls:
            if not cl.get("cached"):
                out["no_call"].append({"api": cl["api_id"], "method": cl["method"], "turn": cl["turn"]})
    for k, cl in enumerate(calls):
        if k not in used_idx and not cl.get("cached"):
            out["extra"].append({"api": cl["api_id"], "flat": cl["flat"], "status": cl.get("status")})
    return out


def _near(calls: list[dict], api: str) -> list[dict]:
    """같은 API를 불렀지만 파라미터가 달랐던 호출(실패 원인 진단용)."""
    return [{"flat": cl["flat"], "status": cl.get("status")} for cl in calls if cl["api_id"] == api][:3]


def score_echo(rub: dict, calls: list[dict], bubbles: list[str]) -> list[dict]:
    text = "\n".join(bubbles)
    res = []
    for api in rub.get("echo") or []:
        ids = []
        for cl in calls:
            if cl["api_id"] == api and is_success(cl) and isinstance(cl.get("resp"), dict):
                ids += [str(cl["resp"][k]) for k in RECEIPT_KEYS if cl["resp"].get(k)]
        if not ids:
            res.append({"api": api, "ok": None, "why": "접수 응답 없음(호출 안 됨 또는 응답 미수집)"})
        else:
            res.append({"api": api, "ok": any(i in text for i in ids), "ids": ids})
    return res


def score_literals(rub: dict, bubbles: list[str]) -> list[dict]:
    text = "\n".join(bubbles)
    out = []
    for n in (rub.get("say") or {}).get("must_not_say") or []:
        for lit in n.get("literal") or []:
            if str(lit) in text:
                out.append({"id": n["id"], "literal": lit})
    return out


def score_format(turns: list[dict]) -> dict:
    """turns: [{bubbles:[str], raw:[str], ms:int, status}] — 카카오로 나간 형태(sanitize 후) 기준."""
    bubbles = [b for t in turns for b in t["bubbles"]]
    lens = [kakao_len(b) for b in bubbles]
    lat_bubble = [t["ms"] for t in turns for _ in t["bubbles"]]
    viol = []
    for i, t in enumerate(turns):
        if t["ms"] >= TIMEOUT_MS:
            viol.append(f"턴{i} 지연 {t['ms']}ms ≥ 60초(케이스 종료)")
        if t.get("status") not in (None, "ok"):
            viol.append(f"턴{i} 처리 상태 {t.get('status')}: {t.get('err')}")
        raw = t.get("raw") or []
        if not (1 <= len(raw) <= 3):
            viol.append(f"턴{i} C1 위반: 말풍선 {len(raw)}개(1~3)")
        for b in raw:
            if kakao_len(str(b)) > 450:
                viol.append(f"턴{i} C1 위반: {kakao_len(str(b))}자 > 450")
    over = [n for n in lens if n > MAX_CHARS]
    if over:
        viol.append(f"500자 초과 말풍선 {len(over)}개(평가 제외)")
    return {"n_bubbles": len(bubbles), "n_turns": len(turns), "chars": lens,
            "avg_chars": round(sum(lens) / len(lens), 1) if lens else 0, "max_chars": max(lens) if lens else 0,
            "over_500": len(over), "turn_ms": [t["ms"] for t in turns], "bubble_ms": lat_bubble,
            "reached_10": len(bubbles) >= MAX_BUBBLES, "violations": viol}


def verdict(calls_sc: dict, fmt: dict, echo: list[dict], literals: list[dict], judge: dict | None) -> tuple[str, list[str]]:
    """ok|partial|fail + 사유. 엄격 판정(BRAIN에 유리하게 완화하지 않는다)."""
    fail, part = [], []
    for f in calls_sc["forbidden"]:
        fail.append(f"금지 호출 {f['id']} {f['api']} {f['flat']} ({f['basis']})")
    for o in calls_sc["off_target"]:
        fail.append(f"대상 외 호출 {o['api']} {o['param']}={o['value']}")
    for n in calls_sc["no_call"]:
        (fail if n["method"] != "GET" else part).append(f"무호출 TC에서 {n['api']} 호출")
    for l in literals:
        fail.append(f"must_not_say {l['id']} 노출: '{l['literal']}'")
    for v in fmt["violations"]:
        (fail if ("60초" in v or "500자" in v) else part).append(v)
    for r in calls_sc["required"]:
        if not r["ok"]:
            part.append(f"필수 미충족 {r['id']} {r['api']}" + (f" ({r['why']})" if r.get("why") else "")
                        + (f" 근접: {r['near']}" if r.get("near") else ""))
    for g in calls_sc["alternative"]:
        if not g["ok"]:
            part.append(f"택1 미충족 {g['id']}(mode={g['mode']}, 충족 옵션 {g['n_options_hit']}개)")
    for r in calls_sc["conditional"]:
        if r["triggered"] and not r["ok"]:
            part.append(f"조건부 미충족 {r['id']} {r['api']}" + (f" 근접: {r['near']}" if r.get("near") else ""))
        if r["triggered"] is False:
            part.append(f"조건부 {r['id']} 미발동(고객 선택 단계에 도달 못 함)")
    for p in calls_sc["premature"]:
        part.append(f"조기 호출 {p['api']} 턴{p['turn']}: {p['why']}")
    for e in echo:
        if e["ok"] is False:
            part.append(f"접수번호 미안내 {e['api']} {e['ids']}")
    if judge is None or judge.get("status") != "ok":
        part.append("LLM 판정 불가(must_say/must_not_say 미판정)" + (f": {judge.get('error')}" if judge else ""))
    else:
        for it in judge["must_say"]:
            if it["basis"] != "expected" or it["verdict"] == "met":
                continue
            if it["verdict"] == "na" and "경우에만" in it["text"]:  # 명시적 조건부 항목만 해당 없음 허용
                continue
            part.append(f"must_say {it['id']} {it['verdict']}: {it['text'][:40]}")
        for it in judge["must_not_say"]:
            if it["verdict"] == "violated":
                fail.append(f"must_not_say {it['id']} 위반: {it['text'][:40]} — {it.get('evidence', '')[:60]}")
    if fail:
        return "fail", fail + part
    if part:
        return "partial", part
    return "ok", []


def tc_ids() -> list[str]:
    return sorted(p.stem for p in (ROOT / "tests" / "tc" / "public").glob("*.md"))


def section(md: str, title: str) -> str:
    """원문 md에서 '###### <title>' 블록 본문."""
    m = re.search(rf"^#+\s*{re.escape(title)}\s*\n(.*?)(?=^#+\s|\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def first_turn(md: str) -> str:
    m = re.search(r"^####\s*초기 대화\s*\n(.*?)(?=^####\s)", md, re.S | re.M)
    return m.group(1).strip("\n") if m else ""


if __name__ == "__main__":  # 루브릭 정합성 자체 점검
    import hashlib
    bad = 0
    for tid in tc_ids():
        r = load_rubric(tid)
        h = hashlib.sha256((ROOT / r["source"]["file"]).read_bytes()).hexdigest()
        if h != r["source"]["sha256"]:
            print(f"✗ {tid} 원문 해시 불일치"); bad += 1
    print("rubric ok" if not bad else f"rubric 문제 {bad}건")
    raise SystemExit(1 if bad else 0)
