#!/usr/bin/env bash
# Run on EC2 through SSM as root after uploading the reviewed private release.
set -euo pipefail
bucket="${1:?Usage: install_release.sh PRIVATE_BUCKET [RELEASE_KEY]}"
release_key="${2:-releases/resolve.tar.gz}"
[[ "$bucket" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || { echo 'Invalid bucket name'; exit 2; }
[[ "$release_key" =~ ^releases/[A-Za-z0-9._/-]+$ ]] || { echo 'Invalid release key'; exit 2; }
work_dir="$(mktemp -d /tmp/resolve-release.XXXXXX)"
trap 'rm -rf "$work_dir"' EXIT
aws s3 cp "s3://$bucket/$release_key" "$work_dir/resolve.tar.gz"
python3 - "$work_dir/resolve.tar.gz" <<'PY'
import pathlib,sys,tarfile
with tarfile.open(sys.argv[1], 'r:gz') as archive:
    for member in archive.getmembers():
        parts = pathlib.PurePosixPath(member.name).parts
        if member.name.startswith('/') or '..' in parts or not parts or parts[0] in ('data', '.git', 'venv') or member.issym() or member.islnk():
            raise SystemExit('Refused unsafe or persistent-data archive path')
        if not (member.isfile() or member.isdir()):
            raise SystemExit('Refused special archive entry')
    print('Release paths validated; persistent data is excluded.')
PY
install -d -m 0700 /opt/resolve /opt/resolve/secrets /opt/resolve/data
# The archive allowlist was verified above; no existing data directory is replaced.
tar -xzf "$work_dir/resolve.tar.gz" -C /opt/resolve --no-same-owner
cd /opt/resolve
chmod 600 .env secrets/gcp-key.json
install -d -m 0755 data/grafana data/models data/caddy
chown 472:472 data/grafana
compose() { docker compose --env-file .env -f deploy/aws/compose.yml -f deploy/aws/compose.neon.yml "$@"; }
compose config --quiet
# Keep these sequential to fit the small host without exhausting memory.
compose build backend
compose build frontend
compose up -d backend frontend grafana proxy
ready=false
for attempt in $(seq 1 90); do
  if compose exec -T backend curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 5
done
if [[ "$ready" != true ]]; then
  echo 'Backend did not become healthy; inspect Docker service logs through SSM.'
  exit 1
fi
# Download the public CPU embedding model once before the first customer request.
# This runs on EC2, never on the Mac, and persists in data/models/.
compose exec -T backend python -W ignore -c 'from app.embeddings.embed import EmbeddingGenerator; model = EmbeddingGenerator(); assert len(model.generate_embedding("deployment verification")) == 384; print("Embedding model cache verified.")'
compose ps
printf '%s\n' 'Release installed. Verify public HTTPS, demo authentication, a live ticket, and Grafana rendering before declaring deployment complete.' 
