#!/usr/bin/env python3
"""Backup giornaliero del gestionale: database PostgreSQL e allegati caricati.

- Un backup per giorno: i file si chiamano con la data
  (``diavoletti-AAAA-MM-GG.dump`` e ``diavoletti-media-AAAA-MM-GG.tar.gz``).
  Se lo script gira più volte nello stesso giorno (es. cron + deploy), il file
  del giorno viene sostituito con quello più recente.
- Si conservano gli ultimi 7 giorni (``BACKUP_RETENTION_DAYS``): i giorni più
  vecchi vengono eliminati automaticamente.
- Il dump è in formato custom di PostgreSQL ed è verificato subito con
  ``pg_restore --list``: un backup illeggibile fa fallire lo script e non
  sostituisce quello precedente.

Il ripristino si fa con ``infrastructure/scripts/restore_backup.sh``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = Path(os.environ.get("COMPOSE_FILE", PROJECT_ROOT / "infrastructure" / "compose.yml"))
ENV_FILE = Path(os.environ.get("COMPOSE_ENV_FILE", PROJECT_ROOT / ".env"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", PROJECT_ROOT / "infrastructure" / "backups"))
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", os.environ.get("BACKUP_RETENTION_COUNT", "7")))
BACKUP_MEDIA = os.environ.get("BACKUP_MEDIA", "true").lower() not in {"0", "false", "no"}

DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    if ENV_FILE.exists():
        command.extend(("--env-file", str(ENV_FILE)))
    command.extend(("-f", str(COMPOSE_FILE), *arguments))
    return command


def run_to_file(command: list[str], destination: Path, verify=None) -> None:
    """Esegue il comando scrivendo l'output in un file temporaneo, poi lo rinomina."""
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("wb") as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip() or "comando non riuscito")
        if temporary.stat().st_size == 0:
            raise RuntimeError("il backup prodotto è vuoto")
        if verify is not None:
            verify(temporary)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def verify_dump(path: Path) -> None:
    """Controlla che il dump sia leggibile da pg_restore e contenga dati."""
    with path.open("rb") as dump:
        completed = subprocess.run(
            compose_command("exec", "-T", "db", "pg_restore", "--list"),
            stdin=dump, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    listing = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0 or "TABLE DATA" not in listing:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"verifica del dump non riuscita: {detail or 'nessuna tabella trovata'}")


def remove_old_backups(prefix: str, suffix: str) -> None:
    """Tiene un file per giorno per gli ultimi RETENTION_DAYS giorni."""
    by_day: dict[str, list[Path]] = {}
    for path in BACKUP_DIR.glob(f"{prefix}*{suffix}"):
        rest = path.name[len(prefix):]
        match = DATE_IN_NAME.match(rest)
        if match is None:
            continue
        by_day.setdefault(match.group(1), []).append(path)
    days = sorted(by_day, reverse=True)
    for index, day in enumerate(days):
        files = sorted(by_day[day], key=lambda item: item.stat().st_mtime, reverse=True)
        # Giorni oltre la finestra: si eliminano tutti. Giorni nella finestra:
        # resta solo il file più recente di quel giorno.
        obsolete = files if index >= RETENTION_DAYS else files[1:]
        for path in obsolete:
            path.unlink()
            logging.info("Backup eliminato per rotazione: %s", path.name)


def backup_database(day: str) -> Path:
    destination = BACKUP_DIR / f"diavoletti-{day}.dump"
    command = compose_command(
        "exec", "-T", "db", "sh", "-c",
        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges',
    )
    logging.info("Avvio backup database in %s", destination)
    run_to_file(command, destination, verify=verify_dump)
    remove_old_backups("diavoletti-", ".dump")
    logging.info("Backup database completato e verificato: %s", destination)
    return destination


def backup_media(day: str) -> Path:
    destination = BACKUP_DIR / f"diavoletti-media-{day}.tar.gz"
    command = compose_command(
        "exec", "-T", "backend", "sh", "-c",
        "mkdir -p /app/media && exec tar -C /app/media -czf - .",
    )
    run_to_file(command, destination)
    remove_old_backups("diavoletti-media-", ".tar.gz")
    logging.info("Backup allegati completato: %s", destination)
    return destination


def main() -> int:
    if RETENTION_DAYS < 1:
        raise ValueError("BACKUP_RETENTION_DAYS deve essere almeno 1.")
    if not COMPOSE_FILE.exists():
        raise FileNotFoundError(f"Compose file non trovato: {COMPOSE_FILE}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    day = datetime.now().astimezone().strftime("%Y-%m-%d")

    backup_database(day)
    if BACKUP_MEDIA:
        try:
            backup_media(day)
        except Exception as error:  # il dump del database resta comunque valido
            logging.warning("Backup allegati non riuscito: %s", error)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.error("Backup non riuscito: %s", error)
        raise SystemExit(1)
