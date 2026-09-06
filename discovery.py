"""Stufe 1: breite Suche ueber Jobaggregatoren.

Zweck: Firmen finden, die auf keiner vorgegebenen Liste stehen.
Quellen sind ausschliesslich offizielle, dafuer vorgesehene APIs.

Bewusst NICHT enthalten:

- Bundesagentur fuer Arbeit. Die Behoerde hat der automatisierten Nutzung ihrer
  Schnittstelle widersprochen und Anti-Bot-Massnahmen eingebaut.
- Jooble. Am 18.08.2026 ersatzlos entfernt: die API hat in 16 aufeinander
  folgenden Laeufen auf jede einzelne der 28 Anfragen pro Lauf mit 403
  geantwortet - insgesamt 448 Fehlschlaege, null Ergebnisse. Eine Quelle, die
  nur Fehlerzeilen produziert, kostet Laufzeit und verdeckt echte Probleme.

Siehe README, Abschnitt 'Quellen'.
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
                    source=f"Adzuna {country.upper()}",
                )
            )
        return jobs


SOURCES = [AdzunaSource]


def run_discovery(cfg: dict) -> tuple[list[Job], list[str], list[dict]]:
    """Fragt alle verfuegbaren Quellen ab.

    Gibt zurueck: (Jobs, Fehlermeldungen, Quellenstatus).

    Der Quellenstatus geht in die Ampel im Dashboard. Er unterscheidet
    ausdruecklich zwischen 'Fehler' und 'lief durch, lieferte aber nichts' -
    die stille Null ist der gefaehrlichere Fall, weil sie wie Erfolg aussieht.
    """
    if not cfg.get("enabled", True):
        return [], [], []

    countries = cfg.get("countries", ["de"])
    queries = cfg.get("queries", [])
    max_pages = int(cfg.get("max_pages", 2))
    per_page = int(cfg.get("results_per_page", 50))

    sources = [S(cfg) for S in SOURCES]
    active = [s for s in sources if s.available]
    errors: list[str] = []
    health: list[dict] = []

    for s in sources:
        if not s.available:
            msg = (f"{s.name}: kein API-Key gesetzt - Quelle uebersprungen "
                   f"(siehe README, Abschnitt 'API-Keys hinterlegen')")
            errors.append(msg)
            health.append({"source": s.name, "kind": "aggregator",
                           "count": 0, "error": "kein API-Key"})

    if not active:
        return [], errors, health

    jobs: list[Job] = []
    seen: set[str] = set()

    for src in active:
        before_src = len(jobs)
        last_error = ""
        for country in countries:
            for query in queries:
                for page in range(1, max_pages + 1):
                    try:
                        batch = src.search(country, query, page, per_page)
                    except Exception as e:
                        last_error = f"{type(e).__name__}: {str(e)[:120]}"
                        errors.append(f"{src.name}/{country}/'{query}': {last_error}")
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

        got = len(jobs) - before_src
        health.append({"source": src.name, "kind": "aggregator",
                       "count": got, "error": last_error})
        log.info("%-10s %d Rohtreffer gesammelt", src.name, got)

    return jobs, errors, health
