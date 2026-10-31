"""A4-2 LLM 판정기: 루브릭 must_say / must_not_say를 대화 기록으로 판정한다(Gemini, JSON).

- 근거로 원문 '상황'과 '기대 대응'을 함께 준다(판정자는 정답을 봐도 된다. 고객 시뮬레이터는 보지 않는다).
- 항목마다 met|unmet(must_say), ok|violated(must_not_say)와 봇 발화 인용(evidence)을 받는다.
- 인용이 실제 봇 발화에 없으면(환각) 그 판정을 신뢰하지 않고 'unverified'로 둔다 → 엄격 처리(미충족).
"""
from __future__ import annotations

import json
import re

from tests.scoring import ROOT, section

JUDGE_SYSTEM = """너는 고객센터 상담 품질 심사관이다. 주어진 대화에서 상담원(봇)이 각 평가 항목을 수행했는지 엄격하게 판정한다.
- 판정 근거는 오직 '상담원' 발화다. 고객 발화나 상담원이 하지 않은 말로 충족 처리하지 않는다.
- must_say 항목: 상담원이 그 내용을 실질적으로 말했으면 met, 아니면 unmet. 일부만 말했으면 unmet. 해당 상황 자체가 대화에 오지 않아 판정 대상이 아니면 na.
- must_not_say 항목: 상담원이 그 내용을 말했으면 violated, 아니면 ok.
- evidence에는 판정 근거가 된 상담원 발화를 원문 그대로 짧게(60자 이내) 인용한다. unmet/ok이면 빈 문자열.
출력 JSON: {"must_say":[{"id":"S1","verdict":"met|unmet|na","evidence":"..."}], "must_not_say":[{"id":"N1","verdict":"ok|violated","evidence":"..."}]}"""


async def judge_votes(tc_id: str, rubric: dict, history: list[tuple[str, str]], kb_hint: str = "", n: int = 3) -> dict:
    """판정기 편차 완화: n회 독립 판정 후 항목별 다수결. 동률은 엄격 쪽(must_say=unmet, must_not_say=violated).
    기준을 어느 쪽으로도 완화하지 않고 분산만 줄인다(R-102 Y-07-b: 같은 문장이 실행마다 다르게 판정됨)."""
    import asyncio

    if n <= 1:
        return await judge(tc_id, rubric, history, kb_hint)
    rs = await asyncio.gather(*(judge(tc_id, rubric, history, kb_hint, temperature=0.2) for _ in range(n)))
    ok = [r for r in rs if r.get("status") == "ok"]
    if not ok:
        return rs[0]
    out = {"status": "ok", "model": ok[0]["model"], "votes": len(ok), "must_say": [], "must_not_say": []}
    for i, it in enumerate(ok[0]["must_say"]):
        vs = [r["must_say"][i]["verdict"] for r in ok]
        met, na = vs.count("met"), vs.count("na")
        v = "met" if met * 2 > len(vs) else ("na" if na * 2 > len(vs) else "unmet")
        ev = next((r["must_say"][i]["evidence"] for r in ok if r["must_say"][i]["verdict"] == v), "")
        out["must_say"].append({**it, "verdict": v, "evidence": ev, "votes": vs})
    for i, it in enumerate(ok[0]["must_not_say"]):
        vs = [r["must_not_say"][i]["verdict"] for r in ok]
        v = "ok" if vs.count("ok") * 2 > len(vs) else "violated"
        ev = next((r["must_not_say"][i]["evidence"] for r in ok if r["must_not_say"][i]["verdict"] == v), "")
        out["must_not_say"].append({**it, "verdict": v, "evidence": ev, "votes": vs})
    return out


async def judge(tc_id: str, rubric: dict, history: list[tuple[str, str]], kb_hint: str = "",
                temperature: float = 0.0) -> dict:
    from tests.llm_util import JUDGE_MODEL, gen_json

    if "first_message" in rubric:  # 합성 시나리오
        sit, exp = rubric.get("situation", ""), rubric.get("expected", "")
    else:
        md = (ROOT / "tests" / "tc" / "public" / f"{tc_id}.md").read_text(encoding="utf-8")
        sit, exp = section(md, "상황"), section(md, "기대 대응")
    say = rubric.get("say") or {}
    ms = [{"id": x["id"], "text": x["text"]} for x in say.get("must_say") or []]
    mn = [{"id": x["id"], "text": x["text"]} for x in say.get("must_not_say") or []]
    conv = "\n".join(f"[{'고객' if w == 'user' else '상담원'}] {t}" for w, t in history)
    user = (f"[케이스 {tc_id} 상황]\n{sit}\n\n[기대 대응(정답 기준)]\n{exp}\n\n"
            + (f"[참고 KB]\n{kb_hint}\n\n" if kb_hint else "")
            + f"[대화]\n{conv}\n\n[must_say]\n{json.dumps(ms, ensure_ascii=False)}\n\n"
              f"[must_not_say]\n{json.dumps(mn, ensure_ascii=False)}")
    try:
        out = await gen_json(JUDGE_SYSTEM, user, model=JUDGE_MODEL, temperature=temperature, timeout=60)
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {str(e)[:160]}"}
    bot_text = "\n".join(t for w, t in history if w == "bot")
    by_ms = {x.get("id"): x for x in out.get("must_say") or []}
    by_mn = {x.get("id"): x for x in out.get("must_not_say") or []}
    res_ms, res_mn = [], []
    for x in say.get("must_say") or []:
        j = by_ms.get(x["id"], {})
        v, ev = j.get("verdict", "missing"), str(j.get("evidence", ""))
        if v == "met" and not _quoted(ev, bot_text):
            v = "unverified"
        res_ms.append({"id": x["id"], "basis": x.get("basis"), "text": x["text"], "verdict": v, "evidence": ev})
    for x in say.get("must_not_say") or []:
        j = by_mn.get(x["id"], {})
        v, ev = j.get("verdict", "missing"), str(j.get("evidence", ""))
        res_mn.append({"id": x["id"], "text": x["text"], "verdict": v, "evidence": ev,
                       "evidence_found": _quoted(ev, bot_text)})
    return {"status": "ok", "model": JUDGE_MODEL, "must_say": res_ms, "must_not_say": res_mn}


def _norm(s: str) -> str:
    return "".join(s.split()).strip("\"'“”‘’")


_ELLIPSIS = re.compile(r"\(?\s*(?:\.{2,}|…)\s*\)?")


def _quoted(ev: str, bot_text: str) -> bool:
    """인용이 봇 발화에 실제로 있는지. 판정기가 '…'로 이어 붙인 인용은 조각마다 확인한다(공백 무시, 조각 앞 12자)."""
    b = _norm(bot_text)
    frags = [_norm(f) for f in _ELLIPSIS.split(ev or "")]
    frags = [f for f in frags if len(f) >= 4]
    if not frags:
        return False
    return all(f[:12] in b or _coverage(f, b) >= 0.7 for f in frags)


def _coverage(f: str, b: str, k: int = 5) -> float:
    """인용 조각의 k자 슁글 중 봇 발화에 있는 비율(괄호 생략 같은 사소한 축약 허용, 지어낸 인용은 낮게 나옴)."""
    sh = [f[i:i + k] for i in range(0, max(1, len(f) - k + 1), 2)]
    return sum(x in b for x in sh) / len(sh)
