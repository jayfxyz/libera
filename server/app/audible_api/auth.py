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

import audible
import audible.auth as audible_auth
import httpx
from audible.auth import register_
from audible.localization import Locale
from audible.login import build_device_serial, build_oauth_url, create_code_verifier, extract_code_from_url

from . import storage

log = logging.getLogger(__name__)

# register_() posts with no headers, which CloudFront blocks; send the iOS app's.
_REGISTER_HEADERS = {
    "User-Agent": "Audible/3.56.2 iOS/15.0.0 iPhone",
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
    account_id: str  # stable key for the token file (Amazon user_id)
    email: str
    name: str
    locale: str


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
        account_id = info.get("user_id") or email.replace("@", "_at_").replace(".", "_")
        storage.save_auth(self.accounts_dir, account_id, auth)
        return LoginResult(account_id=account_id, email=email, name=pending.name, locale=pending.locale)


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
