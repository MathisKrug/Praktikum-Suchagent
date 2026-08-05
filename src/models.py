"""Datenmodell fuer eine gefundene Stelle."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional


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
        """Stabile ID. Bevorzugt die URL, faellt auf Firma+Titel zurueck."""
        basis = self.url.split("?")[0] if self.url else f"{self.company}|{self.title}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        d["reasons"] = "; ".join(self.reasons)
        return d
