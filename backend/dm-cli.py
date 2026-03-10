#!/usr/bin/env python3
"""CLI d'administration pour Download Manager.

Usage:
    python3 dm-cli.py reset-admin                — Supprime tous les comptes (retour a l'ecran de creation)
    python3 dm-cli.py reset-admin <user> <pass>   — Reset et cree un nouveau compte admin
    python3 dm-cli.py list-ips                    — Liste les IPs bloquees
    python3 dm-cli.py unblock <IP>                — Debloque une IP
    python3 dm-cli.py unblock-all                 — Debloque toutes les IPs
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("DM_DB", "/opt/download-manager/config/downloads.db"))


def get_db():
    if not DB_PATH.exists():
        print(f"Erreur: base de donnees introuvable: {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


# ---- Admin reset ----

def cmd_reset_admin(username=None, password=None):
    db = get_db()

    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Comptes existants: {count}")

    db.execute("DELETE FROM users")
    db.commit()
    print("Tous les comptes ont ete supprimes.")

    if username and password:
        if len(password) < 6:
            print("Erreur: le mot de passe doit faire au moins 6 caracteres.")
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
                print("Erreur: ni bcrypt ni passlib n'est installe. Installez: pip install bcrypt")
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
        print(f"Compte admin cree: {username}")
    else:
        print("Au prochain login, l'ecran de creation de compte apparaitra.")

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
            print("Secret JWT regenere (tous les tokens existants sont invalides).")
        except Exception as e:
            print(f"Attention: impossible de regenerer le secret JWT: {e}")

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
        print("Aucune IP bloquee actuellement.")
        return

    print(f"{'IP':<40} {'Bloque le':<22} {'Expire le':<22} {'Raison'}")
    print("-" * 110)
    for ip, blocked_at, expires_at, reason in rows:
        b = blocked_at[:19].replace("T", " ")
        e = expires_at[:19].replace("T", " ")
        print(f"{ip:<40} {b:<22} {e:<22} {reason or ''}")
    print(f"\nTotal: {len(rows)} IP(s) bloquee(s)")


def cmd_unblock(ip):
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
    db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
    db.commit()
    if cursor.rowcount:
        print(f"IP {ip} debloquee.")
    else:
        print(f"IP {ip} non trouvee.")
    db.close()


def cmd_unblock_all():
    db = get_db()
    cursor = db.execute("DELETE FROM blocked_ips")
    db.execute("DELETE FROM login_attempts")
    db.commit()
    print(f"{cursor.rowcount} IP(s) debloquee(s).")
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
        print(f"Commande inconnue: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
