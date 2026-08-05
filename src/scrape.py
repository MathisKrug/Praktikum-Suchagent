"""Hauptlauf.

Drei Stufen:
  1  Entdeckung  - breite Suche ueber Adzuna und Jooble, findet unbekannte Firmen
  2  Register    - jeder relevante Arbeitgeber wird mitgeschrieben
  3  Vertiefung  - gute Firmen werden automatisch in die feste Ueberwachung geholt
Dazu die fest konfigurierten Firmen aus config/companies.yaml.

Aufruf:  python -m src.scrape
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import yaml

from . import adapters
from .adapters import AdapterError
from .score import Scorer
from .store import Store
from .render import render_html, render_xlsx
from .discovery import run_discovery
from .enrich import enrich
from . import employers as emp
from .detect import detect

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scrape")

COMPANIES_PATH = Path("config/companies.yaml")


def load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    companies_cfg = load("config/companies.yaml")
    scoring_cfg = load("config/scoring.yaml")
    disc_cfg = load("config/discovery.yaml")

    terms = companies_cfg.get("search_terms", ["Praktikum"])
    scorer = Scorer(scoring_cfg)
    store = Store()

    relevant = []
    errors: list[str] = []
    raw_total = 0

    # ---------------- Stufe 1: Entdeckung ----------------

    log.info("=== Stufe 1: Entdeckung ueber Aggregatoren ===")
    disc_jobs, disc_errors = run_discovery(disc_cfg)
    errors.extend(disc_errors)
    raw_total += len(disc_jobs)

    # Personaldienstleister und Vermittler raus, bevor ueberhaupt bewertet wird.
    blocklist = disc_cfg.get("employer_blocklist", [])
    bl_norm = [emp.norm_employer(b) for b in blocklist]
    before = len(disc_jobs)
    disc_jobs = [j for j in disc_jobs if not emp.is_blocked(j.company, bl_norm)]
    if before != len(disc_jobs):
        log.info("Vermittler/Blocklist: %d Treffer verworfen", before - len(disc_jobs))

    disc_kept = []
    for j in disc_jobs:
        # strict=True: bei der breiten Suche muss eine Zielfunktion erkennbar sein
        scorer.score(j, strict=True)
        if scorer.passes(j):
            disc_kept.append(j)
    relevant.extend(disc_kept)
    log.info("Entdeckung: %d roh -> %d relevant", before, len(disc_kept))

    # ---------------- Feste Firmenliste ----------------

    log.info("=== Feste Firmenliste ===")
    broken: list[dict] = []
    for company in companies_cfg["companies"]:
        name = company["name"]
        try:
            ad = adapters.build(company, terms)
            jobs = ad.fetch()
        except Exception as e:
            msg = f"{name}: {type(e).__name__}: {str(e)[:180]}"
            errors.append(msg)
            log.warning("  %s", msg)
            broken.append(company)
            continue

        if not jobs and company.get("status") != "auto":
            broken.append(company)

        raw_total += len(jobs)
        kept = []
        for j in jobs:
            scorer.score(j)
            if scorer.passes(j):
                kept.append(j)
        relevant.extend(kept)
        log.info("%-28s %3d roh -> %2d relevant", name[:28], len(jobs), len(kept))

    # ---------------- Selbstreparatur ----------------
    # Adapter, die gar nichts liefern, werden derselben automatischen
    # Systemerkennung unterworfen, die bei den entdeckten Firmen funktioniert.
    # Das ist verlaesslicher als von Hand geratene Konfiguration.

    if broken:
        log.info("=== Selbstreparatur: %d Adapter ohne Ergebnis ===", len(broken))
        repaired = 0
        for company in broken:
            found = detect(company["name"])
            if not found:
                log.info("   %-28s kein System erkannt", company["name"][:28])
                continue
            if found["adapter"] == company.get("adapter") and \
               found["config"] == company.get("config"):
                continue
            log.info("   %-28s %s -> %s", company["name"][:28],
                     company.get("adapter"), found["adapter"])
            company["adapter"] = found["adapter"]
            company["config"] = found["config"]
            company["status"] = "repariert"
            repaired += 1

        if repaired:
            COMPANIES_PATH.write_text(
                yaml.safe_dump(companies_cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            log.info("   %d Adapter neu zugeordnet - greifen ab dem naechsten Lauf", repaired)

    # ---------------- Anreicherung ----------------

    log.info("=== Anreicherung: Detailseiten der besten Treffer ===")
    tried, improved = enrich(relevant, scorer,
                             limit=int(scoring_cfg.get("enrich_limit", 40)))
    log.info("Anreicherung: %d Seiten geladen, %d Treffer mit Laufzeit/Startdatum ergaenzt",
             tried, improved)
    relevant = [j for j in relevant if scorer.passes(j)]

    # ---------------- Stufe 2: Firmenregister ----------------

    n_reg = emp.register(store, relevant, blocklist)
    log.info("=== Stufe 2: %d Treffer ins Firmenregister eingetragen ===", n_reg)

    # ---------------- Stufe 3: Vertiefung ----------------

    promo_cfg = disc_cfg.get("promotion", {})
    promoted_blocks = []
    if promo_cfg.get("enabled", True):
        candidates = emp.promotion_candidates(store, promo_cfg)
        log.info("=== Stufe 3: %d Kandidat(en) fuer Systemerkennung ===", len(candidates))
        for c in candidates:
            block = detect(c["name"])
            store.mark_detect_tried(c["key"], block["adapter"] if block else None)
            if block:
                promoted_blocks.append(block)

        if promoted_blocks:
            existing = {x["key"] for x in companies_cfg["companies"]}
            added = [b for b in promoted_blocks if b["key"] not in existing]
            if added:
                companies_cfg["companies"].extend(added)
                COMPANIES_PATH.write_text(
                    yaml.safe_dump(companies_cfg, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                log.info("Neu in die Ueberwachung aufgenommen: %s",
                         ", ".join(b["name"] for b in added))

    # ---------------- Speichern und Ausgabe ----------------

    new_jobs = store.upsert(relevant)
    store.log_run(len(relevant), len(new_jobs), " | ".join(errors))

    active = store.active(min_score=scorer.min_score)
    employer_rows = store.employers()

    render_html(active, errors, employers=employer_rows)
    render_xlsx(active, employers=employer_rows)

    log.info("")
    log.info("Roh gefunden:      %d", raw_total)
    log.info("Relevant:          %d", len(relevant))
    log.info("Davon neu:         %d", len(new_jobs))
    log.info("Im Dashboard:      %d", len(active))
    log.info("Firmen im Register:%d", len(employer_rows))
    log.info("Fest ueberwacht:   %d", len(companies_cfg["companies"]))
    if errors:
        log.info("Quellen mit Problemen: %d", len(errors))

    if new_jobs:
        log.info("")
        log.info("NEU seit letztem Lauf:")
        for j in sorted(new_jobs, key=lambda x: -x.score)[:40]:
            log.info("  [%3d] %-24s %s", j.score, j.company[:24], j.title[:58])

    store.close()

    if errors and not relevant:
        log.error("Keine einzige Quelle hat funktioniert.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
