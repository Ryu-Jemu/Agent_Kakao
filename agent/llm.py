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
MODEL = os.environ.get("AGENT_MODEL", "gemini-3.6-flash")  # D-015: 3.6 기본 thinking(A5 R-126 실하네스 A/B: ✅5·5, p95 14.0s vs 3.8 LOW p95 39.1s)
FAST_MODEL = os.environ.get("AGENT_FAST_MODEL", "gemini-3.6-flash")  # 축약용
FALLBACK_MODEL = os.environ.get("AGENT_FALLBACK_MODEL", "gemini-3.6-flash")  # 단계 타임아웃 시(A5 R-095: MINIMAL p95 1.2s)
FALLBACK_THINKING = os.environ.get("AGENT_FALLBACK_THINKING", "MINIMAL")
THINKING_BUDGET = os.environ.get("AGENT_THINKING_BUDGET")  # 정수(2.5 계열)
# thinking: 모델별 기본(D-012). 3.8-flash=LOW(A5 R-095), 3.6-flash 등=모델 기본(LOW·MINIMAL은 툴 판단 저하). env로 덮어쓴다.
THINKING_LEVEL = os.environ.get("AGENT_THINKING_LEVEL")  # MINIMAL|LOW|MEDIUM|HIGH. 3.8-flash는 MINIMAL 400
MODEL_THINKING = {"gemini-3.8-flash": "LOW"}

class LLMBlocked(Exception):
    """모든 백엔드가 403 PERMISSION_DENIED(이용 정책 거부) 상태 — 재시도·폴백 호출을 하지 않는다(R-210)."""


def _is_policy_denied(msg: str) -> bool:
    return "403" in msg and "PERMISSION_DENIED" in msg


# 백엔드 체인(D-028·D-029): ① Gemini API 키(AGENT_GEMINI_API_KEY → GOOGLE_GEMINI_API_KEY → GEMINI_API_KEY, D-029·D-030)
# → ② Vertex(GCP_PROJECT, ADC). 403 PERMISSION_DENIED를 받은 백엔드는 BLOCK_COOLDOWN_S 동안 건너뛰고 다음으로 넘어간다.
# AGENT_VERTEX_FALLBACK=0이면 키가 있을 때 Vertex를 쓰지 않는다. 키 값은 로그·보드에 쓰지 않는다.
API_KEY = (os.environ.get("AGENT_GEMINI_API_KEY") or os.environ.get("GOOGLE_GEMINI_API_KEY")  # D-030: HUMAN .env 키 이름
           or os.environ.get("GEMINI_API_KEY") or "").strip()
VERTEX_FALLBACK = os.environ.get("AGENT_VERTEX_FALLBACK", "0") == "1"  # D-027 보강: 키가 있으면 차단 프로젝트(Vertex)로 폴백하지 않음
BLOCK_COOLDOWN_S = float(os.environ.get("AGENT_403_COOLDOWN_S", "300"))


class _Backend:
    def __init__(self, name: str, kind: str):
        self.name, self.kind = name, kind
        self.client: genai.Client | None = None
        self.blocked_until = 0.0

    def get(self) -> genai.Client:
        if self.client is None:
            self.client = (genai.Client(api_key=API_KEY) if self.kind == "key"
                           else genai.Client(vertexai=True, project=PROJECT, location=LOCATION))
        return self.client


BACKENDS: list[_Backend] = []
if API_KEY:
    BACKENDS.append(_Backend("gemini-api-key", "key"))
if not API_KEY or VERTEX_FALLBACK:
    BACKENDS.append(_Backend(f"vertex:{PROJECT}/{LOCATION}", "vertex"))


def _available() -> list[_Backend]:
    import time as _t
    now = _t.monotonic()
    return [b for b in BACKENDS if b.blocked_until <= now]


def backend() -> str:
    av = _available()
    return av[0].name if av else "blocked"


def client() -> genai.Client:
    """현재 사용 가능한 첫 백엔드(vertex_probe·warmup 호환)."""
    av = _available() or BACKENDS
    return av[0].get()


def thinking_config(model: str, override: str | None = None) -> types.ThinkingConfig | None:
    if override:
        return types.ThinkingConfig(thinking_level=override)
    if THINKING_LEVEL:
        return types.ThinkingConfig(thinking_level=THINKING_LEVEL)
    if model in MODEL_THINKING:
        return types.ThinkingConfig(thinking_level=MODEL_THINKING[model])
    if THINKING_BUDGET is not None:
        return types.ThinkingConfig(thinking_budget=int(THINKING_BUDGET))
    return None


async def generate(contents, *, system: str, tools: list | None, model: str | None = None,
                   timeout: float = 25.0, allow_calls: bool = True, max_tokens: int = 2048,
                   fallback: bool = False):
    """fallback=True: 빠른 폴백(FALLBACK_MODEL + FALLBACK_THINKING). 주 모델과 같은 모델이어도 thinking만 낮춘다."""
    m = FALLBACK_MODEL if fallback else (model or MODEL)
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=float(os.environ.get("AGENT_TEMPERATURE", "0")),  # D-014①: 비결정성 축소
        seed=int(os.environ.get("AGENT_SEED", "7")),
        max_output_tokens=max_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    tc = thinking_config(m, FALLBACK_THINKING if fallback else None)
    if tc is not None:
        cfg.thinking_config = tc
    if tools:
        cfg.tools = [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in tools])]
        if not allow_calls:
            cfg.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE))
    import time as _time
    last: Exception | None = None
    for b in _available():
        for attempt in range(2):
            try:
                return await asyncio.wait_for(
                    b.get().aio.models.generate_content(model=m, contents=contents, config=cfg), timeout=timeout)
            except asyncio.TimeoutError as e:
                raise e
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if _is_policy_denied(msg):
                    b.blocked_until = _time.monotonic() + BLOCK_COOLDOWN_S  # 이 백엔드 건너뛰고 다음으로
                    break
                if attempt == 0 and any(k in msg for k in ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                    await asyncio.sleep(1.0)
                    continue
                raise
    if last is None or _is_policy_denied(str(last)):
        raise LLMBlocked(str(last)[:200] if last else "all backends blocked")
    raise last


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
