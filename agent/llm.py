"""Vertex Gemini 클라이언트·미디어(A3-2).

- google-genai, vertexai=True, project=GCP_PROJECT(기본 ai-top-100-2026-513102), location=VERTEX_LOCATION(기본 global), ADC.
- 모델은 환경변수 AGENT_MODEL. 기본값은 Vertex 실측 목록에서 고른 값(agent/logs/models.txt 근거)이며 A5 실측으로 교체한다.
- 미디어: integ.media.fetch(C3)가 있으면 쓰고, 없으면 httpx로 직접 받는다(읽기 전용 다운로드).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

PROJECT = os.environ.get("GCP_PROJECT", "ai-top-100-2026-513102")
# D-008: global 고정(R-063: us-central1은 전 모델 404). .env의 VERTEX_LOCATION은 무시하고, 필요 시 AGENT_VERTEX_LOCATION으로만 바꾼다.
LOCATION = os.environ.get("AGENT_VERTEX_LOCATION", "global")
MODEL = os.environ.get("AGENT_MODEL", "gemini-3.6-flash")  # L-23 실측(warm, LOW) 3.6≈6.3s vs 3.8≈10s(agent/logs/turns.jsonl). 최종은 A5 실측
FAST_MODEL = os.environ.get("AGENT_FAST_MODEL", MODEL)
THINKING_BUDGET = os.environ.get("AGENT_THINKING_BUDGET")  # 정수(2.5 계열)
THINKING_LEVEL = os.environ.get("AGENT_THINKING_LEVEL", "LOW")  # MINIMAL|LOW|MEDIUM|HIGH(3 계열). 3.8-flash는 MINIMAL 400

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _client


def _switch_to_global() -> bool:
    """지역 엔드포인트가 404(모델 접근 불가)면 global로 1회 전환(R-063: 이 프로젝트는 global에서만 동작)."""
    global _client, LOCATION
    if LOCATION == "global":
        return False
    LOCATION = "global"
    _client = genai.Client(vertexai=True, project=PROJECT, location="global")
    return True


def thinking_config(model: str) -> types.ThinkingConfig | None:
    if THINKING_LEVEL:
        return types.ThinkingConfig(thinking_level=THINKING_LEVEL)
    if THINKING_BUDGET is not None:
        return types.ThinkingConfig(thinking_budget=int(THINKING_BUDGET))
    return None


async def generate(contents, *, system: str, tools: list | None, model: str | None = None,
                   timeout: float = 25.0, allow_calls: bool = True, max_tokens: int = 2048):
    m = model or MODEL
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        max_output_tokens=max_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    tc = thinking_config(m)
    if tc is not None:
        cfg.thinking_config = tc
    if tools:
        cfg.tools = [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in tools])]
        if not allow_calls:
            cfg.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE))
    last = None
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                client().aio.models.generate_content(model=m, contents=contents, config=cfg), timeout=timeout)
        except asyncio.TimeoutError as e:
            last = e
            break
        except Exception as e:  # noqa: BLE001 — 429/503 등 1회 재시도
            last = e
            msg = str(e)
            if attempt == 0 and "404" in msg and _switch_to_global():
                continue
            if attempt == 0 and any(k in msg for k in ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                await asyncio.sleep(1.0)
                continue
            break
    raise last  # type: ignore[misc]


# ───────── 미디어 ─────────
_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    ".heic": "image/heic", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".aac": "audio/aac", ".ogg": "audio/ogg",
}
_MEDIA_CACHE: dict[str, tuple[bytes, str]] = {}


def _mime_for(url: str, header: str | None) -> str:
    ext = os.path.splitext(url.split("?")[0].lower())[1]
    if ext in _MIME_BY_EXT:
        return _MIME_BY_EXT[ext]
    h = (header or "").split(";")[0].strip()
    return h or "application/octet-stream"


async def fetch_media(url: str, timeout: float = 8.0) -> tuple[bytes, str] | None:
    if url in _MEDIA_CACHE:
        return _MEDIA_CACHE[url]
    try:
        from integ import media as _m  # C3 v1: async fetch(url)->(bytes, mime), SSRF·크기 제한 포함
    except ImportError:
        _m = None
    try:
        if _m is not None:
            data, mime = await asyncio.wait_for(_m.fetch(url), timeout=timeout + 2)
            if not mime or mime == "application/octet-stream":
                mime = _mime_for(url, mime)
        else:
            import httpx

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                data, mime = r.content, _mime_for(url, r.headers.get("content-type"))
    except Exception:  # noqa: BLE001 — MediaError 포함: '열 수 없음'으로 처리
        return None
    if len(data) > 15 * 1024 * 1024:
        return None
    _MEDIA_CACHE[url] = (data, mime)
    return data, mime


async def media_parts(images: list[str], audios: list[str]) -> tuple[list[types.Part], list[str]]:
    urls = list(images) + list(audios)
    res = await asyncio.gather(*[fetch_media(u) for u in urls])
    parts, failed = [], []
    for u, r in zip(urls, res):
        if r is None:
            failed.append(u)
        else:
            parts.append(types.Part.from_bytes(data=r[0], mime_type=r[1]))
    return parts, failed
