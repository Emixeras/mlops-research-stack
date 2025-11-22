#!/usr/bin/env python3
"""Minimal bcrypt htpasswd generator.

Usage:
  python scripts/gen_htpasswd.py username [password]

If password is omitted the script prompts for it.
Requires the `bcrypt` package: `pip install bcrypt`.
"""
import getpass
import sys

try:
    import bcrypt
except Exception:
    print("Error: python-bcrypt is required. Install with: pip install bcrypt", file=sys.stderr)
    raise


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: gen_htpasswd.py username [password]", file=sys.stderr)
        return 2
    user = argv[0]
    pw = argv[1] if len(argv) > 1 else None
    if pw is None:
        try:
            pw = getpass.getpass(f"Password for {user}: ")
        except Exception:
            pw = input(f"Password for {user}: ")
    if not pw:
        print("no password provided", file=sys.stderr)
        return 3

    pw_bytes = pw.encode()
    h = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    print(f"{user}:{h.decode()}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
