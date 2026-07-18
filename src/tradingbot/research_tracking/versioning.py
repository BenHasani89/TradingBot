"""Optionale Git-Versionierungs-Information für Experimente.

Rein informativ - liefert niemals eine Ausnahme, damit fehlendes oder nicht
verfügbares Git die Research-Pipeline nie unterbricht.
"""

from __future__ import annotations

import subprocess


def current_git_commit() -> str | None:
    """Liest den aktuellen Git-Commit-Hash, falls verfügbar.

    Gibt `None` zurück, wenn kein Git installiert ist, kein Repository
    vorliegt, oder der Commit aus einem anderen Grund nicht ermittelt werden
    kann - wirft niemals eine Ausnahme.
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - bewusst "git" ueber PATH
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    commit = result.stdout.strip()
    return commit or None
