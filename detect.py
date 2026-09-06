"""Erkennt automatisch, welches Bewerbersystem eine Firma einsetzt.

Vorgehen: aus dem Firmennamen wahrscheinliche Slugs bilden und die bekannten
Muster der grossen Bewerbersysteme durchprobieren. Wer antwortet und plausible
Stellendaten liefert, gewinnt.

Absichtlich konservativ: lieber kein Treffer als ein falscher. Ein falsch
erkanntes System wuerde fremde Stellen unter dem Namen der Firma einsortieren.

Stand 18.08.2026 - warum das Raster erweitert wurde:

Die Selbstreparatur lief 16 Laeufe lang, ohne einen einzigen der 12 defekten
Adapter zu reparieren. Der Grund war nicht das Prinzip, sondern die Enge des
Rasters:

  Swarovski  -> tatsaechlich Workday, Site heisst schlicht 'swarovski'.
                In der Site-Liste standen nur External/careers/Careers/
                {slug}careers/broadbean_external. Der blosse Slug fehlte.
  adidas     -> SuccessFactors unter jobs.adidas-group.com. Geprueft wurden
                nur careers.{slug}.com und jobs.{slug}.com.

Deshalb jetzt: mehr Slug-Varianten, mehr Site-Namen, mehr Rechenzentren - und
die Moeglichkeit, in companies.yaml unter 'hints' konkrete Kandidaten
vorzugeben. Ein Hinweis wird zuerst geprueft, aber genau wie jeder geratene
Kandidat verworfen, wenn er nicht antwortet. Nichts wird ungeprueft uebernommen.
"""

from __future__ import annotations

import re
import time
import logging
import unicodedata
import requests

log = logging.getLogger(__name__)

TIMEOUT = 12
DELAY = 0.8
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

LEGAL_SUFFIXES = [
    "gmbh & co. kg", "gmbh & co kg", "se & co. kga", "gmbh", "ag", "se", "kg",
    "ohg", "mbh", "e.k.", "ug", "co", "deutschland", "germany", "austria",
    "oesterreich", "international", "group", "gruppe", "holding",
]


def _fold(name: str) -> str:
    s = (name or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def slugify(name: str) -> str:
    s = _fold(name)
    for suf in LEGAL_SUFFIXES:
        s = re.sub(rf"\b{re.escape(suf)}\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s.strip()


def slug_variants(name: str) -> list[str]:
    """Mehrere plausible Schreibweisen, ohne Dubletten, Reihenfolge = Wahrscheinlichkeit.

    'Marc O'Polo'  -> marcopolo, marc-o-polo
    'adidas'       -> adidas, adidas-group, adidasgroup
    'Prada Group'  -> prada, pradagroup, prada-group
    """
    base = slugify(name)
    if len(base) < 3:
        return []

    hyphen = re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-")
    hyphen = re.sub(r"-+", "-", hyphen)

    out = [base]
    for v in (f"{base}group", f"{base}-group", hyphen, hyphen.replace("-", "")):
        if v and v not in out and len(v) >= 3:
            out.append(v)
    return out


def _get(url: str, **kw):
    time.sleep(DELAY)
    return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, **kw)


# --------------------------------------------------------------------------
# Einzelpruefungen. Jede gibt einen fertigen config-Block zurueck oder None.
# --------------------------------------------------------------------------

def _check_greenhouse(cfg: dict):
    board = cfg.get("board")
    try:
        r = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        if r.status_code == 200 and r.json().get("jobs"):
            return {"adapter": "greenhouse", "config": {"board": board}}
    except Exception:
        pass
    return None


def _check_lever(cfg: dict):
    cid = cfg.get("company_id")
    try:
        r = _get(f"https://api.lever.co/v0/postings/{cid}?mode=json")
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            return {"adapter": "lever", "config": {"company_id": cid}}
    except Exception:
        pass
    return None


def _check_smartrecruiters(cfg: dict):
    cid = cfg.get("company_id")
    try:
        r = _get(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?limit=5")
        if r.status_code == 200 and r.json().get("content"):
            return {"adapter": "smartrecruiters", "config": {"company_id": cid}}
    except Exception:
        pass
    return None


def _check_teamtailor(cfg: dict):
    sub = cfg.get("subdomain")
    try:
        r = _get(f"https://{sub}.teamtailor.com/jobs")
        if r.status_code == 200 and "teamtailor" in r.text.lower() and "/jobs/" in r.text:
            return {"adapter": "teamtailor", "config": {"subdomain": sub}}
    except Exception:
        pass
    return None


def _check_successfactors(cfg: dict):
    base = (cfg.get("base") or "").rstrip("/")
    try:
        r = _get(f"{base}/search/?q=Praktikum")
        if r.status_code == 200 and ("data-row" in r.text or "jobTitle-link" in r.text):
            return {"adapter": "successfactors", "config": {"base": base}}
    except Exception:
        pass
    return None


def _check_workday(cfg: dict):
    tenant, dc, site = cfg.get("tenant"), cfg.get("datacenter"), cfg.get("site")
    try:
        r = requests.post(
            f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""},
            headers={"Accept": "application/json", "User-Agent": UA},
            timeout=TIMEOUT,
        )
        time.sleep(0.4)
        if r.status_code == 200 and r.json().get("jobPostings"):
            return {"adapter": "workday",
                    "config": {"tenant": tenant, "datacenter": dc, "site": site}}
    except Exception:
        pass
    return None


CHECKS = {
    "greenhouse": _check_greenhouse,
    "lever": _check_lever,
    "smartrecruiters": _check_smartrecruiters,
    "teamtailor": _check_teamtailor,
    "successfactors": _check_successfactors,
    "workday": _check_workday,
}

# Workday: Site-Namen in der Reihenfolge, in der sie in freier Wildbahn
# vorkommen. '{slug}' selbst fehlte bisher und ist genau der Fall Swarovski.
WD_SITES = [
    "{slug}", "External", "Careers", "careers", "{slug}careers", "{slug}_careers",
    "External_Career_Site", "Careers_External", "External_Careers",
    "broadbean_external",
]
WD_DATACENTERS = ["wd3", "wd1", "wd5", "wd2", "wd12"]

# SuccessFactors: Hostmuster. '-group' deckt adidas ab.
SF_HOSTS = [
    "https://careers.{slug}.com", "https://jobs.{slug}.com",
    "https://jobs.{slug}-group.com", "https://careers.{slug}-group.com",
    "https://jobs.{slug}group.com",
]


def candidate_grid(name: str) -> list[tuple[str, dict]]:
    """Alle zu pruefenden Kandidaten, guenstigste Pruefung zuerst, ohne Dubletten."""
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()

    def add(adapter: str, cfg: dict) -> None:
        fp = f"{adapter}:{sorted(cfg.items())}"
        if fp not in seen:
            seen.add(fp)
            out.append((adapter, cfg))

    variants = slug_variants(name)
    for slug in variants:
        add("greenhouse", {"board": slug})
        add("lever", {"company_id": slug})
        add("smartrecruiters", {"company_id": slug})
        add("teamtailor", {"subdomain": slug})
        for host in SF_HOSTS:
            add("successfactors", {"base": host.format(slug=slug)})

    # Workday zuletzt: teuerste Pruefung, weil Tenant x Rechenzentrum x Site.
    # Nur die zwei plausibelsten Tenants, sonst explodiert die Laufzeit.
    for slug in variants[:2]:
        for dc in WD_DATACENTERS:
            for site in WD_SITES:
                add("workday", {"tenant": slug, "datacenter": dc,
                                "site": site.format(slug=slug)})
    return out


def detect(company_name: str, hints: list[dict] | None = None,
           max_checks: int = 60) -> dict | None:
    """Gibt einen fertigen companies.yaml-Block zurueck, oder None.

    'hints' sind konkrete Kandidaten aus companies.yaml, z.B.
        hints:
          - adapter: successfactors
            config: {base: "https://jobs.adidas-group.com"}
    Sie werden zuerst geprueft - aber nur uebernommen, wenn sie antworten.
    """
    key = slugify(company_name)
    if len(key) < 3:
        return None

    queue: list[tuple[str, dict]] = []
    for h in (hints or []):
        if h.get("adapter") in CHECKS:
            queue.append((h["adapter"], h.get("config", {}) or {}))
    queue.extend(candidate_grid(company_name))

    tried = 0
    seen: set[str] = set()
    for adapter_name, cfg in queue:
        fingerprint = f"{adapter_name}:{sorted(cfg.items())}"
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        tried += 1
        if tried > max_checks:
            log.debug("   Kandidatenlimit erreicht: %s", company_name)
            break

        hit = CHECKS[adapter_name](cfg)
        if hit:
            log.info("   erkannt: %s -> %s %s", company_name, hit["adapter"], hit["config"])
            return {
                "key": key,
                "name": company_name,
                "sector": "entdeckt",
                "adapter": hit["adapter"],
                "status": "auto",
                "config": hit["config"],
            }

    log.debug("   kein System erkannt: %s (%d Kandidaten geprueft)", company_name, tried)
    return None
