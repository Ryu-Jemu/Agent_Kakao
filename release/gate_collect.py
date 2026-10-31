#!/usr/bin/env python3
"""A6 GATE 자동 수집기: 체크리스트 1·2·4·7·8의 자동 검사를 매번 새로 실행하고 결과를 마크다운으로 낸다.
실행: python3 release/gate_collect.py --build <release SHA> [--seed N]  → stdout + release/logs/gate_collect_<HHMM>.md
- 판정(GO/NO-GO)은 하지 않는다. 사람이 읽는 증거 묶음이다. HUMAN·VM·기능(3)·레드팀(5) 항목은 별도.
- 비밀값은 출력하지 않는다(키 이름별 건수만).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
OUT = []


def run(cmd, timeout=600, env=None, shell=False):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env, shell=shell)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def emit(title, rc, body, keep=12):
    lines = [ln for ln in body.strip().splitlines() if ln.strip()]
    show = lines if len(lines) <= keep else lines[:3] + ["…"] + lines[-(keep - 4):]
    OUT.append(f"### {title} — rc={rc}\n```\n" + "\n".join(show) + "\n```")


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def tc_rows():
    t = open(os.path.join(ROOT, "SHARED_BOARD.md"), encoding="utf-8").read()
    b, e = "<!-- SEC:TC_MATRIX:BEGIN -->", "<!-- SEC:TC_MATRIX:END -->"
    sec = t[t.index(b) + len(b):t.index(e)]
    rows = []
    for ln in sec.splitlines():
        s = ln.strip()
        if s.startswith("|") and not re.match(r"^\|\s*-", s) and not s.startswith("| TC "):
            rows.append([c.strip() for c in s[1:-1].split("|")])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default=None)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    head = run(["git", "rev-parse", "--short", "HEAD"])[1].strip()
    build = a.build or head
    seed = a.seed if a.seed is not None else int(dt.datetime.now().strftime("%H%M%S"))
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    OUT.append(f"## gate_collect {now} · build {build} · HEAD {head} · seed {seed}")

    # 1. 게이트 도구
    OUT.append(f"- coord.py sha256: `{sha256(os.path.join(ROOT, 'coord', 'coord.py'))[:16]}`")
    rc, o = run([sys.executable, "coord/selftest.py"])
    emit("1.1 selftest", rc, "\n".join(ln for ln in o.splitlines() if "FAIL" in ln or "합계" in ln))
    rc, o = run([sys.executable, "release/test_gate_audit.py"])
    emit("1.2 test_gate_audit", rc, "\n".join(ln for ln in o.splitlines() if ln.startswith(("[FAIL", "[FINDING", "합계", "[A6"))))

    # 2. R3
    rc, o = run([sys.executable, "coord/coord.py", "tc", "check", "--build", build])
    emit(f"2.1 tc check --build {build} (interim 아님)", rc, o, keep=22)
    rows = tc_rows()
    evroot = os.path.realpath(os.path.join(ROOT, "tests", "runs")) + os.sep
    seen, msgs = {}, []
    full = run(["git", "rev-parse", build])[1].strip()
    for r in rows:
        if len(r) < 8 or r[3] != "✅":
            msgs.append(f"{r[0] if r else '?'}: 결과 {r[3] if len(r) > 3 else '?'} — 증거 검사 생략")
            continue
        path, _, pin = r[7].rpartition("#")
        fp = os.path.realpath(os.path.join(ROOT, path))
        if not fp.startswith(evroot) or not os.path.isfile(fp):
            msgs.append(f"{r[0]}: ✗ 증거 위치 {r[7]}")
            continue
        d = sha256(fp)
        st = os.stat(fp)
        body = open(fp, encoding="utf-8", errors="replace").read()
        ok_id = re.search(rf"(?<![A-Za-z0-9-]){re.escape(r[0])}(?![A-Za-z0-9-])", body) is not None
        ok_sha = any(full.startswith(tk) for tk in re.findall(r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])", body))
        for k in (("path", fp), ("inode", (st.st_dev, st.st_ino)), ("digest", d)):
            seen.setdefault(k, []).append(r[0])
        msgs.append(f"{r[0]}: pin {'✓' if d[:16] == pin else '✗'} · id {'✓' if ok_id else '✗'} · sha {'✓' if ok_sha else '✗'} · {os.path.relpath(fp, ROOT)}")
    dup = [f"{k[0]} 공유: {v}" for k, v in seen.items() if len(v) > 1]
    emit("2.2·2.3·2.6 증거 독립 검사(경로·해시·ID·SHA·고유성)", 1 if dup or any("✗" in m for m in msgs) else 0,
         "\n".join(msgs + dup or ["(행 없음)"]), keep=20)
    ok_rows = [r for r in rows if len(r) >= 8 and r[3] == "✅"]
    random.seed(seed)
    sample = random.sample(ok_rows, min(3, len(ok_rows)))
    OUT.append(f"- 2.7 무작위 표본(seed {seed}): " + (", ".join(f"{r[0]} → {r[7]}" for r in sample) or "✅ 행 없음 — 표본 불가")
               + " — trace 대조는 수동")
    rc1, o1 = run(["git", "diff", "--quiet", "originals-baseline", "--", "docs/contest", "tests/tc/public", "actions.json", "actions.yaml"])
    rc2, o2 = run("cd docs/contest && shasum -a 256 -c MANIFEST.sha256 | grep -vc ': OK$'; cd ../../tests/tc/public && shasum -a 256 -c MANIFEST.sha256 | grep -vc ': OK$'", shell=True)
    emit("2.4 원문 고정(git diff originals-baseline / MANIFEST 비OK 줄 수)", rc1, f"git diff rc={rc1}\nMANIFEST 비OK: {o2.split()}")
    rel = run(["git", "rev-parse", "--short", "release^{commit}"])
    emit("2.5 release 태그·HEAD·build", 0 if rel[0] == 0 and rel[1].strip() == build == head else 1,
         f"release={rel[1].strip() if rel[0] == 0 else '(없음)'} HEAD={head} build={build} · VM RELEASE는 6.1에서 확인")

    # 4. 형식
    if os.path.exists(VENV_PY):
        rc, o = run([VENV_PY, "release/test_gateway_format.py"])
        emit("4.1·4.2 게이트웨이 형식 퍼징", rc, o)

    # 7. 보안·규정
    env_vals = {}
    for ln in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        k, _, v = ln.strip().partition("=")
        v = v.strip().strip('"').strip("'")
        # 비밀은 키 이름으로 판정한다(GCP_PROJECT·VERTEX_LOCATION은 09_environment.md에 공개된 설정값)
        if k and not k.startswith("#") and len(v) >= 8 and re.search(r"TOKEN|KEY|SECRET|PASSWORD|AI_CS_AGENT", k):
            env_vals[k] = v
    hist = run(["git", "log", "--all", "-p"], timeout=120)[1]
    board = open(os.path.join(ROOT, "SHARED_BOARD.md"), encoding="utf-8").read()
    lines = []
    for k, v in env_vals.items():
        r = subprocess.run(["grep", "-rIlF", "--exclude-dir=.git", "--exclude-dir=.venv", "--exclude=.env", "--", v, "."],
                           cwd=ROOT, capture_output=True, text=True)
        lines.append(f"{k}: git이력 {hist.count(v)} · 작업트리 파일 {len(r.stdout.splitlines())} · 보드 {board.count(v)}")
    emit("7.1 비밀값(키 이름별 건수)", 1 if any(not ln.endswith("0 · 작업트리 파일 0 · 보드 0") for ln in lines) else 0, "\n".join(lines))
    rc, o = run(r"grep -rIlE --exclude-dir=.git --exclude-dir=.venv --exclude=.env 'aitop100_[A-Za-z0-9]{8,}' . || true", shell=True)
    emit("7.2 토큰 패턴 파일", 1 if o.strip() else 0, o or "(없음)")
    rc, o = run([sys.executable, "coord/coord.py", "audit"])
    flagged = [ln for ln in o.splitlines() if ("!" in ln or "없음" in ln or "❌" in ln) and "원문 무결" not in ln]
    emit("7.3 coord audit(플래그 행만)", rc, "\n".join(flagged + [ln for ln in o.splitlines() if "audit 문제" in ln or "MANIFEST" in ln]))
    rc, o = run("git reflog show --all --date=iso | grep -i 'update by push' || true", shell=True)
    emit("7.4 push 기록(규칙 시행 10:37 이후 0이어야 함)", 0, o or "(없음)")
    rc, o = run("ls -l .env | awk '{print $1}'", shell=True)
    emit("7.5 로컬 .env 권한(VM은 6.x에서 600 확인)", 0 if o.strip().startswith("-rw-------") else 1, o)

    # 8. 기록 규칙
    rc, o = run([sys.executable, "release/audit_records.py"])
    emit("8.1·8.3·8.4·8.5 기록 규칙", rc, o, keep=16)

    text = "\n\n".join(OUT) + "\n"
    os.makedirs(os.path.join(ROOT, "release", "logs"), exist_ok=True)
    p = os.path.join(ROOT, "release", "logs", f"gate_collect_{dt.datetime.now().strftime('%H%M')}.md")
    open(p, "w", encoding="utf-8").write(text)
    print(text)
    print(f"[saved] {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    main()
