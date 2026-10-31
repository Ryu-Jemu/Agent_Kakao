"""A4 시뮬레이터·판정기 공용 Vertex Gemini 호출(BRAIN과 독립된 클라이언트·프롬프트).

환경변수: GCP_PROJECT, A4_VERTEX_LOCATION(기본 global), SIM_MODEL(기본 gemini-3.6-flash), JUDGE_MODEL(기본 gemini-3.7-flash),
GEMINI_API_KEY / A4_LLM_BACKEND=apikey|vertex(D-028 백엔드 전환).
JSON 응답만 받는다(response_mime_type). 실패하면 예외를 그대로 올리고 호출자가 대체 경로를 쓴다.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

PROJECT = os.environ.get("GCP_PROJECT", "ai-top-100-2026-513102")
# 하네스는 지연이 점수와 무관하고 3.x 모델 가용 목록이 global 기준(agent/logs/models.txt)이라 BRAIN의 VERTEX_LOCATION과 분리
LOCATION = os.environ.get("A4_VERTEX_LOCATION", "global")
# BRAIN(agent/llm.py 기본 gemini-3.8-flash)과 다른 모델로 독립성 확보. 가용 목록 근거: agent/logs/models.txt
SIM_MODEL = os.environ.get("SIM_MODEL", "gemini-3.6-flash")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-3.7-flash")

_clients: dict[int, object] = {}


def api_key() -> str | None:
    """D-029·D-030: A4 전용 키 → BRAIN과 같은 키(AGENT_GEMINI_API_KEY → GOOGLE_GEMINI_API_KEY) → GEMINI_API_KEY 순. 값은 출력하지 않는다."""
    for k in ("A4_GEMINI_API_KEY", "AGENT_GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY", "GEMINI_API_KEY"):
        if os.environ.get(k):
            return os.environ[k]
    return None


def backend() -> str:
    """D-028 백엔드 선택: A4_LLM_BACKEND=apikey|vertex. 미지정이면 GEMINI_API_KEY가 있으면 apikey, 없으면 vertex(GCP_PROJECT)."""
    b = os.environ.get("A4_LLM_BACKEND")
    if b:
        return b
    return "apikey" if api_key() else "vertex"


def client():
    """이벤트 루프마다 클라이언트를 따로 둔다(aio 세션이 루프에 묶임 → asyncio.run 반복 시 'Event loop is closed').
    키·토큰은 출력하지 않는다."""
    from google import genai

    key = id(asyncio.get_running_loop())
    if key not in _clients:
        if backend() == "apikey":
            _clients[key] = genai.Client(api_key=api_key())
        else:
            _clients[key] = genai.Client(vertexai=True, project=os.environ.get("GCP_PROJECT", PROJECT), location=LOCATION)
    return _clients[key]


async def gen_json(system: str, user: str, *, model: str, timeout: float = 40.0, temperature: float = 0.0) -> dict:
    from google.genai import types

    cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                      response_mime_type="application/json", max_output_tokens=4096)
    if "2.5" in model:
        cfg.thinking_config = types.ThinkingConfig(thinking_budget=0 if "flash" in model else 128)
    r = await asyncio.wait_for(client().aio.models.generate_content(model=model, contents=user, config=cfg), timeout)
    txt = (r.text or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`").removeprefix("json").strip()
    return json.loads(txt)
