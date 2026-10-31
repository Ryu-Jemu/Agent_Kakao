#!/usr/bin/env python3
"""coord.py 회귀 자체검증(재실행 가능). 실제 보드·원문은 건드리지 않고 임시 디렉터리에서만 실행한다.

사용: python3 coord/selftest.py  → 모든 검사 통과 시 exit 0, 하나라도 실패하면 exit 1.
A6 BLOCKER #4(tc check 허위 통과) 재현 케이스를 포함한다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = ['L-03', 'L-05', 'L-11', 'L-20', 'L-23', 'L-32', 'L-33', 'L-34', 'L-40', 'L-47', 'L-60',
       'R-05-a', 'Y-07-b', 'Y-16', 'Y-24']
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


def main():
    t = tempfile.mkdtemp(prefix="coordselftest-")
    try:
        os.makedirs(f"{t}/coord")
        for f in ("coord.py", "owners.json"):
            shutil.copy(f"{ROOT}/coord/{f}", f"{t}/coord/{f}")
        shutil.copy(f"{ROOT}/SHARED_BOARD.md", f"{t}/SHARED_BOARD.md")
        shutil.copytree(f"{ROOT}/docs/contest", f"{t}/docs/contest")
        shutil.copytree(f"{ROOT}/tests/tc/public", f"{t}/tests/tc/public")
        for d in ("release", "agent", "tests/runs"):
            os.makedirs(f"{t}/{d}", exist_ok=True)
        subprocess.run(["chmod", "-R", "u+w", t])
        subprocess.run(["git", "init", "-q", t])
        env0 = {k: v for k, v in os.environ.items() if k != "AGENT_ID"}

        def c(*args, agent=None, stdin=None):
            env = dict(env0)
            if agent:
                env["AGENT_ID"] = agent
            r = subprocess.run([sys.executable, "coord/coord.py", *args], cwd=t, env=env, input=stdin,
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        def pre(path, agent=None):
            return c("hook-pre", agent=agent, stdin=json.dumps({"tool_input": {"file_path": path}, "cwd": t}))

        # ── 훅: 범위 침해 차단 ──
        check("H1 AGENT_ID 없으면 훅 무동작", pre("SHARED_BOARD.md")[1].strip() == "")
        check("H2 보드 직접 편집 deny", '"deny"' in pre("SHARED_BOARD.md", "A6")[1])
        check("H3 원문 편집 deny", '"deny"' in pre("docs/contest/01_guide_judging.md", "A6")[1])
        check("H4 필독 전 쓰기 deny", "필독" in pre("release/x.md", "A6")[1])
        c("read", "docs/contest/*.md", "tests/tc/public/*.md", agent="A6")
        check("H5 필독 후 소유 경로 허용", pre("release/x.md", "A6")[1].strip() == "")
        check("H6 남의 경로 deny", "A3의 소유" in pre("agent/x.py", "A6")[1])
        # ── 트리거 ──
        c("post", "--to", "A6", "--type", "INFO", "알림", agent="A0")
        o1 = c("hook-post", agent="A6", stdin='{"hook_event_name":"PostToolUse"}')[1]
        o2 = c("hook-post", agent="A6", stdin='{"hook_event_name":"PostToolUse"}')[1]
        check("T1 새 이벤트 additionalContext 주입", "additionalContext" in o1 and "[BOARD]" in o1)
        check("T2 같은 버전은 1회만 주입", o2.strip() == "")
        procs = [subprocess.Popen([sys.executable, "coord/coord.py", "post", "--to", "ALL", "--type", "INFO", f"p{i}"],
                                  cwd=t, env={**env0, "AGENT_ID": "A1"}, stdout=subprocess.DEVNULL) for i in range(30)]
        [p.wait() for p in procs]
        board = open(f"{t}/SHARED_BOARD.md", encoding="utf-8").read()
        ev = board[board.find("SEC:EVENTS:BEGIN"):]
        import re
        seqs = [int(x) for x in re.findall(r"^\| (\d+) \|", ev, re.M)]
        check("T3 동시 post 30건 seq 무중복", len(seqs) == len(set(seqs)), f"{len(seqs)} vs {len(set(seqs))}")
        # ── RUNLOG ──
        rc, _ = c("log", "add", "--task", "x", "--result", "fail", "--cmd", "c", "--evidence", "e")
        check("L1 실패 기록에 원인·금지사항 필수", rc != 0)
        rc, rid = c("log", "add", "--task", "x", "--result", "fail", "--cmd", "c", "--evidence", "e", "--issue", "i", "--fix", "f")
        rid = rid.strip().splitlines()[-1]
        rc, _ = c("log", "add", "--task", "x", "--result", "ok", "--cmd", "c", "--evidence", "e", "--retry-of", rid)
        check("L2 실패 재시도는 --change 필수", rc != 0)
        rc, _ = c("log", "add", "--task", "x", "--result", "ok", "--cmd", "c", "--evidence", "e", "--retry-of", rid, "--change", "d")
        check("L3 --change 있으면 재시도 기록 허용", rc == 0)
        # ── 권한 ──
        check("P1 TC_MATRIX는 A4만", c("tc", "set", "--id", "L-03", "--result", "ok", "--build", "x", "--run", "r", agent="A3")[0] != 0)
        check("P2 WU는 담당자만", c("wu", "set", "--id", "A2-1", "--status", "doing", agent="A3")[0] != 0)
        check("P3 HANDOFF 필수 항목 검증", c("handoff", "--wu", "A2-1", "--text", "- 상태: 완료", agent="A2")[0] != 0)
        # ── R3 게이트(tc check) ──
        check("G1 미실행 상태 NO-GO", c("tc", "check", "--build", "deadbeef")[0] == 1)
        # 가짜 성공 15행 + 비커밋 빌드 + 없는 증거 (A6 BLOCKER #4 재현)
        for i in IDS:
            c("tc", "set", "--id", i, "--result", "ok", "--build", "dummy-sha", "--run", "/nonexistent/evidence", agent="A4")
        check("G2 비커밋 빌드·없는 증거 → NO-GO", c("tc", "check", "--build", "dummy-sha")[0] == 1)
        # 진짜 커밋 + 증거 파일 내용 검증
        subprocess.run(["git", "-C", t, "-c", "user.email=s@t", "-c", "user.name=s", "commit", "-q", "--allow-empty", "-m", "r"])
        sha = subprocess.run(["git", "-C", t, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        for i in IDS:
            p = f"tests/runs/ev_{i}.md"
            open(f"{t}/{p}", "w").write(f"{i} build {sha} PASS\n")
            c("tc", "set", "--id", i, "--result", "ok", "--build", sha, "--run", p, agent="A4")
        rc, out = c("tc", "check", "--build", sha)
        check("G3 실제 커밋·증거 15/15 → GO", rc == 0, out[-300:])
        open(f"{t}/tests/runs/ev_L-05.md", "w").write("no id here\n")
        check("G4 증거 내용에 ID/SHA 없으면 NO-GO", c("tc", "check", "--build", sha)[0] == 1)
        open(f"{t}/tests/runs/ev_L-05.md", "w").write(f"L-05 build {sha}\n")
        os.remove(f"{t}/tests/tc/public/Y-24.md")
        check("G5 원문 누락 → NO-GO", c("tc", "check", "--build", sha)[0] == 1)
        shutil.copy(f"{ROOT}/tests/tc/public/Y-24.md", f"{t}/tests/tc/public/Y-24.md")
        subprocess.run(["chmod", "u+w", f"{t}/tests/tc/public/Y-24.md"])
        with open(f"{t}/tests/tc/public/Y-24.md", "a") as f:
            f.write("tamper\n")
        check("G6 원문 변조(MANIFEST 불일치) → NO-GO", c("tc", "check", "--build", sha)[0] == 1)
        shutil.copy(f"{ROOT}/tests/tc/public/Y-24.md", f"{t}/tests/tc/public/Y-24.md")
        check("G7 원상복구 후 GO 재현", c("tc", "check", "--build", sha)[0] == 0)
        check("B1 coord 저장 후 보드는 읽기 전용(444)", (os.stat(f"{t}/SHARED_BOARD.md").st_mode & 0o222) == 0)
        os.chmod(f"{t}/SHARED_BOARD.md", 0o644)
        b = open(f"{t}/SHARED_BOARD.md", encoding="utf-8").read()
        b = b.replace("| L-03 | 배송지 변경 요청 |", "| L-05 | 배송지 변경 요청 |", 1)
        open(f"{t}/SHARED_BOARD.md", "w", encoding="utf-8").write(b)
        check("G8 매트릭스 중복 ID → NO-GO", c("tc", "check", "--build", sha)[0] == 1)
    finally:
        shutil.rmtree(t, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n합계 {len(results)}건 / 실패 {len(failed)}건")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
