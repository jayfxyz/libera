"""Audible login through Amazon's "maplanding" page.

Amazon only accepts https://www.amazon.{domain}/ap/maplanding as the return
URL for the Audible iOS client, so the browser can't be redirected back here:

1. ``start_login`` builds the Amazon login URL and remembers the PKCE verifier.
2. The user logs in; Amazon lands on maplanding (which shows "Not Found").
3. The user pastes that URL; ``complete_login`` extracts the authorization
   code, registers a device and saves the tokens.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from typing import Any

import audible
import audible.auth as audible_auth
import httpx
from audible.auth import register_
from audible.localization import Locale
from audible.login import build_device_serial, build_oauth_url, create_code_verifier, extract_code_from_url
from audible.register import APP_VERSION, OS_VERSION

from . import storage

log = logging.getLogger(__name__)

# The iOS app identity the audible library registers devices as. Since September
# 2026 Audible refuses download licenses ("CustomerThrottled") to devices
# registered with the old 3.56.2 profile, so every request that identifies the
# app must use the same, current version as the registration itself.
APP_USER_AGENT = f"Audible/{APP_VERSION} iOS/{OS_VERSION} iPhone"

# register_() posts with no headers, which CloudFront blocks; send the iOS app's.
_REGISTER_HEADERS = {
    "User-Agent": APP_USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en-US",
}
_register_lock = threading.Lock()


class LoginError(Exception):
    """A login step failed; ``status`` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class _PendingLogin:
    name: str
    locale: str
    domain: str
    code_verifier: bytes
    serial: str


@dataclass
class LoginResult:
    """A completed login, not saved yet: the caller picks its token file (see save)."""
    user_id: str  # Amazon's id for the person; the same in every region
    email: str
    name: str
    locale: str
    auth: Any = None  # audible.Authenticator holding the new device's tokens


class LoginFlow:
    def __init__(self, accounts_dir: str):
        self.accounts_dir = accounts_dir
        self._pending: dict[str, _PendingLogin] = {}
        self._lock = threading.Lock()

    def start(self, locale: str, name: str) -> tuple[str, str]:
        """Return (Amazon login URL, state token)."""
        try:
            loc = Locale(locale)
        except Exception:
            raise LoginError(f"Unknown locale: {locale!r}")

        code_verifier = create_code_verifier()
        url, serial = build_oauth_url(
            country_code=loc.country_code,
            domain=loc.domain,
            market_place_id=loc.market_place_id,
            code_verifier=code_verifier,
            serial=build_device_serial(),
        )
        state = secrets.token_urlsafe(16)
        with self._lock:
            self._pending[state] = _PendingLogin(name, locale, loc.domain, code_verifier, serial)
        return url, state

    def complete(self, state: str, response_url: str) -> LoginResult:
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None:
            raise LoginError("unknown auth state — try starting login again")

        try:
            code = extract_code_from_url(httpx.URL(response_url))
        except (KeyError, IndexError, ValueError):
            raise LoginError(
                "No authorization code found in the URL — make sure you copied the full "
                "address bar URL after login."
            )

        try:
            registration = _register(code, pending)
        except Exception as e:
            log.error("device registration failed: %s", e, exc_info=True)
            raise LoginError(f"Device registration failed: {e}", status=502)

        auth = audible.Authenticator()
        auth.locale = pending.locale
        auth._update_attrs(**registration)

        info = auth.customer_info or {}
        # Amazon doesn't always return an email (UK returns user_id instead).
        email = info.get("email") or info.get("user_id", "")
        user_id = info.get("user_id") or email.replace("@", "_at_").replace(".", "_")
        return LoginResult(user_id=user_id, email=email, name=pending.name, locale=pending.locale, auth=auth)

    def save(self, token_key: str, auth: Any) -> None:
        """Save a login's tokens as token_key, replacing the login saved there before:
        that one's device is deregistered from Amazon. Only the same login in the same
        region shares a key, so other regions' devices are left alone."""
        previous = _load_previous(self.accounts_dir, token_key)
        storage.save_auth(self.accounts_dir, token_key, auth)
        if previous is not None:
            _deregister(previous, token_key)

    def remove(self, token_key: str) -> None:
        """Delete the saved tokens for token_key and deregister its device (best-effort)."""
        previous = _load_previous(self.accounts_dir, token_key)
        storage.delete_auth(self.accounts_dir, token_key)
        if previous is not None:
            _deregister(previous, token_key)


def _load_previous(accounts_dir: str, account_id: str):
    try:
        return storage.load_auth(accounts_dir, account_id)
    except Exception as e:  # unreadable old file: nothing to clean up
        log.warning("could not read the previous login for %s: %s", account_id, e)
        return None


def _deregister(previous, account_id: str) -> None:
    """Remove this app's previous device registration for the account from
    Amazon, so logging in again doesn't leave another "Audible for iPhone"
    behind each time. Best-effort: the new login is already saved."""
    try:
        previous.deregister_device()
        log.info("deregistered the previous device for %s", account_id)
    except Exception as e:
        log.warning("could not deregister the previous device for %s: %s", account_id, e)


def _register(code: str, pending: _PendingLogin) -> dict:
    original_post = audible_auth.httpx.post

    def post_with_headers(url, **kwargs):
        kwargs["headers"] = {**_REGISTER_HEADERS, **(kwargs.get("headers") or {})}
        return original_post(url, **kwargs)

    # The patch is module-global, so registrations run one at a time.
    with _register_lock:
        audible_auth.httpx.post = post_with_headers
        try:
            return register_(
                authorization_code=code,
                code_verifier=pending.code_verifier,
                domain=pending.domain,
                serial=pending.serial,
            )
        finally:
            audible_auth.httpx.post = original_post
