#!/usr/bin/env python3
"""Pre-commit security script to detect and block secret leaks, .env files, and SQLite databases."""

import re
import subprocess
import sys

# Prohibited file extensions and names in git staging
BLOCKED_FILE_PATTERNS = [
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),  # .env, .env.local, .env.production
    re.compile(r"^.*\.db$", re.IGNORECASE),
    re.compile(r"^.*\.sqlite3?$", re.IGNORECASE),
    re.compile(r"^.*ngrok.*\.ya?ml$", re.IGNORECASE),
]

# Files explicitly allowed despite matching patterns
ALLOWED_FILES = {
    ".env.example",
}

# Regex to detect high-entropy keys, private tokens, and API credentials
SECRET_PATTERNS = [
    re.compile(r"(?i)(auth[_-]token|api[_-]key|secret[_-]key|access[_-]token|bearer)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{16,}['\"]"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI secret key format
    re.compile(r"dg-[a-zA-Z0-9]{20,}"),  # Deepgram key format
    re.compile(r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH|PRIVATE)\s+KEY-----"),
]

# Patterns allowed in tests/documentation
SAFE_EXCLUSIONS = re.compile(r"(?i)(example|placeholder|dummy|mock|fake|your_|test_)")


def get_staged_files() -> list[str]:
    """Retrieves list of files staged for commit."""
    try:
        res = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            encoding="utf-8",
            errors="replace",
        )
        return [f.strip() for f in res.splitlines() if f.strip()]
    except Exception as e:
        print(f"[SECURITY CHECK ERROR] Could not get staged files: {e}")
        return []


def check_staged_filenames(staged_files: list[str]) -> bool:
    """Blocks commit if prohibited filenames are staged."""
    has_violation = False
    for filename in staged_files:
        if filename in ALLOWED_FILES:
            continue
        for pattern in BLOCKED_FILE_PATTERNS:
            if pattern.search(filename):
                print(f"[BLOCKED] Prohibited file staged for commit: '{filename}'")
                print("   Never commit environment configurations or database binaries.")
                has_violation = True
    return has_violation


def check_staged_content() -> bool:
    """Inspects staged diff additions for hardcoded credentials."""
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--cached", "-U0"],
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        print(f"[SECURITY CHECK ERROR] Could not read staged diff: {e}")
        return False

    has_violation = False
    for line in diff_output.splitlines():
        # Only check newly added lines
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()

        # Check if line contains a secret pattern
        for pat in SECRET_PATTERNS:
            match = pat.search(content)
            if match:
                matched_str = match.group(0)
                # Ignore test placeholders or dummy credentials
                if SAFE_EXCLUSIONS.search(matched_str):
                    continue
                print("[BLOCKED] Potential hardcoded secret detected in staged changes:")
                print(f"   Line: {content[:80]}...")
                print("   Remedy: Move credential to .env and read via Settings.")
                has_violation = True
                break
    return has_violation


def check_detect_secrets(staged_files: list[str]) -> bool:
    """Runs detect-secrets-hook against staged files if detect-secrets is installed."""
    import shutil
    if not shutil.which("detect-secrets-hook"):
        return False

    baseline_arg = []
    from pathlib import Path
    if Path(".secrets.baseline").exists():
        baseline_arg = ["--baseline", ".secrets.baseline"]

    try:
        # Run detect-secrets-hook on staged files
        cmd = ["detect-secrets-hook"] + baseline_arg + staged_files
        res = subprocess.run(cmd, text=True, capture_output=True)
        if res.returncode != 0:
            print("[BLOCKED] detect-secrets flagged potential secrets in staged files:")
            if res.stdout:
                print(res.stdout)
            if res.stderr:
                print(res.stderr)
            return True
    except Exception as e:
        print(f"[WARNING] Could not execute detect-secrets-hook: {e}")
    return False


def main() -> int:
    staged = get_staged_files()
    if not staged:
        return 0

    file_violation = check_staged_filenames(staged)
    content_violation = check_staged_content()
    detect_secrets_violation = check_detect_secrets(staged)

    if file_violation or content_violation or detect_secrets_violation:
        print("\n[REJECTED] Commit aborted: Security hygiene check failed.\n")
        return 1

    print("[PASSED] Security hygiene check passed: No secrets or prohibited files staged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
