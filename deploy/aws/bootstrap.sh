#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 awscli unzip
systemctl enable --now docker
install -d -m 0700 /opt/resolve /opt/resolve/secrets /opt/resolve/data
# A small encrypted-root-volume swap file keeps the first CPU image build from
# exhausting this 4 GB demo host. It is not a substitute for scaling production.
if ! test -e /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
