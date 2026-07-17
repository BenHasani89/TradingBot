# Phase 3 – Entwicklungsumgebung

Status: **Abgeschlossen** (wartet auf deine Bestätigung, um zu Phase 4 überzugehen)
Datum: 2026-07-17

Grundlage: [00_projektanalyse.md](00_projektanalyse.md), [01_systemarchitektur.md](01_systemarchitektur.md),
[02_technologieauswahl.md](02_technologieauswahl.md)

---

## 1. Kritische Prüfung vor Beginn (neuer Kontext: Schweiz, spätere Kunden/Mitarbeiter)

Du hast für diese Phase zwei neue Rahmenbedingungen genannt, die bisher nicht Teil der Anforderungen
waren: **Entwicklung in der Schweiz** und **spätere mögliche Nutzung durch Kunden oder Mitarbeiter**
(nicht mehr nur durch dich persönlich). Das wird hier ehrlich bewertet, bevor irgendetwas gebaut wird.

### 1.1 Rechtlicher Hinweis (wichtigster Punkt – keine Rechtsberatung)

Sobald ein System wie dieses nicht mehr nur dem Eigengebrauch dient, sondern **Dritte** (Kunden,
Mitarbeiter) damit handeln, Trading-Signale erhalten oder ihr Vermögen darüber verwaltet wird,
bewegt sich das potenziell im Anwendungsbereich der Schweizer Finanzmarktregulierung – u. a.
möglicher Bewilligungs- oder Registrierungspflichten nach **FINIG** (Finanzinstitutsgesetz) und
Pflichten nach **FIDLEG** (Finanzdienstleistungsgesetz), sowie datenschutzrechtlicher Pflichten nach
dem revidierten **Datenschutzgesetz (revDSG)**, sobald Personendaten von Kunden/Mitarbeitern
verarbeitet werden.

Das ist eine **rechtliche Fragestellung, keine technische** – ich bin kein Anwalt und dies ist keine
Rechtsberatung. Ich flagge es hier bewusst deutlich, weil Regel 4 des Projekts ("Frage mich bei
wichtigen Entscheidungen") das verlangt und weil es die technische Planung direkt beeinflusst.

**Konsequenz für dieses Projekt:** Es wird **keine Funktion gebaut, die Kunden- oder
Mitarbeiter-Onboarding technisch ermöglicht**, bevor du das mit einer Fachperson für
Finanzmarktrecht/Compliance geklärt hast. Die aktuelle und alle folgenden Phasen bleiben auf
**Paper-Trading für den Eigengebrauch** ausgerichtet. Sollte eine Nutzung durch Dritte später
tatsächlich verfolgt werden, ist das ein eigener, expliziter Meilenstein außerhalb der aktuellen
Roadmap – nicht etwas, das "nebenbei" in Phase 9 (Dashboard) entsteht.

### 1.2 Technische Konsequenz: bewusst KEINE Mandantenfähigkeit jetzt

Die Architektur aus Phase 1/2 ist für **eine** Person ausgelegt (eine SQLite-Datei, kein
Login-System). Für Kunden/Mitarbeiter bräuchte es Benutzerverwaltung, Authentifizierung,
Zugriffskontrolle pro Mandant und eine Audit-Historie. Zielkonflikt: Der Master-Prompt fordert
gleichzeitig "keine unnötige Komplexität" **und** "produktionsfähige Struktur von Anfang an". Diese
beiden Ziele werden hier bewusst so aufgelöst:

- **Jetzt nicht bauen:** Kein Login, keine Mandantentrennung, keine Rollenverwaltung – das wäre vor
  der rechtlichen Klärung ohnehin verfrüht und reine Spekulation (Regel 6).
- **Aber nicht verbauen:** FastAPI als Backend (statt Streamlit-only) und SQLModel als ORM wurden in
  Phase 2 genau deshalb gewählt, weil sie Authentifizierung/Autorisierung später sauber ergänzen
  können, ohne die Kernmodule (Strategie, Risiko, Portfolio) anzufassen. Die Projektstruktur (Punkt
  3) hält Backend (`api/`) und Dashboard (`dashboard/`) bereits als getrennte Prozesse.

### 1.3 Datenschutz – Merkposten für später

Sobald überhaupt Personendaten (auch nur Name/E-Mail für einen Zugang) verarbeitet werden, greift
das revDSG: Datenminimierung, Zweckbindung, ggf. Wahl eines VPS-Standorts in der Schweiz/EU (Phase
10). Für die aktuelle Paper-Trading-Phase mit dir als einzigem Nutzer ist das **nicht akut**, wird
aber hier dokumentiert, damit es bei der VPS-Wahl (Phase 10) nicht vergessen geht.

### 1.4 Bestätigung der bisherigen Architektur

Abgesehen von den beiden Punkten oben hält die Architektur aus Phase 1/2 einer erneuten Prüfung
stand: Der modulare Monolith mit getrennten Core-/Dashboard-Prozessen, SQLite im WAL-Modus, die
eigene Backtesting-Engine und der Konfigurations-Split (Secrets vs. Parameter) sind weiterhin
sinnvoll und werden **nicht geändert**. Die vier in Phase 2 identifizierten Lücken sind bereits im
Nachtrag zu [01_systemarchitektur.md](01_systemarchitektur.md) dokumentiert.

---

## 2. Python-Entwicklungsumgebung

### 2.1 Aktueller Stand deines Systems (geprüft)

| Werkzeug | Gefunden | Bewertung |
|---|---|---|
| Python | 3.9.6 (`/usr/bin/python3`, Apple-Systemversion) | Zu alt für Zielversion 3.12 – Apples System-Python sollte generell nicht für Projekte verwendet werden |
| Homebrew | nicht installiert | Wird für eine saubere Python-/Tool-Installation empfohlen |
| pyenv | nicht installiert | Optional, siehe unten |
| uv | nicht installiert | Wird benötigt (Phase-2-Entscheidung) |
| VS Code CLI (`code`) | nicht gefunden | VS Code selbst evtl. vorhanden, nur CLI-Link fehlt |
| Git | 2.50.1 | Bereits vorhanden, nichts zu tun |

### 2.2 Python-Version

**Entscheidung (bestätigt aus Phase 2): Python 3.12.** Begründung siehe
[02_technologieauswahl.md](02_technologieauswahl.md) Abschnitt 3.1. Wichtig: **nicht** die
Apple-Systemversion 3.9.6 verwenden – diese wird von macOS selbst benötigt und sollte für eigene
Projekte tabu bleiben (Gefahr, das Betriebssystem zu beschädigen).

### 2.3 Installationsprozess (Schritt für Schritt)

Diese Befehle verändern deine globale Systemkonfiguration (nicht nur den Projektordner) – ich führe
sie erst nach deiner Bestätigung aus (siehe Ende dieses Dokuments), oder du führst sie selbst aus.

**Schritt 1 – Homebrew installieren** (Paketmanager für macOS, kostenlos, Standard-Werkzeug):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Schritt 2 – Python 3.12 über Homebrew installieren:**
```bash
brew install python@3.12
```

**Schritt 3 – uv installieren** (Dependency-Management, Phase-2-Entscheidung):
```bash
brew install uv
```

**Schritt 4 – Projektumgebung einrichten** (im Projektordner):
```bash
cd /Users/benmusic/Desktop/Tradingbot
uv venv --python 3.12
uv sync
```
`uv venv` legt `.venv/` an (bereits in `.gitignore` ausgeschlossen), `uv sync` installiert alle in
`pyproject.toml` festgelegten Abhängigkeiten in dieses `.venv`.

**Schritt 5 – VS Code CLI aktivieren** (nur falls VS Code bereits installiert ist, aber der `code`-Befehl
im Terminal fehlt): In VS Code über die Befehlspalette (Cmd+Shift+P) → "Shell Command: Install 'code'
command in PATH" ausführen. Falls VS Code noch gar nicht installiert ist: kostenloser Download unter
code.visualstudio.com.

### 2.4 Warum uv statt pyenv+pip?

pyenv wird häufig zur Verwaltung mehrerer Python-Versionen genutzt, ist hier aber nicht zwingend
nötig: `uv venv --python 3.12` kann bei Bedarf eigenständig eine passende Python-Version herunterladen
und verwalten, ohne ein zusätzliches Werkzeug. Das reduziert die Anzahl der zu pflegenden Tools
(Regel 6).

---

## 3. Projektstruktur

### 3.1 Kritische Prüfung der vorgeschlagenen Struktur

Die im Auftrag genannte Liste (`src/`, `tests/`, `docs/`, `config/`, `scripts/`, `data/`, `logs/`)
ist ein sinnvoller Ausgangspunkt, wurde aber an drei Stellen angepasst:

1. **`src/tradingbot/` statt nacktem `src/`.** Ein "src-Layout" mit einem benannten Package
   verhindert versehentliche Imports aus dem Arbeitsverzeichnis statt aus der installierten
   Umgebung – Standard-Praxis für produktionsfähige Python-Projekte und Voraussetzung dafür, dass
   `uv`/`pytest` das Projekt sauber als Package auflösen.
2. **Unterordner in `src/tradingbot/` entsprechen 1:1 den zehn Komponenten aus Phase 1**, ergänzt um
   die in Phase 2/3 beschlossene Trennung von `api/` (FastAPI, Steuerung) und `dashboard/`
   (Streamlit) als getrennte Prozesse (siehe Nachtrag in
   [01_systemarchitektur.md](01_systemarchitektur.md) Abschnitt 13).
3. **`data/` unterteilt in `historisch/` und `laufzeit/`**, beide nicht versioniert. Begründung:
   historische Marktdaten (Cache) und die laufende SQLite-Datenbank haben unterschiedliche
   Lebenszyklen (Cache kann gelöscht/neu aufgebaut werden, die Laufzeit-DB nicht) – getrennt zu
   halten vermeidet versehentliches Löschen der eigentlichen Handelsdaten bei einem Cache-Reset.
4. **`docs/handbuch/`** wurde ergänzt (siehe Punkt 6) – im Original-Auftrag nicht explizit gelistet,
   aber vom Master-Prompt und diesem Auftrag ("Dokumentationssystem", "technisches Handbuch",
   "Benutzerhandbuch") gefordert.

`tests/` wird bewusst **noch nicht** mit Unterordnern pro Modul vorbefüllt – das wäre verfrühte
Struktur ohne Inhalt (Regel 6). Unterordner entstehen ab Phase 4, sobald das erste Modul (`data/`)
tatsächlich Code und damit Tests bekommt.

### 3.2 Erstellte Struktur

```
Tradingbot/
├── src/tradingbot/
│   ├── core/            # Ablaufsteuerung, Scheduler, Not-Aus
│   ├── data/             # Datenquellen-Adapter, Validierung, Persistenz
│   ├── strategy/         # Indikatoren, Strategie-Interface
│   ├── risk/              # Positionsgrösse, SL/TP, Verlustlimits
│   ├── execution/         # Paper-Broker-Simulator
│   ├── portfolio/         # Kapitalverwaltung, Historie, Kennzahlen
│   ├── backtest/          # Backtesting-Engine
│   ├── api/                # FastAPI – interne Steuerungs-/Statusschnittstelle
│   ├── dashboard/          # Streamlit – Web-Oberfläche (eigener Prozess)
│   ├── monitoring/         # Logging, Health-Checks
│   └── config/             # Lade-Logik für Einstellungen (kein Fachcode)
├── tests/                  # Noch leer, siehe tests/README.md
├── docs/
│   ├── phasen/              # Diese Roadmap-Dokumentation (bereits vorhanden)
│   └── handbuch/
│       ├── technisch/       # Technisches Handbuch für Entwickler (Platzhalter)
│       └── benutzer/        # Benutzerhandbuch (Platzhalter, siehe Abschnitt 1.1)
├── config/
│   └── einstellungen.toml   # Versionierte Strategie-/Risiko-Parameter (Platzhalter)
├── scripts/                 # Hilfsskripte, noch leer
├── data/
│   ├── historisch/           # Cache historischer Marktdaten (nicht versioniert)
│   └── laufzeit/              # SQLite-Datenbank (nicht versioniert)
├── logs/                     # Rotierende Log-Dateien (nicht versioniert)
├── .vscode/                  # Editor-Konfiguration (versioniert)
├── .env.example               # Vorlage für Secrets (versioniert, ohne echte Werte)
├── .env                        # Echte Secrets (NIE versioniert, existiert erst nach dem Kopieren)
├── .gitignore
├── pyproject.toml              # Projekt-Metadaten, Abhängigkeiten, Tool-Konfiguration
└── README.md
```

Alle Ordner und Basisdateien wurden bereits angelegt. `src/tradingbot/*` enthält jeweils nur eine
leere `__init__.py` – **noch keine Fachlogik**, wie für diese Phase gefordert.

---

## 4. Entwicklungswerkzeuge

### 4.1 VS Code

Konfiguriert in `.vscode/settings.json`:
- Interpreter-Pfad zeigt auf `.venv/bin/python` (entsteht nach `uv venv`)
- Format-on-Save aktiv, Ruff als Standard-Formatter für Python
- Automatisches Sortieren der Imports und Auto-Fixes beim Speichern (Ruff)
- pytest als Test-Runner, `tests/` als Testverzeichnis
- `data/`, `logs/`, `.venv/` vom Datei-Watcher ausgeschlossen (Performance)

### 4.2 Empfohlene Extensions (`.vscode/extensions.json`)

| Extension | Zweck |
|---|---|
| `ms-python.python` | Python-Grundunterstützung |
| `ms-python.vscode-pylance` | Typprüfung, Autovervollständigung |
| `charliermarsh.ruff` | Linting + Formatierung (Phase-2-Entscheidung) |
| `tamasfe.even-better-toml` | Bearbeitung von `pyproject.toml`/`einstellungen.toml` |
| `eamodio.gitlens` | Git-Historie direkt im Editor |

### 4.3 Linter/Formatter

**Ruff** (Phase-2-Entscheidung), konfiguriert in `pyproject.toml` unter `[tool.ruff]`:
Zeilenlänge 100, Zielversion 3.12, aktivierte Regelgruppen: Fehler (E), Pyflakes (F), Import-Sortierung
(I), moderne Syntax (UP), häufige Bugs (B), Vereinfachungen (SIM) und sicherheitsrelevante Regeln
(S) – Letzteres bewusst im Hinblick auf die spätere Echtgeld-Erweiterung. In Tests ist Regel `S101`
(Verwendung von `assert`) ausgenommen, da `assert` dort der übliche und korrekte Weg ist.

### 4.4 Testing-Setup

**pytest** (Phase-2-Entscheidung), konfiguriert in `pyproject.toml` unter `[tool.pytest.ini_options]`:
Testverzeichnis `tests/`, `src/` im Python-Pfad, damit `from tradingbot... import ...` in Tests ohne
Installation funktioniert. Die Dev-Abhängigkeiten (`pytest-cov`, `pytest-mock`, `pytest-asyncio`,
`httpx`) sind in `pyproject.toml` unter `[dependency-groups] dev` hinterlegt und werden mit
`uv sync` installiert.

---

## 5. Git-Workflow

### 5.1 Wichtiger Befund: Es existiert bereits ein Git-Repository mit GitHub-Remote

Bei der Einrichtung wurde festgestellt, dass in diesem Ordner bereits ein Git-Repository mit einem
Commit (`Initial project structure - Phase 0 to 2 documentation`) und einem konfigurierten Remote
existiert:

```
origin  https://github.com/BenHasani89/TradingBot.git
```

Das habe ich **nicht selbst angelegt** – vermutlich ein automatischer Prüfpunkt-Mechanismus dieser
Arbeitsumgebung. Ich habe **nichts gepusht und nichts committet** und werde das ohne deine
ausdrückliche Aufforderung auch nicht tun (siehe Sicherheitsregeln). Bitte bestätige kurz: Ist
`github.com/BenHasani89/TradingBot` dein eigenes Repository? Falls ja, übernehmen wir es einfach als
Remote für den weiteren Verlauf; falls dir das unbekannt ist, schauen wir uns das gemeinsam genauer
an, bevor wir irgendetwas dorthin pushen.

### 5.2 Branch-Strategie

Für Solo-Entwicklung wird bewusst **kein** schweres Gitflow (mit `develop`, `release`, ...)
eingeführt – unnötige Komplexität für eine Person (Regel 6). Stattdessen:

- **`main`** – muss jederzeit lauffähig sein (Tests grün, keine kaputten Imports)
- **`feature/<kurzbeschreibung>`** – für jede grössere Änderung (neues Modul, neue Strategie), Merge
  nach `main` sobald Tests bestehen
- Reine Dokumentations-Commits (wie die `docs/phasen/*`-Dateien) dürfen direkt auf `main`
- **Tags** (z. B. `v0.1.0-paper`) markieren funktionsfähige Meilensteine, beginnend mit dem ersten
  lauffähigen Paper-Trading-Bot (Phase 7)

### 5.3 Commit-Regeln

- Kleine, thematisch fokussierte Commits statt grosser Sammel-Commits
- Präfix nach Art der Änderung (Community-Standard, englische Schlüsselwörter, Beschreibung auf
  Deutsch): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `config:`
  Beispiel: `docs: Phase 3 Entwicklungsumgebung dokumentiert`
- Code-Änderungen und die zugehörige Dokumentation (z. B. ein neues Modul + Handbuch-Ergänzung)
  gehören in denselben Commit, wo sinnvoll möglich

### 5.4 Umgang mit Dokumentation

`docs/phasen/` ist die massgebliche Quelle für getroffene Entscheidungen. Bereits abgeschlossene
Phasen werden **nicht rückwirkend überschrieben**, sondern bei Bedarf per **Nachtrag** ergänzt (wie
in [01_systemarchitektur.md](01_systemarchitektur.md) Abschnitt 13 geschehen) – so bleibt
nachvollziehbar, wann und warum sich eine Entscheidung weiterentwickelt hat.

### 5.5 Umgang mit Secrets

- `.env` ist in `.gitignore` eingetragen und wird **niemals** committet
- `.env.example` (versioniert) enthält nur Variablennamen, keine echten Werte
- Vor jedem Commit lohnt ein kurzer Blick auf `git status`/`git diff`, ob versehentlich Secrets
  enthalten sind (siehe auch Abschnitt 6)
- Optional für später (Phase 11, nicht jetzt zwingend): ein Pre-Commit-Hook mit einem Tool wie
  `gitleaks`, das automatisch nach versehentlich committeten Zugangsdaten sucht

---

## 6. Sicherheit

### 6.1 `.env`-Konzept

Bereits als `.env.example` angelegt (siehe Datei). Prinzip (aus Phase 2, Abschnitt 3.13
bestätigt): **Geheimnisse** (API-Schlüssel, Datenbankpfad) kommen ausschliesslich über
Umgebungsvariablen aus einer lokalen, nicht versionierten `.env`-Datei – geladen und beim
Programmstart validiert über `pydantic-settings` (Implementierung folgt in Phase 4, sobald der erste
Code entsteht). **Fachliche Parameter** (Strategie-/Risiko-Werte) liegen dagegen versioniert in
`config/einstellungen.toml`, da sie keine Geheimnisse sind und ihre Versionsgeschichte wertvoll ist.

### 6.2 API-Key-Management

- Für Alpaca ausschliesslich **Paper-Trading-Schlüssel** verwenden (technisch getrennt von
  Live-Schlüsseln), solange das Projekt in der Paper-Trading-Phase ist
- Schlüssel niemals in Code, niemals in `config/einstellungen.toml` (versioniert), niemals in
  Chat-Nachrichten oder Dokumentation einfügen
- Schlüssel niemals mit weiterreichenden Berechtigungen anlegen als nötig (z. B. keine
  Auszahlungs-Berechtigung, falls der Anbieter das granular anbietet)

### 6.3 Grundsatz

**Niemals geheime Daten in Git.** Dieser Grundsatz ist bereits technisch abgesichert durch
`.gitignore` (schliesst `.env` aus) und wird in Phase 11 um automatisierte Prüfung erweitert.

---

## 7. Dokumentationssystem

### 7.1 Technisches Handbuch für Entwickler

Angelegt unter `docs/handbuch/technisch/README.md` mit einer geplanten Kapitelstruktur, die parallel
zu den kommenden Phasen befüllt wird (Architektur, Setup, Module, Datenbankschema, Strategien,
Backtests, Deployment, Sicherheit). Zielgruppe aktuell: du selbst; Struktur ist aber so angelegt,
dass ein späterer weiterer Entwickler sich anhand des Handbuchs einarbeiten könnte.

### 7.2 Benutzerhandbuch für Kunden/Mitarbeiter

Angelegt unter `docs/handbuch/benutzer/README.md`, **absichtlich ohne Inhalt**. Verweist explizit auf
die in Abschnitt 1.1 beschriebene Voraussetzung: Inhalt entsteht erst ab Phase 9 (Dashboard) im
Entwurf, eine tatsächliche Nutzung durch Dritte erst nach positiver rechtlicher Prüfung.

---

## 8. Abschliessende kritische Architekturprüfung dieser Phase

| Geprüfter Punkt | Ergebnis |
|---|---|
| Ermöglicht die Struktur produktionsfähige Weiterentwicklung? | Ja – src-Layout, klare Modultrennung, FastAPI/SQLModel bereits auf spätere Erweiterung ausgelegt |
| Wurde unnötige Komplexität vermieden? | Ja – kein Gitflow, keine Mandantenfähigkeit vorab, `tests/` ohne leere Vorab-Struktur |
| Bleiben die Kosten bei 0 CHF? | Ja – Homebrew, Python, uv, VS Code, alle gewählten Bibliotheken sind kostenlos |
| Wurden alle Entscheidungen begründet? | Ja, siehe jeweilige Abschnitte |
| Offene Risiken? | (1) Rechtliche Prüfung Kunden/Mitarbeiter-Nutzung noch ausstehend – **von dir zu veranlassen, nicht technisch lösbar**. (2) Unklare Herkunft des bestehenden GitHub-Remotes – **deine Bestätigung ausstehend** (Abschnitt 5.1). (3) macOS-Systemumgebung muss noch aktualisiert werden (Python 3.9.6 → 3.12) – **Installation aussteht, siehe Abschnitt 2.3**. |

Notwendige Anpassung aus dieser Prüfung: keine weiteren strukturellen Änderungen – die drei offenen
Punkte sind Entscheidungen/Aktionen, die bei dir liegen, nicht Architekturfehler.

---

## 9. Nächste Schritte

Bevor Phase 4 (Datensystem) sinnvoll beginnen kann, wird die lokale Python-Umgebung tatsächlich
installiert (Abschnitt 2.3) – entweder durch dich oder durch mich nach deiner Bestätigung.

**Phase abgeschlossen. Möchtest du mit der nächsten Phase fortfahren?**
