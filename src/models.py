"""Datenmodell fuer eine gefundene Stelle."""

from __future__ import annotations

import re
import hashlib
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional

# Firmennamen kommen je Quelle unterschiedlich an: "Nestle", "Nestle Deutschland",
# "Nestle Deutschland AG". Und Titel enthalten Tippfehler ("(m/w/d(").
# Diese Normalisierung buegelt beides aus, damit Dubletten zusammenfallen.
_NOISE = re.compile(
    r"\b(gmbh|ag|se|kg|kgaa|ohg|mbh|co|deutschland|germany|austria|oesterreich"
    r"|international|group|gruppe|holding|m ?w ?d|w ?m ?d|d ?w ?m|all genders|f ?m ?d)\b"
)


def _fold(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Job:
    company: str
    title: str
    url: str
    sector: str = ""
    location: str = ""
    description: str = ""
    posted: str = ""

    # wird vom Scorer gefuellt
    score: int = 0
    duration_months: Optional[float] = None
    start_date: Optional[str] = None
    reasons: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Stabile ID auf Basis von Firma + Titel + Ort.

        Bewusst NICHT die URL: Adzuna und Jooble liefern dieselbe Anzeige mit
        unterschiedlichen Weiterleitungs-URLs, und eine URL-basierte ID haelt
        die beiden faelschlich fuer zwei verschiedene Stellen.
        """
        basis = "|".join([
            _fold(self.company),
            _fold(self.title),
            _fold(self.location.split(",")[0] if self.location else ""),
        ])
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        d["reasons"] = "; ".join(self.reasons)
        return d
