# Phase 0 – Projektanalyse

Status: **Abgeschlossen** (wartet auf deine Bestätigung, um zu Phase 1 überzugehen)
Datum: 2026-07-17

## 1. Ergebnisse der Anforderungserhebung

| Thema | Entscheidung |
|---|---|
| Märkte | Kryptowährungen + Aktien |
| Handelsstil | Swing Trading |
| Risikoprofil | Mittel |
| Programmierkenntnisse | Fortgeschritten |
| Betriebssystem | macOS |
| Budget (Entwicklungsphase) | bis ca. 20–30 €/Monat |
| Bedienung | Web-Dashboard im Browser |

## 2. Projektbeschreibung

Es wird ein vollständig automatisiertes, in deutscher Sprache gehaltenes Trading-System entwickelt,
das zunächst **ausschliesslich mit simuliertem Geld (Paper-Trading)** arbeitet. Das System analysiert
historische und aktuelle Marktdaten aus dem Krypto- und Aktienmarkt, wendet eine Swing-Trading-Strategie
mit mittlerem Risikoprofil an, simuliert Trades automatisiert und stellt alle Ergebnisse über ein
deutschsprachiges Web-Dashboard dar. Echtgeld-Handel ist explizit ausgeschlossen, bis das System in
Phase 12 eine vollständige Prüfung durchlaufen hat – und selbst dann nur nach deiner ausdrücklichen
Freigabe.

## 3. Zieldefinition

- Ein stabiler, 24/7-fähiger Bot, der Krypto- und Aktienmärkte auf Swing-Trading-Setups überwacht
- Vollständige Trade-Simulation ohne echtes Kapital (Paper-Trading)
- Nachvollziehbares Backtesting auf historischen Daten vor jedem Live-Test
- Automatisches Risikomanagement (Stop-Loss, Positionsgrösse, Verlustlimits) entsprechend
  mittlerem Risikoprofil
- Deutschsprachiges Web-Dashboard mit Portfolio-, Trading- und Systemübersicht
- Saubere, verständliche Dokumentation jeder Komponente auf Deutsch

## 4. Funktionsumfang (Phase 1–12, siehe Roadmap)

1. Systemarchitektur & Datenfluss
2. Technologieauswahl (Python-Stack, Datenbank, Frameworks)
3. Entwicklungsumgebung & Projektstruktur
4. Datensystem (historisch + Echtzeit, Krypto & Aktien)
5. Swing-Trading-Strategie (Einstieg, Ausstieg, SL/TP, Positionsgrösse)
6. Backtesting-Engine (Gebühren, Slippage, Kennzahlen)
7. Paper-Trading-Bot (virtuelles Portfolio, Historie, Logs)
8. Optionale KI-Integration (News/Sentiment) – nur ergänzend zum Risikosystem
9. Deutsches Web-Dashboard
10. Vorbereitung 24/7-Betrieb (Server, Monitoring, Backups)
11. Sicherheit (API-Key-Verwaltung, Verschlüsselung, Not-Aus)
12. Echtgeld-Vorbereitung (nur nach vollständiger Prüfung und deiner Freigabe)

## 5. Zeitplan (grobe Orientierung, kein fixer Termin)

Da wir iterativ vorgehen und jede Phase erst nach deiner Bestätigung abgeschlossen wird, ist der
Zeitplan flexibel. Richtwerte für ein Projekt dieser Grösse bei "fortgeschrittenen" Kenntnissen:

| Phase | Grobe Dauer |
|---|---|
| 1–3 (Architektur, Technik, Setup) | 1–2 Sitzungen |
| 4 (Datensystem) | 1–2 Sitzungen |
| 5–6 (Strategie & Backtesting) | 2–4 Sitzungen |
| 7 (Paper-Trading-Bot) | 2–3 Sitzungen |
| 8 (KI-Integration, optional) | 1–2 Sitzungen |
| 9 (Dashboard) | 2–3 Sitzungen |
| 10–11 (Betrieb & Sicherheit) | 1–2 Sitzungen |
| 12 (Echtgeld-Prüfung) | 1 Sitzung |

## 6. Kostenübersicht (Entwicklungs-/Testphase, kein Handelskapital)

| Posten | Kosten | Pflicht? |
|---|---|---|
| Python, VS Code, Git | 0 € | Ja |
| GitHub-Konto | 0 € | Ja (Empfehlung für Versionskontrolle) |
| Krypto-Marktdaten (z.B. Binance Public API) | 0 € | Ja |
| Aktien-Marktdaten (z.B. Alpaca Paper-Trading API) | 0 € | Ja |
| Lokale Datenbank (SQLite) | 0 € | Ja |
| VPS/Server für 24/7-Betrieb (erst ab Phase 10) | ca. 5–15 €/Monat | Optional, erst später |
| Erweiterter Datenanbieter (falls nötig) | ca. 0–20 €/Monat | Optional |

→ Innerhalb deines Budgets von 20–30 €/Monat bleiben wir während der gesamten Entwicklungs- und
Test-Phase voraussichtlich bei **0 €**, da alle Kernkomponenten mit kostenlosen APIs und lokalen
Tools umsetzbar sind. Ein VPS wird erst relevant, wenn wir in Phase 10 den 24/7-Dauerbetrieb
vorbereiten.

## 7. Nächste notwendige Konten/Installationen (Vorschau auf Phase 1–4)

Detaillierte Checkliste folgt zu Beginn von Phase 1, hier schon ein Überblick, damit du dich
vorbereiten kannst:

- **Python 3.11+** (lokal installiert) – kostenlos, keine persönlichen Daten
- **Visual Studio Code** oder vergleichbarer Editor – kostenlos
- **GitHub-Konto** – kostenlos, für Versionskontrolle deines Codes (optional, aber empfohlen)
- **Binance-Konto (nur für öffentliche Marktdaten, kein Trading)** – kostenlos, für Krypto-Kursdaten
- **Alpaca-Konto (Paper-Trading)** – kostenlos, für Aktien-Kursdaten und simuliertes Aktien-Trading

Für jedes dieser Konten bekommst du zu Beginn der jeweiligen Phase eine genaue Anleitung:
Warum benötigt, kostenlos/kostenpflichtig, welche Daten nötig sind, wann es gebraucht wird, wie du
es einrichtest, und was du mir danach zurückmelden musst.
