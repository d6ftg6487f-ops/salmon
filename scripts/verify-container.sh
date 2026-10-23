#!/usr/bin/env bash
set -euo pipefail

# Run only a locally built image. No cloud credentials or remote service is used.
image=${1:-salmon-ts:verify}
container="salmon-ts-verify-$$-${RANDOM}"
container_id=
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker logs "$container" || true
    docker rm -f "$container" >/dev/null
  fi
}
trap cleanup EXIT
container_id=$(docker run -d --name "$container" -p 127.0.0.1::8080 -e PORT=8080 "$image")
port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}' "$container")
base_url="http://127.0.0.1:$port"

ready=false
for attempt in {1..60}; do
  if curl --fail --silent --max-time 2 "$base_url/" >/dev/null; then
    ready=true
    break
  fi
  if [[ $(docker inspect --format '{{.State.Running}}' "$container") != true ]]; then
    echo 'Container exited before becoming ready.' >&2
    exit 1
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo 'Container did not become ready in time.' >&2
  exit 1
fi

# Compare Docker-generated scripts with the independently built working-copy assets.
# CSS, icons and the vendored module graph must also survive source packaging.
for asset in bulb.js chat.js three-bulb.js styles.css favicon-on.svg favicon-off.svg \
  vendor/three.module.min.js vendor/three.core.min.js vendor/THREE-LICENSE.txt; do
  curl --fail --silent --show-error "$base_url/static/$asset" | cmp - "static/$asset"
done

python3 - "$base_url" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
for name in ('bulb.js', 'chat.js', 'three-bulb.js'):
    with urllib.request.urlopen(f'{base}/static/{name}', timeout=10) as response:
        assert response.status == 200
        assert response.headers.get_content_type() in ('text/javascript', 'application/javascript')

states = []
for _ in range(2):
    request = urllib.request.Request(f'{base}/api/toggle', method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        states.append(json.load(response))
assert states[0]['is_on'] is not states[1]['is_on']
assert states[1]['press_count'] == states[0]['press_count'] + 1
print('Container HTTP, static assets and persisted toggle checks passed.')
PY

if docker exec "$container" sh -c 'command -v node' >/dev/null; then
  echo 'Node.js unexpectedly present in the Python runtime image.' >&2
  exit 1
fi

FRONTEND_BASE_URL="$base_url" npm run test:frontend
