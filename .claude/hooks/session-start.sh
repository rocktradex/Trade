#!/bin/bash
# SessionStart hook: prepares a Claude Code on the web session.
# Installs project Python dependencies and the velsvisual CLI (KIE API media generation,
# used by the .claude/skills/visual skill). Runs only in remote (web) sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

echo "[session-start] Installing Python dependencies..."
# The Debian-packaged setuptools is too old to build pybit's wheel; upgrade it first.
python3 -m pip install --quiet --disable-pip-version-check --ignore-installed --upgrade setuptools
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt

echo "[session-start] Installing velsvisual CLI..."
if ! command -v velsvisual >/dev/null 2>&1; then
  npm install -g --no-fund --no-audit velsvisual@latest
else
  echo "[session-start] velsvisual already installed: $(velsvisual --version)"
fi

# Persist KIE API key for the session if the environment provides one
# (set KIE_API_KEY in the Claude Code environment settings; never commit it).
if [ -n "${KIE_API_KEY:-}" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export KIE_API_KEY=\"${KIE_API_KEY}\"" >> "$CLAUDE_ENV_FILE"
fi

echo "[session-start] Done."
