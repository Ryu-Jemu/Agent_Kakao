#!/usr/bin/env bash
# VM 런타임 환경 전환(코드 재배포 없이) — D-028 백엔드 이중화 대비.
#   deploy/vm_env.sh show              # /etc/default/choonsik(비밀 아님) + VM .env 키 목록(값 가림)
#   deploy/vm_env.sh set KEY=VALUE ... # 비밀 아닌 값만(GCP_PROJECT, GATEWAY_WARMUP, AGENT_MODEL 등) → /etc/default/choonsik, 재시작
#   deploy/vm_env.sh unset KEY ...     # 위에서 지정한 키 제거, 재시작
#   deploy/vm_env.sh push-dotenv       # 로컬 .env(HUMAN 소유, 비밀값) → VM /opt/choonsik/.env(600), 재시작
# 우선순위: systemd 환경(/etc/default/choonsik) > .env (python-dotenv override=False).
# 비밀값(KEY·TOKEN·SECRET·PASSWORD 포함 이름)은 set 금지 → .env + push-dotenv로만.
# 재시작은 RESUME 상태를 유지하므로 연결 단절은 약 2초.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VM_HOST="${VM_HOST:-136.65.54.161}"
VM_USER="${VM_USER:-$(whoami)}"
SSH=(ssh -i "$HOME/.ssh/google_compute_engine" -o HostKeyAlias=compute.4935063914578222615
     -o UserKnownHostsFile="$HOME/.ssh/google_compute_known_hosts" -o StrictHostKeyChecking=yes
     -o BatchMode=yes -o ConnectTimeout=15 "$VM_USER@$VM_HOST")

restart_and_check() {
  "${SSH[@]}" 'T0=$(date +%s); sudo systemctl restart choonsik; for i in $(seq 1 40); do sleep 0.5; sudo journalctl -u choonsik --since "@$T0" -o cat --no-pager | grep -q "\"ev\": \"connected\"" && break; done; echo "restart→connected $(( $(date +%s)-T0 ))s · $(systemctl is-active choonsik)"; sudo journalctl -u choonsik --since "@$T0" -o cat --no-pager | grep -E "\"ev\": \"(start|connected)\"|CRITICAL|Traceback" | cut -c1-200'
}

cmd="${1:-show}"; shift || true
case "$cmd" in
  show)
    "${SSH[@]}" 'echo "[/etc/default/choonsik]"; cat /etc/default/choonsik; echo "[VM .env 키]"; sudo sed -E "s/=.*/=<hidden>/" /opt/choonsik/.env; echo "[프로세스 환경]"; sudo cat /proc/$(systemctl show choonsik -p MainPID --value)/environ | tr "\0" "\n" | grep -E "^(GATEWAY_|VERTEX_|AGENT_VERTEX|GCP_PROJECT|AGENT_MODEL)" | sed -E "s/(KEY|TOKEN|SECRET)=.*/\1=<hidden>/"'
    ;;
  set)
    [[ $# -ge 1 ]] || { echo "usage: $0 set KEY=VALUE ..."; exit 2; }
    lines=()
    for kv in "$@"; do
      [[ "$kv" =~ ^[A-Z_][A-Z0-9_]*=[^[:space:]\'\"]*$ ]] || { echo "형식 오류: $kv"; exit 2; }
      k="${kv%%=*}"
      if [[ "$k" =~ (KEY|TOKEN|SECRET|PASSWORD) ]]; then echo "❌ 비밀값 $k 는 set 금지 → .env에 넣고 push-dotenv"; exit 2; fi
      lines+=("$kv")
    done
    keys="$(printf '%s\n' "${lines[@]}" | cut -d= -f1 | paste -sd'|' -)"
    printf '%s\n' "${lines[@]}" | "${SSH[@]}" "sudo bash -c 'T=\$(mktemp); grep -v -E \"^($keys)=\" /etc/default/choonsik > \$T || true; cat >> \$T; install -m 644 \$T /etc/default/choonsik; rm -f \$T; cat /etc/default/choonsik'"
    restart_and_check
    ;;
  unset)
    [[ $# -ge 1 ]] || { echo "usage: $0 unset KEY ..."; exit 2; }
    for k in "$@"; do [[ "$k" =~ ^[A-Z_][A-Z0-9_]*$ ]] || { echo "형식 오류: $k"; exit 2; }; done
    keys="$(printf '%s\n' "$@" | paste -sd'|' -)"
    "${SSH[@]}" "sudo bash -c 'T=\$(mktemp); grep -v -E \"^($keys)=\" /etc/default/choonsik > \$T || true; install -m 644 \$T /etc/default/choonsik; rm -f \$T; cat /etc/default/choonsik'"
    restart_and_check
    ;;
  push-dotenv)
    [[ -f .env ]] || { echo ".env 없음"; exit 2; }
    echo "로컬 .env 키: $(sed -E 's/=.*//' .env | paste -sd' ' -)"
    "${SSH[@]}" "umask 077; cat > /home/$VM_USER/.choonsik_env.tmp" < .env
    "${SSH[@]}" "sudo install -m 600 -o choonsik -g choonsik /home/$VM_USER/.choonsik_env.tmp /opt/choonsik/.env && rm -f /home/$VM_USER/.choonsik_env.tmp && echo '✓ VM .env 갱신(600)'"
    restart_and_check
    ;;
  *) echo "usage: $0 show|set KEY=VALUE..|unset KEY..|push-dotenv"; exit 2 ;;
esac
