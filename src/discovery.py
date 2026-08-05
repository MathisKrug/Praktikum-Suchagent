"""Stufe 1: breite Suche ueber Jobaggregatoren.

Zweck: Firmen finden, die auf keiner vorgegebenen Liste stehen.
Quellen sind ausschliesslich offizielle, dafuer vorgesehene APIs.

Bewusst NICHT enthalten: Bundesagentur fuer Arbeit. Die Behoerde hat der
automatisierten Nutzung ihrer Schnittstelle widersprochen und Anti-Bot-Massnahmen
eingebaut. Siehe README, Abschnitt 'Quellen'.
"""

from __future__ import annotations

import os
import time
import logging
import requests

from .models import Job

log = logging.getLogger(__name__)

TIMEOUT = 25
DELAY = 1.0


class DiscoveryError(Exception):
    pass


class AdzunaSource:
    """https://developer.adzuna.com - kostenloser Key, DE und AT."""

    name = "adzuna"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
        self.app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.app_id and self.app_key)

    def search(self, country: str, query: str, page: int, per_page: int) -> list[Job]:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": per_page,
            "what": query,
            "content-type": "application/json",
        }
        time.sleep(DELAY)
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 429:
            raise DiscoveryError("adzuna: Rate-Limit erreicht")
        r.raise_for_status()
        data = r.json()

        jobs = []
        for it in data.get("results", []):
            company = ((it.get("company") or {}).get("display_name") or "").strip()
            loc = ((it.get("location") or {}).get("display_name") or "").strip()
            jobs.append(
                Job(
                    company=company or "unbekannt",
                    sector="entdeckt",
                    title=(it.get("title") or "").strip(),
                    url=it.get("redirect_url") or "",
                    location=loc,
                    description=(it.get("description") or "")[:3000],
                    posted=(it.get("created") or "")[:10],
                )
            )
        return jobs


class JoobleSource:
    """https://jooble.org/api/about - kostenloser Key."""

    name = "jooble"

    COUNTRY_HOST = {"de": "de", "at": "at"}

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.key = os.environ.get("JOOBLE_API_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.key)

    def search(self, country: str, query: str, page: int, per_page: int) -> list[Job]:
        host = self.COUNTRY_HOST.get(country, "de")
        url = f"https://{host}.jooble.org/api/{self.key}"
        payload = {"keywords": query, "page": str(page)}

        time.sleep(DELAY)
        r = requests.post(url, json=payload, timeout=TIMEOUT,
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()

        jobs = []
        for it in data.get("jobs", [])[:per_page]:
            jobs.append(
                Job(
                    company=(it.get("company") or "").strip() or "unbekannt",
                    sector="entdeckt",
                    title=(it.get("title") or "").strip(),
                    url=it.get("link") or "",
                    location=(it.get("location") or "").strip(),
                    description=(it.get("snippet") or "")[:3000],
                    posted=(it.get("updated") or "")[:10],
                )
            )
        return jobs


SOURCES = [AdzunaSource, JoobleSource]


def run_discovery(cfg: dict) -> tuple[list[Job], list[str]]:
    """Fragt alle verfuegbaren Quellen ab. Gibt (Jobs, Fehlermeldungen) zurueck."""
    if not cfg.get("enabled", True):
        return [], []

    countries = cfg.get("countries", ["de"])
    queries = cfg.get("queries", [])
    max_pages = int(cfg.get("max_pages", 2))
    per_page = int(cfg.get("results_per_page", 50))

    sources = [S(cfg) for S in SOURCES]
    active = [s for s in sources if s.available]
    errors: list[str] = []

    for s in sources:
        if not s.available:
            errors.append(
                f"{s.name}: kein API-Key gesetzt - Quelle uebersprungen "
                f"(siehe README, Abschnitt 'API-Keys hinterlegen')"
            )

    if not active:
        return [], errors

    jobs: list[Job] = []
    seen: set[str] = set()

    for src in active:
        for country in countries:
            for query in queries:
                for page in range(1, max_pages + 1):
                    try:
                        batch = src.search(country, query, page, per_page)
                    except Exception as e:
                        errors.append(f"{src.name}/{country}/'{query}': {type(e).__name__}: {str(e)[:120]}")
                        break

                    if not batch:
                        break

                    fresh = 0
                    for j in batch:
                        if j.uid in seen:
                            continue
                        seen.add(j.uid)
                        jobs.append(j)
                        fresh += 1

                    log.debug("%s %s '%s' S.%d: %d neu", src.name, country, query, page, fresh)

                    if len(batch) < per_page:
                        break

        log.info("%-10s %d Rohtreffer gesammelt", src.name, len(jobs))

    return jobs, errors
