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
        item = LibraryItem(data=item_data, api_client=c, parent=None, response_groups="product_attrs,customer_rights")

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

        # Fall back to AAX
        try:
            url, codec = await item.get_aax_url_old(quality)
        except Exception as e:
            log.error("get_aax_url_old failed for %s: %s", asin, e, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Get download URL failed: {e}")

        return DownloadInfoResponse(
            download_url=str(url),
            codec=codec,
            format="aax",
            activation_bytes=_get_activation_bytes(c),
        )


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
