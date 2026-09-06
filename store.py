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
    status         TEXT DEFAULT 'neu',
    source         TEXT,   -- woher die Anzeige kam (Adzuna DE, Karriereseite X)
    posted         TEXT    -- Ausschreibungsdatum laut Quelle, leer wenn keins
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
CREATE TABLE IF NOT EXISTS source_health (
    source        TEXT PRIMARY KEY,
    kind          TEXT,     -- aggregator | karriereseite
    last_check    TEXT,     -- wann zuletzt abgefragt
    last_ok       TEXT,     -- wann zuletzt mindestens eine Stelle geliefert
    last_count    INTEGER DEFAULT 0,
    last_error    TEXT,
    quiet_runs    INTEGER DEFAULT 0   -- Laeufe in Folge ohne Ergebnis
);
"""

# Spalten, die nach dem ersten Release dazugekommen sind. Werden bei jedem
# Start nachgezogen, damit eine bestehende jobs.db weiterlaeuft und die
# Historie erhalten bleibt.
MIGRATIONS = {
    "jobs": {"source": "TEXT", "posted": "TEXT"},
}


class Store:
    def __init__(self, path: str = "data/jobs.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrate()
        self.con.commit()

    def _migrate(self) -> None:
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in self.con.execute(f"PRAGMA table_info({table})")}
            for col, coltype in cols.items():
                if col not in have:
                    self.con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")

        # Einmalige Nachtragung der Herkunft fuer den Altbestand. Kein Raten:
        # die Weiterleitungs-URL von Adzuna nennt die Quelle selbst. Wo sich die
        # Herkunft nicht aus der URL ergibt, bleibt das Feld leer und wird als
        # "Quelle nicht vermerkt" angezeigt.
        #
        # Das Ausschreibungsdatum laesst sich rueckwirkend NICHT nachtragen -
        # es wurde nie gespeichert. Diese Stellen bleiben auf "nicht auffindbar".
        # Das Erfassungsdatum hier einzusetzen waere eine Faelschung.
        self.con.execute(
            "UPDATE jobs SET source='Adzuna DE' "
            "WHERE (source IS NULL OR source='') AND url LIKE '%adzuna.de%'"
        )
        self.con.execute(
            "UPDATE jobs SET source='Adzuna AT' "
            "WHERE (source IS NULL OR source='') AND url LIKE '%adzuna.at%'"
        )
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
                    start_date, reasons, first_seen, last_seen, status, source, posted)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_uid, keep["company"], keep["sector"], keep["title"], keep["url"],
                 keep["location"], keep["score"], keep["duration"], keep["start_date"],
                 keep["reasons"], first_seen, last_seen, keep["status"] or "neu",
                 keep.get("source"), keep.get("posted")),
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
                        start_date, reasons, first_seen, last_seen, source, posted)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (j.uid, j.company, j.sector, j.title, j.url, j.location, j.score,
                     j.duration_months, j.start_date, "; ".join(j.reasons), now, now,
                     j.source, j.posted),
                )
            else:
                # source und posted nur setzen, wenn die Quelle diesmal etwas
                # liefert - ein spaeterer Treffer ohne Datum soll ein frueher
                # erfasstes Ausschreibungsdatum nicht ueberschreiben.
                cur.execute(
                    """UPDATE jobs SET score=?, duration=?, start_date=?,
                       reasons=?, last_seen=?, location=?,
                       source = COALESCE(NULLIF(?, ''), source),
                       posted = COALESCE(NULLIF(?, ''), posted)
                       WHERE uid=?""",
                    (j.score, j.duration_months, j.start_date,
                     "; ".join(j.reasons), now, j.location, j.source, j.posted, j.uid),
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

    # ---- Quellenampel ----

    def record_health(self, entries: list[dict]) -> None:
        """Schreibt je Quelle fest, ob sie diesmal etwas geliefert hat.

        Der Sinn ist die stille Null: eine Karriereseite, die ohne Fehler
        antwortet und trotzdem nie eine Stelle liefert, sieht im Log wie
        Erfolg aus. quiet_runs zaehlt genau diesen Fall mit.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self.con.cursor()
        for e in entries:
            src = e.get("source") or "?"
            count = int(e.get("count") or 0)
            err = (e.get("error") or "")[:300]
            row = cur.execute(
                "SELECT quiet_runs, last_ok FROM source_health WHERE source=?", (src,)
            ).fetchone()
            quiet = 0 if count > 0 else ((row["quiet_runs"] if row else 0) + 1)
            last_ok = now if count > 0 else (row["last_ok"] if row else None)
            cur.execute(
                """INSERT INTO source_health
                   (source, kind, last_check, last_ok, last_count, last_error, quiet_runs)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(source) DO UPDATE SET
                     kind=excluded.kind, last_check=excluded.last_check,
                     last_ok=excluded.last_ok, last_count=excluded.last_count,
                     last_error=excluded.last_error, quiet_runs=excluded.quiet_runs""",
                (src, e.get("kind") or "", now, last_ok, count, err, quiet),
            )
        self.con.commit()

    def health(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT * FROM source_health ORDER BY quiet_runs DESC, source ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def last_runs(self, n: int = 10) -> list[dict]:
        rows = self.con.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.con.close()
