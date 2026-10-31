#!/usr/bin/env python3
"""체크리스트 3·4: A4 회귀 산출물(tests/runs/<ts>/results.json)을 A4 루브릭과 독립적으로 재계산한다.
실행: python3 release/verify_run.py tests/runs/<ts>
- 기대(EXP): tests/tc/public/<ID>.md '기대 대응'을 A6가 직접 읽고 옮긴 최소 규칙(필수·택1·허용 쓰기·금지). 루브릭 파일은 쓰지 않는다.
- 대상 외 호출(독립 규칙): 호출 파라미터의 식별자(주문·배송·결제·회원·로트·SKU·코드)가 그 이전 고객 발화나
  이전 호출 응답에 나온 값인지 본다. 처음 보는 값이면 '출처 불명'으로 보고한다(정책상 허용되는 고정값은 EXP.fixed).
- 형식·성능: 턴당 평균 말풍선, 말풍선당 평균 글자, 최대 글자(500 초과), 턴 지연 p50·p95·최대.
- must_say(LLM 판정)는 재계산하지 않고 A4 수치를 '인용(미검증)'으로만 표기한다.
"""
import json
import os
import re
import statistics
import sys

# TC별 기대(원문 기대 대응 기준). req: 모두 필요, one_of: 그룹마다 정확히 1개 이상, writes: 허용 POST, forbid: 금지 API
EXP = {
    "L-03": dict(req={"API-11", "API-24"}, writes={"API-24"}),
    "L-05": dict(req={"API-07", "API-32"}, writes={"API-32"}, fixed={"PAY-3706-0003", "019-2314-9701"}, exact={"body.receipt_number": "019-2314-9701"}),
    "L-11": dict(req={"API-11", "API-03", "API-04", "API-06", "API-35", "API-29"}, writes={"API-29", "API-35"}, fixed={"KD-WTM-370624-03"}),
    "L-20": dict(req=set(), writes=set(), no_calls=True),
    "L-23": dict(req={"API-07", "API-35"}, writes={"API-35"}),
    "L-32": dict(req={"API-07", "API-11", "API-35"}, writes={"API-35"}, forbid={"API-29"}),
    "L-33": dict(req={"API-11", "API-35"}, writes={"API-35"}),
    "L-34": dict(req={"API-07", "API-35"}, one_of=[{"API-25", "API-27"}], exactly_one=True, writes={"API-25", "API-27", "API-35"}),
    "L-40": dict(req={"API-08"}, one_of=[{"API-13", "API-12"}], writes=set(), fixed={"MB-77016"}),
    "L-47": dict(req={"API-07", "API-01", "API-33"}, writes={"API-33"}, forbid={"API-29"}, fixed={"WTM-STD-8", "MB-77017", "CARE5000"}),
    "L-60": dict(req={"API-20"}, writes=set(), fixed={"SUBAK15"}),
    "R-05-a": dict(req={"API-11", "API-03", "API-28"}, writes={"API-28"}, fixed={"KD-HGL-370624-03", "SHP-100300009-01"}),
    "Y-07-b": dict(req={"API-07", "API-11"}, writes=set()),
    "Y-16": dict(req={"API-28"}, one_of=[{"API-10", "API-11"}], writes={"API-28"}, fixed={"SHP-100400017-01"}),
    "Y-24": dict(req=set(), writes=set(), no_calls=True),
}
ID_KEYS = re.compile(r"(order_no|shipment_id|approval_no|member_id|lot_id|sku|code|name)$")


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * len(xs) + 0.5)) - 1))
    return xs[k]


def strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)
    elif o is not None:
        yield str(o)


def main(run):
    res = json.load(open(os.path.join(run, "results.json"), encoding="utf-8"))
    out, totals = [], dict(turns=0, bubbles=0, chars=0, over500=0, maxlen=0, lat=[], fail=0, unknown=0)
    for r in res:
        tc = r["tc"]
        e = EXP.get(tc, {})
        probs = []
        calls = r.get("calls", [])
        apis = [c["api_id"] for c in calls]
        posts = [c["api_id"] for c in calls if c.get("method") == "POST"]
        if e.get("no_calls") and calls:
            probs.append(f"호출 없어야 함: {apis}")
        miss = sorted(e.get("req", set()) - set(apis))
        if miss:
            probs.append(f"필수 누락 {miss}")
        for g in e.get("one_of", []):
            n = len(g & set(apis))
            if n == 0 or (e.get("exactly_one") and n > 1):
                probs.append(f"택1 {sorted(g)} → {n}개")
        for k, want in e.get("exact", {}).items():  # 원문이 값을 그대로 지정한 파라미터
            got = [str((c.get("flat") or {}).get(k)) for c in calls if k in (c.get("flat") or {})]
            if got and want not in got:
                probs.append(f"{k} 원문 값 '{want}' ≠ 실제 {got}")
        bad_w = sorted(set(posts) - e.get("writes", set()))
        if bad_w:
            probs.append(f"허용 밖 쓰기 {bad_w}")
        forb = sorted(e.get("forbid", set()) & set(apis))
        if forb:
            probs.append(f"금지 API {forb}")
        # 식별자 출처(독립 규칙)
        seen = set(e.get("fixed", set()))
        turns = r.get("turns", [])
        unknown = []
        for c in calls:
            t_idx = c.get("turn", 0)
            for tt in turns[: t_idx + 1]:
                seen |= set(re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}", tt.get("user", "")))
                seen |= {tt.get("user", "")}
            for k, v in (c.get("flat") or {}).items():
                if ID_KEYS.search(k) and str(v) not in seen and not any(str(v) in s for s in seen):
                    unknown.append(f"{c['api_id']} {k}={v}")
            seen |= set(strings(c.get("resp")))
        if unknown:
            probs.append(f"출처 불명 식별자 {unknown[:3]}")
            totals["unknown"] += len(unknown)
        # 형식·성능
        for tt in turns:
            bs = tt.get("bubbles") or []
            totals["turns"] += 1
            totals["bubbles"] += len(bs)
            for b in bs:
                totals["chars"] += len(b)
                totals["maxlen"] = max(totals["maxlen"], len(b))
                totals["over500"] += len(b) > 500
            if tt.get("ms") is not None:
                totals["lat"].append(tt["ms"])
        totals["fail"] += bool(probs)
        out.append((tc, r.get("verdict"), probs, apis))
    print(f"run {run} · TC {len(res)}건")
    print("| TC | A4 판정 | A6 독립 판정 | 호출 |\n|---|---|---|---|")
    for tc, v, probs, apis in out:
        print(f"| {tc} | {v} | {'OK' if not probs else '; '.join(probs)} | {', '.join(apis) or '-'} |")
    lat = totals["lat"]
    print(f"\n형식·성능: 턴 {totals['turns']} · 턴당 말풍선 {totals['bubbles'] / max(totals['turns'], 1):.2f} · "
          f"말풍선당 글자 {totals['chars'] / max(totals['bubbles'], 1):.1f} · 최대 {totals['maxlen']}자 · 500자 초과 {totals['over500']} · "
          f"지연 p50 {pct(lat, 50)}ms p95 {pct(lat, 95)}ms 최대 {max(lat) if lat else None}ms")
    print(f"A6 독립 판정 문제 TC {totals['fail']}건 · 출처 불명 식별자 {totals['unknown']}건 (must_say는 A4 LLM 판정 인용·미검증)")
    return 1 if totals["fail"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
