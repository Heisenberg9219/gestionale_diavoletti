#!/usr/bin/env python3
"""Create a PostgreSQL backup (and a copy of uploaded files) and retain seven copies."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = Path(os.environ.get("COMPOSE_FILE", PROJECT_ROOT / "infrastructure" / "compose.yml"))
ENV_FILE = Path(os.environ.get("COMPOSE_ENV_FILE", PROJECT_ROOT / ".env"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", PROJECT_ROOT / "infrastructure" / "backups"))
RETENTION_COUNT = int(os.environ.get("BACKUP_RETENTION_COUNT", "7"))
BACKUP_MEDIA = os.environ.get("BACKUP_MEDIA", "true").lower() not in {"0", "false", "no"}


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    if ENV_FILE.exists():
        command.extend(("--env-file", str(ENV_FILE)))
    command.extend(("-f", str(COMPOSE_FILE), *arguments))
    return command


def remove_old_backups(pattern: str = "diavoletti-*.dump") -> None:
    backups = sorted(
        BACKUP_DIR.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for backup in backups[RETENTION_COUNT:]:
        backup.unlink()
        logging.info("Backup eliminato per rotazione: %s", backup.name)


def backup_media(timestamp: str) -> None:
    """Archive uploaded files (invoices, receipts) from the backend container."""
    destination = BACKUP_DIR / f"diavoletti-media-{timestamp}.tar.gz"
    temporary = destination.with_name(destination.name + ".tmp")
    command = compose_command(
        "exec", "-T", "backend", "sh", "-c",
        "mkdir -p /app/media && exec tar -C /app/media -czf - .",
    )
    try:
        with temporary.open("wb") as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
        temporary.replace(destination)
        remove_old_backups("diavoletti-media-*.tar.gz")
        logging.info("Backup allegati completato: %s", destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    if RETENTION_COUNT < 1:
        raise ValueError("BACKUP_RETENTION_COUNT deve essere almeno 1.")
    if not COMPOSE_FILE.exists():
        raise FileNotFoundError(f"Compose file non trovato: {COMPOSE_FILE}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    destination = BACKUP_DIR / f"diavoletti-{timestamp}.dump"
    temporary = destination.with_suffix(".tmp")
    dump_command = compose_command(
        "exec", "-T", "db", "sh", "-c",
        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges',
    )

    logging.info("Avvio backup PostgreSQL in %s", destination)
    try:
        with temporary.open("wb") as output:
            completed = subprocess.run(
                dump_command,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
        if temporary.stat().st_size == 0:
            raise RuntimeError("pg_dump ha prodotto un file vuoto.")
        temporary.replace(destination)
        remove_old_backups()
        logging.info("Backup completato: %s", destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if BACKUP_MEDIA:
        try:
            backup_media(timestamp)
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
