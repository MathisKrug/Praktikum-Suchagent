"""Zweiter Durchgang: laedt die Stellenseite der besten Treffer nach.

Hintergrund: Die Kurztexte der Aggregatoren enthalten fast nie Laufzeit oder
Startdatum. Im ersten Lauf lagen deshalb praktisch alle Scores zwischen 53 und
63 - nicht weil die Stellen nicht passen, sondern weil die entscheidenden
Angaben fehlten. Ohne Laufzeit kann man aber nicht entscheiden, wo sich eine
Bewerbung lohnt.

Deshalb: fuer die N besten Treffer die eigentliche Anzeige holen und Laufzeit
und Startdatum daraus lesen. Bewusst begrenzt, damit der Lauf nicht ausufert.
"""

from __future__ import annotations

import time
import logging
import requests
from bs4 import BeautifulSoup

from .models import Job
from .score import Scorer

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 15
DELAY = 1.2


def _text_of(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)[:12000]


def enrich(jobs: list[Job], scorer: Scorer, limit: int = 40,
           only_missing: bool = True) -> tuple[int, int]:
    """Laedt Detailseiten nach und bewertet betroffene Jobs neu.

    Gibt (versucht, verbessert) zurueck.
    """
    # Kandidaten: hoch bewertet, aber ohne Laufzeit oder ohne Startdatum
    cands = [j for j in jobs
             if not only_missing or j.duration_months is None or j.start_date is None]
    cands.sort(key=lambda j: -j.score)
    cands = [j for j in cands if j.url.startswith("http")][:limit]

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "de,en;q=0.8"})

    tried = improved = 0
    for j in cands:
        tried += 1
        try:
            time.sleep(DELAY)
            r = session.get(j.url, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                continue
            body = _text_of(r.text)
        except Exception as e:
            log.debug("   Detailseite nicht ladbar (%s): %s", j.company, str(e)[:80])
            continue

        before_dur, before_start = j.duration_months, j.start_date
        j.description = (j.description + " " + body)[:14000]
        scorer.score(j, strict=False)

        if (j.duration_months is not None and before_dur is None) or \
           (j.start_date is not None and before_start is None):
            improved += 1
            log.info("   angereichert: %-22s %-42s -> %s Mon., Start %s",
                     j.company[:22], j.title[:42],
                     j.duration_months, j.start_date or "?")

    return tried, improved
