#!/bin/bash
# M4 최종 GO 전제 감시(읽기 전용). 이상이 있을 때만 한 줄 출력, 15분마다 생존 줄 1개. 사용: bash release/premise_watch.sh <종료 HHMM>
cd "$(dirname "$0")/.." || exit 1
END=${1:-1446}
REL=48de01f1b0bfc15923b904d284b5591cfb8feedc
DEBRIEF=${DEBRIEF_SHA:-40cc5767d7a1247f}
COORD=8ea7284789f8cb51
BOT="agent integ deploy pyproject.toml uv.lock kb/policy_pack.md kb/api_usage.md kb/VERSION"
last_ok=""; i=0
while [ "$(date +%H%M)" -lt "$END" ]; do
  bad=()
  [ "$(git rev-parse release^{commit} 2>/dev/null)" = "$REL" ] || bad+=("release 태그≠48de01f")
  [ -z "$(git diff --name-only $REL -- $BOT | grep -v '^agent/logs/')" ] || bad+=("봇 경로가 release와 다름: $(git diff --name-only $REL -- $BOT | grep -v agent/logs | head -3 | tr '\n' ' ')")
  [ -z "$(git status --porcelain -- $BOT | grep -vE 'agent/logs/|__pycache__')" ] || bad+=("봇 경로 미커밋 변경")
  [ "$(shasum -a 256 docs/debrief.md | cut -c1-16)" = "$DEBRIEF" ] || bad+=("디브리프 sha 변경 $(shasum -a 256 docs/debrief.md | cut -c1-16)")
  [ "$(shasum -a 256 coord/coord.py | cut -c1-16)" = "$COORD" ] || bad+=("coord.py 해시 변경")
  (cd docs/contest && shasum -a 256 -c MANIFEST.sha256 >/dev/null 2>&1) || bad+=("docs/contest MANIFEST 불일치")
  (cd tests/tc/public && shasum -a 256 -c MANIFEST.sha256 >/dev/null 2>&1) || bad+=("tests/tc/public MANIFEST 불일치")
  if [ $((i % 5)) -eq 0 ]; then  # VM은 약 5분마다
    vm=$(CLOUDSDK_ACTIVE_CONFIG_NAME=aitop100 gcloud compute ssh ai-top-100-choonsik --zone us-central1-a --project ai-top-100-2026-513102 --quiet --command '
      echo "A=$(systemctl is-active choonsik) R=$(sudo cat /opt/choonsik/RELEASE | cut -c1-12)"
      sudo journalctl -u choonsik --since "-6min" --no-pager -o cat | grep -E "\"ev\": \"(alive|warmup|warmup_stopped|disconnect)\"" | tail -3' 2>/dev/null)
    echo "$vm" | grep -q "A=active" || bad+=("VM 서비스 비활성 또는 SSH 실패")
    echo "$vm" | grep -q "R=48de01f1b0bf" || bad+=("VM RELEASE≠48de01f")
    echo "$vm" | grep -q '"connected": false' && bad+=("VM 게이트웨이 connected=false")
    echo "$vm" | grep -q 'warmup_stopped' && bad+=("VM warmup 자동 중지(키 경로 오류 연속)")
    echo "$vm" | grep -q '"warmup".*"ok": false' && bad+=("VM warmup 실패(키 경로 오류 가능)")
  fi
  if [ ${#bad[@]} -gt 0 ]; then
    echo "[$(date +%H:%M:%S)] ✗ 전제 변경: ${bad[*]}"
  elif [ $((i % 15)) -eq 0 ]; then
    echo "[$(date +%H:%M:%S)] ✓ 전제 유지(release·봇 경로·디브리프·coord·원문·VM)"
  fi
  i=$((i+1)); sleep 60
done
echo "[$(date +%H:%M:%S)] 감시 종료"
