#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/otree ]]; then
  echo 'Install first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt' >&2
  exit 1
fi
if [[ -z "${WORK_SETUP_PASSWORD:-}" || -z "${OTREE_ADMIN_PASSWORD:-}" ]]; then
  echo 'Set WORK_SETUP_PASSWORD and OTREE_ADMIN_PASSWORD before starting. See README.md.' >&2
  exit 1
fi
export PATH="$PWD/.venv/bin:$PATH"
# A separate database is essential: never inherit the original experiment's DATABASE_URL.
export DATABASE_URL="${WORK_DATABASE_URL:-sqlite:///db.sqlite3}"
unset OTREE_IN_MEMORY
export OTREE_AUTH_LEVEL=STUDY
export OTREE_PRODUCTION=1
if [[ -z "${OTREE_SECRET_KEY:-}" ]]; then
  if [[ ! -s .work_secret_key ]]; then
    (umask 077; .venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))' > .work_secret_key)
  fi
  OTREE_SECRET_KEY=$(cat .work_secret_key)
  export OTREE_SECRET_KEY
fi
exec otree prodserver "${1:-8001}"
