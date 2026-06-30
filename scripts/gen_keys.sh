#!/usr/bin/env bash
# Generate the SSH keypair used for NETCONF public-key auth.
# The PUBLIC key is baked into the container image (root's authorized_keys);
# the PRIVATE key stays on the host and is used by the ncclient harness.
# Keys live in secrets/ which is .gitignored — they are never committed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${REPO_ROOT}/secrets"
KEY="${SECRETS_DIR}/netconf_key"

mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

if [[ -f "${KEY}" ]]; then
  echo "[gen_keys] key already exists at ${KEY} — leaving it in place."
else
  ssh-keygen -t ed25519 -N "" -C "track1-netconf" -f "${KEY}"
  echo "[gen_keys] generated ${KEY} (+ .pub)"
fi
