"""Adapter fuer Karriereseiten, die ihre Trefferliste als fertiges HTML ausliefern.

SAP SuccessFactors ist hier der wichtigste Fall: sehr viele Konzerne
(u.a. im FMCG- und Fashion-Bereich) setzen es ein, und die Suchergebnisseite
wird serverseitig gerendert - also gut auslesbar ohne Browser.
"""

from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup

from .base import Adapter, AdapterError
from ..models import Job

log = logging.getLogger(__name__)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


class SuccessFactorsAdapter(Adapter):
    """SAP SuccessFactors Career Site.

    Suchergebnisse liegen unter /search/ und kommen als HTML-Tabelle
    mit Zeilen der Klasse 'data-row'.
    """

    name = "successfactors"

    def fetch(self) -> list[Job]:
        base = self.cfg.get("base", "").rstrip("/")
        if not base:
            raise AdapterError("successfactors: 'base' fehlt in der Konfiguration")

        jobs: list[Job] = []
        seen: set[str] = set()
        errors = []

        for term in self.search_terms:
            startrow = 0
            while startrow < 200:
                url = f"{base}/search/?q={term}&startrow={startrow}"
                try:
                    html = self.get(url).text
                except Exception as e:
                    errors.append(str(e))
                    break

                soup = BeautifulSoup(html, "lxml")
                rows = soup.select("tr.data-row") or soup.select("li.job-tile")
                if not rows:
                    break

                found_this_page = 0
                for row in rows:
                    link = row.select_one("a.jobTitle-link") or row.select_one("a[href*='/job/']")
                    if not link:
                        continue
                    href = self.abs_url(base, link.get("href", ""))
                    if href in seen:
                        continue
                    seen.add(href)
                    found_this_page += 1

                    loc_el = (
                        row.select_one(".jobLocation")
                        or row.select_one("span[class*='location']")
                        or row.select_one(".job-location")
                    )
                    date_el = row.select_one(".jobDate") or row.select_one("[class*='date']")

                    jobs.append(
                        Job(
                            company=self.label,
                            sector=self.sector,
                            title=_clean(link.get_text()),
                            url=href,
                            location=_clean(loc_el.get_text()) if loc_el else "",
                            posted=_clean(date_el.get_text()) if date_el else "",
                        )
                    )

                if found_this_page == 0:
                    break
                startrow += 25

        if not jobs and errors:
            raise AdapterError(f"successfactors: keine Treffer, Fehler: {errors[0]}")
        return jobs


class TeamtailorAdapter(Adapter):
    name = "teamtailor"

    def fetch(self) -> list[Job]:
        sub = self.cfg.get("subdomain")
        if not sub:
            raise AdapterError("teamtailor: 'subdomain' fehlt")
        base = f"https://{sub}.teamtailor.com"
        try:
            html = self.get(f"{base}/jobs").text
        except Exception as e:
            raise AdapterError(f"teamtailor: {e}") from e

        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for a in soup.select("a[href*='/jobs/']"):
            href = self.abs_url(base, a.get("href", ""))
            title = _clean(a.get_text())
            if not title or href.rstrip("/").endswith("/jobs"):
                continue
            jobs.append(
                Job(company=self.label, sector=self.sector, title=title, url=href)
            )
        return _dedupe(jobs)


class EployAdapter(Adapter):
    """Eploy-basierte Karriereseiten (z.B. OC&C)."""

    name = "eploy"

    def fetch(self) -> list[Job]:
        url = self.cfg.get("url")
        if not url:
            raise AdapterError("eploy: 'url' fehlt")
        try:
            html = self.get(url).text
        except Exception as e:
            raise AdapterError(f"eploy: {e}") from e

        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for h in soup.select("h2 a[href*='/vacancies/'], h3 a[href*='/vacancies/']"):
            href = self.abs_url(url, h.get("href", ""))
            title = _clean(h.get_text())
            if not title:
                continue
            block = h.find_parent(["div", "li", "article"])
            loc = ""
            if block:
                m = re.search(
                    r"\*Location\*\s*(.+?)\s*\*", block.get_text(" ", strip=True)
                )
                if m:
                    loc = _clean(m.group(1))
            desc = _clean(block.get_text(" ", strip=True))[:2000] if block else ""
            jobs.append(
                Job(
                    company=self.label,
                    sector=self.sector,
                    title=title,
                    url=href,
                    location=loc,
                    description=desc,
                )
            )
        return _dedupe(jobs)


class GenericHtmlAdapter(Adapter):
    """Fallback: holt eine Seite und sammelt alle Links, die einem Selektor entsprechen.

    Bewusst grob. Filtert spaeter der Scorer. Wenn eine Firma hierueber
    schlechte Ergebnisse liefert, lohnt es sich, einen eigenen Adapter zu bauen.
    """

    name = "generic_html"

    def fetch(self) -> list[Job]:
        url = self.cfg.get("url")
        selector = self.cfg.get("link_selector", "a")
        if not url:
            raise AdapterError("generic_html: 'url' fehlt")
        try:
            html = self.get(url).text
        except Exception as e:
            raise AdapterError(f"generic_html: {e}") from e

        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for a in soup.select(selector):
            title = _clean(a.get_text())
            href = a.get("href", "")
            if not title or not href or len(title) < 6:
                continue
            jobs.append(
                Job(
                    company=self.label,
                    sector=self.sector,
                    title=title,
                    url=self.abs_url(url, href),
                )
            )
        return _dedupe(jobs)


def _dedupe(jobs: list[Job]) -> list[Job]:
    out, seen = [], set()
    for j in jobs:
        if j.uid in seen:
            continue
        seen.add(j.uid)
        out.append(j)
    return out
