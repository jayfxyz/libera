from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
import storage

router = APIRouter()
log = logging.getLogger(__name__)


class DownloadInfoResponse(BaseModel):
    download_url: str
    activation_bytes: str
    codec: str


@router.get("/{account_id}/{asin}", response_model=DownloadInfoResponse)
async def get_download_info(account_id: str, asin: str, quality: str = "best"):
    from audible_cli.models import LibraryItem

    try:
        client = storage.load_client(account_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")

    async with client as c:
        # Fetch library item with the fields LibraryItem needs
        try:
            resp = await c.get(
                f"1.0/library/{asin}",
                response_groups="product_attrs,customer_rights",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Library fetch failed: {e}")

        item_data = resp.get("item", {})
        item = LibraryItem(data=item_data, api_client=c, parent=None, response_groups="product_attrs,customer_rights")

        try:
            url, codec = await item.get_aax_url_old(quality)
            download_url = str(url)
        except Exception as e:
            log.error("get_aax_url_old failed: %s", e, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Get download URL failed: {e}")

        # Get activation bytes
        activation_bytes = ""
        try:
            raw = c.auth.get_activation_bytes(extract=True)
            log.info("activation_bytes raw type=%s value=%r", type(raw).__name__, raw)
            # May return bytes or str; ffmpeg needs a lowercase hex string
            if isinstance(raw, bytes):
                activation_bytes = raw.hex()
            elif isinstance(raw, str):
                activation_bytes = raw
            log.info("activation_bytes final=%r len=%d", activation_bytes, len(activation_bytes))
        except Exception as e:
            log.warning("get_activation_bytes failed: %s", e)

    return DownloadInfoResponse(
        download_url=download_url,
        activation_bytes=activation_bytes,
        codec=codec,
    )
