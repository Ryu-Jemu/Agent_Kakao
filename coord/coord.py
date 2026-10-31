#!/usr/bin/env python3
"""SHARED_BOARD.md 조정 CLI (표준 라이브러리만 사용).

AGENTS.md U1~U6을 기계적으로 강제한다.
- 보드 쓰기는 fcntl 잠금을 잡고 tmp 파일에 쓴 뒤 os.replace로 원자 교체한다.
- 훅 3종(hook-pre/hook-post/hook-prompt)은 환경변수 AGENT_ID가 없으면 아무것도 하지 않는다.
- CLI 호출자 ID는 AGENT_ID → --agent → 'SETUP' 순으로 정한다.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))  # realpath: 심볼릭 링크 경로 우회 방지
BOARD = os.path.join(ROOT, "SHARED_BOARD.md")
STATE = os.path.join(ROOT, ".coord")
OWNERS = os.path.join(ROOT, "coord", "owners.json")
AGENTS = ["A0", "A1", "A2", "A3", "A4", "A5", "A6"]
RESULT = {"ok": "✅성공", "fail": "❌실패", "partial": "⚠️부분"}
TC_RESULT = {"ok": "✅", "fail": "❌", "partial": "⚠️"}
WU_STATUS = {"todo": "⬜", "doing": "🔄", "done": "✅", "blocked": "⛔"}
EVENT_TYPES = {"TASK_NEW", "TASK_DONE", "WU", "CONTRACT", "KB_UPDATE", "BUILD", "DEPLOY", "TEST_REPORT",
               "ANALYSIS", "GATE", "DATA_RESET", "FREEZE", "REQUEST", "BLOCKER", "DECISION", "HUMAN_TODO",
               "INBOX", "READ_AGAIN", "INFO"}


# ───────────────────────── 공통 유틸 ─────────────────────────
def now_hm() -> str:
    return dt.datetime.now().strftime("%H:%M")


def now_full() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M KST")


def esc(s) -> str:
    return str(s if s not in (None, "") else "-").replace("|", "¦").replace("\r", "").replace("\n", " / ").strip()


def die(msg: str, code: int = 2):
    print(f"[coord] 거부: {msg}", file=sys.stderr)
    sys.exit(code)


def owners() -> dict:
    with open(OWNERS, encoding="utf-8") as f:
        return json.load(f)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: str) -> str:
    p = os.path.abspath(path)
    return os.path.relpath(p, ROOT)


def state_path(*parts) -> str:
    p = os.path.join(STATE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_int(path: str, default: int = 0) -> int:
    try:
        with open(path) as f:
            return int(f.read().strip() or default)
    except (FileNotFoundError, ValueError):
        return default


def write_text(path: str, text: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


@contextlib.contextmanager
def locked():
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "board.lock"), "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def load() -> str:
    with open(BOARD, encoding="utf-8") as f:
        return f.read()


def save(text: str):
    write_text(BOARD, text)
    os.chmod(BOARD, 0o444)  # 훅 없는 런타임(Codex 등)의 직접 편집 차단. os.replace는 디렉터리 권한으로 동작한다.


# ───────────────────────── 보드 구조 ─────────────────────────
def sec_bounds(text: str, name: str):
    b, e = f"<!-- SEC:{name}:BEGIN -->", f"<!-- SEC:{name}:END -->"
    i, j = text.find(b), text.find(e)
    if i < 0 or j < 0:
        die(f"보드에 섹션 {name}이 없습니다")
    return i + len(b), j


def get_sec(text: str, name: str) -> str:
    i, j = sec_bounds(text, name)
    return text[i:j]


def set_sec(text: str, name: str, content: str) -> str:
    i, j = sec_bounds(text, name)
    if not content.startswith("\n"):
        content = "\n" + content
    if not content.endswith("\n"):
        content += "\n"
    return text[:i] + content + text[j:]


def get_version(text: str) -> int:
    m = re.search(r"<!-- BOARD_VERSION: (\d+) -->", text)
    return int(m.group(1)) if m else 0


def set_version(text: str, v: int) -> str:
    return re.sub(r"<!-- BOARD_VERSION: \d+ -->", f"<!-- BOARD_VERSION: {v} -->", text, count=1)


def split_row(line: str):
    s = line.strip()
    return [c.strip() for c in s[1:-1].split("|")]


def fmt_row(cells) -> str:
    return "| " + " | ".join(esc(c) for c in cells) + " |"


def table(content: str):
    """(lines, header, [(line_idx, cells)]) — 헤더와 구분선을 제외한 데이터 행."""
    lines = content.split("\n")
    header, rows, seen_sep = None, [], False
    for idx, ln in enumerate(lines):
        if not ln.strip().startswith("|"):
            continue
        if header is None:
            header = split_row(ln)
            continue
        if not seen_sep and re.match(r"^\|\s*-", ln.strip()):
            seen_sep = True
            continue
        rows.append((idx, split_row(ln)))
    return lines, header, rows


def append_row(content: str, cells) -> str:
    lines, header, rows = table(content)
    last = rows[-1][0] if rows else max(i for i, ln in enumerate(lines) if ln.strip().startswith("|"))
    lines.insert(last + 1, fmt_row(cells))
    return "\n".join(lines)


def replace_row(content: str, key: str, cells) -> str:
    lines, header, rows = table(content)
    for idx, c in rows:
        if c and c[0] == key:
            lines[idx] = fmt_row(cells)
            return "\n".join(lines)
    die(f"행 {key}을 찾지 못했습니다")


def find_row(content: str, key: str):
    _, header, rows = table(content)
    for _, c in rows:
        if c and c[0] == key:
            return header, c
    return header, None


def mutate(fn):
    """잠금 → 최신 보드 로드 → fn(text)->text → 저장."""
    with locked():
        text = load()
        new = fn(text)
        if new is not None and new != text:
            save(new)
        return new


# ───────────────────────── 이벤트 ─────────────────────────
def events(text: str):
    _, _, rows = table(get_sec(text, "EVENTS"))
    out = []
    for _, c in rows:
        if len(c) < 7 or not c[0].isdigit():
            continue
        frm, _, to = c[2].partition("→")
        out.append({"seq": int(c[0]), "time": c[1], "from": frm, "to": [t.strip() for t in to.split(",")],
                    "type": c[3], "msg": c[4], "ref": c[5], "ack": c[6]})
    return out


def relevant(ev, agent: str) -> bool:
    if agent == "HUMAN":  # 사람에게는 명시적으로 HUMAN을 지목한 요청만 보낸다(U8, ALL 소음 제외)
        return "HUMAN" in ev["to"]
    return ev["from"] != agent and ("ALL" in ev["to"] or agent in ev["to"])


def ev_line(ev) -> str:
    return f"#{ev['seq']} {ev['time']} {ev['from']}→{','.join(ev['to'])} [{ev['type']}] {ev['msg']} (ref: {ev['ref']})"


def post_event(text: str, agent: str, to: str, etype: str, msg: str, ref: str = "-") -> tuple[str, int]:
    seq = get_version(text) + 1
    sec = append_row(get_sec(text, "EVENTS"), [seq, now_hm(), f"{agent}→{to}", etype, msg, ref, "-"])
    text = set_sec(text, "EVENTS", sec)
    return set_version(text, seq), seq


# ───────────────────────── 명령 구현 ─────────────────────────
def cmd_status(a):
    text = load()
    ag = a.agent
    print(f"== {ag} · BOARD_VERSION {get_version(text)} · seen {read_int(state_path('seen', ag))}")
    print("-- NEXT\n" + get_sec(text, "NEXT").split("\n", 2)[-1].rstrip())
    _, _, wus = table(get_sec(text, "WORK_UNITS"))
    mine = [c for _, c in wus if c[1] == ag]
    if mine:
        print("-- 내 WU")
        for c in mine:
            print(f"   {c[0]} {c[4]} {c[2]} (선행 {c[3]}) 남은: {c[6]} 다음: {c[7]}")
    _, _, tasks = table(get_sec(text, "TASKS"))
    mt = [c for _, c in tasks if len(c) > 1 and c[1] == ag and c[2] != "DONE"]
    if mt:
        print("-- 내 TASKS")
        for c in mt:
            print("   " + " | ".join(c))
    evs = events(text)
    unacked = [e for e in evs if e["type"] in ("CONTRACT", "FREEZE") and relevant(e, ag) and ag not in e["ack"]]
    if unacked:
        print("-- 미ACK (반영 후 coord.py ack <seq>)")
        for e in unacked:
            print("   " + ev_line(e))
    print("-- 최근 이벤트")
    for e in evs[-8:]:
        print(("*  " if relevant(e, ag) else "   ") + ev_line(e))
    _, _, runs = table(get_sec(text, "RUNLOG"))
    fails = [c for _, c in runs if "❌" in c[4]][-5:]
    if fails:
        print("-- 최근 실패(재시도 금지사항 확인)")
        for c in fails:
            print(f"   {c[0]} {c[2]} {c[3]} — {c[7]} / 금지: {c[8]}")


def cmd_pull(a):
    text = load()
    ag = a.agent
    seen = read_int(state_path("seen", ag))
    evs = [e for e in events(text) if e["seq"] > seen]
    for e in evs:
        print(("* " if relevant(e, ag) else "  ") + ev_line(e))
    if not evs:
        print("(새 이벤트 없음)")
    v = get_version(text)
    write_text(state_path("seen", ag), str(v))
    write_text(state_path("notified", ag), str(v))


def cmd_post(a):
    if a.type not in EVENT_TYPES:
        die(f"TYPE은 {sorted(EVENT_TYPES)} 중 하나")
    box = {}

    def fn(text):
        new, seq = post_event(text, a.agent, a.to, a.type, a.msg, a.ref)
        box["seq"] = seq
        return new
    mutate(fn)
    print(f"#{box['seq']} 게시")


def cmd_ack(a):
    def fn(text):
        sec = get_sec(text, "EVENTS")
        lines, _, rows = table(sec)
        for idx, c in rows:
            if c[0] == str(a.seq):
                acks = [x for x in c[6].split(",") if x and x != "-"]
                if a.agent not in acks:
                    acks.append(a.agent)
                c[6] = ",".join(acks)
                lines[idx] = fmt_row(c)
                return set_sec(text, "EVENTS", "\n".join(lines))
        die(f"이벤트 #{a.seq} 없음")
    mutate(fn)
    print(f"#{a.seq} ACK")


def cmd_section(a):
    name = a.name or f"STATUS:{a.agent}"
    admin = owners()["board_admin"]
    if name.startswith("STATUS:"):
        if name != f"STATUS:{a.agent}" and a.agent not in admin:
            die("자기 STATUS 섹션만 수정할 수 있습니다")
    elif name in ("FACTS", "NEXT", "DECISIONS", "OWNERS"):
        if a.agent not in admin:
            die(f"{name}은 A0만 수정합니다(필요하면 REQUEST)")
    else:
        die(f"{name}은 section 명령으로 수정할 수 없습니다(전용 명령 사용)")
    body = open(a.file, encoding="utf-8").read() if a.file else a.set
    if body is None:
        die("--set 또는 --file 필요")

    def fn(text):
        cur = get_sec(text, name)
        head = next((ln for ln in cur.split("\n") if ln.startswith("## ")), f"## {name}")
        if name.startswith("STATUS:"):
            hand = cur[cur.find("### HANDOFF"):] if "### HANDOFF" in cur else ""
            return set_sec(text, name, f"{head}\n{body.strip()}\n\n{hand.strip()}\n")
        return set_sec(text, name, f"{head}\n{body.strip()}\n")
    mutate(fn)
    print(f"{name} 갱신")


HANDOFF_REQ = ["- 상태:", "- 마지막 성공:", "- 남은 단계", "- 다음 명령"]


def cmd_handoff(a):
    body = open(a.file, encoding="utf-8").read() if a.file else (a.text or "")
    missing = [k for k in HANDOFF_REQ if k not in body]
    if missing:
        die(f"HANDOFF 필수 항목 누락: {missing} (AGENTS.md §4 형식)")
    block = f"### HANDOFF {a.wu} {now_full()} {a.agent}\n" + "\n".join(
        ln for ln in body.strip().split("\n") if not ln.startswith("### HANDOFF"))
    name = f"STATUS:{a.agent}"

    def fn(text):
        cur = get_sec(text, name)
        head_end = cur.find("### HANDOFF")
        top = cur if head_end < 0 else cur[:head_end]
        blocks = re.split(r"(?=### HANDOFF )", cur[head_end:]) if head_end >= 0 else []
        blocks = [b.strip() for b in blocks if b.strip() and not b.startswith(f"### HANDOFF {a.wu} ")]
        blocks = [block] + blocks[:2]  # 최신 3개 유지
        return set_sec(text, name, top.rstrip() + "\n\n" + "\n\n".join(blocks) + "\n")
    mutate(fn)
    print(f"HANDOFF {a.wu} 기록")


def cmd_read(a):
    files = []
    for pat in a.files:
        hits = sorted(glob.glob(os.path.join(ROOT, pat))) or ([pat] if os.path.exists(pat) else [])
        if not hits:
            die(f"파일 없음: {pat}")
        files += hits
    rec_path = state_path("read", f"{a.agent}.json")
    try:
        rec = json.load(open(rec_path))
    except (FileNotFoundError, json.JSONDecodeError):
        rec = {}
    for f in files:
        rec[rel(f)] = sha256(f)
    write_text(rec_path, json.dumps(rec, ensure_ascii=False, indent=1))
    summary = ", ".join(f"{os.path.basename(k)}:{v[:8]}" for k, v in sorted(rec.items()))

    def fn(text):
        sec = get_sec(text, "READ")
        _, _, rows = table(sec)
        cells = [a.agent, now_hm(), summary]
        if any(c[0] == a.agent for _, c in rows):
            return set_sec(text, "READ", replace_row(sec, a.agent, cells))
        return set_sec(text, "READ", append_row(sec, cells))
    mutate(fn)
    miss = missing_reading(a.agent)
    print(f"필독 기록 {len(files)}건." + (f" 아직 미기록·변경: {miss}" if miss else " 필독 요건 충족."))


def missing_reading(agent: str):
    req = owners()["required_reading"].get(agent, [])
    try:
        rec = json.load(open(os.path.join(STATE, "read", f"{agent}.json")))
    except (FileNotFoundError, json.JSONDecodeError):
        rec = {}
    miss = []
    for pat in req:
        hits = sorted(glob.glob(os.path.join(ROOT, pat)))
        if not hits:
            miss.append(f"{pat}(파일 없음)")
        for h in hits:
            r = rel(h)
            if rec.get(r) != sha256(h):
                miss.append(r)
    return miss


def cmd_log_add(a):
    if a.result not in RESULT:
        die("--result는 ok|fail|partial")
    if a.result == "fail" and (not a.issue or not a.fix):
        die("실패 기록에는 --issue(원인)와 --fix(조치·재시도 금지사항)가 필수입니다(R2)")
    box = {}

    def fn(text):
        sec = get_sec(text, "RUNLOG")
        _, _, rows = table(sec)
        if a.retry_of:
            prev = next((c for _, c in rows if c[0] == a.retry_of), None)
            if prev is None:
                die(f"{a.retry_of} 없음")
            if "❌" in prev[4] and not a.change:
                die(f"{a.retry_of}은 실패 건입니다. --change '달라진 점' 없이 같은 접근을 반복할 수 없습니다(R2)")
        n = max([int(c[0][2:]) for _, c in rows if c[0].startswith("R-") and c[0][2:].isdigit()] + [0]) + 1
        rid = f"R-{n:03d}"
        retry = f"{a.retry_of} ({a.change})" if a.retry_of else "-"
        cells = [rid, now_hm(), a.agent, a.task, RESULT[a.result], a.command, a.evidence, a.issue, a.fix, retry]
        box["rid"] = rid
        text = set_sec(text, "RUNLOG", append_row(sec, cells))
        if a.result == "fail":
            text, _ = post_event(text, a.agent, "A0", "BLOCKER" if a.blocker else "INFO", f"{rid} 실패: {a.task}", a.evidence)
        return text
    mutate(fn)
    print(box["rid"])


def cmd_log_search(a):
    _, _, rows = table(get_sec(load(), "RUNLOG"))
    kw = a.keyword.lower()
    hits = [c for _, c in rows if kw in " ".join(c).lower()]
    for c in hits:
        print(" | ".join(c))
    if not hits:
        print("(이력 없음 — 새 작업)")


def cmd_tc_set(a):
    if a.agent not in (owners()["tc_matrix_writer"], "SETUP"):
        die("TC_MATRIX는 A4만 갱신합니다")
    if a.result not in TC_RESULT:
        die("--result는 ok|fail|partial")
    if a.result != "ok" and not a.why:
        die("실패·부분에는 --why(원인)가 필수입니다")

    def fn(text):
        sec = get_sec(text, "TC_MATRIX")
        header, row = find_row(sec, a.id)
        if row is None:
            die(f"TC {a.id}가 매트릭스에 없습니다")
        row[3:8] = [TC_RESULT[a.result], a.build, now_hm(), a.why or "-", a.run]
        return set_sec(text, "TC_MATRIX", replace_row(sec, a.id, row))
    mutate(fn)
    print(f"{a.id} → {TC_RESULT[a.result]}")


TC_EXPECTED = 15  # 공개 TC 목록 페이지 기준(docs/contest/07_public_tc_index.md). 목록이 늘면 A0가 갱신한다.


def tc_source_ids() -> tuple[list[str], list[str]]:
    """원문 ID 목록과 무결성 문제. 원문 ID는 파일 본문의 '- id:'와 파일명이 일치해야 한다."""
    problems, ids = [], []
    pub = os.path.join(ROOT, "tests", "tc", "public")
    for p in sorted(glob.glob(os.path.join(pub, "*.md"))):
        fid = os.path.basename(p)[:-3]
        m = re.search(r"^- id: (\S+)$", open(p, encoding="utf-8").read(), re.M)
        if not m or m.group(1) != fid:
            problems.append(f"{fid}: 원문 본문의 '- id:'가 파일명과 다름/없음")
        ids.append(fid)
    man = os.path.join(pub, "MANIFEST.sha256")
    if not os.path.exists(man):
        problems.append("tests/tc/public/MANIFEST.sha256 없음(원문 무결성 검증 불가)")
    else:
        listed = set()
        for ln in open(man, encoding="utf-8"):
            h, _, name = ln.strip().partition("  ")
            listed.add(name)
            fp = os.path.join(pub, name)
            if not os.path.exists(fp) or sha256(fp) != h:
                problems.append(f"{name}: MANIFEST 해시 불일치 또는 파일 없음(원문 변조)")
        for fid in ids:
            if f"{fid}.md" not in listed:
                problems.append(f"{fid}.md: MANIFEST에 없는 원문")
    return ids, problems


def cmd_tc_check(a):
    """R3 제출 게이트. 하나라도 걸리면 NO-GO(exit 1). AGENTS.md U5: 예외 없음."""
    _, _, rows = table(get_sec(load(), "TC_MATRIX"))
    problems = []
    # 1) 빌드 SHA는 실제 git 커밋이어야 한다
    r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", f"{a.build}^{{commit}}"], capture_output=True)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.build or "") or r.returncode != 0:
        problems.append(f"빌드 '{a.build}'는 이 저장소의 git 커밋이 아님(릴리스 SHA 필요)")
    # 2) 원문 ID 집합과 매트릭스 ID 집합의 양방향 일치·중복
    src, src_problems = tc_source_ids()
    problems += src_problems
    mids = [c[0] for _, c in rows]
    dup = sorted({i for i in mids if mids.count(i) > 1})
    if dup:
        problems.append(f"매트릭스 중복 ID: {dup}")
    if len(src) != TC_EXPECTED:
        problems.append(f"원문 {len(src)}건 ≠ 기대 {TC_EXPECTED}건")
    for i in sorted(set(src) - set(mids)):
        problems.append(f"{i}: 원문은 있으나 매트릭스에 없음")
    for i in sorted(set(mids) - set(src)):
        problems.append(f"{i}: 매트릭스에만 있고 원문 없음")
    # 3) 행별 결과·빌드·증거(파일 실재 + 내용에 TC ID와 빌드 SHA 포함)
    for _, c in rows:
        tid, res, build, ev = c[0], c[3], c[4], c[7]
        if res != "✅":
            problems.append(f"{tid}: 결과 {res} {c[6]}")
            continue
        if build != a.build:
            problems.append(f"{tid}: 빌드 {build} ≠ 릴리스 {a.build}")
        evp = ev if os.path.isabs(ev) else os.path.join(ROOT, ev)
        if ev in ("-", "") or not os.path.isfile(evp) or os.path.getsize(evp) == 0:
            problems.append(f"{tid}: 증거 파일 없음/빈 파일({ev})")
            continue
        body = open(evp, encoding="utf-8", errors="replace").read()
        if tid not in body or a.build not in body:
            problems.append(f"{tid}: 증거({ev})에 TC ID 또는 빌드 SHA가 없음")
    print(f"TC_MATRIX {len(mids)}행 / 원문 {len(src)}건 / 기대 {TC_EXPECTED}건 / 빌드 {a.build}")
    for p in problems:
        print("  ✗ " + p)
    if problems:
        print("결과: NO-GO (R3 미충족 — 예외 없음, AGENTS.md U5)")
        sys.exit(1)
    print(f"결과: {TC_EXPECTED}/{TC_EXPECTED} ✅ (R3 충족)")


def cmd_task(a):
    def fn(text):
        sec = get_sec(text, "TASKS")
        _, _, rows = table(sec)
        if a.action == "new":
            n = max([int(c[0][2:]) for _, c in rows if c[0].startswith("T-")] + [0]) + 1
            tid = f"T-{n:03d}"
            sec = append_row(sec, [tid, a.owner, "TODO", a.deps, a.title, a.out, a.agent])
            text = set_sec(text, "TASKS", sec)
            text, _ = post_event(text, a.agent, a.owner, "TASK_NEW", f"{tid} {a.title}", a.out)
            print(tid)
            return text
        header, row = find_row(sec, a.id)
        if row is None:
            die(f"{a.id} 없음")
        if row[1] != a.agent and a.agent not in owners()["board_admin"]:
            die(f"{a.id}의 owner는 {row[1]}입니다")
        row[2] = {"claim": "DOING", "done": "DONE", "block": "BLOCKED", "review": "REVIEW"}[a.action]
        text = set_sec(text, "TASKS", replace_row(sec, a.id, row))
        if a.action in ("done", "block"):
            text, _ = post_event(text, a.agent, row[6] if row[6] != a.agent else "A0",
                                 "TASK_DONE" if a.action == "done" else "BLOCKER", f"{a.id} {row[2]} {a.note or ''}", row[5])
        print(f"{a.id} → {row[2]}")
        return text
    mutate(fn)


def cmd_wu(a):
    if a.action == "next":
        text = load()
        print(get_sec(text, "NEXT").strip())
        _, _, rows = table(get_sec(text, "WORK_UNITS"))
        done = {c[0] for _, c in rows if c[4] == "✅"}
        ids = {c[0] for _, c in rows}
        # 선행이 WU ID면 ✅여야 한다. 마일스톤(M2 등)·'-'는 ORCH 판단에 맡기고 통과시킨다.
        ready = [c for _, c in rows if c[1] == a.agent and c[4] in ("⬜", "🔄")
                 and all(d.strip() in done or d.strip() not in ids for d in c[3].split(","))]
        print(f"-- {a.agent} 착수 가능 WU")
        for c in ready:
            print(f"   {c[0]} {c[4]} {c[2]} (선행 {c[3]})")
        return

    def fn(text):
        sec = get_sec(text, "WORK_UNITS")
        if a.action == "add":
            if a.agent not in owners()["board_admin"]:
                die("WU 추가는 A0만 합니다")
            sec = append_row(sec, [a.id, a.owner, a.title, a.deps or "-", "⬜", "-", "-", "-"])
            return set_sec(text, "WORK_UNITS", sec)
        header, row = find_row(sec, a.id)
        if row is None:
            die(f"WU {a.id} 없음")
        if row[1] != a.agent and a.agent not in owners()["board_admin"]:
            die(f"WU {a.id}의 담당은 {row[1]}입니다")
        if a.status:
            row[4] = WU_STATUS[a.status]
        if a.record:
            # A6 BLOCKER #7: 예상 번호·타인 번호 오기 방지 — 존재하고 내가 기록한 R-번호만 허용(--foreign으로 명시적 예외)
            _, _, runs = table(get_sec(text, "RUNLOG"))
            owner_of = {c[0]: c[2] for _, c in runs}
            for rid in [x.strip() for x in a.record.split(",") if x.strip() not in ("", "-")]:
                if rid not in owner_of:
                    die(f"--record {rid}: RUNLOG에 없는 번호입니다(log add가 반환한 번호만 사용)")
                if owner_of[rid] != a.agent and not a.foreign:
                    die(f"--record {rid}: {owner_of[rid]}가 기록한 항목입니다. 타인 기록을 인용하려면 --foreign")
            row[5] = a.record
        if a.remaining is not None:
            row[6] = a.remaining
        if a.next is not None:
            row[7] = a.next
        if a.owner and a.agent in owners()["board_admin"]:
            row[1] = a.owner
        text = set_sec(text, "WORK_UNITS", replace_row(sec, a.id, row))
        if a.status in ("done", "blocked"):
            text, _ = post_event(text, a.agent, "ALL", "WU" if a.status == "done" else "BLOCKER",
                                 f"WU {a.id} {row[4]} {row[2]}", row[5])
        return text
    mutate(fn)
    print(f"WU {a.id} 갱신")


def cmd_contract(a):
    own = owners()["contracts"].get(a.id)
    if own is None:
        die(f"계약 {a.id} 없음")
    if a.agent != own and a.agent not in owners()["board_admin"]:
        die(f"{a.id} 소유자는 {own}입니다")

    def fn(text):
        sec = get_sec(text, "CONTRACTS")
        lines = sec.split("\n")
        line = f"- {a.id} ({own}) {esc(a.text)}"
        idx = next((i for i, ln in enumerate(lines) if ln.startswith(f"- {a.id} ")), None)
        if idx is None:
            lines.insert(len(lines) - 1, line)
        else:
            lines[idx] = line
        text = set_sec(text, "CONTRACTS", "\n".join(lines))
        text, _ = post_event(text, a.agent, "ALL", "CONTRACT", f"{a.id} 변경: {a.text[:80]}", a.ref)
        return text
    mutate(fn)
    print(f"{a.id} 갱신 — 소비자 ACK 필요")


def cmd_watch(a):
    ag = a.agent
    last = max(read_int(state_path("seen", ag)), read_int(state_path("notified", ag)))
    inbox_mt = inbox_mtime() if ag == "A1" else 0
    print(f"[watch] {ag} 대기 시작 (기준 #{last})", flush=True)
    while True:
        try:
            text = load()
            for e in events(text):
                if e["seq"] > last and relevant(e, ag):
                    print("[BOARD] " + ev_line(e), flush=True)
            last = max(last, get_version(text))
            if ag == "A1":
                m = inbox_mtime()
                if m > inbox_mt:
                    print(f"[INBOX] inbox/ 변경 감지 {dt.datetime.fromtimestamp(m).strftime('%H:%M:%S')}", flush=True)
                    inbox_mt = m
        except Exception as ex:  # 감시는 죽지 않는다
            print(f"[watch] 오류 {ex}", flush=True)
        time.sleep(a.interval)


def inbox_mtime() -> float:
    m = 0.0
    for p in glob.glob(os.path.join(ROOT, "inbox", "**", "*"), recursive=True):
        if os.path.isfile(p):
            m = max(m, os.path.getmtime(p))
    return m


def cmd_audit(a):
    o = owners()
    out = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"], capture_output=True, text=True).stdout
    problems = 0
    for ln in out.splitlines():
        path = ln[3:].strip().strip('"')
        owner = path_owner(path, o)
        ro = is_readonly(path, o)
        flag = "READONLY 변경!" if ro and ln[:2].strip() not in ("??", "A") else ""
        if owner is None and not ro:
            flag = flag or "소유자 없음"
        if flag:
            problems += 1
        print(f"{ln[:2]} {path:60s} owner={owner or '-'} {flag}")
    for man in ("docs/contest/MANIFEST.sha256", "tests/tc/public/MANIFEST.sha256"):
        mp = os.path.join(ROOT, man)
        if os.path.exists(mp):
            r = subprocess.run(["shasum", "-a", "256", "-c", os.path.basename(mp)], cwd=os.path.dirname(mp),
                               capture_output=True, text=True)
            ok = r.returncode == 0
            problems += 0 if ok else 1
            print(f"{man}: {'원문 무결 ✅' if ok else '원문 변경 ❌'}")
    print(f"audit 문제 {problems}건")
    sys.exit(1 if problems else 0)


# ───────────────────────── 소유권·훅 ─────────────────────────
def match(path: str, pats) -> bool:
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in pats)


def is_readonly(path: str, o) -> bool:
    return match(path, o["readonly"])


def path_owner(path: str, o):
    for ag, spec in o["agents"].items():
        if match(path, spec["write"]):
            return ag
    return None


def hook_out(event: str, ctx: str | None = None, deny: str | None = None):
    if deny:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": deny}}, ensure_ascii=False))
    elif ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}, ensure_ascii=False))
    sys.exit(0)


def cmd_hook_pre(_a):
    ag = os.environ.get("AGENT_ID")
    if not ag:
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp:
        sys.exit(0)
    ap = os.path.realpath(os.path.join(data.get("cwd") or ROOT, fp))
    if not ap.startswith(ROOT + os.sep):
        sys.exit(0)  # 저장소 밖(스크래치 등)은 관여하지 않는다
    path = os.path.relpath(ap, ROOT)
    o = owners()
    if path == "SHARED_BOARD.md":
        hook_out("PreToolUse", deny="SHARED_BOARD.md는 직접 편집 금지입니다. `python3 coord/coord.py …`(post/wu/log/section/handoff 등)로만 수정하세요 (AGENTS.md U2).")
    if is_readonly(path, o):
        hook_out("PreToolUse", deny=f"{path}는 읽기 전용 원문입니다(AGENTS.md U3/R1). 수정하지 말고 필요하면 A0에게 REQUEST 하세요.")
    miss = missing_reading(ag)
    if miss:
        hook_out("PreToolUse", deny=f"필독 기록 전에는 쓸 수 없습니다(R1). 다음을 읽고 `python3 coord/coord.py read <파일들>`을 실행하세요: {', '.join(miss[:12])}{' …' if len(miss) > 12 else ''}")
    spec = o["agents"].get(ag, {"write": []})
    if not match(path, spec["write"]):
        owner = path_owner(path, o) or "A0(소유자 미지정)"
        hook_out("PreToolUse", deny=f"{path}는 {owner}의 소유입니다(AGENTS.md U1). `python3 coord/coord.py post --to {owner.split('(')[0]} --type REQUEST \"무엇을 왜\" --ref <근거>`로 요청하세요.")
    sys.exit(0)


def cmd_hook_post(_a):
    ag = os.environ.get("AGENT_ID")
    if not ag:
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    event = data.get("hook_event_name") or "PostToolUse"
    try:
        text = load()
    except FileNotFoundError:
        sys.exit(0)
    seen = read_int(state_path("seen", ag))
    notified = read_int(state_path("notified", ag))
    base = max(seen, notified)
    new = [e for e in events(text) if e["seq"] > base and relevant(e, ag)]
    msgs = []
    if new:
        msgs.append(f"[BOARD] {ag}에게 새 이벤트 {len(new)}건(#{new[0]['seq']}~#{new[-1]['seq']}). 지금 하던 단계를 마무리하기 전에 `python3 coord/coord.py pull`로 확인하세요:")
        msgs += ["  " + ev_line(e) for e in new[-6:]]
        write_text(state_path("notified", ag), str(get_version(text)))
    if ag == "A1":
        mt_path = state_path("inbox_notified")
        m = inbox_mtime()
        if m > float(open(mt_path).read() if os.path.exists(mt_path) else 0):
            msgs.append("[INBOX] inbox/ 인터뷰 원문이 갱신되었습니다. KB 작업 루프 2단계를 수행하세요.")
            write_text(mt_path, str(m))
    if event == "UserPromptSubmit" and missing_reading(ag):
        msgs.append(f"[R1] 필독 미완료: {', '.join(missing_reading(ag)[:8])} … 읽은 뒤 `coord.py read`.")
    hook_out(event, ctx="\n".join(msgs) if msgs else None)


# ───────────────────────── CLI ─────────────────────────
def main():
    p = argparse.ArgumentParser(prog="coord.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("pull")
    s = sub.add_parser("post"); s.add_argument("--to", required=True); s.add_argument("--type", required=True); s.add_argument("msg"); s.add_argument("--ref", default="-")
    s = sub.add_parser("ack"); s.add_argument("seq", type=int)
    s = sub.add_parser("section"); s.add_argument("--name"); s.add_argument("--set"); s.add_argument("--file")
    s = sub.add_parser("handoff"); s.add_argument("--wu", required=True); s.add_argument("--file"); s.add_argument("--text")
    s = sub.add_parser("read"); s.add_argument("files", nargs="+")
    s = sub.add_parser("log"); ls = s.add_subparsers(dest="action", required=True)
    la = ls.add_parser("add")
    la.add_argument("--task", required=True)
    la.add_argument("--cmd", dest="command", required=True)  # 'cmd'는 서브커맨드 dest와 충돌
    la.add_argument("--evidence", required=True)
    la.add_argument("--result", required=True); la.add_argument("--issue"); la.add_argument("--fix")
    la.add_argument("--retry-of", dest="retry_of"); la.add_argument("--change"); la.add_argument("--blocker", action="store_true")
    lsr = ls.add_parser("search"); lsr.add_argument("keyword")
    s = sub.add_parser("tc"); ts = s.add_subparsers(dest="action", required=True)
    tset = ts.add_parser("set"); tset.add_argument("--id", required=True); tset.add_argument("--result", required=True)
    tset.add_argument("--build", required=True); tset.add_argument("--run", required=True); tset.add_argument("--why")
    tchk = ts.add_parser("check"); tchk.add_argument("--build", required=True)
    s = sub.add_parser("task"); s.add_argument("action", choices=["new", "claim", "review", "done", "block"])
    s.add_argument("--id"); s.add_argument("--owner"); s.add_argument("--title"); s.add_argument("--deps", default="-")
    s.add_argument("--out", default="-"); s.add_argument("--note")
    s = sub.add_parser("wu"); s.add_argument("action", choices=["set", "next", "add"]); s.add_argument("--id")
    s.add_argument("--status", choices=list(WU_STATUS)); s.add_argument("--record"); s.add_argument("--remaining")
    s.add_argument("--next"); s.add_argument("--owner"); s.add_argument("--title"); s.add_argument("--deps")
    s.add_argument("--foreign", action="store_true", help="타인이 기록한 R-번호 인용 허용")
    s = sub.add_parser("contract"); s.add_argument("--id", required=True); s.add_argument("--text", required=True); s.add_argument("--ref", default="-")
    s = sub.add_parser("watch"); s.add_argument("--interval", type=float, default=2.0)
    sub.add_parser("audit")
    sub.add_parser("hook-pre"); sub.add_parser("hook-post"); sub.add_parser("hook-prompt")
    a = p.parse_args()
    a.agent = os.environ.get("AGENT_ID") or a.agent or "SETUP"
    if a.cmd == "task" and a.action == "new" and not (a.owner and a.title):
        die("task new에는 --owner와 --title이 필요합니다")
    if a.cmd == "task" and a.action != "new" and not a.id:
        die("--id 필요")
    if a.cmd == "wu" and a.action in ("set", "add") and not a.id:
        die("--id 필요")
    dispatch = {
        "status": cmd_status, "pull": cmd_pull, "post": cmd_post, "ack": cmd_ack, "section": cmd_section,
        "handoff": cmd_handoff, "read": cmd_read, "task": cmd_task, "wu": cmd_wu, "contract": cmd_contract,
        "watch": cmd_watch, "audit": cmd_audit, "hook-pre": cmd_hook_pre, "hook-post": cmd_hook_post,
        "hook-prompt": cmd_hook_post,
    }
    if a.cmd == "log":
        (cmd_log_add if a.action == "add" else cmd_log_search)(a)
    elif a.cmd == "tc":
        (cmd_tc_set if a.action == "set" else cmd_tc_check)(a)
    else:
        dispatch[a.cmd](a)


if __name__ == "__main__":
    main()
