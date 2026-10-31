"""C3 media — 메시지 본문 속 image:/audio: URL을 내려받아 (bytes, mime)으로 돌려준다.

입력 형식(공개 TC 원문, docs/contest/08 '추정'): 본문에 `image: https://...jpg` 또는 `audio: https://...m4a` 줄.

    from integ.media import fetch, extract_media
    for kind, url in extract_media(text):          # [('image', 'https://...jpg')]
        data, mime = await fetch(url)               # mime: image/jpeg|image/png|audio/mp4|...

제한: 크기 5MB(MEDIA_MAX_BYTES), 전체 10초(MEDIA_TIMEOUT), http(s)만, 리다이렉트 3회,
사설·루프백·링크로컬(메타데이터 169.254.169.254 포함) 주소 차단(SSRF 방지). 같은 URL은 메모리 캐시(최근 32개).
오류는 MediaError(사유 문자열). 프롬프트에 원인을 노출하지 말고 '사진/음성을 열 수 없음'으로 처리할 것.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
from collections import OrderedDict
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = int(os.environ.get("MEDIA_MAX_BYTES", str(5 * 1024 * 1024)))
TIMEOUT = float(os.environ.get("MEDIA_TIMEOUT", "10"))
MEDIA_RE = re.compile(r"^\s*(image|audio|video|file)\s*:\s*(https?://\S+)\s*$", re.I | re.M)
_CACHE: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
_CACHE_MAX = 32


class MediaError(Exception):
    pass


def extract_media(text: str) -> list[tuple[str, str]]:
    """본문에서 (kind, url) 목록 추출. kind는 소문자(image|audio|video|file)."""
    return [(m.group(1).lower(), m.group(2)) for m in MEDIA_RE.finditer(text or "")]


def sniff_mime(data: bytes, header_ct: str = "", url: str = "") -> str:
    """매직바이트 우선, 다음 Content-Type, 마지막으로 확장자."""
    h = data[:16]
    if h.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return "audio/wav"
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "image/heic"
        if brand in (b"qt  ",):
            return "video/quicktime"
        # M4A /isom/mp42 등: 확장자가 m4a거나 brand가 M4A면 오디오
        if brand.startswith(b"M4A") or url.lower().split("?")[0].endswith((".m4a", ".aac")):
            return "audio/mp4"
        return "video/mp4" if "video" in header_ct else "audio/mp4"
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if h[:4] == b"OggS":
        return "audio/ogg"
    if h[:4] == b"fLaC":
        return "audio/flac"
    ct = (header_ct or "").split(";")[0].strip().lower()
    if ct and ct != "application/octet-stream":
        return "audio/mp4" if ct in ("audio/x-m4a", "audio/m4a") else ct
    ext = url.lower().split("?")[0].rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "m4a": "audio/mp4",
            "mp3": "audio/mpeg", "wav": "audio/wav", "webp": "image/webp"}.get(ext, "application/octet-stream")


async def _check_host(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise MediaError("허용되지 않는 URL")
    host = u.hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80),
                                                             type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise MediaError("호스트 확인 실패") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            raise MediaError("내부 주소 차단")


async def _fetch(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=5.0), follow_redirects=False,
                                 headers={"User-Agent": "choonsik-cs-agent/0.1"}) as cli:
        cur = url
        for _ in range(4):
            await _check_host(cur)
            async with cli.stream("GET", cur) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur = urljoin(cur, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise MediaError(f"HTTP {r.status_code}")
                cl = r.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > MAX_BYTES:
                    raise MediaError("크기 초과")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise MediaError("크기 초과")
                data = bytes(buf)
                return data, sniff_mime(data, r.headers.get("content-type", ""), cur)
        raise MediaError("리다이렉트 과다")


async def fetch(url: str) -> tuple[bytes, str]:
    """URL → (bytes, mime). 전체 TIMEOUT초 상한. 실패 시 MediaError."""
    if url in _CACHE:
        _CACHE.move_to_end(url)
        return _CACHE[url]
    try:
        res = await asyncio.wait_for(_fetch(url), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        raise MediaError("시간 초과") from None
    except httpx.HTTPError as e:
        raise MediaError(f"네트워크 오류 {type(e).__name__}") from None
    _CACHE[url] = res
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return res


def fetch_sync(url: str) -> tuple[bytes, str]:
    return asyncio.run(fetch(url))


if __name__ == "__main__":  # python -m integ.media <url>
    import sys
    import time

    for u in sys.argv[1:]:
        t0 = time.perf_counter()
        try:
            d, m = fetch_sync(u)
            print(f"OK {m} {len(d)}B {round((time.perf_counter() - t0) * 1000)}ms {u}")
        except MediaError as e:
            print(f"ERR {e} {u}")
