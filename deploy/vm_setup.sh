#!/usr/bin/env bash
# VM 1회 초기 설정(멱등). deploy.sh가 원격에서 sudo로 실행한다.
#  - apt: rsync, python3-venv (Debian 공식 저장소)
#  - 시스템 사용자 choonsik, /opt/choonsik
#  - uv(PyPI, 로컬과 같은 버전) → /opt/uv
#  - 스왑 1GB(e2-micro 1GB RAM, 스왑 0 → OOM 방지)
#  - journald 영구 보관
set -euo pipefail
UV_VERSION="${UV_VERSION:-0.12.5}"

need_apt=()
command -v rsync >/dev/null || need_apt+=(rsync)
dpkg -s python3-venv >/dev/null 2>&1 || need_apt+=(python3-venv)
if ((${#need_apt[@]})); then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "${need_apt[@]}"
fi

id choonsik >/dev/null 2>&1 || useradd --system --home-dir /opt/choonsik --shell /usr/sbin/nologin choonsik
mkdir -p /opt/choonsik
chown choonsik:choonsik /opt/choonsik

if [ ! -x /opt/uv/bin/uv ] || [ "$(/opt/uv/bin/uv --version | awk '{print $2}')" != "$UV_VERSION" ]; then
  python3 -m venv /opt/uv
  /opt/uv/bin/pip install -q "uv==${UV_VERSION}"
fi

if ! swapon --show | grep -q '/swapfile'; then
  if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -q vm.swappiness=10
echo 'vm.swappiness=10' > /etc/sysctl.d/99-choonsik.conf

mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal >/dev/null 2>&1 || true
systemctl restart systemd-journald

echo "vm_setup ok: uv=$(/opt/uv/bin/uv --version) swap=$(swapon --show --noheadings | awk '{print $3}')"
