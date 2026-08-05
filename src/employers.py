"""Stufe 2: Firmenregister.

Jeder Arbeitgeber, der ueber die Aggregatoren einen relevanten Treffer liefert,
landet hier. Ueber die Zeit entsteht daraus eine empirische Karte davon, wer
fuer dein Profil ueberhaupt einstellt.
"""

from __future__ import annotations

import re
import logging
import unicodedata

from .models import Job

log = logging.getLogger(__name__)


def norm_employer(name: str) -> str:
    s = (name or "").lower().strip()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_blocked(name: str, blocklist: list[str]) -> bool:
    n = norm_employer(name)
    if not n or n == "unbekannt":
        return True
    return any(b in n for b in blocklist)


def register(store, jobs: list[Job], blocklist: list[str]) -> int:
    """Traegt Arbeitgeber aus den relevanten Treffern ins Register ein."""
    blocklist = [norm_employer(b) for b in blocklist]
    touched = 0

    for j in jobs:
        if is_blocked(j.company, blocklist):
            continue
        store.touch_employer(
            key=norm_employer(j.company),
            name=j.company.strip(),
            score=j.score,
            sector_hint=j.sector or "",
            sample_title=j.title,
        )
        touched += 1

    return touched


def promotion_candidates(store, cfg: dict) -> list[dict]:
    """Firmen, die reif fuer die feste Ueberwachung sind."""
    if not cfg.get("enabled", True):
        return []
    return store.promotion_candidates(
        min_hits=int(cfg.get("min_hits", 2)),
        min_best_score=int(cfg.get("min_best_score", 55)),
        limit=int(cfg.get("max_promoted", 60)),
    )
