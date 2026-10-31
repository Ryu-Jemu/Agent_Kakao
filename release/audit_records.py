#!/usr/bin/env python3
"""체크리스트 8.1·8.3·8.4·8.5: 기록 규칙(R1~R3) 독립 감사. 보드·파일을 읽기만 한다.
실행: python3 release/audit_records.py  → 문제 0이면 exit 0.
- 8.1 READ 최신성: owners.json required_reading의 현재 sha256과 .coord/read/<ID>.json 기록 비교(coord 코드를 쓰지 않고 직접 계산)
- 8.3 미기록 실행: tests/runs/*, release/redteam/runs/* 산출물 디렉터리 이름이 RUNLOG 어느 행에도 언급되지 않으면 보고
- 8.4 ❌ 반복: ❌ 행 뒤에 같은 담당자의 유사 작업(토큰 자카드 ≥0.5)이 retry 칸 '-'로 다시 기록되면 보고
- 8.5 R-번호 무결성: WU 행 '기록'과 WU 완료 이벤트 ref의 R-번호가 RUNLOG에 있고 담당자가 같은지(다르면 보고, --foreign 여부는 보드에 남지 않으므로 '확인 필요')
"""
import glob
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sec(text, name):
    b, e = f"<!-- SEC:{name}:BEGIN -->", f"<!-- SEC:{name}:END -->"
    return text[text.index(b) + len(b):text.index(e)]


def rows(content):
    out, hdr, sep = [], None, False
    for ln in content.split("\n"):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if hdr is None:
            hdr = cells
            continue
        if not sep and re.match(r"^\|\s*-", s):
            sep = True
            continue
        out.append(cells)
    return out


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def toks(s):
    return set(re.findall(r"[가-힣A-Za-z0-9]{2,}", s.lower()))


def main():
    board = open(os.path.join(ROOT, "SHARED_BOARD.md"), encoding="utf-8").read()
    owners = json.load(open(os.path.join(ROOT, "coord", "owners.json"), encoding="utf-8"))
    runlog = rows(sec(board, "RUNLOG"))
    owner_of = {r[0]: r[2] for r in runlog if r and r[0].startswith("R-")}
    problems, notes = [], []

    # 8.1
    for ag, pats in owners["required_reading"].items():
        rec_p = os.path.join(ROOT, ".coord", "read", f"{ag}.json")
        rec = json.load(open(rec_p)) if os.path.exists(rec_p) else {}
        miss = []
        for pat in pats:
            hits = sorted(glob.glob(os.path.join(ROOT, pat)))
            if not hits:
                miss.append(f"{pat}(파일 없음)")
            for h in hits:
                r = os.path.relpath(h, ROOT)
                if rec.get(r) != sha(h):
                    miss.append(r)
        if miss:
            problems.append(f"8.1 {ag}: 필독 미기록·변경 {len(miss)}건 — {', '.join(miss[:4])}{' …' if len(miss) > 4 else ''}")
        else:
            notes.append(f"8.1 {ag}: 필독 {sum(len(glob.glob(os.path.join(ROOT, p))) for p in pats)}건 최신 ✅")

    # 8.3
    blob = "\n".join(" | ".join(r) for r in runlog)
    for d in sorted(glob.glob(os.path.join(ROOT, "tests", "runs", "*")) + glob.glob(os.path.join(ROOT, "release", "redteam", "runs", "*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        if name not in blob:
            mt = max([os.path.getmtime(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs] + [os.path.getmtime(d)])
            if time.time() - mt < 600:
                notes.append(f"8.3 {os.path.relpath(d, ROOT)}: RUNLOG 언급 없음 — 최근 10분 내 수정, 진행 중일 수 있음(확인 필요)")
            else:
                problems.append(f"8.3 미기록 실행 산출물: {os.path.relpath(d, ROOT)} (RUNLOG에 '{name}' 언급 없음)")
    # 8.4
    for i, r in enumerate(runlog):
        if len(r) < 10 or "❌" not in r[4]:
            continue
        for later in runlog[i + 1:]:
            if len(later) < 10 or later[2] != r[2]:
                continue
            a, b = toks(r[3]), toks(later[3])
            if a and b and len(a & b) / len(a | b) >= 0.5 and later[9] in ("-", ""):
                problems.append(f"8.4 ❌ {r[0]} 이후 {later[0]}({later[2]})가 유사 작업을 --retry-of 없이 기록: '{later[3][:60]}'")
    # 8.5
    for w in rows(sec(board, "WORK_UNITS")):
        if len(w) < 6 or w[5] in ("-", ""):
            continue
        for rid in [x.strip() for x in w[5].split(",") if x.strip()]:
            if rid not in owner_of:
                problems.append(f"8.5 WU {w[0]} 기록 {rid}: RUNLOG에 없음")
            elif owner_of[rid] != w[1] and not (w[1] == "SETUP" or owner_of[rid] == "SETUP"):
                notes.append(f"8.5 WU {w[0]}({w[1]}) 기록 {rid}는 {owner_of[rid]} 작성 — --foreign 인용인지 확인 필요")
    for e in rows(sec(board, "EVENTS")):
        if len(e) < 7 or e[3] != "WU":
            continue
        frm = e[2].split("→")[0]
        for rid in re.findall(r"R-\d{3}", e[5]):
            if rid not in owner_of:
                problems.append(f"8.5 이벤트 #{e[0]} ref {rid}: RUNLOG에 없음")
            elif owner_of[rid] != frm and frm not in ("SETUP", "A0"):
                notes.append(f"8.5 이벤트 #{e[0]}({frm}) ref {rid}는 {owner_of[rid]} 작성 — 확인 필요")

    for n in notes:
        print("  · " + n)
    for p in problems:
        print("  ✗ " + p)
    print(f"기록 규칙 감사: 문제 {len(problems)}건 · 확인 필요 {sum('확인 필요' in n for n in notes)}건")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
