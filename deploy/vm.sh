#!/usr/bin/env bash
# VM 운영 보조: deploy/vm.sh status|logs [N]|replies [N]|release|mem|cmd "<명령>"
#   status  : 서비스 상태·RELEASE·메모리·최근 연결 이벤트
#   logs N  : journald 최근 N줄(기본 50)
#   replies N : 지연 로그(reply JSON) 최근 N건 → A5 분석용
set -euo pipefail
VM_HOST="${VM_HOST:-136.65.54.161}"
VM_USER="${VM_USER:-$(whoami)}"
SSH=(ssh -i "$HOME/.ssh/google_compute_engine" -o HostKeyAlias=compute.4935063914578222615
     -o UserKnownHostsFile="$HOME/.ssh/google_compute_known_hosts" -o StrictHostKeyChecking=yes
     -o BatchMode=yes -o ConnectTimeout=15 "$VM_USER@$VM_HOST")
case "${1:-status}" in
  status)
    "${SSH[@]}" 'echo "service: $(systemctl is-active choonsik) since $(systemctl show choonsik -p ActiveEnterTimestamp --value) restarts=$(systemctl show choonsik -p NRestarts --value)"; echo "RELEASE: $(sudo cat /opt/choonsik/RELEASE 2>/dev/null)"; echo "mode: $(cat /etc/default/choonsik 2>/dev/null)"; free -m | sed -n 1,3p; echo "gateway procs: $(pgrep -fc "integ\.gateway" || true)"; sudo journalctl -u choonsik -n 400 --no-pager -o cat | grep -E "\"ev\": \"(start|connected|disconnect|alive)\"" | tail -4' ;;
  logs)    "${SSH[@]}" "sudo journalctl -u choonsik -n ${2:-50} --no-pager -o short-iso" ;;
  replies) "${SSH[@]}" "sudo journalctl -u choonsik --no-pager -o cat | grep '\"ev\": \"reply\"' | tail -n ${2:-50}" ;;
  release) "${SSH[@]}" "sudo cat /opt/choonsik/RELEASE" ;;
  mem)     "${SSH[@]}" 'free -m; ps -o rss,etime,cmd -C python3.11,python3 --sort=-rss | head -5' ;;
  cmd)     shift; "${SSH[@]}" "$@" ;;
  *) echo "usage: $0 status|logs [N]|replies [N]|release|mem|cmd ..."; exit 2 ;;
esac
