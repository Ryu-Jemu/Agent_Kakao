"""Vertex 가용 모델 실측(모델명을 기억으로 정하지 않는다 — A3_BRAIN 설계 3).

실행: CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100 .venv/bin/python -m agent.vertex_probe [모델 ...]
1) 후보 모델마다 짧은 생성 1회 + 함수 호출 1회를 시도해 가용성과 지연을 잰다(목록 API 대신 실호출로 확인).
2) 결과는 agent/logs/models.txt.
"""
from __future__ import annotations

import asyncio
import sys
import time

from google.genai import types

from agent import llm

CANDIDATES = [
    "gemini-3-flash-preview", "gemini-3.0-flash", "gemini-3-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    "gemini-3-pro-preview", "gemini-2.5-pro",
]
TOOL = [{"name": "get_order", "description": "주문 조회", "parameters_json_schema": {
    "type": "object", "properties": {"order_no": {"type": "string"}}, "required": ["order_no"]}}]


async def probe(m: str) -> str:
    t0 = time.monotonic()
    try:
        r = await llm.generate([types.Content(role="user", parts=[types.Part.from_text(text="주문 100100001 조회해줘")])],
                               system="너는 상담원이다. 필요하면 도구를 호출한다.", tools=TOOL, model=m, timeout=30)
        ms = (time.monotonic() - t0) * 1000
        parts = r.candidates[0].content.parts if r.candidates and r.candidates[0].content else []
        fc = [p.function_call.name for p in parts if getattr(p, "function_call", None)]
        return f"OK   {m:28s} {ms:6.0f}ms fc={fc} usage={getattr(r, 'usage_metadata', None) and r.usage_metadata.total_token_count}"
    except Exception as e:  # noqa: BLE001
        return f"FAIL {m:28s} {type(e).__name__}: {str(e)[:160]}"


async def main(models: list[str]) -> None:
    lines = [f"project={llm.PROJECT} location={llm.LOCATION} {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    try:
        names = []
        for mm in llm.client().models.list(config={"page_size": 200}):
            n = getattr(mm, "name", "")
            if "gemini" in n:
                names.append(n.split("/")[-1])
        lines.append("list: " + ", ".join(sorted(set(names))[:80]))
    except Exception as e:  # noqa: BLE001
        lines.append(f"list FAIL {type(e).__name__}: {str(e)[:160]}")
    for r in await asyncio.gather(*[probe(m) for m in models or CANDIDATES]):
        lines.append(r)
    txt = "\n".join(lines)
    print(txt)
    open("agent/logs/models.txt", "a", encoding="utf-8").write(txt + "\n\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
