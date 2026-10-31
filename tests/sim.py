"""A4-2 고객 시뮬레이터. 원문 '고객 문의'·'상황'대로 다중 턴을 진행하고, 질문받은 것만 답한다.

- 첫 메시지는 원문 '#### 초기 대화' 블록을 그대로 보낸다(메타데이터·image/audio 줄 포함).
- 고객 자신의 주문번호 등은 R-018 사전 조회(API-13→API-08, tests/logs/customers.json)로 확인해
  루브릭 sim.facts에 고정했다(회귀마다 30회 호출 절약, 갱신: tests/tools/probe_members.py).
- mode='llm': Gemini(BRAIN과 다른 프롬프트). 실패한 턴은 규칙 기반(scripted)으로 대체하고 기록한다.
- mode='scripted': 루브릭 sim.rules 키워드 규칙(결정적, LLM 없음).
- 종료: 봇 말풍선 누적 10개(러너), sim.end_when 충족, sim.max_turns 도달, 같은 대체 응답 2회 반복.
- sim.pressure: 원문 '상황'에 적힌 고객의 압박·재요구 발화. 끝내려 할 때 아직 안 한 것(key가 이전 고객 발화에 없음)이 있으면
  끝내지 않고 그 발화를 보낸다(A5 #189: 접수번호가 나오자마자 끝나 압박 단계가 시험되지 않던 공백).
- 고객은 기대 대응(정답)을 보지 않는다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from tests.scoring import ROOT, first_turn, section

SIM_SYSTEM = """너는 온라인 농수산물 쇼핑몰 「교동마을 산지직송」의 '고객' 역할 배우다. 상담원(봇)과 카카오톡으로 대화한다.
규칙:
- 아래 [고객 문의]와 [상황]에 적힌 고객 입장·태도·선택을 그대로 따른다. 상담원이 '물어본 것만' 답한다. 묻지 않은 사실을 먼저 늘어놓지 않는다.
- [고객 사실]에 있는 값(주문번호·주소 등)만 쓴다. 없는 값은 지어내지 말고 "잘 모르겠어요"라고 한다.
- [행동 지침]의 반응은 해당 상황이 오면 그 문장을 거의 그대로 말한다(특히 선택을 말할 때의 문구).
- 한국어 구어체, 1~2문장, 80자 이내. 상담원 흉내·요약·평가를 하지 않는다. 너는 AI라고 밝히지 않는다.
- 상담원이 요청을 처리(접수 완료 안내 등)했고 더 물을 것이 없으면 end=true로 하고 reply는 짧은 마무리 인사로 한다.
출력은 JSON 하나: {"reply": "<고객 발화>", "end": true|false}"""


@dataclass
class Simulator:
    tc_id: str
    rubric: dict
    mode: str = "llm"
    turns: list[str] = field(default_factory=list)       # 고객 발화(0 = 초기 대화)
    used: set = field(default_factory=set)
    log: list[dict] = field(default_factory=list)          # 턴별 생성 경로(llm|scripted|fallback)
    done: bool = False
    _fallback_streak: int = 0

    def __post_init__(self):
        self.sim = self.rubric.get("sim") or {}
        if "first_message" in self.rubric:  # 합성 시나리오(tests/scenarios/*)
            self.md = None
            self.sections = {"고객 문의": self.rubric.get("inquiry", ""), "상황": self.rubric.get("situation", "")}
        else:
            self.md = (ROOT / "tests" / "tc" / "public" / f"{self.tc_id}.md").read_text(encoding="utf-8")
            self.sections = {k: section(self.md, k) for k in ("고객 문의", "상황")}

    def first(self) -> str:
        t = self.rubric["first_message"].rstrip("\n") if self.md is None else first_turn(self.md)
        self.turns.append(t)
        return t

    @property
    def max_turns(self) -> int:
        return int(self.sim.get("max_turns", 6))

    # ── 규칙 기반 ──
    def _end_hit(self, bot_text: str) -> bool:
        """종료 신호: end_when(문자열 또는 're:정규식')이 맞고, 봇이 질문 중이 아니며, min_turns를 넘었을 때(A3 #208)."""
        if len(self.turns) - 1 < int(self.sim.get("min_turns", 1)):
            return False
        if "?" in bot_text.strip()[-80:]:
            return False
        for k in self.sim.get("end_when") or []:
            k = str(k)
            if (re.search(k[3:], bot_text) if k.startswith("re:") else k in bot_text):
                return True
        return False

    def _scripted(self, bot_text: str) -> tuple[str, bool]:
        # 아직 쓰지 않은 규칙 응답(질문에 대한 답·선택)이 있으면 종료보다 먼저 답한다
        # (R-280: '이관 접수했습니다'+'재배송/환불 중 선택' 동시 메시지에서 선택 전에 끝나던 결함)
        replies, seen_when = [], set()
        for i, r in enumerate(self.sim.get("rules") or []):
            key = tuple(r["when"])
            if i in self.used or key in seen_when:
                continue
            if any(str(k) in bot_text for k in r["when"]):
                seen_when.add(key)  # 같은 when 묶음은 순서대로 하나씩(once 체인)
                self.used.add(i)
                if r["say"] not in replies:
                    replies.append(r["say"])
        if replies:
            self._fallback_streak = 0
            return " ".join(replies), False
        if self._end_hit(bot_text):
            return self.sim.get("closing", "네, 감사합니다."), True
        self._fallback_streak += 1
        return self.sim.get("fallback", "네."), self._fallback_streak >= 2

    # ── LLM ──
    async def _llm(self, history: list[tuple[str, str]]) -> tuple[str, bool]:
        from tests.llm_util import SIM_MODEL, gen_json

        facts = json.dumps(self.sim.get("facts") or {}, ensure_ascii=False)
        rules = "\n".join(f"- 상담원이 {'/'.join(map(str, r['when']))} 관련 말을 하면: \"{r['say']}\"" for r in self.sim.get("rules") or [])
        rules += "".join(f"\n- (대화 중 적절한 때 반드시 한 번) \"{p['say']}\"" for p in self.sim.get("pressure") or [])
        ctx = (f"[고객 문의]\n{self.sections['고객 문의']}\n\n[상황]\n{self.sections['상황']}\n\n"
               f"[페르소나]\n{self.sim.get('persona', '')}\n\n[고객 사실]\n{facts}\n\n[행동 지침]\n{rules}\n"
               f"- 대화를 끝낼 때: \"{self.sim.get('closing', '네, 감사합니다.')}\"")
        conv = "\n".join(f"{'고객' if who == 'user' else '상담원'}: {t}" for who, t in history)
        user = f"{ctx}\n\n[지금까지의 대화]\n{conv}\n\n다음 고객 발화를 JSON으로."
        out = await gen_json(SIM_SYSTEM, user, model=SIM_MODEL, temperature=0.0)
        reply = str(out.get("reply", "")).strip()
        if not reply:
            raise ValueError("빈 reply")
        return reply, bool(out.get("end"))

    def _pending_pressure(self) -> str | None:
        said = "\n".join(self.turns[1:])
        for p in self.sim.get("pressure") or []:
            if p["key"] not in said:
                return p["say"]
        return None

    async def next(self, bot_bubbles: list[str], history: list[tuple[str, str]]) -> str | None:
        """봇 말풍선을 받고 다음 고객 발화. None이면 대화 종료."""
        if self.done:
            return None
        if len(self.turns) - 1 >= self.max_turns:
            self.done = True
            self.log.append({"turn": len(self.turns), "path": "stop", "why": "max_turns"})
            return None
        bot_text = "\n".join(bot_bubbles)
        path = "scripted"
        if self.mode == "llm":
            try:
                reply, end = await self._llm(history)
                path = "llm"
                # min_turns는 규칙 모드 전용(R-255: LLM 모드에서 규칙 응답으로 대체하면 이미 한 말을 반복해 말풍선만 늘었음).
                # LLM 모드의 조기 종료 방지는 아래 pressure(원문 상황 발화 미소진 시 계속)로만 한다.
            except Exception as e:  # LLM 불가 → 규칙 기반 대체
                reply, end = self._scripted(bot_text)
                path = f"scripted(llm 실패: {type(e).__name__})"
        else:
            reply, end = self._scripted(bot_text)
        if end or len(self.turns) - 1 >= self.max_turns - 1:
            pend = self._pending_pressure()
            if pend and len(self.turns) - 1 < self.max_turns:
                reply, end, path = pend, False, path + "+pressure"
        self.log.append({"turn": len(self.turns), "path": path, "end": end})
        if end:
            # 마무리 인사는 보내지 않는다(봇 말풍선 수를 부풀리지 않음). 필요 시 러너 --closing
            self.done = True
            self.closing = reply
            return None
        self.turns.append(reply)
        return reply
