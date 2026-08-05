"""Gemeinsame Basis fuer alle Adapter."""

from __future__ import annotations

import time
import logging
import requests
from urllib.parse import urljoin

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Hoeflichkeit gegenueber den Servern. Nicht runtersetzen.
DELAY_SECONDS = 1.5
TIMEOUT = 25


class AdapterError(Exception):
    pass


class Adapter:
    """Basisklasse. Jeder Adapter implementiert fetch() und gibt Job-Objekte zurueck."""

    name = "base"

    def __init__(self, company: dict, search_terms: list[str]):
        self.company = company
        self.key = company["key"]
        self.label = company["name"]
        self.sector = company.get("sector", "")
        self.cfg = company.get("config", {}) or {}
        self.search_terms = search_terms
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "de,en;q=0.8"})

    # ---- HTTP-Helfer ----

    def get(self, url: str, **kw) -> requests.Response:
        time.sleep(DELAY_SECONDS)
        log.debug("GET %s", url)
        r = self.session.get(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r

    def post(self, url: str, **kw) -> requests.Response:
        time.sleep(DELAY_SECONDS)
        log.debug("POST %s", url)
        r = self.session.post(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return r

    def abs_url(self, base: str, href: str) -> str:
        return urljoin(base, href)

    # ---- Schnittstelle ----

    def fetch(self) -> list:
        raise NotImplementedError
