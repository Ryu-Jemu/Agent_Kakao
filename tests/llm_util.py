"""A4 시뮬레이터·판정기 공용 Vertex Gemini 호출(BRAIN과 독립된 클라이언트·프롬프트).

환경변수: GCP_PROJECT, A4_VERTEX_LOCATION(기본 global), SIM_MODEL(기본 gemini-3.6-flash), JUDGE_MODEL(기본 gemini-3.7-flash).
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

_client = None


def client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _client


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
