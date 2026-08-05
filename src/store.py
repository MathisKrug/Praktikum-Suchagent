"""SQLite-Speicher. Haelt fest, welche Stellen schon bekannt sind,
damit das Dashboard 'neu seit letztem Lauf' anzeigen kann.

Die Datei data/jobs.db wird vom Workflow mit ins Repo committet -
das ist der Grund, warum der Zustand zwischen den Laeufen erhalten bleibt.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid            TEXT PRIMARY KEY,
    company        TEXT,
    sector         TEXT,
    title          TEXT,
    url            TEXT,
    location       TEXT,
    score          INTEGER,
    duration       REAL,
    start_date     TEXT,
    reasons        TEXT,
    first_seen     TEXT,
    last_seen      TEXT,
    status         TEXT DEFAULT 'neu'
);
CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at    TEXT,
    found     INTEGER,
    new       INTEGER,
    errors    TEXT
);
CREATE TABLE IF NOT EXISTS employers (
    key           TEXT PRIMARY KEY,
    name          TEXT,
    hits          INTEGER DEFAULT 0,
    best_score    INTEGER DEFAULT 0,
    sector_hint   TEXT,
    sample_title  TEXT,
    first_seen    TEXT,
    last_seen     TEXT,
    promoted      INTEGER DEFAULT 0,   -- 1 = in feste Ueberwachung uebernommen
    detect_tried  INTEGER DEFAULT 0,   -- 1 = System-Erkennung schon versucht
    adapter       TEXT
);
"""


class Store:
    def __init__(self, path: str = "data/jobs.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    def dedupe_existing(self) -> int:
        """Fuehrt bereits gespeicherte Dubletten mit der neuen ID zusammen.

        Noetig, weil die ID frueher an der URL hing. Adzuna und Jooble liefern
        dieselbe Anzeige mit unterschiedlichen Weiterleitungen - dadurch stand
        etwa Nestle fuenfmal in der Datenbank. Laeuft bei jedem Start und ist
        danach wirkungslos, kostet also nichts.
        """
        rows = [dict(r) for r in self.con.execute("SELECT * FROM jobs").fetchall()]
        groups: dict[str, list[dict]] = {}
        for r in rows:
            probe = Job(
                company=r["company"] or "",
                title=r["title"] or "",
                url=r["url"] or "",
                location=r["location"] or "",
            )
            groups.setdefault(probe.uid, []).append(r)

        removed = 0
        cur = self.con.cursor()
        for new_uid, items in groups.items():
            if len(items) == 1 and items[0]["uid"] == new_uid:
                continue

            # Den aussagekraeftigsten Eintrag behalten: hoechster Score,
            # aber das aelteste first_seen, damit "neu" ehrlich bleibt.
            keep = max(items, key=lambda x: (x["score"] or 0, x["last_seen"] or ""))
            first_seen = min((x["first_seen"] or "9999") for x in items)
            last_seen = max((x["last_seen"] or "") for x in items)

            for x in items:
                cur.execute("DELETE FROM jobs WHERE uid = ?", (x["uid"],))
            removed += len(items) - 1

            cur.execute(
                """INSERT OR REPLACE INTO jobs
                   (uid, company, sector, title, url, location, score, duration,
                    start_date, reasons, first_seen, last_seen, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_uid, keep["company"], keep["sector"], keep["title"], keep["url"],
                 keep["location"], keep["score"], keep["duration"], keep["start_date"],
                 keep["reasons"], first_seen, last_seen, keep["status"] or "neu"),
            )

        self.con.commit()
        return removed

    def upsert(self, jobs: list[Job]) -> list[Job]:
        """Speichert alle Jobs. Gibt die zurueck, die vorher unbekannt waren."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new: list[Job] = []
        cur = self.con.cursor()

        for j in jobs:
            row = cur.execute("SELECT uid FROM jobs WHERE uid = ?", (j.uid,)).fetchone()
            if row is None:
                new.append(j)
                cur.execute(
                    """INSERT INTO jobs
                       (uid, company, sector, title, url, location, score, duration,
                        start_date, reasons, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (j.uid, j.company, j.sector, j.title, j.url, j.location, j.score,
                     j.duration_months, j.start_date, "; ".join(j.reasons), now, now),
                )
            else:
                cur.execute(
                    """UPDATE jobs SET score=?, duration=?, start_date=?,
                       reasons=?, last_seen=?, location=? WHERE uid=?""",
                    (j.score, j.duration_months, j.start_date,
                     "; ".join(j.reasons), now, j.location, j.uid),
                )

        self.con.commit()
        return new

    def log_run(self, found: int, new: int, errors: str) -> None:
        self.con.execute(
            "INSERT INTO runs (ran_at, found, new, errors) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), found, new, errors),
        )
        self.con.commit()

    def active(self, min_score: int, days: int = 14) -> list[dict]:
        """Alle Stellen, die beim letzten Lauf noch online waren."""
        rows = self.con.execute(
            """SELECT * FROM jobs
               WHERE score >= ?
                 AND julianday('now') - julianday(last_seen) < ?
               ORDER BY score DESC, company ASC""",
            (min_score, days),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- Firmenregister (Stufe 2 / 3) ----

    def touch_employer(self, key: str, name: str, score: int,
                       sector_hint: str = "", sample_title: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self.con.cursor()
        row = cur.execute("SELECT hits, best_score FROM employers WHERE key=?", (key,)).fetchone()
        if row is None:
            cur.execute(
                """INSERT INTO employers
                   (key, name, hits, best_score, sector_hint, sample_title, first_seen, last_seen)
                   VALUES (?,?,1,?,?,?,?,?)""",
                (key, name, score, sector_hint, sample_title, now, now),
            )
        else:
            cur.execute(
                """UPDATE employers
                   SET hits = hits + 1,
                       best_score = MAX(best_score, ?),
                       last_seen = ?,
                       sample_title = CASE WHEN ? > best_score THEN ? ELSE sample_title END
                   WHERE key = ?""",
                (score, now, score, sample_title, key),
            )
        self.con.commit()

    def promotion_candidates(self, min_hits: int, min_best_score: int,
                             limit: int) -> list[dict]:
        promoted = self.con.execute(
            "SELECT COUNT(*) AS n FROM employers WHERE promoted = 1"
        ).fetchone()["n"]
        room = max(0, limit - promoted)
        if room == 0:
            return []
        rows = self.con.execute(
            """SELECT * FROM employers
               WHERE promoted = 0 AND detect_tried = 0
                 AND hits >= ? AND best_score >= ?
               ORDER BY best_score DESC, hits DESC
               LIMIT ?""",
            (min_hits, min_best_score, room),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_detect_tried(self, key: str, adapter: str | None) -> None:
        self.con.execute(
            "UPDATE employers SET detect_tried = 1, promoted = ?, adapter = ? WHERE key = ?",
            (1 if adapter else 0, adapter or "", key),
        )
        self.con.commit()

    def employers(self, limit: int = 400) -> list[dict]:
        rows = self.con.execute(
            """SELECT * FROM employers
               ORDER BY best_score DESC, hits DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def last_runs(self, n: int = 10) -> list[dict]:
        rows = self.con.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.con.close()
