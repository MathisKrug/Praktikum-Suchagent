"""Adapter fuer Bewerbersysteme mit offener JSON-Schnittstelle.

Diese sind die schnellsten und stabilsten. Wenn eine Firma hierueber
erreichbar ist, sollte sie auch hier konfiguriert werden.
"""

from __future__ import annotations

import logging

from .base import Adapter, AdapterError
from ..models import Job

log = logging.getLogger(__name__)


class WorkdayAdapter(Adapter):
    """SAP-Konkurrent Workday. Endpoint-Muster:

    POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    """

    name = "workday"

    def fetch(self) -> list[Job]:
        tenant = self.cfg.get("tenant")
        dc = self.cfg.get("datacenter", "wd3")
        site = self.cfg.get("site", "External")
        if not tenant:
            raise AdapterError("workday: 'tenant' fehlt in der Konfiguration")

        host = f"https://{tenant}.{dc}.myworkdayjobs.com"
        endpoint = f"{host}/wday/cxs/{tenant}/{site}/jobs"

        jobs: list[Job] = []
        seen: set[str] = set()

        for term in self.search_terms:
            offset = 0
            while offset < 200:  # Sicherheitsgrenze
                payload = {
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": offset,
                    "searchText": term,
                }
                try:
                    r = self.post(
                        endpoint,
                        json=payload,
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                    )
                    data = r.json()
                except Exception as e:
                    raise AdapterError(f"workday: {e}") from e

                postings = data.get("jobPostings", [])
                if not postings:
                    break

                for p in postings:
                    path = p.get("externalPath", "")
                    url = f"{host}/{site}{path}" if path else ""
                    if url in seen:
                        continue
                    seen.add(url)
                    jobs.append(
                        Job(
                            company=self.label,
                            sector=self.sector,
                            title=p.get("title", "").strip(),
                            url=url,
                            location=p.get("locationsText", "") or "",
                            description=p.get("bulletFields", [""])[0] if p.get("bulletFields") else "",
                            posted=p.get("postedOn", "") or "",
                        )
                    )

                if len(postings) < 20:
                    break
                offset += 20

        return jobs


class SmartRecruitersAdapter(Adapter):
    """Oeffentliche API, kein Schluessel noetig."""

    name = "smartrecruiters"

    def fetch(self) -> list[Job]:
        company_id = self.cfg.get("company_id")
        if not company_id:
            raise AdapterError("smartrecruiters: 'company_id' fehlt")

        jobs: list[Job] = []
        offset = 0
        while offset < 400:
            url = (
                f"https://api.smartrecruiters.com/v1/companies/{company_id}"
                f"/postings?limit=100&offset={offset}"
            )
            try:
                data = self.get(url, headers={"Accept": "application/json"}).json()
            except Exception as e:
                raise AdapterError(f"smartrecruiters: {e}") from e

            content = data.get("content", [])
            if not content:
                break

            for p in content:
                loc = p.get("location", {}) or {}
                jobs.append(
                    Job(
                        company=self.label,
                        sector=self.sector,
                        title=p.get("name", "").strip(),
                        url=p.get("ref", "") or f"https://jobs.smartrecruiters.com/{company_id}/{p.get('id','')}",
                        location=", ".join(filter(None, [loc.get("city"), loc.get("country")])),
                        posted=p.get("releasedDate", "") or "",
                    )
                )

            if len(content) < 100:
                break
            offset += 100

        return jobs


class GreenhouseAdapter(Adapter):
    name = "greenhouse"

    def fetch(self) -> list[Job]:
        board = self.cfg.get("board")
        if not board:
            raise AdapterError("greenhouse: 'board' fehlt")
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        try:
            data = self.get(url, headers={"Accept": "application/json"}).json()
        except Exception as e:
            raise AdapterError(f"greenhouse: {e}") from e

        jobs = []
        for p in data.get("jobs", []):
            jobs.append(
                Job(
                    company=self.label,
                    sector=self.sector,
                    title=p.get("title", "").strip(),
                    url=p.get("absolute_url", ""),
                    location=(p.get("location") or {}).get("name", ""),
                    description=(p.get("content") or "")[:4000],
                    posted=p.get("updated_at", "") or "",
                )
            )
        return jobs


class LeverAdapter(Adapter):
    name = "lever"

    def fetch(self) -> list[Job]:
        company_id = self.cfg.get("company_id")
        if not company_id:
            raise AdapterError("lever: 'company_id' fehlt")
        url = f"https://api.lever.co/v0/postings/{company_id}?mode=json"
        try:
            data = self.get(url, headers={"Accept": "application/json"}).json()
        except Exception as e:
            raise AdapterError(f"lever: {e}") from e

        jobs = []
        for p in data:
            cats = p.get("categories", {}) or {}
            jobs.append(
                Job(
                    company=self.label,
                    sector=self.sector,
                    title=p.get("text", "").strip(),
                    url=p.get("hostedUrl", ""),
                    location=cats.get("location", "") or "",
                    description=(p.get("descriptionPlain") or "")[:4000],
                )
            )
        return jobs


class ZalandoAdapter(Adapter):
    """Zalando betreibt eine eigene Next.js-Seite.

    Die Suchergebnisse werden ueber einen internen Endpoint geladen.
    Falls sich das Muster aendert, meldet probe.py das als 'broken'.
    """

    name = "zalando"

    def fetch(self) -> list[Job]:
        base = self.cfg.get("base", "https://jobs.zalando.com").rstrip("/")
        candidates = [
            f"{base}/api/jobs?q=intern&limit=200",
            f"{base}/api/v1/jobs?query=intern&limit=200",
        ]

        last_err = None
        for url in candidates:
            try:
                data = self.get(url, headers={"Accept": "application/json"}).json()
            except Exception as e:
                last_err = e
                continue

            items = data.get("jobs") or data.get("data") or data.get("results") or []
            if not isinstance(items, list) or not items:
                continue

            jobs = []
            for p in items:
                slug = p.get("slug") or p.get("id") or ""
                jobs.append(
                    Job(
                        company=self.label,
                        sector=self.sector,
                        title=(p.get("title") or p.get("name") or "").strip(),
                        url=p.get("url") or f"{base}/en/jobs/{slug}",
                        location=p.get("office") or p.get("location") or "",
                        description=(p.get("description") or "")[:4000],
                        posted=p.get("publishedAt") or "",
                    )
                )
            return jobs

        raise AdapterError(
            f"zalando: kein bekannter JSON-Endpoint erreichbar (letzter Fehler: {last_err}). "
            "Siehe README, Abschnitt 'Adapter reparieren'."
        )
