#!/usr/bin/env python3
"""Cross-platform installer for git pre-commit hook."""

from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent.parent
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        print("Error: .git directory not found.")
        return 1

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_file = hooks_dir / "pre-commit"
    hook_content = "#!/bin/sh\npython scripts/check_secrets.py\n"

    hook_file.write_text(hook_content, encoding="utf-8")
    try:
        hook_file.chmod(0o755)
    except Exception:
        pass

    print(f"Pre-commit hook installed successfully into {hook_file}.")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
