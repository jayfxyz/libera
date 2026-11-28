"""Network errors, worded for people and safe to show or log.

httpx puts the full request URL in its messages, and Audible's download and PDF URLs are signed: the query
string is a credential. So the message shown in the app (stored with the download and sent to the browser) is
a short sentence without the URL, and what goes to the log has the query string cut off.
"""

from __future__ import annotations

import re

import httpx

_QUERY = re.compile(r"(https?://[^\s'\"?]+)\?[^\s'\"]*")


def redact_urls(text: str) -> str:
    """text with every URL's query string replaced by "?…"."""
    return _QUERY.sub(r"\1?…", text)


def describe(e: httpx.HTTPError) -> str:
    """One sentence for the user about what went wrong talking to Audible's servers."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return f"Audible's server refused the download (HTTP {code})."
        if code == 404:
            return "Audible's server couldn't find the file (HTTP 404)."
        if code == 429:
            return "Audible's server asked to slow down (HTTP 429)."
        if code >= 500:
            return f"Audible's server had a problem (HTTP {code})."
        return f"Audible's server answered HTTP {code}."
    if isinstance(e, httpx.TimeoutException):
        return "The connection to Audible timed out."
    if isinstance(e, httpx.ConnectError):
        return "Couldn't connect to Audible. Check the internet connection."
    if isinstance(e, (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)):
        return "The connection to Audible dropped before the download finished."
    return "A network error interrupted the download."


def for_log(e: BaseException) -> str:
    """The full error for the log, with URL query strings cut off."""
    return redact_urls(f"{type(e).__name__}: {e}")
