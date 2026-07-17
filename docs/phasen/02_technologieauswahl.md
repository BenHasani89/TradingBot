# Phase 2 – Technologieauswahl

Status: **Abgeschlossen** (wartet auf deine Bestätigung, um zu Phase 3 überzugehen)
Datum: 2026-07-17

Grundlage: [01_systemarchitektur.md](01_systemarchitektur.md)

Hinweis: Auch diese Phase ist reine Planung – **es wird noch kein Code geschrieben**. Es werden
konkrete Bibliotheken/Frameworks ausgewählt und begründet.

---

## 1. Kritische Bewertung der bestehenden Architektur (Phase 1)

Bevor Technologien gewählt werden, hier eine ehrliche Prüfung der Architektur aus
[01_systemarchitektur.md](01_systemarchitektur.md). Ergebnis vorweg: **Die Grundstruktur trägt.**
Modularer Monolith, Adapter-Pattern für Datenquellen, gemeinsame Logik für Backtest und Live-Betrieb
– das sind an dieser Stelle keine Fehlentscheidungen und werden nicht verworfen. Es gibt aber vier
Lücken, die bei der Technologieauswahl mitgedacht werden müssen und die Architektur-Doku am Ende
dieser Phase in einer kurzen Ergänzung erhält:

| # | Lücke in Phase 1 | Risiko, wenn ignoriert | Lösung (fliesst in Technologieauswahl ein) |
|---|---|---|---|
| 1 | Dashboard und Trading-Kern waren implizit "ein Prozess" | Ein langsamer Dashboard-Request oder ein Absturz der Web-Oberfläche könnte den Trading-Zyklus verzögern oder mitreissen | Zwei getrennte Prozesse (Core-Prozess + Dashboard-Prozess) **in derselben Codebasis**, Kommunikation über die Datenbank und eine schlanke interne API |
| 2 | SQLite-Nebenläufigkeit nicht adressiert | Gleichzeitiges Lesen (Dashboard) und Schreiben (Core) kann zu `database is locked`-Fehlern führen | SQLite im **WAL-Modus**, kurze Transaktionen, ORM-Wahl darauf abgestimmt |
| 3 | Scheduler kennt keine Börsenzeiten | Krypto handelt 24/7, Aktien nur zu Börsenöffnungszeiten + ohne Feiertage – ein naiver "alle 15 Min"-Scheduler würde ausserhalb der Handelszeiten sinnlos Aktien-Daten abfragen bzw. Signale auf veralteten/fehlenden Daten erzeugen | Scheduler-Bibliothek kombiniert mit einer Handelskalender-Prüfung für Aktien |
| 4 | Konfigurations-/Secrets-Schicht war nur als Platzhalter benannt | Ohne konkrete Festlegung besteht die Gefahr, dass API-Schlüssel doch im Code landen | Konkrete Bibliothek mit Validierung beim Start (siehe Punkt 13) |

Diese vier Punkte sind **Ergänzungen**, keine Kurskorrektur – sie werden unten bei den jeweiligen
Technologie-Entscheidungen aufgelöst und am Ende als kurzer Nachtrag in `01_systemarchitektur.md`
ergänzt.

---

## 2. Bewertungskriterien

Jede Entscheidung wird konsistent gegen dieselben fünf Kriterien geprüft:

- **Wartbarkeit** – wie leicht bleibt der Code in einem Jahr verständlich und änderbar?
- **Einfachheit für Solo-Entwicklung** – wie viel Einarbeitungs-/Betriebsaufwand für eine Person?
- **Erweiterbarkeit Richtung Echtgeldhandel** – erschwert die Wahl den Übergang in Phase 12?
- **Kosten** – bleibt es innerhalb des 0 €-Budgets der Entwicklungsphase?
- **Community-Unterstützung** – aktiv gepflegt, gute Dokumentation, langfristig verfügbar?

---

## 3. Technologie-Entscheidungen

### 3.1 Python-Version

| Option | Vorteile | Nachteile |
|---|---|---|
| Python 3.13 (neueste) | Neueste Sprachfeatures, beste Performance | Manche Bibliotheken (v. a. mit C-Erweiterungen) hinken bei Kompatibilität hinterher |
| **Python 3.12** | Stabil, breite Bibliotheks-Unterstützung, aktueller Support-Zeitraum bis ~2028 | Nicht ganz die neueste Version |
| Python 3.11 | Sehr stabil, maximale Kompatibilität | Wird mittelfristig älter, kein Vorteil gegenüber 3.12 für dieses Projekt |

**Eignung:** Für ein Projekt mit Datenanalyse-Bibliotheken (pandas, ggf. ML in Phase 8) ist
Kompatibilität wichtiger als das allerneueste Feature-Set.

**Empfehlung: Python 3.12.** Guter Mittelweg zwischen Aktualität und garantierter Kompatibilität
mit dem gesamten Daten-/Finance-Ökosystem. Installation auf macOS unkompliziert über `pyenv` oder
Homebrew (Details in Phase 3).

---

### 3.2 Virtuelle Umgebung / Dependency Management

| Option | Vorteile | Nachteile |
|---|---|---|
| venv + pip + requirements.txt | Standardbibliothek, keine Zusatzinstallation, jeder kennt es | Kein echtes Lockfile ohne Zusatzwerkzeug (pip-tools), manuelles Versions-Pinning |
| Poetry | Ausgereift, Lockfile, Paket-Metadaten, grosse Community | Eigene, teils langsame Resolver-Logik, zusätzliches Tool-Konzept zu lernen |
| **uv** (Astral) | Sehr schnell (Rust-basiert), vereint venv + pip + Lockfile in einem Tool, moderner Standard, gleiche Firma wie der empfohlene Linter (Ruff, siehe 3.14) | Jünger als Poetry, aber inzwischen breit adoptiert |
| conda | Gut für binäre Abhängigkeiten (z. B. TA-Lib) | Deutlich schwerer, Lizenzänderungen bei den "defaults"-Channels seit 2024 können bei kommerzieller Nutzung Kosten auslösen – Risiko für ein Projekt mit späterem Echtgeld-Bezug |

**Eignung:** Solo-Entwicklung profitiert am meisten von einem Tool mit wenig Konfigurationsaufwand
und schnellen Installationen (kurze Feedback-Schleifen).

**Empfehlung: uv.** Ein Tool für virtuelle Umgebung, Paketinstallation und Lockfile, sehr schnell,
kostenlos, wachsende Community, passt zum übrigen modernen Tooling-Stack (siehe Ruff unten). Poetry
wäre die solide, etwas schwergewichtigere Alternative, falls sich uv im Projektverlauf nicht bewährt.

---

### 3.3 Backend-Framework

Hier geht es um eine schlanke interne API-Schicht (siehe Ergänzung 1 aus der Architekturkritik), die
Dashboard-Prozess und Trading-Kern-Prozess verbindet und später auch externen Clients (z. B.
Benachrichtigungsdienst, evtl. mobile Ansicht) offenstehen kann.

| Option | Vorteile | Nachteile |
|---|---|---|
| **FastAPI** | Modern, async-fähig, automatische OpenAPI-Doku, Typvalidierung via Pydantic, riesige Community, sehr gut geeignet für spätere Broker-Webhooks (Order-Status) | Etwas mehr Konzepte zu lernen als Flask (async, Pydantic-Modelle) |
| Flask | Einfach, sehr ausgereift, riesiges Ökosystem | Synchron, weniger eingebaute Validierung, für die Steuerbefehle/Statusabfragen kein klarer Vorteil gegenüber FastAPI |
| Django (+DRF) | "Batteries included", Admin-Oberfläche, ORM eingebaut | Deutlich zu schwergewichtig für ein Solo-Backend ohne Multi-User-Anforderungen, hoher Einarbeitungsaufwand |
| Kein Backend, Dashboard direkt auf DB | Am einfachsten, kein zusätzliches Modul | Verletzt die in Phase 1 festgelegte Trennung, erschwert spätere Erweiterungen (z. B. Benachrichtigungen, mobiler Zugriff), kein sauberer Ort für Steuerbefehle wie Not-Aus |

**Eignung:** Da Dashboard und Trading-Kern laut Architekturkritik als getrennte Prozesse laufen
sollen, braucht es eine klar definierte Schnittstelle zwischen ihnen – dafür ist eine schlanke API
sinnvoller als impliziten Datenbank-Zugriff von beiden Seiten.

**Empfehlung: FastAPI.** Passt zur asynchronen Natur von Marktdaten-Abrufen, liefert automatische
Validierung (wichtig bei einer Trading-Anwendung, wo fehlerhafte Eingaben teuer werden können – auch
im Paper-Modus als Übungssache für Phase 12), und legt die Basis für Punkt 9 (ORM/SQLModel) und
Punkt 10 (Dashboard). Community und Dokumentation sind exzellent, Entwicklung sehr aktiv.

---

### 3.4 Datenverarbeitung

| Option | Vorteile | Nachteile |
|---|---|---|
| **pandas** | Industriestandard für Finanzdaten, praktisch jede Indikator-/Analyse-Bibliothek erwartet pandas-DataFrames, riesige Community, unzählige Tutorials speziell für Trading | Etwas langsamer als polars bei sehr grossen Datenmengen |
| polars | Deutlich schneller, moderner, speichereffizienter | Ökosystem-Kompatibilität mit Trading-/Indikator-Bibliotheken schwächer, kleinere Community, mehr Reibung beim Einbinden bestehender Finance-Tools |
| Nur numpy | Sehr schnell, minimal | Zu low-level, man müsste Zeitreihen-Funktionalität selbst nachbauen – unnötige Komplexität |

**Eignung:** Swing-Trading-Datenmengen (Kerzen im 15-Minuten- bis Tages-Takt für einige Dutzend
Symbole) sind klein genug, dass Performance-Unterschiede zwischen pandas und polars irrelevant sind.
Ökosystem-Kompatibilität ist der entscheidende Faktor.

**Empfehlung: pandas.** Beste Kompatibilität mit Indikator-Bibliotheken (3.5), Backtesting (3.6) und
den SDKs von Binance/Alpaca. Ein späterer Wechsel zu polars wäre möglich, ist aber aktuell nicht
nötig (Regel 6: keine unnötige Komplexität).

---

### 3.5 Technische Indikatoren

| Option | Vorteile | Nachteile |
|---|---|---|
| TA-Lib | Sehr schnell (C-Bibliothek), riesiger Funktionsumfang, Industriestandard | Erfordert Installation der C-Bibliothek via Homebrew vor dem Python-Paket – zusätzliche Einrichtungshürde auf macOS |
| **pandas-ta** | Reines Python, einfache Installation ohne Compiler, grosser Indikator-Umfang, direkte pandas-Integration | Community-Aktivität schwankt zeitweise – Risiko wird durch geringe Abhängigkeit von Exotik minimiert |
| Eigene Implementierung der Kernindikatoren | Volle Kontrolle, keine Fremdabhängigkeit | Mehr Aufwand, Fehlerrisiko bei Eigenimplementierung von z. B. Wilder-Glättung (RSI) |

**Eignung:** Für Phase 5 werden voraussichtlich nur wenige Indikatoren gebraucht (z. B. gleitende
Durchschnitte, RSI, MACD, ATR für Stop-Loss-Berechnung). Eine einfache Installation ohne
C-Toolchain ist für Solo-Entwicklung auf macOS klar von Vorteil.

**Empfehlung: pandas-ta.** Deckt den benötigten Indikator-Umfang ab, lässt sich ohne
Compiler-Hürden installieren. Sollte die Pflege eines einzelnen benötigten Indikators einmal
stocken, lässt sich dieser jederzeit punktuell selbst nachbauen (geringes Risiko, da Kernindikatoren
mathematisch einfach sind). TA-Lib bleibt eine Option, falls später Performance oder
Indikator-Breite zum Engpass werden.

---

### 3.6 Backtesting-Framework

| Option | Vorteile | Nachteile |
|---|---|---|
| backtrader | Bekannt, ereignisbasiert | Entwicklung ist seit Jahren nahezu eingeschlafen, erzwingt eigene Strategie-/Order-Abstraktionen – würde dem Phase-1-Prinzip "gleiche Logik für Backtest und Live" widersprechen |
| vectorbt | Sehr schnell (vektorisiert), gut für Parameter-Optimierung | Vektorisierter Ansatz passt schlecht zur Kerzen-für-Kerzen-Entscheidungslogik, die live wiederverwendet werden soll; Open-Source-Version weniger aktiv gepflegt als die kommerzielle Pro-Version |
| Backtesting.py | Leichtgewichtig, einfache API | Eigenständiges Tool ohne Wiederverwendung der Live-Trading-Logik – gleiches Problem wie backtrader |
| **Eigene Backtesting-Engine** (wie in Phase 1 architektiert) | Nutzt exakt dieselbe Strategie-/Risiko-/Ausführungs-/Portfolio-Logik wie der Live-Betrieb, keine Fremd-Abstraktionen, volle Kontrolle über Look-Ahead-Bias-Vermeidung | Muss selbst gebaut werden (mehr Aufwand als ein Framework "von der Stange") |

**Eignung:** Das zentrale Architekturprinzip aus Phase 1 – identische Logik in Backtest und
Live-Betrieb – lässt sich mit keinem der genannten Frameworks sauber umsetzen, da sie alle eigene
Strategie-/Order-Modelle vorschreiben.

**Empfehlung: Eigene Backtesting-Engine auf Basis von pandas**, wie bereits in
[01_systemarchitektur.md](01_systemarchitektur.md) Abschnitt 7 vorgesehen. Diese Entscheidung
**bestätigt** die bestehende Architektur, statt sie zu ändern. `Backtesting.py` oder `vectorbt`
können optional zur **Gegenprobe** einzelner Ergebnisse herangezogen werden, sind aber nicht die
primäre Engine.

---

### 3.7 Scheduler

| Option | Vorteile | Nachteile |
|---|---|---|
| **APScheduler** | Ausgereift, reine Python-Lösung, unterstützt Cron- und Intervall-Jobs, aktiv gepflegt, lässt sich gut mit FastAPI kombinieren | Kein verteiltes System (aber das wird auch nicht gebraucht) |
| `schedule`-Bibliothek | Sehr simpel | Keine Persistenz, keine native Unterstützung für komplexere Zeitpläne (z. B. Börsenkalender) |
| Celery + Redis/RabbitMQ | Sehr mächtig, verteilt | Deutlich überdimensioniert für einen Einzelprozess-Bot, zusätzliche Infrastruktur (Message Broker) widerspricht dem 0 €-Budget und Regel 6 |
| Betriebssystem-Cron | Einfach | Schlechter in die Anwendung integriert (Logging, Fehlerbehandlung, Status), weniger portabel |

**Eignung:** Direkt bezogen auf Lücke 3 aus der Architekturkritik: Aktien und Krypto brauchen
unterschiedliche Zeitpläne (Krypto 24/7, Aktien nur während Börsenöffnungszeiten).

**Empfehlung: APScheduler**, kombiniert mit der Bibliothek `pandas_market_calendars` zur Prüfung von
Börsenöffnungszeiten/-feiertagen für die Aktien-Abfragen. Krypto-Jobs laufen durchgehend im
gewählten Intervall, Aktien-Jobs prüfen vor jedem Lauf den Handelskalender. Beides bleibt in einem
Prozess, kein zusätzlicher Infrastruktur-Bedarf.

---

### 3.8 Datenbank

| Option | Vorteile | Nachteile |
|---|---|---|
| **SQLite (WAL-Modus)** | Dateibasiert, kein Server, 0 € Kosten, für Swing-Trading-Datenmengen mehr als ausreichend, WAL-Modus erlaubt gleichzeitiges Lesen (Dashboard) und Schreiben (Core) | Bei sehr hoher paralleler Schreiblast ungeeignet (hier irrelevant) |
| PostgreSQL | Robuste Nebenläufigkeit, produktionsreif | Braucht einen laufenden Datenbankserver – unnötiger Aufwand/Kosten in der jetzigen Phase |
| DuckDB | Sehr schnell für Analysen (OLAP) | Für transaktionale Schreibvorgänge (einzelne Trades/Positionen aktualisieren) nicht das primäre Einsatzgebiet |

**Eignung:** Bestätigt die Wahl aus Phase 1, mit einer konkreten Ergänzung zur Lösung von Lücke 2
(Nebenläufigkeit).

**Empfehlung: SQLite im WAL-Modus** (Write-Ahead-Logging) für die gesamte Entwicklungs- und
Paper-Trading-Phase. Der WAL-Modus erlaubt, dass der Dashboard-Prozess liest, während der
Core-Prozess schreibt, ohne sich gegenseitig zu blockieren – das löst die in der Architekturkritik
identifizierte Lücke. Migration zu PostgreSQL bleibt für den 24/7-VPS-Betrieb (Phase 10) als Option
bestehen, dank ORM-Abstraktionsschicht (siehe 3.9) ohne grösseren Umbau möglich.

---

### 3.9 ORM

| Option | Vorteile | Nachteile |
|---|---|---|
| **SQLModel** | Kombiniert SQLAlchemy (Datenbank) und Pydantic (Validierung) in einer Modell-Definition, entwickelt vom FastAPI-Autor, passt nahtlos zu FastAPI (3.3), weniger doppelter Code | Jünger als reines SQLAlchemy, kleineres (aber wachsendes) Ökosystem |
| SQLAlchemy (klassisch) | Der De-facto-Standard, extrem ausgereift, Alembic für Migrationen | Getrennte Modelle für DB-Schema und API-Validierung nötig – mehr Code-Duplizierung |
| Peewee | Einfache API | Kleinere Community, schwächere Migrations-Tools, keine natürliche FastAPI/Pydantic-Integration |
| Rohes SQL ohne ORM | Volle Kontrolle | Mehr Boilerplate, manuelle Migrationen, erschwert den in Phase 1 vorgesehenen späteren DB-Wechsel |

**Eignung:** Da FastAPI (3.3) bereits gewählt wurde, ist die Kombination aus SQLAlchemy und Pydantic
in einem Modell besonders wartungsarm – ein Modell dient gleichzeitig als Datenbank-Schema und als
API-Datentyp.

**Empfehlung: SQLModel**, mit Alembic für Datenbank-Migrationen (kommt technisch aus dem
SQLAlchemy-Ökosystem). Reduziert Duplizierung für eine Einzelperson deutlich, bleibt aber im Kern
SQLAlchemy – bei Bedarf ist ein Wechsel zu reinem SQLAlchemy jederzeit möglich, da SQLModel darauf
aufbaut statt es zu ersetzen.

---

### 3.10 Dashboard-Framework

| Option | Vorteile | Nachteile |
|---|---|---|
| **Streamlit** | Sehr schneller Einstieg, riesige Community speziell im Finance-/Data-Bereich, minimaler Frontend-Aufwand, gute Chart-Integration | "Rerun-von-oben-nach-unten"-Modell macht feingranulare Echtzeit-Updates und Steuerbefehle (Not-Aus) etwas unkonventioneller umzusetzen |
| Dash (Plotly) | Flexibler/komponentenbasierter als Streamlit | Steilere Lernkurve, mehr Code für denselben Funktionsumfang |
| FastAPI + eigenes Frontend (HTML/JS) | Maximale Kontrolle, ein Technologie-Stack mit dem Backend | Deutlich mehr Entwicklungsaufwand, Frontend-Kenntnisse nötig |
| NiceGUI | Python-only, baut direkt auf FastAPI/Starlette auf, näher an Echtzeit-Interaktionen | Kleinere Community als Streamlit, weniger Trading-spezifische Tutorials |

**Eignung:** Für Solo-Entwicklung mit dem Ziel "möglichst schnell ein funktionierendes,
professionell wirkendes Dashboard" ist die Entwicklungsgeschwindigkeit entscheidend. Die in Phase 1
geforderten Steuerbefehle (Start/Pause/Not-Aus) lassen sich über einen Status-Datensatz in der
Datenbank lösen, den der Core-Prozess pro Zyklus prüft – das passt zum ohnehin DB-vermittelten
Kommunikationsmodell zwischen den beiden Prozessen und macht Streamlits Einschränkung
unproblematisch.

**Empfehlung: Streamlit.** Schnellster Weg zu einem funktionierenden, gut aussehenden Dashboard in
reinem Python, riesige Community mit vielen Trading-Dashboard-Beispielen. **NiceGUI** ist die
naheliegende Aufwertung, falls später engere Echtzeit-Interaktion gewünscht ist (baut auf demselben
FastAPI/Starlette-Fundament auf wie das Backend) – kein Grund, jetzt schon den höheren initialen
Aufwand zu tragen.

---

### 3.11 Testing-Framework

| Option | Vorteile | Nachteile |
|---|---|---|
| **pytest** | De-facto-Standard, einfache Syntax, riesiges Plugin-Ökosystem (Coverage, Mocking, async-Support für FastAPI) | – |
| unittest (Standardbibliothek) | Keine Zusatzabhängigkeit | Deutlich mehr Boilerplate, unüblich für neue Projekte |

**Eignung:** Regel 8 aus dem Master-Prompt fordert, dass jede Funktion getestet wird – pytest ist
hierfür der Community-Standard mit der besten Werkzeugunterstützung.

**Empfehlung: pytest**, ergänzt um `pytest-cov` (Testabdeckung), `pytest-mock` (Mocking der
Binance-/Alpaca-Aufrufe in Tests, damit Tests nicht von echten APIs abhängen) und
`httpx`/`pytest-asyncio` für Tests der FastAPI-Endpunkte.

---

### 3.12 Logging

| Option | Vorteile | Nachteile |
|---|---|---|
| Standard-`logging` | Eingebaut, keine Abhängigkeit, maximal flexibel | Viel Konfigurations-Boilerplate für vernünftige Formatierung/Rotation |
| structlog | Strukturierte/JSON-Logs, ideal für spätere Log-Aggregation | Mehr Einrichtungsaufwand, lohnt sich erst mit zentralem Log-Tooling auf einem VPS |
| **loguru** | Nahezu ohne Konfiguration einsatzbereit, sinnvolle Standardeinstellungen (Konsole + rotierende Datei), einfach um weitere "Sinks" erweiterbar (z. B. Telegram-Benachrichtigung in Phase 11) | Zusätzliche Abhängigkeit (aber sehr leichtgewichtig) |

**Eignung:** Für Solo-Entwicklung zählt eine gute Out-of-the-box-Erfahrung ohne grosses
Konfigurations-Setup, aber mit Raum für spätere Erweiterung (Benachrichtigungen bei kritischen
Fehlern, Phase 11).

**Empfehlung: loguru.** Minimaler Konfigurationsaufwand, gute Lesbarkeit im Terminal während der
Entwicklung, eingebaute Log-Rotation für den späteren Dauerbetrieb. Ein Wechsel zu `structlog` bleibt
möglich, falls auf dem VPS später strukturierte Logs für ein Monitoring-System (Phase 10) gebraucht
werden.

---

### 3.13 Konfigurationsmanagement

Direkt bezogen auf Lücke 4 aus der Architekturkritik.

| Option | Vorteile | Nachteile |
|---|---|---|
| **pydantic-settings** | Typsichere Konfiguration aus Umgebungsvariablen/`.env`-Datei, validiert beim Programmstart (Fehler werden sofort sichtbar, nicht erst mitten im Trading-Zyklus), passt nahtlos zu FastAPI/SQLModel | Zusätzliches (aber bereits im Stack vorhandenes) Pydantic-Konzept |
| Nur `.env` + `python-dotenv` | Einfach, verbreitet | Keine automatische Typprüfung, Fehler fallen erst zur Laufzeit auf |
| Config im Code | Kein Zusatzaufwand | Verstösst gegen die Sicherheitsanforderung "keine Passwörter im Code" (Phase 11) – nicht akzeptabel |

**Eignung:** Bei einer Anwendung, die (perspektivisch) Geld bewegt, ist eine Konfiguration, die
**beim Start fehlschlägt**, wenn z. B. ein API-Schlüssel fehlt, klar sicherer als ein stiller Fehler
mitten im Betrieb.

**Empfehlung:** Zweigeteilt, um Geheimnisse und fachliche Einstellungen sauber zu trennen:

- **Geheimnisse & Umgebungseinstellungen** (API-Schlüssel, Datenbankpfad): `pydantic-settings`,
  geladen aus einer lokalen, **nicht versionierten** `.env`-Datei.
- **Strategie-/Risiko-Parameter** (z. B. Positionsgrössen-Prozentsatz, RSI-Schwellenwerte): eine
  versionierbare **TOML-Datei**, gelesen über das seit Python 3.11 in der Standardbibliothek
  enthaltene `tomllib` – keine Zusatzabhängigkeit, menschlich lesbar, gut diff-fähig in Git.

---

### 3.14 Code-Qualität (Formatter/Linter)

| Option | Vorteile | Nachteile |
|---|---|---|
| Black + Flake8 + isort | Klassische, bewährte Kombination | Drei separate Tools mit drei Konfigurationen zu pflegen |
| **Ruff** | Ein einziges, sehr schnelles (Rust-basiertes) Tool für Linting, Formatierung und Import-Sortierung, hat sich als neuer Community-Standard etabliert, enthält auch sicherheitsrelevante Regeln | Jünger als Black/Flake8, aber inzwischen extrem breite Adoption |

**Eignung:** Für Solo-Entwicklung ist ein einziges, schnelles Tool mit einer Konfigurationsdatei
klar wartungsärmer als drei separate Tools.

**Empfehlung: Ruff.** Deckt Linting, Formatierung und Import-Sortierung in einem Tool ab, stammt vom
selben Team wie das gewählte Dependency-Management-Tool `uv` (Astral) – ein kohärenter, moderner
Werkzeug-Stack. Sicherheitsrelevante Lint-Regeln sind ein zusätzlicher Vorteil im Hinblick auf die
spätere Echtgeld-Erweiterung.

---

## 4. Zusammenfassung – finaler Technologie-Stack

| # | Bereich | Entscheidung | Kernbegründung |
|---|---|---|---|
| 1 | Python-Version | **3.12** | Stabilität + breite Bibliothekskompatibilität |
| 2 | Dependency Management | **uv** | Ein schnelles Tool für venv, Pakete, Lockfile |
| 3 | Backend-Framework | **FastAPI** | Async, Typvalidierung, Basis für Dashboard-Trennung |
| 4 | Datenverarbeitung | **pandas** | Ökosystem-Kompatibilität mit Finance-Tools |
| 5 | Technische Indikatoren | **pandas-ta** | Reines Python, keine Compiler-Hürde auf macOS |
| 6 | Backtesting | **Eigene Engine** | Identische Logik wie Live-Betrieb (Phase-1-Prinzip) |
| 7 | Scheduler | **APScheduler** + `pandas_market_calendars` | Cron/Intervall + Börsenkalender-Bewusstsein |
| 8 | Datenbank | **SQLite (WAL-Modus)** | 0 €, dateibasiert, löst Nebenläufigkeits-Lücke |
| 9 | ORM | **SQLModel** | SQLAlchemy + Pydantic in einem Modell, passt zu FastAPI |
| 10 | Dashboard | **Streamlit** | Schnellster Weg zu professionellem Dashboard, riesige Community |
| 11 | Testing | **pytest** | Community-Standard, bestes Tooling |
| 12 | Logging | **loguru** | Minimaler Konfigurationsaufwand, erweiterbar |
| 13 | Konfiguration | **pydantic-settings** (Secrets) + **TOML** (Parameter) | Fail-fast bei fehlender Konfiguration, saubere Trennung |
| 14 | Code-Qualität | **Ruff** | Ein Tool statt drei, moderner Standard |

**Kostenprüfung:** Alle 14 Technologien sind Open-Source und kostenlos. Das 0 €-Budget der
Entwicklungsphase bleibt vollständig eingehalten.

---

## 5. Auswirkung auf die Architektur-Dokumentation

Die vier in Abschnitt 1 identifizierten Lücken werden als kurzer Nachtrag in
[01_systemarchitektur.md](01_systemarchitektur.md) ergänzt (Prozess-Trennung Dashboard/Core,
WAL-Modus, Börsenkalender im Scheduler, konkrete Config-Schicht) – die Grundarchitektur selbst bleibt
unverändert gültig.

---

## 6. Nächste Schritte

Mit dem festgelegten Technologie-Stack kann Phase 3 (Entwicklungsumgebung) konkret werden:
Installation von Python 3.12, uv, VS Code, Einrichtung der Projektstruktur gemäss Phase 1, sowie die
Konten-Checkliste (GitHub, Binance, Alpaca).

**Phase abgeschlossen. Möchtest du mit der nächsten Phase fortfahren?**
