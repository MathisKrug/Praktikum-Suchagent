"""Stufe 3: erkennt automatisch, welches Bewerbersystem eine Firma einsetzt.

Vorgehen: aus dem Firmennamen einen wahrscheinlichen Slug bilden und die
bekannten Muster der grossen Bewerbersysteme durchprobieren. Wer antwortet
und plausible Stellendaten liefert, gewinnt.

Absichtlich konservativ: lieber kein Treffer als ein falscher. Ein falsch
erkanntes System wuerde fremde Stellen unter dem Namen der Firma einsortieren.
"""

from __future__ import annotations

import re
import time
import logging
import unicodedata
import requests

log = logging.getLogger(__name__)

TIMEOUT = 12
DELAY = 1.0
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

LEGAL_SUFFIXES = [
    "gmbh & co. kg", "gmbh & co kg", "se & co. kga", "gmbh", "ag", "se", "kg",
    "ohg", "mbh", "e.k.", "ug", "co", "deutschland", "germany", "austria",
    "oesterreich", "international", "group", "gruppe", "holding",
]


def slugify(name: str) -> str:
    s = (name or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for suf in LEGAL_SUFFIXES:
        s = re.sub(rf"\b{re.escape(suf)}\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s.strip()


def _get(url: str, **kw):
    time.sleep(DELAY)
    return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, **kw)


def _try_greenhouse(slug: str):
    try:
        r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        if r.status_code == 200 and isinstance(r.json().get("jobs"), list) and r.json()["jobs"]:
            return {"adapter": "greenhouse", "config": {"board": slug}}
    except Exception:
        pass
    return None


def _try_lever(slug: str):
    try:
        r = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            return {"adapter": "lever", "config": {"company_id": slug}}
    except Exception:
        pass
    return None


def _try_smartrecruiters(slug: str):
    try:
        r = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=5")
        if r.status_code == 200 and r.json().get("content"):
            return {"adapter": "smartrecruiters", "config": {"company_id": slug}}
    except Exception:
        pass
    return None


def _try_teamtailor(slug: str):
    try:
        r = _get(f"https://{slug}.teamtailor.com/jobs")
        if r.status_code == 200 and "teamtailor" in r.text.lower() and "/jobs/" in r.text:
            return {"adapter": "teamtailor", "config": {"subdomain": slug}}
    except Exception:
        pass
    return None


def _try_successfactors(slug: str):
    for host in (f"https://careers.{slug}.com", f"https://jobs.{slug}.com"):
        try:
            r = _get(f"{host}/search/?q=Praktikum")
            if r.status_code == 200 and ("data-row" in r.text or "jobTitle-link" in r.text):
                return {"adapter": "successfactors", "config": {"base": host}}
        except Exception:
            continue
    return None


def _try_workday(slug: str):
    """Viele Luxus- und Modekonzerne fahren Workday (Richemont, Kering, Burberry).

    Der Tenant entspricht meist dem Firmen-Slug, das Rechenzentrum und der
    Site-Name variieren - deshalb ein kleines Raster.
    """
    sites = ["External", "careers", "Careers", f"{slug}careers", "broadbean_external"]
    for dc in ("wd3", "wd1", "wd5"):
        host = f"https://{slug}.{dc}.myworkdayjobs.com"
        for site in sites:
            try:
                r = requests.post(
                    f"{host}/wday/cxs/{slug}/{site}/jobs",
                    json={"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""},
                    headers={"Accept": "application/json", "User-Agent": UA},
                    timeout=TIMEOUT,
                )
                time.sleep(0.4)
                if r.status_code == 200 and r.json().get("jobPostings"):
                    return {"adapter": "workday",
                            "config": {"tenant": slug, "datacenter": dc, "site": site}}
            except Exception:
                continue
    return None


DETECTORS = [
    _try_greenhouse,
    _try_lever,
    _try_smartrecruiters,
    _try_teamtailor,
    _try_successfactors,
    _try_workday,     # zuletzt: teuerste Pruefung, weil mehrere Kombinationen
]


def detect(company_name: str) -> dict | None:
    """Gibt einen fertigen companies.yaml-Block zurueck, oder None."""
    slug = slugify(company_name)
    if len(slug) < 3:
        return None

    for fn in DETECTORS:
        hit = fn(slug)
        if hit:
            log.info("   erkannt: %s -> %s", company_name, hit["adapter"])
            return {
                "key": slug,
                "name": company_name,
                "sector": "entdeckt",
                "adapter": hit["adapter"],
                "status": "auto",
                "config": hit["config"],
            }

    log.debug("   kein System erkannt: %s (slug '%s')", company_name, slug)
    return None
