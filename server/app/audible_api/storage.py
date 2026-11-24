"""Audible tokens, one JSON file per account in ACCOUNTS_DIR."""

from __future__ import annotations

from pathlib import Path

import audible


class AccountNotFound(Exception):
    pass


def token_path(accounts_dir: str, account_id: str) -> Path:
    # account_id comes from Amazon ("amzn1.account.…"); keep it to a file name.
    return Path(accounts_dir) / f"{Path(account_id).name}.json"


def load_client(accounts_dir: str, account_id: str) -> audible.AsyncClient:
    path = token_path(accounts_dir, account_id)
    if not path.exists():
        raise AccountNotFound(f"No tokens for account {account_id}")
    return audible.AsyncClient(auth=audible.Authenticator.from_file(str(path)))


def load_auth(accounts_dir: str, account_id: str) -> audible.Authenticator | None:
    """The saved login for an account, or None if there isn't one."""
    path = token_path(accounts_dir, account_id)
    return audible.Authenticator.from_file(str(path)) if path.exists() else None


def save_auth(accounts_dir: str, account_id: str, auth: audible.Authenticator) -> None:
    path = token_path(accounts_dir, account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    auth.to_file(str(path))
    path.chmod(0o600)  # the file holds the account's credentials


def delete_auth(accounts_dir: str, account_id: str) -> None:
    token_path(accounts_dir, account_id).unlink(missing_ok=True)
