#!/bin/bash
# Bulut oturumlarinda ECC eklentisini (71 ajan + skill'ler) kurar.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "session-start: claude CLI bulunamadi, ECC kurulumu atlandi" >&2
  exit 0
fi

ECC_MARKETPLACE_URL="https://github.com/affaan-m/ECC.git"
INSTALLED_JSON="$HOME/.claude/plugins/installed_plugins.json"

if [ -f "$INSTALLED_JSON" ] && grep -q '"ecc@ecc"' "$INSTALLED_JSON"; then
  echo "session-start: ecc@ecc zaten kurulu"
  exit 0
fi

# Ag hatasi oturumu engellemesin diye hatalar uyari olarak raporlanir.
if ! claude plugin marketplace list 2>/dev/null | grep -q '\becc\b'; then
  timeout 150 claude plugin marketplace add "$ECC_MARKETPLACE_URL" \
    || echo "session-start: ECC marketplace eklenemedi" >&2
fi

timeout 180 claude plugin install ecc@ecc --scope user \
  || echo "session-start: ecc@ecc kurulamadi" >&2
