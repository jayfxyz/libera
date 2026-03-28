"""
Audible browser-based OAuth using Amazon's maplanding flow.

Amazon only allows openid.return_to = https://www.amazon.{domain}/ap/maplanding
for the Audible iOS client ID — custom redirect URIs are rejected.

Flow:
  1. POST /auth/register  → returns the Amazon login URL + a state token
  2. User opens the URL, logs in at Amazon
  3. Amazon redirects to https://www.amazon.{domain}/ap/maplanding?openid.oa2.authorization_code=...
     (This page shows "Not Found" — that's expected)
  4. User copies the full URL from the browser address bar
  5. POST /auth/callback { state, response_url }  → extracts the code, registers device, saves tokens
"""

import logging
import secrets

import audible
from audible.auth import register_
from audible.localization import Locale
from audible.login import (
    build_oauth_url,
    build_device_serial,
    create_code_verifier,
    extract_code_from_url,
)
import httpx
import storage
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()

# Pending sessions: state → {code_verifier, serial, domain, locale_str}
_pending: dict[str, dict] = {}


class RegisterRequest(BaseModel):
    locale: str = "us"


class RegisterResponse(BaseModel):
    auth_url: str
    state: str


class CallbackRequest(BaseModel):
    state: str
    response_url: str  # The full maplanding URL the user copies from their browser


class CallbackResponse(BaseModel):
    account_id: str
    email: str
    activation_bytes: str


@router.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest):
    try:
        locale = Locale(req.locale)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Unknown locale: {req.locale!r}")

    code_verifier = create_code_verifier()
    serial = build_device_serial()

    oauth_url, serial = build_oauth_url(
        country_code=locale.country_code,
        domain=locale.domain,
        market_place_id=locale.market_place_id,
        code_verifier=code_verifier,
        serial=serial,
    )

    state = secrets.token_urlsafe(16)
    _pending[state] = {
        "code_verifier": code_verifier,
        "serial": serial,
        "locale_str": req.locale,
        "domain": locale.domain,
    }

    return RegisterResponse(auth_url=oauth_url, state=state)


@router.post("/callback", response_model=CallbackResponse)
def callback(req: CallbackRequest):
    session = _pending.pop(req.state, None)
    if session is None:
        raise HTTPException(status_code=400, detail="Unknown or expired auth state")

    try:
        url = httpx.URL(req.response_url)
        authorization_code = extract_code_from_url(url)
        log.info("Extracted authorization_code type=%s value=%r", type(authorization_code).__name__, authorization_code[:20] if authorization_code else None)
    except (KeyError, IndexError) as e:
        log.error("Failed to extract code from URL %r: %s", req.response_url, e)
        raise HTTPException(
            status_code=400,
            detail="No authorization code found in the URL — make sure you copied the full address bar URL after login.",
        )

    cv = session["code_verifier"]
    log.info("code_verifier type=%s len=%s", type(cv).__name__, len(cv) if cv else None)
    log.info("serial type=%s value=%r", type(session['serial']).__name__, session['serial'])
    log.info("domain=%r", session['domain'])

    try:
        # register_() uses plain httpx.post with no headers, which CloudFront blocks.
        # Patch it temporarily to add iOS Audible app headers.
        import audible.auth as _audible_auth
        _orig_post = _audible_auth.httpx.post

        def _patched_post(url, **kwargs):
            hdrs = kwargs.pop("headers", {})
            hdrs.setdefault("User-Agent", "Audible/3.56.2 iOS/15.0.0 iPhone")
            hdrs.setdefault("Accept", "application/json")
            hdrs.setdefault("Accept-Language", "en-US")
            kwargs["headers"] = hdrs
            return _orig_post(url, **kwargs)

        _audible_auth.httpx.post = _patched_post
        try:
            register_result = register_(
                authorization_code=authorization_code,
                code_verifier=cv,
                domain=session["domain"],
                serial=session["serial"],
            )
        finally:
            _audible_auth.httpx.post = _orig_post
    except Exception as e:
        log.error("register_() failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Device registration failed: {e}")

    auth = audible.Authenticator()
    auth.locale = session["locale_str"]
    auth._update_attrs(**register_result)

    ci = auth.customer_info or {}
    # Amazon doesn't always return email (e.g. UK locale returns user_id instead)
    email = ci.get("email") or ci.get("user_id", "")
    name = ci.get("name") or ci.get("given_name", "")
    # Use user_id as the stable file-storage key if available
    account_id = ci.get("user_id") or email.replace("@", "_at_").replace(".", "_")
    storage.save_auth(account_id, auth)

    return CallbackResponse(
        account_id=account_id,
        email=email,
        activation_bytes="",
    )
