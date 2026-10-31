#!/usr/bin/env python3
"""coord.py 회귀 자체검증(재실행 가능). 실제 보드·원문은 건드리지 않고 임시 디렉터리에서만 실행한다.

사용: python3 coord/selftest.py  → 모든 검사 통과 시 exit 0, 하나라도 실패하면 exit 1.
A6 BLOCKER #4(tc check 허위 통과) 재현 케이스를 포함한다.
"""
import hashlib
import json
import os
import re
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
        os.rename(f"{t}/coord/owners.json", f"{t}/coord/owners.json.bak")
        check("H7 훅 내부 오류 시 fail-closed(deny)", '"deny"' in pre("release/y.md", "A6")[1])
        os.rename(f"{t}/coord/owners.json.bak", f"{t}/coord/owners.json")
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
        check("P4 wu --record 없는 R-번호 거부", c("wu", "set", "--id", "A2-1", "--record", "R-999", agent="A2")[0] != 0)
        check("P5 wu --record 타인 R-번호 거부", c("wu", "set", "--id", "A2-1", "--record", rid, agent="A2")[0] != 0)
        rc_own, rid2 = c("log", "add", "--task", "own", "--result", "ok", "--cmd", "c", "--evidence", "e", agent="A2")
        check("P6 wu --record 본인 R-번호 허용", c("wu", "set", "--id", "A2-1", "--record", rid2.strip().splitlines()[-1], agent="A2")[0] == 0)
        # ── R3 게이트(tc check) ──
        # NO-GO 판정은 exit 1 + '결과: NO-GO' 출력(+기대 사유 문자열)으로 확인한다. 예외 traceback도 exit 1이므로 rc만으로는 부족하다.
        def nogo(*args, why=None):
            rc, out = c("tc", "check", *args)
            ok = rc == 1 and "결과: NO-GO" in out and "Traceback" not in out and (why is None or why in out)
            return ok, out[-400:]

        def go(*args):
            rc, out = c("tc", "check", *args)
            return rc == 0 and "Traceback" not in out, out[-400:]

        def g(*args):
            return subprocess.run(["git", "-C", t, "-c", "user.email=s@t", "-c", "user.name=s", "-c", "commit.gpgsign=false",
                                   "-c", "tag.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                                  capture_output=True, text=True, env=env0)

        def put_row(tid, res, build, ev):
            """tc set을 거치지 않고 보드 행을 직접 쓴다(위조·구형 행 재현용)."""
            os.chmod(f"{t}/SHARED_BOARD.md", 0o644)
            lines = open(f"{t}/SHARED_BOARD.md", encoding="utf-8").read().split("\n")
            for k, ln in enumerate(lines):
                if ln.startswith(f"| {tid} |"):
                    cells = [x.strip() for x in ln.strip()[1:-1].split("|")]
                    cells[3:8] = [res, build, "00:00", "-", ev]
                    lines[k] = "| " + " | ".join(cells) + " |"
            open(f"{t}/SHARED_BOARD.md", "w", encoding="utf-8").write("\n".join(lines))

        def tset(tid, path, build):
            return c("tc", "set", "--id", tid, "--result", "ok", "--build", build, "--run", path, agent="A4")

        check("G1 미실행 상태 NO-GO", *nogo("--build", "deadbeef"))
        # 가짜 성공 15행 + 비커밋 빌드 + 없는 증거를 보드에 직접 기록 (A6 BLOCKER #4 재현)
        for i in IDS:
            put_row(i, "✅", "dummy-sha", "/nonexistent/evidence")
        check("G2 비커밋 빌드·없는 증거(직접 기록) → NO-GO", *nogo("--build", "dummy-sha"))
        # PIN: tc set 단계에서 tests/runs/ 밖·없는 증거를 거부한다
        open(f"{t}/release/ev.md", "w").write("L-03 build 0000000\n")
        os.symlink("../../release/ev.md", f"{t}/tests/runs/link.md")
        rc1, o1 = tset("L-03", "/nonexistent/evidence", "deadbeef")
        rc2, o2 = tset("L-03", "release/ev.md", "deadbeef")
        rc3, o3 = tset("L-03", "tests/runs/link.md", "deadbeef")
        rc4, o4 = tset("L-03", "tests/runs/none.md", "deadbeef")
        check("PIN1 tc set: 없는 증거·tests/runs/ 밖·밖을 가리키는 링크 거부",
              all(r != 0 and "tests/runs/" in o for r, o in ((rc1, o1), (rc2, o2), (rc3, o3), (rc4, o4))),
              " / ".join(o.strip()[-80:] for o in (o1, o2, o3, o4)))
        os.remove(f"{t}/tests/runs/link.md")
        # 원문 고정 커밋 + originals-baseline 태그 → 릴리스 커밋 + release 태그(HEAD)
        open(f"{t}/.gitignore", "w").write("tests/runs/\n.coord/\n")
        g("add", "-A")
        g("commit", "-q", "-m", "originals")
        g("tag", "originals-baseline")
        base_full = g("rev-parse", "HEAD").stdout.strip()
        g("commit", "-q", "--allow-empty", "-m", "release")
        g("tag", "release")
        full = g("rev-parse", "HEAD").stdout.strip()
        sha = g("rev-parse", "--short", "HEAD").stdout.strip()
        run = "tests/runs/20261031-1200"
        os.makedirs(f"{t}/{run}", exist_ok=True)
        orig_ev = {}
        for i in IDS:
            orig_ev[i] = f"# {i}\n- tc: {i}\n- build: {sha}\n- 판정: PASS\n"
            open(f"{t}/{run}/{i}.md", "w").write(orig_ev[i])
            tset(i, f"{run}/{i}.md", sha)

        def restore(*tids):
            for i in tids:
                open(f"{t}/{run}/{i}.md", "w").write(orig_ev[i])
                tset(i, f"{run}/{i}.md", sha)

        check("G3 실제 커밋·release 태그·증거 15/15 → GO", *go("--build", sha))
        b = open(f"{t}/SHARED_BOARD.md", encoding="utf-8").read()
        check("PIN2 tc set이 증거 해시(sha256 앞 16자)를 행에 기록",
              all(re.search(rf"^\| {re.escape(i)} \|.*\| {re.escape(run)}/{re.escape(i)}\.md#[0-9a-f]{{16}} \|$", b, re.M) for i in IDS))
        open(f"{t}/{run}/L-05.md", "w").write("no id here\n")
        check("G4 증거 내용에 ID/SHA 없으면 NO-GO", *nogo("--build", sha))
        restore("L-05")
        # PIN: 기록 후 증거 교체(ID·SHA는 그대로) → 해시 불일치
        open(f"{t}/{run}/L-05.md", "w").write(f"# L-05\n- tc: L-05\n- build: {sha}\n- 판정: PASS (사후 교체)\n")
        check("PIN3 tc set 이후 증거 교체 → NO-GO(해시 불일치)", *nogo("--build", sha, why="해시 불일치"))
        restore("L-05")
        # PIN: 해시 없는 구형 행 → NO-GO
        put_row("L-03", "✅", sha, f"{run}/L-03.md")
        check("PIN4 해시 없는 구형 행 → NO-GO(hash missing)", *nogo("--build", sha, why="hash missing"))
        restore("L-03")
        # W1: 여러 행이 같은 증거(같은 경로·하드링크·동일 내용 사본)를 공유 → NO-GO
        both = f"L-03 L-05 build {sha}\n"
        open(f"{t}/{run}/both.md", "w").write(both)
        tset("L-03", f"{run}/both.md", sha); tset("L-05", f"{run}/both.md", sha)
        check("W1a 증거 파일 1개 공유 → NO-GO", *nogo("--build", sha, why="증거 공유"))
        os.link(f"{t}/{run}/both.md", f"{t}/{run}/both_link.md")
        tset("L-05", f"{run}/both_link.md", sha)
        check("W1b 하드링크로 같은 증거 공유 → NO-GO", *nogo("--build", sha, why="증거 공유"))
        open(f"{t}/{run}/both_copy.md", "w").write(both)
        tset("L-05", f"{run}/both_copy.md", sha)
        check("W1c 동일 내용 사본 공유 → NO-GO", *nogo("--build", sha, why="증거 공유"))
        restore("L-03", "L-05")
        check("W1r 원상복구 후 GO", *go("--build", sha))
        # W6: ID·SHA는 경계가 있는 독립 토큰이어야 한다
        open(f"{t}/{run}/L-03.md", "w").write(f"L-033 build {sha}\n"); tset("L-03", f"{run}/L-03.md", sha)
        check("W6a ID 부분일치(L-033) → NO-GO", *nogo("--build", sha, why="TC ID가 독립 토큰"))
        wrong = "0" if full[len(sha)] != "0" else "1"
        open(f"{t}/{run}/L-03.md", "w").write(f"L-03 build {sha}{wrong}\n"); tset("L-03", f"{run}/L-03.md", sha)
        check("W6b SHA 뒤에 다른 16진 문자(커밋 접두 아님) → NO-GO", *nogo("--build", sha, why="16진 토큰"))
        open(f"{t}/{run}/L-03.md", "w").write(f"L-03 build g{sha}\n"); tset("L-03", f"{run}/L-03.md", sha)
        check("W6c SHA 앞이 영숫자(경계 없음) → NO-GO", *nogo("--build", sha, why="16진 토큰"))
        open(f"{t}/{run}/L-03.md", "w").write(f"L-03 build {full}\n"); tset("L-03", f"{run}/L-03.md", sha)
        check("W6p 증거에 40자 전체 SHA(접두 일치) → GO", *go("--build", sha))
        restore("L-03")
        # W5·G09: release 태그 필수(기본), --interim은 그 요구만 생략, --build = HEAD는 항상 필수
        g("tag", "-d", "release")
        check("W5a release 태그 없음 → NO-GO", *nogo("--build", sha, why="'release'"))
        rc, out = c("tc", "check", "--build", sha, "--interim")
        check("W5b --interim은 release 태그 없이 통과하되 '중간 점검: 제출 판정 아님' 표시",
              rc == 0 and "중간 점검: 제출 판정 아님" in out and "Traceback" not in out, out[-300:])
        g("tag", "release", base_full)
        check("W5c release 태그가 다른 커밋 → NO-GO", *nogo("--build", sha, why="태그("))
        g("tag", "-f", "release", full)
        g("commit", "-q", "--allow-empty", "-m", "after-release")
        check("G09a --build ≠ HEAD → NO-GO", *nogo("--build", sha, why="≠ HEAD"))
        check("G09b --interim이어도 --build ≠ HEAD → NO-GO", *nogo("--build", sha, "--interim", why="≠ HEAD"))
        g("reset", "-q", "--soft", full)
        check("W5r 태그·HEAD 원상복구 후 GO", *go("--build", sha))
        # W4: 원문은 originals-baseline 태그와 같아야 한다
        pub = f"{t}/tests/tc/public"
        with open(f"{pub}/Y-24.md", "a") as f:
            f.write("tamper\n")
        man_lines = []
        for ln in open(f"{pub}/MANIFEST.sha256", encoding="utf-8"):
            if ln.strip():
                h, _, name = ln.strip().partition("  ")
                man_lines.append(f"{hashlib.sha256(open(f'{pub}/{name}', 'rb').read()).hexdigest()}  {name}")
        open(f"{pub}/MANIFEST.sha256", "w").write("\n".join(man_lines) + "\n")
        check("W4a 원문+MANIFEST 일관 변조(미커밋) → NO-GO", *nogo("--build", sha, why="originals-baseline"))
        for n in ("Y-24.md", "MANIFEST.sha256"):
            shutil.copy(f"{ROOT}/tests/tc/public/{n}", f"{pub}/{n}")
            os.chmod(f"{pub}/{n}", 0o644)
        open(f"{pub}/notes.txt", "w").write("x\n")
        check("W4b tests/tc/public에 추적 안 된 파일 → NO-GO", *nogo("--build", sha, why="추적 안 된"))
        os.remove(f"{pub}/notes.txt")
        # clean 필터로 git diff·status를 속여도(마지막 줄 숨김) 기준 blob과 디스크 바이트 직접 비교로 잡는다
        open(f"{t}/.git/info/attributes", "w").write("Y-24.md filter=hide\n")
        g("config", "filter.hide.clean", "sed '$d'")
        with open(f"{pub}/Y-24.md", "a") as f:
            f.write("tamper\n")
        hidden = g("diff", "--quiet", "originals-baseline", "--", "tests/tc/public").returncode == 0
        check("W4d clean 필터로 diff를 속인 변조 → NO-GO(blob 직접 비교)",
              hidden and nogo("--build", sha, why="blob과 다름")[0], f"diff 은닉={hidden}")
        os.remove(f"{t}/.git/info/attributes")
        g("config", "--unset", "filter.hide.clean")
        shutil.copy(f"{ROOT}/tests/tc/public/Y-24.md", f"{pub}/Y-24.md")
        os.chmod(f"{pub}/Y-24.md", 0o644)
        g("tag", "-d", "originals-baseline")
        check("W4c originals-baseline 태그 없음 → NO-GO(명확한 메시지)", *nogo("--build", sha, why="'originals-baseline'가 없음"))
        g("tag", "originals-baseline", base_full)
        check("W4r 원상복구 후 GO", *go("--build", sha))
        os.remove(f"{t}/tests/tc/public/Y-24.md")
        check("G5 원문 누락 → NO-GO", *nogo("--build", sha))
        shutil.copy(f"{ROOT}/tests/tc/public/Y-24.md", f"{t}/tests/tc/public/Y-24.md")
        subprocess.run(["chmod", "u+w", f"{t}/tests/tc/public/Y-24.md"])
        with open(f"{t}/tests/tc/public/Y-24.md", "a") as f:
            f.write("tamper\n")
        check("G6 원문 변조(MANIFEST 불일치) → NO-GO", *nogo("--build", sha))
        shutil.copy(f"{ROOT}/tests/tc/public/Y-24.md", f"{t}/tests/tc/public/Y-24.md")
        check("G7 원상복구 후 GO 재현", *go("--build", sha))
        # 보드 쓰기(coord) 후 444 확인을 위해 tc set을 한 번 더 거친다(put_row가 644로 바꿨을 수 있음)
        restore("L-03")
        check("B1 coord 저장 후 보드는 읽기 전용(444)", (os.stat(f"{t}/SHARED_BOARD.md").st_mode & 0o222) == 0)
        os.chmod(f"{t}/SHARED_BOARD.md", 0o644)
        b = open(f"{t}/SHARED_BOARD.md", encoding="utf-8").read()
        b = b.replace("| L-03 | 배송지 변경 요청 |", "| L-05 | 배송지 변경 요청 |", 1)
        open(f"{t}/SHARED_BOARD.md", "w", encoding="utf-8").write(b)
        check("G8 매트릭스 중복 ID → NO-GO", *nogo("--build", sha, why="중복 ID"))
    finally:
        shutil.rmtree(t, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n합계 {len(results)}건 / 실패 {len(failed)}건")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
