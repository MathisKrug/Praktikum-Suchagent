"""Fit-Scoring. Regelbasiert, konfiguriert ueber config/scoring.yaml."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from .models import Job

MONTHS_DE = {
    "januar": 1, "jaenner": 1, "februar": 2, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}
MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def normalize(s: str) -> str:
    """Kleinschreibung + Umlaute aufloesen, damit 'Muenchen' und 'München' matchen."""
    s = (s or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def extract_duration(text: str) -> float | None:
    """Findet Laufzeitangaben wie '6 Monate', '3-4 months', 'fuer 12 Wochen'."""
    t = normalize(text)

    # Bereiche: "3-6 Monate" -> nimm das Minimum, das ist die verhandelbare Untergrenze
    m = re.search(r"(\d{1,2})\s*(?:-|–|bis|to)\s*(\d{1,2})\s*(monate?|months?)", t)
    if m:
        return float(m.group(1))

    m = re.search(r"(\d{1,2})\s*(monate?|months?)", t)
    if m:
        return float(m.group(1))

    m = re.search(r"(\d{1,2})\s*(?:-|–|bis|to)\s*(\d{1,2})\s*(wochen|weeks?)", t)
    if m:
        return round(float(m.group(1)) / 4.33, 1)

    m = re.search(r"(\d{1,2})\s*(wochen|weeks?)", t)
    if m:
        return round(float(m.group(1)) / 4.33, 1)

    return None


def extract_start_date(text: str) -> date | None:
    """Findet Startdaten wie '01.01.2027', 'ab Januar 2027', 'starting February 2027'."""
    t = normalize(text)

    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    all_months = {**MONTHS_DE, **MONTHS_EN}
    names = "|".join(sorted(all_months, key=len, reverse=True))
    m = re.search(rf"\b({names})\s+(20\d{{2}})", t)
    if m:
        try:
            return date(int(m.group(2)), all_months[m.group(1)], 1)
        except ValueError:
            pass

    return None


class Scorer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        w = cfg["window"]
        self.win_start = datetime.strptime(w["start"], "%Y-%m-%d").date()
        self.win_end = datetime.strptime(w["end"], "%Y-%m-%d").date()
        self.min_months = w.get("min_months", 2)
        self.functions = {int(k): [normalize(x) for x in v] for k, v in cfg["functions"].items()}
        self.exclude = [normalize(x) for x in cfg.get("exclude", [])]
        self.locations = {int(k): [normalize(x) for x in v] for k, v in cfg["locations"].items()}
        self.dur = cfg["duration"]
        self.start_points = cfg.get("start_date_in_window_points", 25)
        self.min_score = cfg.get("min_score", 25)
        sec = cfg.get("sector_signals", {}) or {}
        if "words" in sec:      # altes Format: ein Gewicht fuer alle
            self.sectors = {int(sec.get("points", 0)): [normalize(w) for w in sec["words"]]}
        else:                   # neues Format: nach Gewicht gestaffelt
            self.sectors = {int(k): [normalize(x) for x in v] for k, v in sec.items()}

    def score(self, job: Job, strict: bool = False) -> Job:
        """strict=True verlangt einen Treffer bei den Zielfunktionen.

        Wird fuer die breite Aggregatorsuche genutzt: dort kommen tausende
        beliebige Praktika herein, und ohne diese Huerde reichen schon
        Standort und Laufzeit, um die Mindestpunktzahl zu erreichen.
        Fuer die kuratierte Firmenliste bleibt es aus, weil dort auch
        vage betitelte Stellen ("Internship") relevant sein koennen.
        """
        title = normalize(job.title)
        body = normalize(f"{job.title} {job.description} {job.location}")
        haystack = f"{title} {title} {body}"  # Titel zaehlt doppelt
        reasons: list[str] = []
        total = 0

        # Ausschluss
        for bad in self.exclude:
            if bad in title:
                job.score = -1
                job.reasons = [f"ausgeschlossen: '{bad}' im Titel"]
                return job

        # Muss ueberhaupt ein Praktikum sein
        if not re.search(r"praktik|intern(ship)?\b|trainee", haystack):
            job.score = -1
            job.reasons = ["kein Praktikum"]
            return job

        # Funktion
        best_fn = 0
        for pts, words in sorted(self.functions.items(), reverse=True):
            hit = next((w for w in words if w in haystack), None)
            if hit:
                best_fn = pts
                reasons.append(f"Funktion '{hit}' (+{pts})")
                break

        if strict and best_fn == 0:
            job.score = -1
            job.reasons = ["keine Zielfunktion im Titel oder Text erkannt"]
            return job

        total += best_fn

        # Branchenbezug - hoechste passende Stufe gewinnt
        for pts, words in sorted(self.sectors.items(), reverse=True):
            hit = next((w for w in words if w in body), None)
            if hit:
                total += pts
                reasons.append(f"Branche '{hit}' (+{pts})")
                break

        # Standort
        best_loc = 0
        for pts, words in sorted(self.locations.items(), reverse=True):
            hit = next((w for w in words if w in body), None)
            if hit:
                best_loc = pts
                reasons.append(f"Standort '{hit}' (+{pts})")
                break
        total += best_loc

        # Laufzeit
        months = extract_duration(f"{job.title} {job.description}")
        job.duration_months = months
        ideal_max = max(float(x) for x in self.dur["ideal"])
        acc_max = max([float(x) for x in self.dur["acceptable"]] or [ideal_max])

        if months is None:
            total += self.dur["unknown_points"]
            reasons.append(f"Laufzeit unbekannt (+{self.dur['unknown_points']})")
        elif months < self.min_months:
            reasons.append(f"nur {months} Monate - zu kurz (+0)")
        elif months <= ideal_max:
            # Alles bis zur Obergrenze des Wunschbereichs ist gut - auch kuerzer.
            total += self.dur["ideal_points"]
            reasons.append(f"{months} Monate - passt ins Fenster (+{self.dur['ideal_points']})")
        elif months <= acc_max:
            total += self.dur["acceptable_points"]
            reasons.append(f"{months} Monate - verhandelbar (+{self.dur['acceptable_points']})")
        else:
            total += self.dur["long_points"]
            reasons.append(f"{months} Monate - zu lang, nur mit Verhandlung (+{self.dur['long_points']})")

        # Startdatum
        sd = extract_start_date(f"{job.title} {job.description}")
        if sd:
            job.start_date = sd.isoformat()
            if self.win_start <= sd <= self.win_end:
                total += self.start_points
                reasons.append(f"Start {sd.isoformat()} im Fenster (+{self.start_points})")
            else:
                reasons.append(f"Start {sd.isoformat()} ausserhalb des Fensters (+0)")

        job.score = total
        job.reasons = reasons
        return job

    def passes(self, job: Job) -> bool:
        return job.score >= self.min_score
