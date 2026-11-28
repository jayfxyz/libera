"""Network errors are shown without Audible's signed URLs, and logged without their query strings."""

import logging

import httpx
import pytest

from app import http_errors
from app.audible_api.content import DownloadInfo
from app.jobs import download
from app.jobs.download import DownloadFailed, Target

SIGNED = "https://dcdn.audible.com/x/book.aaxc?Expires=1&Signature=SECRET123&Key-Pair-Id=K"


def status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", SIGNED)
    response = httpx.Response(code, request=request)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("not an error status")


@pytest.mark.parametrize("error, sentence", [
    (status_error(403), "Audible's server refused the download (HTTP 403)."),
    (status_error(404), "Audible's server couldn't find the file (HTTP 404)."),
    (status_error(503), "Audible's server had a problem (HTTP 503)."),
    (httpx.ReadTimeout("timed out"), "The connection to Audible timed out."),
    (httpx.ConnectError("refused"), "Couldn't connect to Audible. Check the internet connection."),
    (httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
     "The connection to Audible dropped before the download finished."),
])
def test_errors_become_one_sentence_without_the_url(error, sentence):
    assert http_errors.describe(error) == sentence


def test_logs_keep_the_detail_but_not_the_signature():
    logged = http_errors.for_log(status_error(403))
    assert "403" in logged and "dcdn.audible.com/x/book.aaxc" in logged
    assert "SECRET123" not in logged and "Signature" not in logged


async def test_a_failed_download_stores_a_sentence_and_logs_no_signature(tmp_path, monkeypatch, caplog):
    async def refused(url, dest, on_progress):
        raise status_error(403)

    monkeypatch.setattr(download, "_stream_download", refused)
    target = Target(download_id="d1", audible_account_id="a", audible_id="B0X", title="T", format="m4b",
                    split_chapters=False, path=str(tmp_path), base_name="T", has_pdf=None)
    with caplog.at_level(logging.WARNING), pytest.raises(DownloadFailed) as failed:
        await download._download_encrypted(DownloadInfo(SIGNED, "LC_64", "aaxc"), target, str(tmp_path),
                                           lambda *a, **k: None)
    assert str(failed.value) == "Audible's server refused the download (HTTP 403)."
    assert failed.value.retry
    assert "SECRET123" not in caplog.text and "403" in caplog.text
