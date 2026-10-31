#!/opt/anaconda3/bin/python3
"""마을 관계자 인터뷰 실행기 (사용자가 직접 실행·승인하는 도구, D-005).

흐름(📸→🤔→⌨️→🔁): 질문 큐(kb/questions/<관계자>.md, A1 작성)에서 미전송 질문을 묶음으로 보여 주고
사용자가 'APPROVE'를 입력하면 한 건씩 → 카톡 채팅창 확인 → 붙여넣기·Enter → 답이 다 올 때까지 대기(화면 변화가
멈추고 새 줄이 생길 때까지, 최대 75초) → 캡처·OCR → inbox/interviews/<관계자>.md에 기록 → 다음 질문.

안전장치(대회 규정 03:127~131 '자동화 대량 요청' 금지 해석 — 답을 기다리며 1건씩, 묶음 승인):
- 한 번에 한 질문만 보낸다. 답이 다 오기 전에는 다음 질문을 보내지 않는다. 묶음은 최대 10건, 기본 5건.
- 200자 초과·시스템 프롬프트/설정/지침을 묻는 문장은 거부한다(실격 사유).
- 대상 창 제목이 일치할 때만 붙여넣는다(다른 대화방 오전송 방지). [SYSTEM] 안내가 보이면 즉시 멈춘다.
- 관계자당 누적 95건에서 멈춘다(상한 100). 중지: Ctrl+C 또는 `touch .coord/interview/STOP`.

필요 권한(사용자가 직접 허용): 시스템 설정 > 개인정보 보호 및 보안 > '손쉬운 사용'과 '화면 및 시스템 오디오 녹음'에
이 스크립트를 실행하는 터미널 앱. 처음 실행하면 'System Events 제어' 허용 창이 뜬다.

사용:
  bin/interview_runner.py --person 이민준 --check         # 권한·창·영역 점검(전송 안 함), 캡처 확인용 이미지 저장
  bin/interview_runner.py --person 이민준 --dry-run       # 큐 검증과 보낼 목록만 출력
  bin/interview_runner.py --person 이민준 --max 5         # 실제 실행(APPROVE 입력 필요)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HELPER = os.path.join(ROOT, ".coord", "bin", "kakao_helper")
STATE_DIR = os.path.join(ROOT, ".coord", "interview")
BUNDLE = "com.kakao.KakaoTalkMac"
MAX_PER_PERSON = 95
FORBIDDEN = re.compile(r"(시스템\s*프롬프트|프롬프트|system\s*prompt|내부\s*설정|설정값|(너|네|당신)의?\s*(지침|규칙|설정|역할)|instruction|ignore|이전\s*지시|무시하고|역할극|너는\s*AI|AI\s*모델)", re.I)
TIMESTAMP = re.compile(r"^\s*(오전|오후)?\s*\d{1,2}:\d{2}\s*$")


def now() -> str:
    return dt.datetime.now().strftime("%H:%M")


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def osa(script: str) -> str:
    r = sh(["osascript", "-e", script])
    if r.returncode != 0:
        raise RuntimeError(f"osascript 실패: {r.stderr.strip()} — '손쉬운 사용'·'System Events 제어' 권한을 확인하세요")
    return r.stdout.strip()


def proc() -> str:
    return f'(first process whose bundle identifier is "{BUNDLE}")'


# ── 큐·상태 ──────────────────────────────────────────────
def load_state(person: str) -> dict:
    p = os.path.join(STATE_DIR, f"{person}.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sent": [], "count": None}


def save_state(person: str, st: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, f"{person}.json")
    tmp = p + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def load_queue(person: str, st: dict) -> list[tuple[str, str, str]]:
    """(qid, text, 거부사유) — 거부사유가 빈 문자열이면 보낼 수 있다."""
    path = os.path.join(ROOT, "kb", "questions", f"{person}.md")
    out = []
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"^- \[ \] (Q\d+)\s+(.+?)\s*$", ln)
        if not m:
            continue
        qid, text = m.group(1), m.group(2)
        if qid in st["sent"]:
            continue
        why = ""
        if len(text) > 200:
            why = f"{len(text)}자 > 200자"
        elif FORBIDDEN.search(text):
            why = "금지 표현(시스템 프롬프트·설정·지침 탈취로 오인 가능)"
        out.append((qid, text, why))
    return out


# ── 창·캡처·OCR ──────────────────────────────────────────
def windows() -> list[dict]:
    """손쉬운 사용(System Events)으로 카톡 창 제목·위치·크기를 얻는다."""
    raw = osa(f'''tell application "System Events" to tell {proc()}
  set out to ""
  repeat with w in windows
    set {{px, py}} to position of w
    set {{sx, sy}} to size of w
    set out to out & (name of w) & "\t" & px & "\t" & py & "\t" & sx & "\t" & sy & linefeed
  end repeat
  return out
end tell''')
    res = []
    for ln in raw.splitlines():
        p = ln.split("\t")
        if len(p) == 5:
            res.append({"title": p[0], "x": int(p[1]), "y": int(p[2]), "w": int(p[3]), "h": int(p[4])})
    return res


def find_window(title: str) -> dict:
    ws = [w for w in windows() if w["title"] == title]
    if len(ws) != 1:
        raise RuntimeError(f"제목이 정확히 '{title}'인 카톡 창이 {len(ws)}개입니다 — 해당 대화방을 별도 창으로 하나만 열어 두세요")
    return ws[0]


def raise_window(title: str):
    osa(f'''tell application "System Events" to tell {proc()}
  set frontmost to true
  perform action "AXRaise" of (first window whose name is "{title}")
end tell''')
    time.sleep(0.4)
    front = osa(f'tell application "System Events" to tell {proc()} to return name of window 1')
    if front != title:
        raise RuntimeError(f"맨 앞 창이 '{front}'입니다(대상 '{title}') — 오전송 방지를 위해 중단")


def region(w: dict, top: int, bottom: int) -> tuple[int, int, int, int]:
    return w["x"], w["y"] + top, w["w"], max(50, w["h"] - top - bottom)


def capture(rect, path: str) -> str:
    x, y, w, h = rect
    r = sh(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path])
    if r.returncode != 0 or not os.path.exists(path):
        raise RuntimeError("화면 캡처 실패 — '화면 및 시스템 오디오 녹음' 권한을 확인하세요")
    return path


def img_small(path: str):
    from PIL import Image
    return Image.open(path).convert("L").resize((128, 192))


def changed(a, b, eps: float = 0.8) -> bool:
    """평균 밝기 차이로 판정 — 입력창 커서 깜빡임 같은 미세 변화는 무시하고, 새 말풍선·스크롤만 변화로 본다."""
    from PIL import ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] > eps


def ocr(path: str) -> list[str]:
    r = sh([HELPER, "ocr", path])
    if r.returncode != 0:
        raise RuntimeError(f"OCR 실패: {r.stderr.strip()}")
    return [l["text"] for l in json.loads(r.stdout)]


def norm(s: str) -> str:
    # OCR이 ·를 •로, 따옴표·물음표를 다르게 읽는 경우가 있어 한글·영숫자만 남겨 비교한다
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s)


def new_lines(before: list[str], after: list[str], question: str) -> list[str]:
    """after에서 before에 없던 줄 중 내 질문 조각·시각 표시를 뺀 것 = 관계자 답(OCR)."""
    pool = {}
    for l in before:
        pool[norm(l)] = pool.get(norm(l), 0) + 1
    q = norm(question)
    out = []
    for l in after:
        k = norm(l)
        if pool.get(k, 0) > 0:
            pool[k] -= 1
            continue
        if not k or TIMESTAMP.match(l) or (len(k) >= 3 and k in q):
            continue
        out.append(l)
    return out


# ── 전송·대기 ────────────────────────────────────────────
def send(title: str, text: str):
    old = sh(["pbpaste"]).stdout
    subprocess.run(["pbcopy"], input=text, text=True, check=True)
    raise_window(title)
    osa('tell application "System Events" to keystroke "v" using command down')
    time.sleep(0.35)
    osa('tell application "System Events" to key code 36')
    time.sleep(0.2)
    subprocess.run(["pbcopy"], input=old, text=True)


def wait_reply(rect, base_lines: list[str], question: str, shot_dir: str, tag: str, timeout=75, settle=6.0):
    t0 = time.time()
    last_hash, last_change, changes = None, time.time(), 0
    tmp = os.path.join(shot_dir, f".poll_{tag}.png")
    while time.time() - t0 < timeout:
        if os.path.exists(os.path.join(STATE_DIR, "STOP")):
            raise KeyboardInterrupt
        capture(rect, tmp)
        h = img_small(tmp)
        if last_hash is not None and changed(last_hash, h):
            changes += 1
            last_change = time.time()
        last_hash = h
        if changes >= 1 and time.time() - last_change >= settle:
            lines = ocr(tmp)
            reply = new_lines(base_lines, lines, question)
            if reply:
                final = os.path.join(shot_dir, f"{tag}.png")
                os.replace(tmp, final)
                return reply, final, False
        time.sleep(1.5)
    final = os.path.join(shot_dir, f"{tag}_timeout.png")
    if os.path.exists(tmp):
        os.replace(tmp, final)
    return new_lines(base_lines, ocr(final), question) if os.path.exists(final) else [], final, True


def log_entry(person: str, qid: str, question: str, reply: list[str], shot: str, timeout: bool):
    path = os.path.join(ROOT, "inbox", "interviews", f"{person}.md")
    flags = []
    joined = "\n".join(reply)
    if "전체보기" in joined:
        flags.append("⚠️ 답이 잘림('전체보기') — 카톡에서 원문을 복사해 이 항목 아래에 붙여넣기 필요")
    if timeout:
        flags.append("⚠️ 75초 안에 답 완료를 확인하지 못함 — 캡처 확인 필요")
    body = (f"\n## {now()} {qid} (자동 전송 · bin/interview_runner, 사용자 묶음 승인)\n"
            f"나: {question}\n\n{person} (OCR 인식 — 오인식 가능, 캡처 원본이 정본):\n{joined or '(인식된 새 줄 없음)'}\n\n"
            f"[캡처] {os.path.relpath(shot, ROOT)}\n" + "".join(f"{f}\n" for f in flags))
    with open(path, "a", encoding="utf-8") as f:
        f.write(body)


def notify(person: str, n: int):
    env = dict(os.environ, AGENT_ID="HUMAN")
    sh([sys.executable, os.path.join(ROOT, "coord", "coord.py"), "post", "--to", "A1", "--type", "INBOX",
        f"{person} 자동 인터뷰 {n}건 기록(OCR+캡처). 큐 갱신·잘림 표시 확인 요청",
        "--ref", f"inbox/interviews/{person}.md"], env=env)


# ── 메인 ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--person", required=True, help="kb/questions/<이름>.md·inbox/interviews/<이름>.md의 이름")
    ap.add_argument("--window", help="카톡 대화방 창 제목(기본: --person과 같음)")
    ap.add_argument("--max", type=int, default=5, help="묶음 크기(최대 10)")
    ap.add_argument("--top", type=int, default=105, help="캡처에서 뺄 창 위쪽 높이(px)")
    ap.add_argument("--bottom", type=int, default=122, help="캡처에서 뺄 입력창 높이(px)")
    ap.add_argument("--status", action="store_true", help="묶음 끝에 ./status 전송(차감 없음)")
    ap.add_argument("--dry-run", action="store_true", help="큐 검증·목록 출력만")
    ap.add_argument("--check", action="store_true", help="권한·창·캡처 영역 점검(전송 안 함)")
    a = ap.parse_args()
    title = a.window or a.person
    batch = max(1, min(a.max, 10))
    st = load_state(a.person)
    q = load_queue(a.person, st)
    ok = [x for x in q if not x[2]]
    print(f"[{a.person}] 미전송 {len(q)}건, 보낼 수 있음 {len(ok)}건, 누적 기록 {len(st['sent'])}건")
    for qid, text, why in q:
        if why:
            print(f"  ✗ {qid} 거부: {why} — A1에게 수정 요청")
    if a.dry_run:
        for qid, text, _ in ok[:batch]:
            print(f"  → {qid} ({len(text)}자) {text}")
        return
    if not os.path.exists(HELPER):
        sys.exit("보조 도구 없음: swiftc -O bin/kakao_helper.swift -o .coord/bin/kakao_helper")
    shot_dir = os.path.join(ROOT, "inbox", "images", "auto", a.person)
    os.makedirs(shot_dir, exist_ok=True)
    w = find_window(title)
    rect = region(w, a.top, a.bottom)
    if a.check:
        raise_window(title)
        p = capture(rect, os.path.join(shot_dir, "_check_region.png"))
        lines = ocr(p)
        print(f"창 OK {w} / 캡처 영역 {rect} / OCR {len(lines)}줄 — 확인 이미지: {os.path.relpath(p, ROOT)}")
        print("  마지막 3줄:", lines[-3:])
        return
    todo = ok[:batch]
    if not todo:
        print("보낼 질문이 없습니다. A1이 kb/questions에 다음 질문을 올릴 때까지 기다리세요.")
        return
    if len(st["sent"]) + len(todo) > MAX_PER_PERSON:
        sys.exit(f"누적 상한 {MAX_PER_PERSON}건 초과 — 중단")
    print(f"\n대상 창: '{title}'. 아래 {len(todo)}건을 한 건씩, 답을 받은 뒤에 보냅니다:")
    for qid, text, _ in todo:
        print(f"  {qid} ({len(text)}자) {text}")
    if input("\n보내려면 APPROVE 입력(그 외 입력은 취소): ").strip() not in ("APPROVE", "승인"):
        print("취소했습니다.")
        return
    done = 0
    try:
        for qid, text, _ in todo:
            base = os.path.join(shot_dir, f".base_{qid}.png")
            capture(rect, base)
            base_lines = ocr(base)
            send(title, text)
            st["sent"].append(qid)
            save_state(a.person, st)
            stamp = dt.datetime.now().strftime("%H%M%S")
            reply, shot, to = wait_reply(rect, base_lines, text, shot_dir, f"{stamp}_{qid}")
            log_entry(a.person, qid, text, reply, shot, to)
            done += 1
            print(f"  ✓ {qid} 답 {len(reply)}줄{' (타임아웃)' if to else ''} → 기록")
            if any("[SYSTEM]" in l for l in reply):
                print("  ⛔ [SYSTEM] 안내 감지 — 묶음을 멈춥니다. 내용을 확인하세요.")
                break
            if to:
                print("  ⛔ 답 완료를 확인하지 못해 멈춥니다(다음 질문 미전송).")
                break
            time.sleep(4)
        if a.status and done:
            base = os.path.join(shot_dir, ".base_status.png")
            capture(rect, base)
            send(title, "./status")
            reply, shot, to = wait_reply(rect, ocr(base), "./status", shot_dir, f"{dt.datetime.now():%H%M%S}_status", timeout=30, settle=3)
            log_entry(a.person, "./status", "./status", reply, shot, to)
            print("  ✓ ./status:", " ".join(reply)[:120])
    except KeyboardInterrupt:
        print("\n중지 요청 — 여기서 멈춥니다.")
    finally:
        if done:
            notify(a.person, done)
        print(f"완료 {done}건. 기록: inbox/interviews/{a.person}.md")


if __name__ == "__main__":
    main()
