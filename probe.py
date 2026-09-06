"""Probe-Modus: prueft fuer jede konfigurierte Firma, ob der Adapter funktioniert.

Das ist der ehrliche erste Schritt. Die Adapter-Zuordnung in companies.yaml ist
teils gepruefte Tatsache, teils begruendete Vermutung - hier stellt sich heraus,
was davon stimmt.

Neu seit 18.08.2026: Wenn ein Adapter scheitert oder leer bleibt, laeuft direkt
die Systemerkennung mit und schreibt einen fertigen, geprueften YAML-Block in den
Bericht. Du musst nichts mehr weiterleiten und auf eine Antwort warten - der
Bericht enthaelt die Loesung, sofern es eine gibt.

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
from .detect import detect

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("probe")

CONFIG = Path("config/companies.yaml")


def _yaml_block(company: dict, found: dict) -> str:
    block = {
        "key": company["key"],
        "name": company["name"],
        "sector": company.get("sector", ""),
        "adapter": found["adapter"],
        "status": "geprueft",
        "config": found["config"],
    }
    return yaml.safe_dump([block], allow_unicode=True, sort_keys=False).rstrip()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    terms = cfg.get("search_terms", ["Praktikum"])
    results = []
    proposals: list[str] = []

    for company in cfg["companies"]:
        name = company["name"]
        adapter_name = company.get("adapter", "?")

        if company.get("enabled") is False:
            note = company.get("note", "")
            results.append((name, adapter_name, "AUS", 0, note[:220]))
            log.info("Ueberspringe %-24s (enabled: false)", name[:24])
            continue

        log.info("Pruefe %-28s (%s) ...", name, adapter_name)

        status, jobs, detail = "OK", [], ""
        try:
            ad = adapters.build(company, terms[:1])  # nur ein Suchbegriff, spart Zeit
            jobs = ad.fetch()
        except AdapterError as e:
            status, detail = "FEHLER", str(e)[:220]
        except Exception as e:
            status, detail = "FEHLER", f"{type(e).__name__}: {e}"[:220]

        if status == "OK" and not jobs:
            status, detail = "LEER", "Abruf lief durch, aber 0 Stellen"

        if status == "OK":
            detail = "; ".join(j.title for j in jobs[:3])[:220]
            log.info("   OK - %d Stellen. Beispiel: %s", len(jobs), detail[:90])
        else:
            log.info("   %s: %s", status, detail[:140])
            # Direkt nach einer funktionierenden Alternative suchen.
            found = detect(name, hints=company.get("hints"), max_checks=120)
            if found:
                log.info("   -> Alternative gefunden: %s %s",
                         found["adapter"], found["config"])
                proposals.append(f"### {name}\n\n```yaml\n{_yaml_block(company, found)}\n```")
            else:
                log.info("   -> keine funktionierende Alternative gefunden")

        results.append((name, adapter_name, status, len(jobs), detail))

    ok = [r for r in results if r[2] == "OK"]
    empty = [r for r in results if r[2] == "LEER"]
    bad = [r for r in results if r[2] == "FEHLER"]
    off = [r for r in results if r[2] == "AUS"]

    lines = [
        "# Probe-Bericht",
        "",
        f"- Funktionieren: **{len(ok)}** von {len(results) - len(off)} geprueften",
        f"- Leer (Adapter laeuft, findet aber nichts): **{len(empty)}**",
        f"- Fehler: **{len(bad)}**",
        f"- Bewusst abgeschaltet: **{len(off)}**",
        "",
        "| Unternehmen | Adapter | Status | Treffer | Details |",
        "|---|---|---|---|---|",
    ]
    for name, ad, status, n, detail in results:
        detail = (detail or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {name} | {ad} | {status} | {n} | {detail} |")

    if proposals:
        lines += [
            "",
            "## Geprueft funktionierende Ersatzkonfigurationen",
            "",
            "Diese Bloecke wurden nicht geraten - sie haben im Probe-Lauf",
            "tatsaechlich Stellen geliefert. Den jeweiligen Block in",
            "`config/companies.yaml` ueber den alten Eintrag derselben Firma legen.",
            "",
        ] + proposals
    else:
        lines += [
            "",
            "## Ersatzkonfigurationen",
            "",
            "Keine gefunden. Fuer die fehlerhaften Firmen laesst sich mit den",
            "bekannten Bewerbersystemen nichts erreichen - das heisst meist:",
            "die Seite laedt ihre Stellen per JavaScript nach, oder sie sperrt",
            "automatisierte Zugriffe. Beides ist kein Konfigurationsfehler.",
        ]

    lines += [
        "",
        "## Lesehilfe",
        "",
        "- **OK**: laeuft.",
        "- **LEER**: Abruf klappt, aber keine Treffer. Haeufigste Ursache: die",
        "  Stellenliste wird erst im Browser per JavaScript aufgebaut. Das ist",
        "  der gefaehrlichste Zustand, weil er im Log wie Erfolg aussieht -",
        "  deshalb faerbt die Quellenampel im Dashboard solche Quellen ein.",
        "- **FEHLER**: Adapter oder URL passen nicht.",
        "- **AUS**: absichtlich abgeschaltet, Begruendung steht in der Detailspalte.",
    ]

    Path("probe_report.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("\nBericht geschrieben: probe_report.md  (%d ok / %d leer / %d Fehler / %d aus)",
             len(ok), len(empty), len(bad), len(off))
    return 0


if __name__ == "__main__":
    sys.exit(main())
