from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from . import data

AUTH_PATH = data.RUNTIME_DIR / "auth.json"
SECRET_PATH = data.RUNTIME_DIR / ".session_secret"
LOGIN_PATH = data.RUNTIME_DIR / "login.txt"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "bioforge-demo"
SESSION_TTL = 12 * 3600
COOKIE_NAME = "bioforge_session"


def _hash(password: str, salt: str, iterations: int = 240_000) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ensure_account() -> dict[str, Any]:
    data.ensure_dirs()
    env_password = os.environ.get("BIOFORGE_ADMIN_PASSWORD")
    if AUTH_PATH.exists():
        try:
            account = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
            if account.get("username") and account.get("salt") and account.get("hash"):
                return account
        except Exception:
            pass
    username = os.environ.get("BIOFORGE_ADMIN_USER", DEFAULT_USER).strip() or DEFAULT_USER
    password = env_password or DEFAULT_PASSWORD
    salt = secrets.token_hex(16)
    account = {
        "username": username,
        "salt": salt,
        "hash": _hash(password, salt),
        "iterations": 240_000,
        "created": int(time.time()),
        "demo_default": not bool(env_password),
    }
    _write_private(AUTH_PATH, json.dumps(account, ensure_ascii=False, indent=2))
    _write_private(LOGIN_PATH, f"username: {username}\npassword: {password}\nnote: change this demo password before exposing the server.\n")
    return account


def change_password(current: str, new_password: str, username: str | None = None) -> dict[str, Any]:
    account = ensure_account()
    if not verify(username or account["username"], current):
        raise ValueError("current password is incorrect")
    if len(new_password) < 8:
        raise ValueError("new password must be at least 8 characters")
    salt = secrets.token_hex(16)
    account.update({"salt": salt, "hash": _hash(new_password, salt), "iterations": 240_000, "demo_default": False})
    _write_private(AUTH_PATH, json.dumps(account, ensure_ascii=False, indent=2))
    _write_private(LOGIN_PATH, f"username: {account['username']}\npassword changed at {int(time.time())}\nnote: password is not stored in plaintext here.\n")
    return {"username": account["username"], "updated": True}


def verify(username: str, password: str) -> bool:
    account = ensure_account()
    if not hmac.compare_digest(str(username), str(account["username"])):
        return False
    candidate = _hash(str(password), account["salt"], int(account.get("iterations", 240_000)))
    return hmac.compare_digest(candidate, account["hash"])


def _secret() -> bytes:
    data.ensure_dirs()
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    secret = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(secret)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return secret


def issue_session(username: str) -> tuple[str, int]:
    expires = int(time.time()) + SESSION_TTL
    payload = json.dumps({"u": username, "exp": expires, "n": secrets.token_hex(8)}, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}", expires


def verify_session(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    account = ensure_account()
    if payload.get("u") != account["username"]:
        return None
    return payload


def public_account() -> dict[str, Any]:
    account = ensure_account()
    return {
        "username": account["username"],
        "demo_default": bool(account.get("demo_default")),
        "password_file": str(LOGIN_PATH),
        "session_ttl_seconds": SESSION_TTL,
    }
