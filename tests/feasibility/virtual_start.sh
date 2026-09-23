#!/bin/bash
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]
install -d -m 0700 -o tester /test/state /test/tokens '/test/profile/Example User é'
chown tester /evidence
/usr/sbin/pcscd --foreground --error > /test/pcsc.txt 2>&1 &
pcsc_pid=$!
trap 'kill "$pcsc_pid" 2>/dev/null || true' EXIT
for i in {1..30}; do [[ -S /run/pcscd/pcscd.comm ]] && break; sleep 1; done
test -S /run/pcscd/pcscd.comm
runuser -u tester -- env HOME='/test/profile/Example User é' XDG_RUNTIME_DIR=/test/state \
    SOFTHSM2_CONF=/test/state/softhsm.conf PROBE_REPORT=/evidence PROBE_INPUT=/input \
    GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=github-hosted \
    dbus-run-session -- xvfb-run -a -s '-screen 0 1280x1024x24' bash tests/feasibility/virtual_session.sh
