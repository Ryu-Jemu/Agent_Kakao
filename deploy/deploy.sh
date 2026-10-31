#!/usr/bin/env bash
# VM 배포: [GATEWAY_WARMUP=0] deploy/deploy.sh echo|agent [<git-sha>]   (GATEWAY_WARMUP=0: agent.warmup 주기 호출 끔, D-027)
#   <git-sha>를 주면 작업 트리가 아니라 그 커밋 내용(git archive)을 그대로 배포한다(BUILD sha = VM 코드 보장).
#   1) 로컬 gateway 프로세스 0개 확인(4004 방지)  2) 스테이징(agent/ integ/ kb/ deploy/ pyproject uv.lock .python-version .env)
#   3) RELEASE(git SHA[-dirty] + 내용 지문) · MANIFEST.sha256  4) VM 초기설정(vm_setup.sh, 멱등)
#   5) rsync → /opt/choonsik, sha256 검증, uv sync --frozen(시스템 python3.11)  6) systemd 재시작·READY 확인
# 비밀값은 출력하지 않는다(.env는 권한 600으로만 전송·설치).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:?사용법: deploy/deploy.sh echo|agent [<git-sha>]}"
REF="${2:-}"
[[ "$MODE" == echo || "$MODE" == agent ]] || { echo "MODE는 echo|agent"; exit 2; }

VM_HOST="${VM_HOST:-136.65.54.161}"
VM_USER="${VM_USER:-$(whoami)}"
SSH=(ssh -i "$HOME/.ssh/google_compute_engine" -o HostKeyAlias=compute.4935063914578222615
     -o UserKnownHostsFile="$HOME/.ssh/google_compute_known_hosts" -o StrictHostKeyChecking=yes
     -o BatchMode=yes -o ConnectTimeout=15)
R="$VM_USER@$VM_HOST"

# 1) 로컬 gateway 0개
if pgrep -fl 'integ\.gateway( |$)' >/dev/null; then
  echo "❌ 로컬에서 integ.gateway 실행 중 — 종료 후 다시 배포(4004 방지)"; pgrep -fl 'integ\.gateway( |$)'; exit 1
fi
echo "✓ 로컬 gateway 프로세스 0개"

# 2) 스테이징
PATHS=(agent integ kb deploy pyproject.toml uv.lock .python-version)
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/choonsik"; mkdir -p "$STAGE"
if [[ -n "$REF" ]]; then
  SHA="$(git rev-parse --short=12 "$REF^{commit}")"
  REL="$SHA"
  git archive --format=tar "$SHA" -- "${PATHS[@]}" | tar -x -C "$STAGE"
  find "$STAGE" \( -name '__pycache__' -o -name 'logs' \) -prune -exec rm -rf {} +
else
  SHA="$(git rev-parse --short=12 HEAD 2>/dev/null || echo nogit)"
  DIRTY="$(git status --porcelain -- "${PATHS[@]}" 2>/dev/null | wc -l | tr -d ' ')"
  REL="$SHA"; [[ "$DIRTY" != 0 ]] && REL="$SHA-dirty"
  rsync -a --exclude '__pycache__/' --exclude '*.pyc' --exclude 'logs/' --exclude '.DS_Store' \
    "${PATHS[@]}" "$STAGE/"
fi
install -m 600 .env "$STAGE/.env"
( cd "$STAGE" && find . -type f ! -name .env ! -name MANIFEST.sha256 ! -name RELEASE -print0 | sort -z \
    | xargs -0 shasum -a 256 > MANIFEST.sha256 )
FP="$(shasum -a 256 "$STAGE/MANIFEST.sha256" | cut -c1-16)"
echo "$REL fp=$FP mode=$MODE deployed=$(date '+%Y-%m-%dT%H:%M:%S%z')" > "$STAGE/RELEASE"
echo "✓ 스테이징: RELEASE=$(cat "$STAGE/RELEASE") 파일 $(wc -l < "$STAGE/MANIFEST.sha256")개"

# 3) VM 초기설정(멱등)
"${SSH[@]}" "$R" "sudo bash -s" < "$STAGE/deploy/vm_setup.sh"

# 4) 업로드 → 설치
rsync -az --delete --chmod=Du=rwx,Dgo=,Fu=rw,Fgo= -e "${SSH[*]}" "$STAGE/" "$R:choonsik_stage/"
"${SSH[@]}" "$R" "sudo MODE=$MODE WARMUP=${GATEWAY_WARMUP:-1} STAGE=/home/$VM_USER/choonsik_stage bash -s" <<'REMOTE'
set -euo pipefail
rsync -a --delete --exclude '.venv/' --exclude '.cache/' --exclude 'integ/logs/' --exclude 'agent/logs/' "$STAGE/" /opt/choonsik/
rm -f "$STAGE/.env"
chown -R choonsik:choonsik /opt/choonsik
chmod 600 /opt/choonsik/.env
chmod -R go-rwx /opt/choonsik
( cd /opt/choonsik && sha256sum -c --quiet MANIFEST.sha256 ) && echo "✓ VM 파일 sha256 일치"
mkdir -p /opt/choonsik/integ/logs /opt/choonsik/agent/logs && chown -R choonsik:choonsik /opt/choonsik/integ/logs /opt/choonsik/agent/logs
sudo -u choonsik env HOME=/opt/choonsik UV_CACHE_DIR=/opt/choonsik/.cache/uv UV_PYTHON_DOWNLOADS=never \
  /opt/uv/bin/uv sync --frozen --no-dev --python /usr/bin/python3.11 --project /opt/choonsik -q
sudo -u choonsik /opt/choonsik/.venv/bin/python -c "import httpx, websockets, google.genai, dotenv" && echo "✓ 의존성 import"
if [ "$MODE" = agent ]; then
  sudo -u choonsik bash -c 'cd /opt/choonsik && .venv/bin/python -c "from agent import handle_message; print(\"✓ agent.handle_message import\")"'
fi
# 런타임 환경 고정(systemd 환경변수가 .env보다 우선 — dotenv override=False). D-008·#234: Vertex는 global
# 관리 키만 갱신하고, vm_env.sh set으로 넣은 다른 키(GCP_PROJECT 등)는 보존한다
T=$(mktemp)
grep -v -E '^(GATEWAY_MODE|VERTEX_LOCATION|AGENT_VERTEX_LOCATION|GATEWAY_WARMUP)=' /etc/default/choonsik > "$T" 2>/dev/null || true
printf 'GATEWAY_MODE=%s\nVERTEX_LOCATION=global\nAGENT_VERTEX_LOCATION=global\nGATEWAY_WARMUP=%s\n' "$MODE" "$WARMUP" >> "$T"
install -m 644 "$T" /etc/default/choonsik; rm -f "$T"
install -m 644 /opt/choonsik/deploy/choonsik.service /etc/systemd/system/choonsik.service
systemctl daemon-reload
systemctl enable -q choonsik
T0=$(date '+%Y-%m-%d %H:%M:%S')
systemctl restart choonsik
for i in $(seq 1 20); do
  sleep 1
  if journalctl -u choonsik --since "$T0" --no-pager -o cat | grep -q '"ev": "connected"'; then break; fi
done
echo "--- systemctl: $(systemctl is-active choonsik) · RELEASE: $(cat /opt/choonsik/RELEASE)"
journalctl -u choonsik --since "$T0" --no-pager -o cat | grep -E '"ev": "(start|connected|disconnect)"|READY|CRITICAL|ERROR|Traceback' | tail -8
journalctl -u choonsik --since "$T0" --no-pager -o cat | grep -q '"ev": "connected"' && echo "✓ 게이트웨이 연결됨" || { echo "❌ 연결 확인 실패"; exit 1; }
REMOTE
echo "✓ 배포 완료: $REL mode=$MODE"
