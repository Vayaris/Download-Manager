#!/usr/bin/env python3
"""CLI tool to manage blocked IPs for Download Manager.

Usage:
    python3 cli_unblock.py list              — List all currently blocked IPs
    python3 cli_unblock.py unblock <IP>      — Unblock a specific IP
    python3 cli_unblock.py unblock-all       — Unblock all IPs
"""
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/opt/download-manager/config/downloads.db")

# Allow override via env or check common locations
import os
env_db = os.environ.get("DM_DB")
if env_db:
    DB_PATH = Path(env_db)


def get_db():
    if not DB_PATH.exists():
        print(f"Erreur: base de donnees introuvable: {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def cmd_list():
    db = get_db()
    now = datetime.utcnow().isoformat()
    rows = db.execute(
        "SELECT ip, blocked_at, expires_at, reason FROM blocked_ips WHERE expires_at > ? ORDER BY blocked_at DESC",
        (now,),
    ).fetchall()
    db.close()

    if not rows:
        print("Aucune IP bloquee actuellement.")
        return

    print(f"{'IP':<40} {'Bloque le':<22} {'Expire le':<22} {'Raison'}")
    print("-" * 110)
    for ip, blocked_at, expires_at, reason in rows:
        b = blocked_at[:19].replace("T", " ")
        e = expires_at[:19].replace("T", " ")
        print(f"{ip:<40} {b:<22} {e:<22} {reason or ''}")
    print(f"\nTotal: {len(rows)} IP(s) bloquee(s)")


def cmd_unblock(ip: str):
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
    db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
    db.commit()
    if cursor.rowcount:
        print(f"IP {ip} debloquee avec succes.")
    else:
        print(f"IP {ip} non trouvee dans les IPs bloquees.")
    db.close()


def cmd_unblock_all():
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips")
    db.execute("DELETE FROM login_attempts")
    db.commit()
    print(f"{cursor.rowcount} IP(s) debloquee(s).")
    db.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "list":
        cmd_list()
    elif cmd == "unblock":
        if len(sys.argv) < 3:
            print("Usage: python3 cli_unblock.py unblock <IP>")
            sys.exit(1)
        cmd_unblock(sys.argv[2])
    elif cmd == "unblock-all":
        cmd_unblock_all()
    else:
        print(f"Commande inconnue: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
