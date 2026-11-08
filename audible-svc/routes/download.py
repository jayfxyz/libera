from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import logging
import storage

router = APIRouter()
log = logging.getLogger(__name__)


class DownloadInfoResponse(BaseModel):
    download_url: str
    codec: str
    format: str        # "aax" or "aaxc"
    activation_bytes: str = ""  # AAX only
    key: str = ""               # AAXC only
    iv: str = ""                # AAXC only
    # Why Audible refused the AAXC license, when the download fell back to AAX.
    # The AAX fallback only works for older titles, so this is usually the real
    # reason a download fails.
    license_denied: str = ""


class _LicenseCapture:
    """Proxy for an audible client that keeps the last license response.

    audible-cli raises a bare LicenseDenied and drops Audible's denial reasons;
    capturing the response lets us tell the user why (e.g. throttling).
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


def describe_license_denial(license_response) -> str:
    """Plain-language reason for a denied license, or "" if it wasn't denied.

    Audible lists every route it tried (membership, ownership, client, ...).
    For a purchased title the ownership check is the one that matters.
    """
    cl = (license_response or {}).get("content_license") or {}
    if cl.get("status_code") != "Denied":
        return ""
    reasons = cl.get("license_denial_reasons") or []
    if any(r.get("rejectionReason") == "CustomerThrottled" for r in reasons):
        return ("Audible is temporarily refusing download licenses for this account "
                "(throttled after heavy downloading). It usually clears within a day or two.")
    ownership = [r.get("message", "") for r in reasons if r.get("validationType") == "Ownership"]
    detail = "; ".join(m for m in ownership if m) or cl.get("message") or "no reason given"
    return f"Audible denied the download license: {detail}"


@router.get("/{account_id}/{asin}", response_model=DownloadInfoResponse)
async def get_download_info(account_id: str, asin: str, quality: str = "best"):
    from audible_cli.models import LibraryItem

    try:
        client = storage.load_client(account_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")

    async with client as c:
        try:
            resp = await c.get(
                f"1.0/library/{asin}",
                response_groups="product_attrs,customer_rights",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Library fetch failed: {e}")

        item_data = resp.get("item", {})
        capture = _LicenseCapture(c)
        item = LibraryItem(data=item_data, api_client=capture, parent=None, response_groups="product_attrs,customer_rights")

        # Try AAXC first — its offline_url is a pre-signed URL that works without
        # additional auth headers. AAX URLs require the audible session cookies.
        try:
            url, codec, lr = await item.get_aaxc_url(quality)
            voucher = lr.get("content_license", {}).get("license_response", {})
            if not isinstance(voucher, dict):
                raise ValueError("Failed to decrypt AAXC voucher")

            return DownloadInfoResponse(
                download_url=str(url),
                codec=codec,
                format="aaxc",
                key=voucher.get("key", ""),
                iv=voucher.get("iv", ""),
            )
        except Exception as aaxc_err:
            log.info("AAXC not available for %s (%s), trying AAX", asin, aaxc_err)
        denied = describe_license_denial(capture.license_response)
        if denied:
            log.warning("AAXC license denied for %s: %s", asin, denied)

        # Fall back to AAX
        try:
            url, codec = await item.get_aax_url_old(quality)
        except Exception as e:
            log.error("get_aax_url_old failed for %s: %s", asin, e, exc_info=True)
            raise HTTPException(status_code=502, detail=denied or f"Get download URL failed: {e}")

        return DownloadInfoResponse(
            download_url=str(url),
            codec=codec,
            format="aax",
            license_denied=denied,
            activation_bytes=_get_activation_bytes(c),
        )


@router.get("/{account_id}/{asin}/chapters")
async def get_chapters(account_id: str, asin: str, quality: str = "best"):
    """Return Audible's chapter outline (``chapter_info``) for a title.

    Uses the content metadata endpoint rather than the license response: the
    license sometimes carries incorrect chapters, while this endpoint is
    accurate (same approach as Libation). Chapters are requested as a tree so
    parts/sections keep their nested chapters.
    """
    try:
        client = storage.load_client(account_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")

    async with client as c:
        try:
            resp = await c.get(
                f"content/{asin}/metadata",
                params={
                    "response_groups": "content_reference,chapter_info",
                    "quality": "High" if quality in ("best", "high") else "Normal",
                    "drm_type": "Adrm",
                    "chapter_titles_type": "Tree",
                },
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Content metadata fetch failed: {e}")

    chapter_info = (resp.get("content_metadata") or {}).get("chapter_info")
    if not chapter_info or not chapter_info.get("chapters"):
        raise HTTPException(status_code=404, detail="No chapter info available for this title")
    return chapter_info


@router.get("/{account_id}/{asin}/pdf")
async def get_pdf(account_id: str, asin: str):
    from audible_cli.models import LibraryItem

    try:
        client = storage.load_client(account_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")

    async with client as c:
        try:
            resp = await c.get(f"1.0/library/{asin}", response_groups="pdf_url")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Library fetch failed: {e}")

        item = LibraryItem(data=resp, api_client=c, parent=None, response_groups="pdf_url")

        try:
            pdf_url = item.get_pdf_url()
        except Exception:
            pdf_url = None

        if pdf_url is None:
            raise HTTPException(status_code=404, detail="No PDF available for this title")

        pdf_resp = await c.session.get(pdf_url, follow_redirects=True)
        if pdf_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"PDF fetch failed: HTTP {pdf_resp.status_code}")

        content_type = pdf_resp.headers.get("content-type", "application/pdf")
        return Response(
            content=pdf_resp.content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{asin}.pdf"'},
        )


def _get_activation_bytes(client) -> str:
    try:
        raw = client.auth.get_activation_bytes(extract=True)
        if isinstance(raw, bytes):
            return raw.hex()
        return raw or ""
    except Exception as e:
        log.warning("get_activation_bytes failed: %s", e)
        return ""
