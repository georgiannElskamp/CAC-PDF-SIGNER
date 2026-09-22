#!/bin/bash
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]] || { echo 'GitHub-hosted runners only'; exit 1; }
input=$(realpath "$1")
mkdir -p "$2"
report=$(realpath "$2")
root=$(git rev-parse --show-toplevel)
container="cac-simulation-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker build --pull -f tests/linux/Dockerfile -t cac-simulation .
docker create --name "$container" --shm-size=1g \
    --mount "type=bind,src=$root,dst=/repo,readonly" \
    --mount "type=bind,src=$input,dst=/input,readonly" cac-simulation
status=0
docker start -a "$container" || status=$?
for name in signing-result.json signed-preview.png field-screen.png; do
    docker cp "$container:/evidence/$name" "$report/$name" 2>/dev/null || true
done
exit "$status"
