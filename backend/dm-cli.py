#!/usr/bin/env python3
"""Administration CLI for Download Manager.

Usage:
    python3 dm-cli.py reset-admin                — Delete all accounts (returns to setup screen)
    python3 dm-cli.py reset-admin <user> <pass>   — Reset and create a new admin account
    python3 dm-cli.py list-ips                    — List blocked IPs
    python3 dm-cli.py unblock <IP>                — Unblock an IP
    python3 dm-cli.py unblock-all                 — Unblock all IPs
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("DM_DB", "/opt/download-manager/config/downloads.db"))


def get_db():
    if not DB_PATH.exists():
        print(f"Error: database not found: {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


# ---- Admin reset ----

def cmd_reset_admin(username=None, password=None):
    db = get_db()

    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Existing accounts: {count}")

    db.execute("DELETE FROM users")
    db.commit()
    print("All accounts have been deleted.")

    if username and password:
        if len(password) < 6:
            print("Error: password must be at least 6 characters.")
            db.close()
            sys.exit(1)

        # Hash password with bcrypt (same as the app)
        try:
            import bcrypt
            pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        except ImportError:
            try:
                from passlib.context import CryptContext
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
                pw_hash = pwd_context.hash(password)
            except ImportError:
                print("Error: neither bcrypt nor passlib is installed. Install with: pip install bcrypt")
                db.close()
                sys.exit(1)

        import uuid
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, pw_hash, now),
        )
        db.commit()
        print(f"Admin account created: {username}")
    else:
        print("On next login, the account creation screen will appear.")

    # Invalidate existing tokens by regenerating JWT secret
    config_path = Path(os.environ.get("DM_CONFIG", "/etc/download-manager/config.yml"))
    if config_path.exists():
        try:
            import yaml
            import secrets
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            if "auth" not in cfg:
                cfg["auth"] = {}
            cfg["auth"]["jwt_secret"] = secrets.token_hex(32)
            with open(config_path, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
            print("JWT secret regenerated (all existing tokens are now invalid).")
        except Exception as e:
            print(f"Warning: could not regenerate JWT secret: {e}")

    db.close()


# ---- IP management ----

def cmd_list_ips():
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        "SELECT ip, blocked_at, expires_at, reason FROM blocked_ips WHERE expires_at > ? ORDER BY blocked_at DESC",
        (now,),
    ).fetchall()
    db.close()

    if not rows:
        print("No IPs currently blocked.")
        return

    print(f"{'IP':<40} {'Blocked at':<22} {'Expires at':<22} {'Reason'}")
    print("-" * 110)
    for ip, blocked_at, expires_at, reason in rows:
        b = blocked_at[:19].replace("T", " ")
        e = expires_at[:19].replace("T", " ")
        print(f"{ip:<40} {b:<22} {e:<22} {reason or ''}")
    print(f"\nTotal: {len(rows)} blocked IP(s)")


def cmd_unblock(ip):
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
    db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
    db.commit()
    if cursor.rowcount:
        print(f"IP {ip} unblocked.")
    else:
        print(f"IP {ip} not found.")
    db.close()


def cmd_unblock_all():
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips")
    db.execute("DELETE FROM login_attempts")
    db.commit()
    print(f"{cursor.rowcount} IP(s) unblocked.")
    db.close()


# ---- Main ----

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "reset-admin":
        username = sys.argv[2] if len(sys.argv) > 2 else None
        password = sys.argv[3] if len(sys.argv) > 3 else None
        if username and not password:
            print("Usage: python3 dm-cli.py reset-admin <username> <password>")
            sys.exit(1)
        cmd_reset_admin(username, password)
    elif cmd == "list-ips":
        cmd_list_ips()
    elif cmd == "unblock":
        if len(sys.argv) < 3:
            print("Usage: python3 dm-cli.py unblock <IP>")
            sys.exit(1)
        cmd_unblock(sys.argv[2])
    elif cmd == "unblock-all":
        cmd_unblock_all()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
