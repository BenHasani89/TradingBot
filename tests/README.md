# Tests

Dieses Verzeichnis ist noch leer, da in Phase 3 ausschliesslich die Entwicklungsumgebung aufgebaut
wird - es existiert noch keine Fachlogik, die getestet werden koennte.

Ab Phase 4 (Datensystem) entstehen hier Unterordner, die `src/tradingbot/` spiegeln (z. B.
`tests/data/`, `tests/strategy/`, ...). Jedes neue Modul erhaelt seine Tests im selben Commit wie die
zugehoerige Implementierung (siehe Regel 8 des Projekts: "Jede Funktion muss getestet werden").

Test-Framework: pytest (siehe [docs/phasen/02_technologieauswahl.md](../docs/phasen/02_technologieauswahl.md)
und [docs/phasen/03_entwicklungsumgebung.md](../docs/phasen/03_entwicklungsumgebung.md)).
