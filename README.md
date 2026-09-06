# Praktikum-Radar

Sucht täglich nach Praktika für dein Profil (Brand Management, Buying &
Merchandising, Strategy) in Deutschland und Österreich, bewertet jeden Treffer
gegen dein Zeitfenster Januar bis Ende März 2027 und stellt das Ergebnis als
Webseite bereit, die du auf dem iPhone zum Homescreen hinzufügen kannst.

Läuft kostenlos auf GitHub Actions. Dein Rechner muss dafür nicht an sein.

## Wie es arbeitet

Das Werkzeug löst zwei verschiedene Probleme gleichzeitig.

**Überwachung** — die in `config/companies.yaml` konfigurierten Unternehmen aus
Fashion und FMCG werden direkt auf ihrer Karriereseite abgefragt. Dort erscheinen
Stellen zuerst, oft ein bis zwei Wochen bevor Jobbörsen sie einsammeln.

**Entdeckung** — parallel läuft eine breite Suche über Adzuna nach deinen
Funktionsbegriffen, ohne Firmennamen vorzugeben. Das findet Arbeitgeber, die auf
keiner Liste stehen, die du oder ich hätten aufschreiben können.

Aus der Entdeckung wächst über die Zeit ein **Firmenregister**: wer wie oft
Praktika in deinem Profil ausschreibt und wie gut die im Schnitt passen. Nach
etwa vier Wochen hast du damit eine empirische Karte deines Marktes statt einer
geratenen Liste. Firmen, die wiederholt gut punkten, werden automatisch in die
direkte Überwachung übernommen — das Skript erkennt dazu selbstständig, welches
Bewerbersystem sie einsetzen.

Im Dashboard sind das die beiden Reiter **Stellen** und **Firmen**.

---

## Einrichtung — etwa 15 Minuten

### 1. Repository anlegen

Auf github.com auf **New repository**. Name z.B. `praktikum-radar`.
Sichtbarkeit **Public** wählen — dann sind GitHub Actions und Pages unbegrenzt kostenlos.
(Private geht auch, du hast dann 2.000 Action-Minuten im Monat. Dieser Scraper
braucht etwa 60 im Monat, reicht also locker. Bei Private musst du für Pages
allerdings ein bezahltes Konto haben — deshalb: Public.)

Falls dir Public unangenehm ist: Im Repo stehen nur Firmennamen und Suchbegriffe,
keine persönlichen Daten. Dein CV liegt nicht darin.

### 2. Dateien hochladen

Auf der leeren Repo-Seite auf **uploading an existing file**.
Dann den kompletten Inhalt des Ordners `praktikum-radar` per Drag-and-drop
ins Browserfenster ziehen — inklusive der Unterordner.

Wichtig: Der versteckte Ordner `.github` muss mit. Falls dein Finder ihn nicht
anzeigt, blende versteckte Dateien mit `Cmd + Shift + .` ein.

Unten auf **Commit changes**.

### 3. API-Keys hinterlegen

Ohne diesen Schritt läuft nur die Überwachung der festen Firmenliste — die
Entdeckung bleibt still. Der Dienst ist kostenlos.

**Adzuna:** auf [developer.adzuna.com](https://developer.adzuna.com) registrieren.
Du bekommst eine **Application ID** und einen **Application Key**.

Dann im Repo: **Settings → Secrets and variables → Actions → New repository secret**.
Zwei Stück anlegen, Namen exakt so:

| Name | Wert |
|---|---|
| `ADZUNA_APP_ID` | deine Adzuna Application ID |
| `ADZUNA_APP_KEY` | dein Adzuna Application Key |

Falls du noch ein `JOOBLE_API_KEY`-Secret hast: kann weg. Jooble ist am
18.08.2026 aus dem Projekt entfernt worden, siehe Abschnitt „Quellen".

Secrets sind verschlüsselt und auch bei einem öffentlichen Repository für
niemanden außer dich sichtbar. Schreib sie **nicht** in eine Datei im Repo.

Fehlt ein Schlüssel, überspringt das Skript die betreffende Quelle und schreibt
einen Hinweis ins Log — es bricht nicht ab.

### 4. Actions Schreibrechte geben

**Settings → Actions → General**, ganz nach unten zu *Workflow permissions*:
**Read and write permissions** auswählen, **Save**.

Ohne diesen Schritt kann der Workflow die Ergebnisse nicht zurückschreiben.

### 5. Ersten Lauf starten

Tab **Actions** → links **Praktikum-Radar** → rechts **Run workflow** → grüner Button.

Der Lauf dauert fünf bis zehn Minuten (die Entdeckungsstufe braucht Zeit).
Ein gelber Punkt heißt „läuft", grün heißt „fertig", rot heißt „Fehler" — dann
draufklicken, das Log lesen und mir schicken.

### 6. Pages aktivieren

**Settings → Pages**. Bei *Source* **Deploy from a branch**, Branch **main**,
Ordner **/docs**. **Save**.

Nach ein bis zwei Minuten ist deine Seite erreichbar unter:

```
https://DEIN-GITHUB-NAME.github.io/praktikum-radar/
```

### 7. Aufs iPhone legen

Adresse in Safari öffnen → Teilen-Symbol → **Zum Home-Bildschirm**.
Sieht danach aus wie eine App und öffnet ohne Browserleiste.

Ab jetzt läuft der Scraper täglich um 06:00 UTC von selbst.

---

## Erster inhaltlicher Schritt: Probe-Lauf

**Das hier ist wichtig.** Die Zuordnung „welche Firma nutzt welches Bewerbersystem"
in `config/companies.yaml` ist teils geprüfte Tatsache, teils begründete Vermutung.
Jeder Eintrag sagt selbst, was er ist — im Feld `status`:

| `status` | Bedeutung |
|---|---|
| `geprueft-TT-MM-JJJJ` | am genannten Tag nachgewiesen, dass der Endpunkt Stellen liefert |
| `kandidat-TT-MM-JJJJ` | starkes Indiz (URL-Muster des Systems), aber nicht abschließend geprüft |
| `verified` | läuft nachweislich seit dem ersten Lauf |
| `unverified` | Vermutung, noch nie bestätigt |
| `stille-null` | antwortet ohne Fehler, liefert aber nichts — meist JavaScript-Seite |
| `quelle-defekt` / `abgeschaltet` | bewusst inaktiv, Begründung steht im Feld `note` |

**Den Probe-Lauf starten:** Tab **Actions** → links **Probe-Lauf** → **Run workflow**.

Er geht jede Firma einzeln durch und schreibt `probe_report.md`. Neu ist:
Wenn ein Adapter scheitert, sucht der Probe-Lauf **selbst** nach einer
funktionierenden Alternative und legt einen fertigen YAML-Block in den Bericht.
Du kopierst ihn über den alten Eintrag — fertig. Nichts davon ist geraten: im
Bericht landet nur, was im Test tatsächlich Stellen zurückgegeben hat.

Findet er nichts, steht das auch da. Das heißt dann meist: die Seite baut ihre
Stellenliste erst im Browser auf, oder sie sperrt automatisierte Zugriffe.
Beides ist kein Konfigurationsfehler und lässt sich durch Herumprobieren an
`companies.yaml` nicht beheben.

Lokal geht dasselbe schneller:

```bash
pip install -r requirements.txt
python -m src.probe        # schreibt probe_report.md
python -m src.scrape       # kompletter Lauf
```

---

## Quellenampel

Dritter Reiter im Dashboard, **Quellen**. Jede Quelle mit Farbe:

- **grün** — hat beim letzten Lauf Stellen geliefert
- **gelb** — lief durch, lieferte aber nichts
- **rot** — Fehler, oder seit sieben Läufen still

Der eigentliche Grund für die Ampel ist Gelb. Ein Fehler im Log fällt auf. Eine
Karriereseite, die brav mit HTTP 200 antwortet und trotzdem nie eine Stelle
liefert, fällt nicht auf — sie sieht im Log aus wie Erfolg. Genau das war
zwischen dem 5. und 17. August bei LVMH, Hermès, Kering und ABOUT YOU der Fall:
kein einziger Fehler, kein einziger Treffer.

## Nachweis auf jeder Karte

Unten auf jeder Stellenkarte steht jetzt:

```
Quelle: Adzuna DE · ausgeschrieben: 2026-08-14 · erfasst: 2026-08-15
```

**Ausgeschrieben** ist das Datum der Quelle, **erfasst** der Tag, an dem der
Scraper die Anzeige zum ersten Mal gesehen hat. Liefert eine Quelle kein
Ausschreibungsdatum, steht dort `nicht auffindbar` — nie das Erfassungsdatum
als Ersatz. Beide Felder stehen auch in der Excel-Datei.

Für den Altbestand aus den ersten 16 Läufen wurde die Quelle nachgetragen,
soweit sie sich aus der Weiterleitungs-URL ergibt (129 von 139 Stellen kamen
über Adzuna). Das Ausschreibungsdatum ließ sich nicht nachtragen — es wurde
damals nicht gespeichert. Diese Stellen bleiben ehrlich auf `nicht auffindbar`.

---

## Was du selbst anpassen kannst

Alles Wichtige steht in zwei Dateien, beide bearbeitbar direkt im Browser
(Datei öffnen → Stift-Symbol → ändern → Commit changes).

**`config/scoring.yaml`** — dein Filter:

| Was | Wo |
|---|---|
| Zeitfenster | `window.start` / `window.end` |
| Zielfunktionen und ihre Gewichtung | `functions` |
| Begriffe, die sofort aussortieren | `exclude` |
| Standorte und ihre Priorität | `locations` |
| Wunsch-Laufzeit | `duration.ideal` |
| Wie streng gefiltert wird | `min_score` (höher = weniger Treffer) |

Wenn zu wenig kommt: `min_score` auf 15 senken.
Wenn zu viel Rauschen kommt: auf 40 anheben.

**`config/companies.yaml`** — die Zielliste. Neue Firma hinzufügen heißt:
einen Block kopieren, `key`, `name` und `config` anpassen.

Zusätzliche Felder je Firma:

- `enabled: false` — Firma wird übersprungen, ohne sie zu löschen. Für Quellen,
  die nachweislich defekt sind oder nicht in deinen Zielsektor gehören. Die
  Begründung gehört ins Feld `note`, damit in drei Monaten noch nachvollziehbar
  ist, warum.
- `note:` — Freitext. Überlebt im Gegensatz zu YAML-Kommentaren, dass das Skript
  die Datei bei der Selbstreparatur neu schreibt.
- `hints:` — konkrete Kandidaten für die Systemerkennung, die zuerst geprüft
  werden. Ein Hinweis wird nur übernommen, wenn er im Test tatsächlich Stellen
  liefert.

Zeitpunkt des täglichen Laufs: in `.github/workflows/scrape.yml`, Zeile mit `cron`.

---

## Wie bewertet wird

Regelbasiert, keine KI. Punkte gibt es für:

- **Funktion** (bis 30) — Brand Management und Product Marketing am höchsten,
  dann Buying und Merchandising, dann Strategy
- **Laufzeit** (bis 30) — alles bis 4 Monate volle Punkte, 5 Monate abgewertet,
  6 Monate null Punkte
- **Startdatum** (25) — wenn erkennbar im Fenster Januar bis März 2027
- **Standort** (bis 25) — Frankfurt und Wien oben, dann die übrigen DACH-Städte

Sechsmonatige Stellen werden **nicht** aussortiert, nur abgewertet. Du wolltest
dir die Verhandlung offenhalten — sie tauchen also weiter auf, nur weiter unten.

Jede Karte im Dashboard zeigt in der letzten Zeile, wie ihr Score zustande kam.
Wenn dir eine Bewertung unplausibel vorkommt, siehst du sofort warum.

---

## Quellen — und was bewusst fehlt

**Genutzt wird** die offizielle Entwickler-API von
[Adzuna](https://developer.adzuna.com) — kostenlos, mit Abdeckung für
Deutschland und Österreich — sowie die Karriereseiten der konfigurierten
Unternehmen direkt.

**Jooble ist am 18.08.2026 ersatzlos entfernt worden.** Die API hat in 16
aufeinanderfolgenden Läufen auf jede einzelne der 28 Anfragen pro Lauf mit
`403 Forbidden` geantwortet — 448 Fehlschläge, null Ergebnisse. Ob der
Schlüssel nie gültig war oder zurückgezogen wurde, ließ sich nicht klären.
Eine Quelle, die ausschließlich Fehlerzeilen produziert, kostet Laufzeit und
verdeckt echte Probleme im Log. Falls du Jooble später neu aufsetzt, lässt sich
die Klasse aus der Versionsgeschichte zurückholen — die Struktur in
`discovery.py` ist unverändert.

**Nicht genutzt wird die Bundesagentur für Arbeit.** Sie hat die mit Abstand
größte Stellendatenbank Deutschlands, und es existiert eine
[dokumentierte Schnittstelle](https://github.com/bundesAPI/jobsuche-api) dazu.
Die Behörde hat dieser Nutzung aber widersprochen, 2021 einen
Anti-Automatisierungsdienst mit CAPTCHA vorgeschaltet und erklärt, die
Schnittstelle sei nicht für Massenabfragen gedacht. Eine Quelle, deren Betreiber
aktiv gegen dich arbeitet, ist für einen laufenden Bewerbungsprozess wertlos —
und Adzuna aggregiert einen guten Teil derselben Anzeigen ohnehin.

**LinkedIn, StepStone und Indeed sind ebenfalls nicht dabei.** Aggressiver
Bot-Schutz, und automatisiertes Auslesen ist in ihren Nutzungsbedingungen
untersagt.

## Grenzen — damit du sie kennst, bevor sie dich überraschen

**Aggregatoren erwischen nicht alles.** Große Konzerne schalten viele Praktika
ausschließlich auf der eigenen Karriereseite. Genau deshalb laufen beide Ebenen
nebeneinander: Entdeckung findet die Unbekannten, die feste Liste deckt die
Großen ab. Verlass dich nicht auf eine allein.

**Adapter gehen kaputt.** Karriereseiten werden umgebaut, dann liefert eine Quelle
nichts mehr. Das Dashboard zeigt oben aufklappbar, welche Quellen Probleme hatten.
Rechne mit ein bis zwei Reparaturen pro Quartal.

**Laufzeit und Startdatum werden aus dem Text geraten.** Steht die Angabe nur in
einem PDF oder erst im Bewerbungsformular, bleibt das Feld leer und die Stelle
bekommt Zweifelspunkte. Ein leeres Feld heißt nicht „passt nicht", sondern
„musst du selbst nachsehen".

**Der Scraper liest nur Trefferlisten, keine Stellendetailseiten.** Das hält ihn
schnell und die Server-Last niedrig, kostet aber Genauigkeit bei Laufzeit und
Startdatum. Wenn dir das zu ungenau ist, bauen wir einen zweiten Durchgang ein,
der für hoch bewertete Treffer die Detailseite nachlädt.

**Die automatische Systemerkennung ist absichtlich vorsichtig.** Sie rät
Firmen-Slugs aus dem Namen und probiert die bekannten Muster durch. Bei
„Douglas Deutschland GmbH" wird daraus `douglas` — das trifft oft, aber nicht
immer. Erkennt sie nichts, wird die Firma nicht aufgenommen und im Register
ohne System-Eintrag geführt. Lieber kein Treffer als ein falscher, denn ein
falsch erkanntes System würde fremde Stellen unter dem Namen der Firma
einsortieren.

Das Raster war anfangs zu eng: In 16 Läufen hat die Selbstreparatur keinen
einzigen der zwölf defekten Adapter repariert. Zwei Beispiele, die zeigen warum —
Swarovski fährt Workday unter dem Site-Namen `swarovski`, aber die Site-Liste
kannte nur `External`, `careers`, `Careers`, `{slug}careers` und
`broadbean_external`; der bloße Firmenname fehlte. adidas liegt auf
`jobs.adidas-group.com`, geprüft wurden nur `careers.{slug}.com` und
`jobs.{slug}.com`. Seit dem 18.08.2026 gibt es mehr Slug-Varianten, mehr
Site-Namen, mehr Rechenzentren und das Feld `hints` für konkrete Vorgaben.
Am Prinzip ändert sich nichts: übernommen wird nur, was antwortet.

**Höflichkeit ist eingebaut:** 1,0 bis 1,5 Sekunden Pause zwischen Abrufen.
Bitte nicht runtersetzen — sonst wirst du geblockt, und zwar zu Recht.

---

## Struktur

```
config/companies.yaml     fest ueberwachte Firmen (waechst automatisch)
config/scoring.yaml       dein Filter
config/discovery.yaml     breite Suche: Laender, Suchbegriffe, Blocklist
src/adapters/             ein Adapter pro Bewerbersystem, nicht pro Firma
src/discovery.py          Stufe 1 - Adzuna
src/employers.py          Stufe 2 - Firmenregister
src/detect.py             Stufe 3 - erkennt das Bewerbersystem einer Firma
src/score.py              Bewertung
src/store.py              SQLite, erkennt was neu ist, fuehrt die Quellenampel
src/render.py             Dashboard + Excel
src/probe.py              Diagnose der festen Firmenliste, schlaegt Fixes vor
src/scrape.py             Hauptlauf
.github/workflows/scrape.yml   taeglicher Lauf, 06:00 UTC
.github/workflows/probe.yml    Probe-Lauf auf Knopfdruck
docs/                     wird von GitHub Pages ausgeliefert
data/jobs.db              Zustand, wird vom Workflow committet
```

Zwei Dateien ändert das Skript selbst: `data/jobs.db` und `config/companies.yaml`
(wenn eine entdeckte Firma aufgenommen wird). Wenn du `companies.yaml` im Browser
bearbeitest, kann es dabei zu einem Konflikt kommen — dann einfach die Seite neu
laden und noch einmal speichern.

Der Kniff liegt in `src/adapters/`: dort steht ein Adapter je Bewerbersystem,
nicht je Unternehmen. Weil sich die meisten Konzerne auf eine Handvoll Systeme
verteilen, deckt eine neue Firma meist schon ein vorhandener Adapter ab —
sie einzutragen kostet dann vier Zeilen YAML.
