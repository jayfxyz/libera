"""Download URLs and decryption keys, chapter outlines and companion PDFs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


class ContentError(Exception):
    """Audible couldn't provide what was asked; the message is user-facing."""


@dataclass
class DownloadInfo:
    download_url: str
    codec: str
    format: str  # "aaxc" or "aax"
    activation_bytes: str = ""  # AAX only
    key: str = ""  # AAXC only
    iv: str = ""  # AAXC only
    # Why Audible refused the AAXC license when we fell back to AAX. The AAX
    # fallback only works for older titles, so this is usually the real reason
    # a download fails.
    license_denied: str = ""
    cover_url: str = ""  # largest cover Audible offers; "" if none


class _LicenseCapture:
    """Client proxy that keeps the last license response.

    audible-cli raises a bare LicenseDenied and drops Audible's denial reasons;
    keeping the response lets us tell the user why (e.g. throttling).
    """

    def __init__(self, client):
        self._client = client
        self.license_response = None

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def post(self, path, *args, **kwargs):
        resp = await self._client.post(path, *args, **kwargs)
        if str(path).endswith("/licenserequest"):
            self.license_response = resp
        return resp


def describe_license_denial(license_response: dict | None) -> str:
    """Plain-language reason for a denied license, or "" if it wasn't denied.

    Audible lists every route it checked (membership, ownership, client, ...);
    for a purchased title the ownership check is the one that matters.
    """
    cl = (license_response or {}).get("content_license") or {}
    if cl.get("status_code") != "Denied":
        return ""
    reasons = cl.get("license_denial_reasons") or []
    if any(r.get("rejectionReason") == "CustomerThrottled" for r in reasons):
        # Since September 2026 Audible also says this to devices registered with
        # an outdated app profile, regardless of how much was downloaded.
        return (
            "Audible refused the download license (\"throttled\"). This usually means the "
            "account's device registration is outdated: remove the account under Accounts and "
            "add it again (your library and downloads are kept). If it persists after that, "
            "Audible may really be rate-limiting the account; that clears within a day or two."
        )
    ownership = [r.get("message", "") for r in reasons if r.get("validationType") == "Ownership"]
    detail = "; ".join(m for m in ownership if m) or cl.get("message") or "no reason given"
    return f"Audible denied the download license: {detail}"


# Largest first; the library's default is only 500 px.
COVER_SIZES = ("3200", "2400", "1215", "500")


def largest_cover(item: dict[str, Any]) -> str:
    images = item.get("product_images") or {}
    return next((images[s] for s in COVER_SIZES if images.get(s)), "")


async def get_download_info(client, asin: str, quality: str = "best") -> DownloadInfo:
    from audible_cli.models import LibraryItem

    async with client as c:
        groups = "product_attrs,customer_rights,media"
        try:
            resp = await c.get(f"1.0/library/{asin}", response_groups=groups, image_sizes=",".join(COVER_SIZES))
        except Exception as e:
            raise ContentError(f"Library fetch failed: {e}")

        item_data = resp.get("item", {})
        cover = largest_cover(item_data)
        capture = _LicenseCapture(c)
        item = LibraryItem(data=item_data, api_client=capture, parent=None, response_groups=groups)

        # AAXC first: its offline_url is pre-signed and its voucher carries the key.
        try:
            url, codec, lr = await item.get_aaxc_url(quality)
            voucher = (lr.get("content_license") or {}).get("license_response")
            if not isinstance(voucher, dict):
                raise ValueError("Failed to decrypt AAXC voucher")
            return DownloadInfo(str(url), codec, "aaxc", key=voucher.get("key", ""), iv=voucher.get("iv", ""),
                                cover_url=cover)
        except Exception as e:
            log.info("AAXC not available for %s (%s), trying AAX", asin, e)

        denied = describe_license_denial(capture.license_response)
        if denied:
            log.warning("AAXC license denied for %s: %s", asin, denied)

        try:
            url, codec = await item.get_aax_url_old(quality)
        except Exception as e:
            log.error("AAX fallback failed for %s: %s", asin, e)
            raise ContentError(denied or f"Get download URL failed: {e}")

        return DownloadInfo(str(url), codec, "aax", activation_bytes=_activation_bytes(c), license_denied=denied,
                            cover_url=cover)


def _activation_bytes(client) -> str:
    try:
        raw = client.auth.get_activation_bytes(extract=True)
    except Exception as e:
        log.warning("get_activation_bytes failed: %s", e)
        return ""
    return raw.hex() if isinstance(raw, bytes) else (raw or "")


async def get_chapter_info(client, asin: str, quality: str = "best") -> dict[str, Any]:
    """Audible's chapter outline for a title, as a tree (parts keep their chapters).

    Uses the content metadata endpoint rather than the license response: the
    license sometimes carries incorrect chapters, while this one is accurate
    (same approach as Libation).
    """
    async with client as c:
        resp = await c.get(
            f"content/{asin}/metadata",
            params={
                "response_groups": "content_reference,chapter_info",
                "quality": "High" if quality in ("best", "high") else "Normal",
                "drm_type": "Adrm",
                "chapter_titles_type": "Tree",
            },
        )
    info = (resp.get("content_metadata") or {}).get("chapter_info")
    if not info or not info.get("chapters"):
        raise ContentError("No chapter info available for this title")
    return info


async def get_pdf(client, asin: str) -> bytes | None:
    """The title's companion PDF, or None if it has none."""
    from audible_cli.models import LibraryItem

    async with client as c:
        try:
            resp = await c.get(f"1.0/library/{asin}", response_groups="pdf_url")
        except Exception as e:  # e.g. 404 when the login is for another region's store
            raise ContentError(f"Audible couldn't look up this book: {e}")
        item = LibraryItem(data=resp.get("item", resp), api_client=c, parent=None, response_groups="pdf_url")
        try:
            pdf_url = item.get_pdf_url()
        except Exception:
            pdf_url = None
        if not pdf_url:
            return None
        r = await c.session.get(pdf_url, follow_redirects=True)
        if r.status_code != 200:
            raise ContentError(f"PDF fetch failed: HTTP {r.status_code}")
        return r.content
