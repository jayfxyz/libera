"""
Thin wrapper around audible's built-in FileAuthenticator for token persistence.
Tokens are stored as JSON files in /data/accounts/<account_id>.json
"""

import os
import audible

ACCOUNTS_DIR = os.environ.get("ACCOUNTS_DIR", "/data/accounts")


def _ensure_dir():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)


def token_path(account_id: str) -> str:
    _ensure_dir()
    return os.path.join(ACCOUNTS_DIR, f"{account_id}.json")


def load_client(account_id: str) -> audible.AsyncClient:
    path = token_path(account_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No tokens for account {account_id}")
    auth = audible.Authenticator.from_file(path)
    return audible.AsyncClient(auth=auth)


def save_auth(account_id: str, auth: audible.Authenticator):
    _ensure_dir()
    auth.to_file(token_path(account_id))
