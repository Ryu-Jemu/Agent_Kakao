#!/usr/bin/env python3
"""A6 독립 적대 감사: `coord.py tc check` (R3 게이트).

v2 (A-6-1, 2026-10-31). v1은 수정 전 결함(R-005, BLOCKER #4)이 '존재'함을 assert했으므로 폐기한다.
- 실제 보드·원문·API를 건드리지 않는다. 임시 디렉터리에 coord/·보드·공개 TC 원문을 복제하고 git 커밋을 만든 뒤
  그 복제본의 coord.py를 서브프로세스로 실행한다(selftest.py와 독립된 케이스 위주).
- N*: 반드시 NO-GO(exit≠0)여야 하는 케이스. 하나라도 GO면 게이트 회귀 → 스크립트 exit 1.
- P*: 정상 입력은 GO(exit 0)여야 한다(하네스 자체 검증).
- W*: 약점 탐침. 현재 GO가 나오면 FINDING으로 출력한다(스크립트 실패로 치지 않음).
  A6는 W*가 GO인 동안 수동 보완 검사(release/checklist_v1.md §2)를 GO 조건에 추가한다.
사용: python3 release/test_gate_audit.py [--coord <coord.py 경로>]  (기본: 현재 저장소의 coord/coord.py)
"""
import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = ["L-03", "L-05", "L-11", "L-20", "L-23", "L-32", "L-33", "L-34", "L-40", "L-47", "L-60",
       "R-05-a", "Y-07-b", "Y-16", "Y-24"]
results = []  # (kind, name, rc, ok, tail)


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def writable(path):
    for dp, dn, fn in os.walk(path):
        for n in dn + fn:
            p = os.path.join(dp, n)
            os.chmod(p, os.stat(p).st_mode | stat.S_IWUSR)
    os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)


class Env:
    def __init__(self, t, coord_src):
        self.t = t
        os.makedirs(f"{t}/coord")
        shutil.copy(coord_src, f"{t}/coord/coord.py")
        shutil.copy(f"{ROOT}/coord/owners.json", f"{t}/coord/owners.json")
        shutil.copy(f"{ROOT}/SHARED_BOARD.md", f"{t}/SHARED_BOARD.md")
        shutil.copytree(f"{ROOT}/tests/tc/public", f"{t}/tests/tc/public")
        writable(t)
        src = open(coord_src, encoding="utf-8").read()
        self.pinned = "PIN_SEP" in src      # S8 v2: 증거 칸 '경로#sha256앞16자'
        self.tagged = "RELEASE_TAG" in src  # S8 v2: release·originals-baseline 태그, --build=HEAD
        sh("git", "init", "-q", t)
        self.commit("old")
        self.old = self.head()
        if self.tagged:
            sh("git", "-C", t, "tag", "originals-baseline")
        self.commit("release")
        self.sha = self.head()
        if self.tagged:
            sh("git", "-C", t, "tag", "release")

    def commit(self, msg):
        sh("git", "-C", self.t, "add", "-A")
        sh("git", "-C", self.t, "-c", "user.email=a6@audit", "-c", "user.name=a6", "commit", "-q",
           "--allow-empty", "-m", msg)

    def head(self, short=True):
        return sh("git", "-C", self.t, "rev-parse", *(["--short"] if short else []), "HEAD").stdout.strip()

    def board(self):
        return open(f"{self.t}/SHARED_BOARD.md", encoding="utf-8").read()

    def set_matrix(self, rows):
        """rows: [(id, result, build, evidence)] 또는 원시 문자열 행."""
        text = self.board()
        b, e = "<!-- SEC:TC_MATRIX:BEGIN -->", "<!-- SEC:TC_MATRIX:END -->"
        i, j = text.index(b) + len(b), text.index(e)
        lines = ["", "## TC_MATRIX (audit)", "| TC | 제목 | 주요 API | 결과 | 빌드 | 실행 시각 | 실패 원인 | 증거 |",
                 "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(r if isinstance(r, str) else f"| {r[0]} | t | - | {r[1]} | {r[2]} | 11:11 | - | {r[3]} |")
        open(f"{self.t}/SHARED_BOARD.md", "w", encoding="utf-8").write(text[:i] + "\n".join(lines) + "\n" + text[j:])

    def evidence(self, tid, body, pin=True):
        p = f"tests/runs/audit/{tid}.md"
        os.makedirs(os.path.dirname(f"{self.t}/{p}"), exist_ok=True)
        open(f"{self.t}/{p}", "w", encoding="utf-8").write(body)
        return self.cell(p) if pin else p

    def cell(self, p):
        """증거 칸 값. 해시 고정 모드면 '경로#sha256앞16자'."""
        fp = p if os.path.isabs(p) else f"{self.t}/{p}"
        if not self.pinned or not os.path.isfile(fp):
            return p
        return f"{p}#{hashlib.sha256(open(fp, 'rb').read()).hexdigest()[:16]}"

    def good_rows(self, build=None):
        build = build or self.sha
        return [(i, "✅", build, self.evidence(i, f"trace {i} build {build}\n")) for i in IDS]

    def check(self, build, interim=False):
        env = {k: v for k, v in os.environ.items() if k != "AGENT_ID"}
        r = subprocess.run([sys.executable, f"{self.t}/coord/coord.py", "tc", "check", "--build", build]
                           + (["--interim"] if interim else []), capture_output=True, text=True, env=env)
        return r.returncode, (r.stdout + r.stderr)


MUST = {}  # 이름 접두 → v2 모드에서 NO-GO 출력에 반드시 있어야 하는 사유(엉뚱한 사유로 통과하는 것 방지)


def case(kind, name, rc, out):
    must = next((m for k, m in MUST.items() if name.startswith(k + " ")), None)
    if must and rc != 0 and must not in out:
        rc_note = f"사유 불일치(기대 '{must}')"
        results.append((kind, name, rc, False, rc_note + " ← " + " ; ".join(ln.strip() for ln in out.splitlines() if ln.strip().startswith("✗"))[:200]))
        return
    if kind == "N":
        ok = rc != 0
    elif kind == "P":
        ok = rc == 0
    else:  # W: 약점 탐침 — GO면 FINDING
        ok = rc != 0
    lines = out.strip().splitlines()
    why = [ln.strip() for ln in lines if ln.strip().startswith("✗")][:2]
    tail = (lines[-1] if lines else "") + (f" ← {' ; '.join(why)}" if why else "")
    results.append((kind, name, rc, ok, tail))


def regen_manifest(pub):
    lines = []
    for n in sorted(os.listdir(pub)):
        if n.endswith(".md"):
            lines.append(f"{hashlib.sha256(open(os.path.join(pub, n), 'rb').read()).hexdigest()}  {n}")
    for n in sorted(os.listdir(os.path.join(pub, "media"))):
        p = os.path.join(pub, "media", n)
        lines.append(f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  media/{n}")
    open(os.path.join(pub, "MANIFEST.sha256"), "w").write("\n".join(lines) + "\n")


def run(coord_src):
    with tempfile.TemporaryDirectory(prefix="a6gate_") as t:
        E = Env(t, coord_src)
        pub = f"{t}/tests/tc/public"
        sha, full = E.sha, E.head(short=False)
        if E.tagged and E.pinned:
            MUST.update({"W1": "증거 공유", "W2": "tests/runs/ 밖", "W3": "tests/runs/ 밖", "W4": "originals-baseline",
                         "W5": "≠ HEAD", "W6": "독립 토큰", "N20": "해시 불일치", "N21": "해시 없음", "N22": "하드링크 동일",
                         "N23": "내용 동일", "N24": "태그(", "N25": "'release'가 없음", "N26": "originals-baseline"})

        # P1 기준선: 실제 커밋 + TC별 증거(ID+SHA) 15/15 → GO
        E.set_matrix(E.good_rows())
        case("P", "P1 정상 15/15(커밋 SHA·TC별 증거)", *E.check(sha))

        # N1 실제 보드 그대로(현 시점 미실행) + 실제 커밋 → NO-GO
        shutil.copy(f"{ROOT}/SHARED_BOARD.md", f"{t}/SHARED_BOARD.md"); writable(t)
        case("N", "N1 현 보드 TC_MATRIX 그대로", *E.check(sha))
        # N2 대문자 SHA(같은 커밋) → NO-GO(정규식)
        E.set_matrix(E.good_rows(sha.upper()))
        case("N", "N2 대문자 SHA", *E.check(sha.upper()))
        # N3 'HEAD'·태그 이름 → NO-GO
        E.set_matrix(E.good_rows("HEAD"))
        case("N", "N3 빌드='HEAD'", *E.check("HEAD"))
        # N4 1행 ❌
        rows = E.good_rows(); rows[4] = (rows[4][0], "❌", sha, rows[4][3]); E.set_matrix(rows)
        case("N", "N4 1행 ❌", *E.check(sha))
        # N5 1행 ⚠️
        rows = E.good_rows(); rows[7] = (rows[7][0], "⚠️", sha, rows[7][3]); E.set_matrix(rows)
        case("N", "N5 1행 ⚠️", *E.check(sha))
        # N6 1행 빌드 다름(구 커밋)
        rows = E.good_rows(); rows[2] = (rows[2][0], "✅", E.old, E.evidence(rows[2][0], f"{rows[2][0]} {E.old}")); E.set_matrix(rows)
        case("N", "N6 1행 빌드≠릴리스", *E.check(sha))
        # N7 빈 증거 파일
        rows = E.good_rows(); rows[0] = (rows[0][0], "✅", sha, E.evidence(rows[0][0], "")); E.set_matrix(rows)
        case("N", "N7 빈 증거 파일", *E.check(sha))
        # N8 증거가 디렉터리
        rows = E.good_rows(); rows[1] = (rows[1][0], "✅", sha, "tests/runs/audit"); E.set_matrix(rows)
        case("N", "N8 증거=디렉터리", *E.check(sha))
        # N9 증거 '-'
        rows = E.good_rows(); rows[3] = (rows[3][0], "✅", sha, "-"); E.set_matrix(rows)
        case("N", "N9 증거='-'", *E.check(sha))
        # N10 증거에 다른 SHA만
        rows = E.good_rows(); rows[5] = (rows[5][0], "✅", sha, E.evidence(rows[5][0], f"{rows[5][0]} {E.old}")); E.set_matrix(rows)
        case("N", "N10 증거 SHA 불일치", *E.check(sha))
        # N11 증거에 TC ID 없음(SHA만)
        rows = E.good_rows(); rows[6] = (rows[6][0], "✅", sha, E.evidence(rows[6][0], f"build {sha}")); E.set_matrix(rows)
        case("N", "N11 증거 TC ID 없음", *E.check(sha))
        # N12 14행(누락)
        E.set_matrix(E.good_rows()[:-1])
        case("N", "N12 매트릭스 14행", *E.check(sha))
        # N13 16행(원문에 없는 ID)
        E.set_matrix(E.good_rows() + [("L-99", "✅", sha, E.evidence("L-99", f"L-99 {sha}"))])
        case("N", "N13 매트릭스에만 있는 ID", *E.check(sha))
        # N14 형식 깨진 행(열 부족) → 예외라도 exit≠0이면 안전
        E.set_matrix(E.good_rows()[:-1] + ["| Y-24 | t | - | ✅ |"])
        case("N", "N14 열 부족 행(fail-closed)", *E.check(sha))
        # N15 원문 변조(MANIFEST 그대로)
        E.set_matrix(E.good_rows())
        orig = open(f"{pub}/L-20.md", encoding="utf-8").read()
        open(f"{pub}/L-20.md", "w", encoding="utf-8").write(orig.replace("MELON99", "MELON98"))
        case("N", "N15 원문 변조", *E.check(sha))
        open(f"{pub}/L-20.md", "w", encoding="utf-8").write(orig)
        # N16 MANIFEST 삭제
        man = open(f"{pub}/MANIFEST.sha256").read(); os.remove(f"{pub}/MANIFEST.sha256")
        case("N", "N16 MANIFEST 없음", *E.check(sha))
        open(f"{pub}/MANIFEST.sha256", "w").write(man)
        # N17 원문 파일명≠본문 id (+MANIFEST 재생성으로 해시는 맞춤)
        o5 = open(f"{pub}/L-05.md", encoding="utf-8").read()
        open(f"{pub}/L-05.md", "w", encoding="utf-8").write(o5.replace("- id: L-05", "- id: L-5"))
        regen_manifest(pub)
        case("N", "N17 본문 id≠파일명", *E.check(sha))
        open(f"{pub}/L-05.md", "w", encoding="utf-8").write(o5); open(f"{pub}/MANIFEST.sha256", "w").write(man)
        # N18 원문 16번째 파일 추가(+MANIFEST 재생성)
        open(f"{pub}/L-99.md", "w", encoding="utf-8").write("# L-99\n- id: L-99\n"); regen_manifest(pub)
        E.set_matrix(E.good_rows() + [("L-99", "✅", sha, E.evidence("L-99", f"L-99 {sha}"))])
        case("N", "N18 원문 16건(기대 15)", *E.check(sha))
        os.remove(f"{pub}/L-99.md"); open(f"{pub}/MANIFEST.sha256", "w").write(man)
        # P2 원상복구 후 GO 재현
        E.set_matrix(E.good_rows())
        case("P", "P2 원상복구 후 GO", *E.check(sha))

        # ── 약점 탐침 (GO면 FINDING) ──
        # W1 15행이 같은 증거 파일 1개(모든 ID+SHA 나열)를 공유
        shared = E.evidence("ALL", " ".join(IDS) + f" {sha}\n")
        E.set_matrix([(i, "✅", sha, shared) for i in IDS])
        case("W", "W1 증거 1개 공유(trace 아님)", *E.check(sha))
        # W2 증거=SHARED_BOARD.md 자기참조(보드에 ID+SHA가 이미 있음)
        E.set_matrix([(i, "✅", sha, "SHARED_BOARD.md") for i in IDS])
        E.set_matrix([(i, "✅", sha, E.cell("SHARED_BOARD.md")) for i in IDS])
        case("W", "W2 증거=보드 자기참조", *E.check(sha))
        # W3 증거가 저장소 밖 절대경로
        outside = tempfile.NamedTemporaryFile("w", delete=False, suffix=".md")
        outside.write(" ".join(IDS) + f" {sha}"); outside.close()
        E.set_matrix([(i, "✅", sha, E.cell(outside.name)) for i in IDS])
        case("W", "W3 증거=저장소 밖 경로", *E.check(sha))
        os.unlink(outside.name)
        # W4 원문 변조 + MANIFEST 재생성(일관 변조) — MANIFEST가 git에 고정되지 않음
        E.set_matrix(E.good_rows())
        o47 = open(f"{pub}/L-47.md", encoding="utf-8").read()  # 먼저 읽는다(open "w"가 먼저 비우는 것 방지)
        assert "API-29로 환불을 신청하지 않는다" in o47
        open(f"{pub}/L-47.md", "w", encoding="utf-8").write(o47.replace("API-29로 환불을 신청하지 않는다", "API-29로 환불을 신청한다"))
        regen_manifest(pub)
        case("W", "W4 원문+MANIFEST 일관 변조", *E.check(sha))
        shutil.rmtree(pub); shutil.copytree(f"{ROOT}/tests/tc/public", pub); writable(pub)
        # W5 릴리스가 아닌 과거 커밋으로 15/15 (게이트는 릴리스 태그를 모름)
        E.set_matrix(E.good_rows(E.old))
        case("W", "W5 비릴리스(과거) 커밋 SHA", *E.check(E.old))
        # W6 ID 부분일치: L-03 증거에 'L-033'만
        rows = E.good_rows(); rows[0] = ("L-03", "✅", sha, E.evidence("L-03x", f"L-033 {sha}")); E.set_matrix(rows)
        case("W", "W6 ID 부분일치(L-033)", *E.check(sha))
        # W7 전체 40자 SHA로 행 기록·7자 SHA로 검사(또는 반대) — 불일치면 NO-GO가 맞으나 운영 혼선 확인용
        E.set_matrix(E.good_rows(full))
        case("N", "N19 행=40자·검사=7자(정확 일치 요구)", *E.check(sha))

        if E.pinned or E.tagged:  # ── S8 v2 기능 적대 검사 ──
            E.set_matrix(E.good_rows())
            case("P", "P3 v2 기준선(태그·해시 고정) GO", *E.check(sha))
            # N20 tc set 이후 증거 내용 변경 → 해시 불일치
            rows = E.good_rows(); E.set_matrix(rows)
            open(f"{t}/tests/runs/audit/L-11.md", "a", encoding="utf-8").write("tampered\n")
            case("N", "N20 증거 사후 변경(해시 불일치)", *E.check(sha))
            # N21 해시 없는 증거 칸
            rows = E.good_rows(); rows[0] = (rows[0][0], "✅", sha, rows[0][3].split("#")[0]); E.set_matrix(rows)
            case("N", "N21 증거 해시 없음", *E.check(sha))
            # N22 하드링크로 같은 inode 공유(경로는 다름)
            rows = E.good_rows()
            a_ = f"{t}/tests/runs/audit/L-03.md"; open(a_, "w").write(f"L-03 L-05 {sha}\n")
            b_ = f"{t}/tests/runs/audit/L-05.md"; os.remove(b_); os.link(a_, b_)
            rows[0] = ("L-03", "✅", sha, E.cell("tests/runs/audit/L-03.md")); rows[1] = ("L-05", "✅", sha, E.cell("tests/runs/audit/L-05.md"))
            E.set_matrix(rows)
            case("N", "N22 하드링크 증거 공유", *E.check(sha))
            os.remove(a_); os.remove(b_)  # 하드링크 잔여 제거(이후 케이스 오염 방지)
            # N23 서로 다른 파일이지만 내용 동일
            rows = E.good_rows()
            for tid in ("L-20", "L-23"):
                open(f"{t}/tests/runs/audit/{tid}.md", "w").write(f"L-20 L-23 {sha}\n")
            rows[3] = ("L-20", "✅", sha, E.cell("tests/runs/audit/L-20.md")); rows[4] = ("L-23", "✅", sha, E.cell("tests/runs/audit/L-23.md"))
            E.set_matrix(rows)
            case("N", "N23 내용 동일 증거 공유", *E.check(sha))
            # N24 release 태그가 다른 커밋 / N25 release 태그 없음 / I1 --interim은 GO가 아님을 명시
            E.set_matrix(E.good_rows())
            sh("git", "-C", t, "tag", "-f", "release", E.old)
            case("N", "N24 release 태그≠빌드", *E.check(sha))
            sh("git", "-C", t, "tag", "-d", "release")
            case("N", "N25 release 태그 없음", *E.check(sha))
            rc, out = E.check(sha, interim=True)
            case("P" if "제출 판정 아님" in out else "N", "P4 --interim은 exit0이어도 '제출 판정 아님' 표기", rc, out)
            sh("git", "-C", t, "tag", "release", sha)
            # N26 원문 변조를 커밋하고 그 커밋에 release 태그(MANIFEST도 재생성) → baseline 대조로 차단
            o47 = open(f"{pub}/L-47.md", encoding="utf-8").read()
            open(f"{pub}/L-47.md", "w", encoding="utf-8").write(o47.replace("API-29로 환불을 신청하지 않는다", "API-29로 환불을 신청한다"))
            regen_manifest(pub); E.commit("tamper"); bad = E.head()
            sh("git", "-C", t, "tag", "-f", "release", bad)
            E.set_matrix(E.good_rows(bad))
            case("N", "N26 원문 변조 커밋+release 태그", *E.check(bad))
            sh("git", "-C", t, "reset", "-q", "--hard", sha); sh("git", "-C", t, "tag", "-f", "release", sha)
            E.set_matrix(E.good_rows())
            case("P", "P5 되돌린 뒤 GO 재현", *E.check(sha))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coord", default=os.path.join(ROOT, "coord", "coord.py"))
    a = ap.parse_args()
    print(f"[A6 gate audit] coord={os.path.relpath(a.coord, ROOT)} sha256={hashlib.sha256(open(a.coord,'rb').read()).hexdigest()[:16]}")
    run(a.coord)
    reg = [r for r in results if r[0] in "NP" and not r[3]]
    finds = [r for r in results if r[0] == "W" and not r[3]]
    for kind, name, rc, ok, tail in results:
        tag = ("PASS" if ok else "FAIL") if kind in "NP" else ("OK-REJECT" if ok else "FINDING")
        print(f"[{tag}] {name} — exit {rc} — {tail[:220]}")
    print(f"\n합계 {len(results)}건 / 회귀(N·P 실패) {len(reg)}건 / 약점 FINDING {len(finds)}건")
    for r in finds:
        print(f"  FINDING {r[1]}: tc check가 GO(exit 0) — 수동 보완 검사 필요(checklist_v1 §2)")
    sys.exit(1 if reg else 0)


if __name__ == "__main__":
    main()
