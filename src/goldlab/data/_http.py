"""One HTTPS opener for every external fetch.

Exists because cftc.gov failed certificate verification against the system trust
store while fred.stlouisfed.org succeeded. The fix is a proper CA bundle, not
disabling verification — an unverified download of the data a strategy will be
built on is a supply chain anyone can edit.
"""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request

import certifi

_UA = "goldlab/1.0 (research; contact via repo owner)"


def _context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def get(url: str, timeout: float = 120.0, attempts: int = 4) -> bytes:
    """Fetch a URL with verified TLS, retrying transient failures.

    Public data endpoints time out intermittently under load. Retrying with a
    growing pause is the difference between a research script that reports "no
    data" and one that reports the data — and "no data" quietly becomes "skip this
    factor", which is a silent change to what gets tested.
    """
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
                return response.read()
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"failed after {attempts} attempts: {url}") from last


def get_text(url: str, timeout: float = 120.0, attempts: int = 4, encoding: str = "utf-8") -> str:
    return get(url, timeout, attempts).decode(encoding, "replace")
