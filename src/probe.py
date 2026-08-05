"""Probe-Modus: prueft fuer jede konfigurierte Firma, ob der Adapter funktioniert.

Das ist der ehrliche erste Schritt. Die Adapter-Zuordnung in companies.yaml
ist zunaechst eine Vermutung - hier stellt sich heraus, welche stimmt.

Aufruf:   python -m src.probe
Ergebnis: Bericht im Terminal + probe_report.md
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import yaml

from . import adapters
from .adapters import AdapterError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("probe")

CONFIG = Path("config/companies.yaml")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    terms = cfg.get("search_terms", ["Praktikum"])
    results = []

    for company in cfg["companies"]:
        name = company["name"]
        adapter_name = company.get("adapter", "?")
        log.info("Pruefe %-28s (%s) ...", name, adapter_name)

        try:
            ad = adapters.build(company, terms[:1])  # nur ein Suchbegriff, spart Zeit
            jobs = ad.fetch()
        except AdapterError as e:
            results.append((name, adapter_name, "FEHLER", 0, str(e)[:220]))
            log.info("   FEHLER: %s", str(e)[:160])
            continue
        except Exception as e:
            results.append((name, adapter_name, "FEHLER", 0, f"{type(e).__name__}: {e}"[:220]))
            log.info("   FEHLER: %s: %s", type(e).__name__, str(e)[:140])
            continue

        if not jobs:
            results.append((name, adapter_name, "LEER", 0, "Abruf lief durch, aber 0 Stellen"))
            log.info("   LEER - Abruf ok, aber keine Treffer")
            continue

        sample = "; ".join(j.title for j in jobs[:3])
        results.append((name, adapter_name, "OK", len(jobs), sample[:220]))
        log.info("   OK - %d Stellen. Beispiel: %s", len(jobs), sample[:90])

    ok = [r for r in results if r[2] == "OK"]
    empty = [r for r in results if r[2] == "LEER"]
    bad = [r for r in results if r[2] == "FEHLER"]

    lines = [
        "# Probe-Bericht",
        "",
        f"- Funktionieren: **{len(ok)}** von {len(results)}",
        f"- Leer (Adapter laeuft, findet aber nichts): **{len(empty)}**",
        f"- Fehler: **{len(bad)}**",
        "",
        "| Unternehmen | Adapter | Status | Treffer | Details |",
        "|---|---|---|---|---|",
    ]
    for name, ad, status, n, detail in results:
        detail = detail.replace("|", "/").replace("\n", " ")
        lines.append(f"| {name} | {ad} | {status} | {n} | {detail} |")

    lines += [
        "",
        "## Was jetzt zu tun ist",
        "",
        "- **OK**: nichts. Laeuft.",
        "- **LEER**: Der Abruf klappt, aber die Suchbegriffe greifen nicht. Meist",
        "  hilft es, in `config/companies.yaml` einen anderen `link_selector` zu",
        "  setzen oder auf einen passenderen Adapter zu wechseln.",
        "- **FEHLER**: Falscher Adapter oder falsche URL. Schick mir diese Zeilen,",
        "  dann suche ich das richtige System heraus.",
    ]

    Path("probe_report.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("\nBericht geschrieben: probe_report.md  (%d ok / %d leer / %d Fehler)",
             len(ok), len(empty), len(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
