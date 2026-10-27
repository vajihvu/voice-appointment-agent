#!/usr/bin/env bash
# Installs git pre-commit hook into .git/hooks
set -e

HOOK_DIR=".git/hooks"
HOOK_FILE="${HOOK_DIR}/pre-commit"

if [ ! -d ".git" ]; then
    echo "Error: .git directory not found. Please run this script from the root of the repository."
    exit 1
fi

mkdir -p "${HOOK_DIR}"

# Write pre-commit hook to invoke the version-controlled script
cat << 'EOF' > "${HOOK_FILE}"
#!/bin/sh
python scripts/check_secrets.py
EOF

chmod +x "${HOOK_FILE}"
echo "Pre-commit hook installed successfully into ${HOOK_FILE}."
