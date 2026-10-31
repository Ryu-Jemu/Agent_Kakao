#!/usr/bin/env python3
"""coord.py audit의 보드 판정(D-016: .coord/board.sha256 대조) 독립 검증. 임시 복제본만 사용.
기대: ①coord post 후 audit에 보드 플래그 없음 ②chmod 후 직접 편집하면 'coord 외 편집' 플래그 ③해시 파일 삭제 시 판정 불가를 문제로 보고."""
import os, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
res = []
with tempfile.TemporaryDirectory(prefix="a6audit_") as t:
    os.makedirs(f"{t}/coord")
    for f in ("coord.py", "owners.json"):
        shutil.copy(f"{ROOT}/coord/{f}", f"{t}/coord/{f}")
    shutil.copy(f"{ROOT}/SHARED_BOARD.md", f"{t}/SHARED_BOARD.md"); os.chmod(f"{t}/SHARED_BOARD.md", 0o644)
    for d in ("docs/contest", "tests/tc/public"):
        shutil.copytree(f"{ROOT}/{d}", f"{t}/{d}")
    sh = lambda *a: subprocess.run(a, cwd=t, capture_output=True, text=True)
    sh("git", "init", "-q"); sh("git", "add", "-A"); sh("git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x")
    env = {k: v for k, v in os.environ.items() if k != "AGENT_ID"} | {"AGENT_ID": "A6"}
    c = lambda *a: subprocess.run([sys.executable, f"{t}/coord/coord.py", *a], cwd=t, capture_output=True, text=True, env=env)
    c("post", "--to", "A0", "--type", "INFO", "audit test")
    o = c("audit").stdout
    res.append(("coord 경유 변경은 보드 플래그 없음", "SHARED_BOARD.md" not in "".join(l for l in o.splitlines() if "!" in l), o))
    os.chmod(f"{t}/SHARED_BOARD.md", 0o644); open(f"{t}/SHARED_BOARD.md", "a").write("\n<!-- direct edit -->\n")
    o = c("audit").stdout
    res.append(("직접 편집은 플래그", any("SHARED_BOARD" in l and "!" in l for l in o.splitlines()), o))
    p = os.path.join(t, ".coord", "board.sha256")
    if os.path.exists(p):
        os.remove(p)
    o2 = c("audit")
    res.append(("해시 기록 없으면 통과시키지 않음", o2.returncode != 0, o2.stdout))
bad = 0
for name, ok, out in res:
    bad += not ok
    flag = [l for l in out.splitlines() if "SHARED" in l or "audit 문제" in l]
    print(("PASS" if ok else "FAIL"), name, "|", " / ".join(flag)[:200])
sys.exit(1 if bad else 0)
