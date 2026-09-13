#!/usr/bin/env python3
"""Create a PostgreSQL backup from the Docker database and retain seven copies."""

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


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    if ENV_FILE.exists():
        command.extend(("--env-file", str(ENV_FILE)))
    command.extend(("-f", str(COMPOSE_FILE), *arguments))
    return command


def remove_old_backups() -> None:
    backups = sorted(
        BACKUP_DIR.glob("diavoletti-*.dump"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for backup in backups[RETENTION_COUNT:]:
        backup.unlink()
        logging.info("Backup eliminato per rotazione: %s", backup.name)


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
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.error("Backup non riuscito: %s", error)
        raise SystemExit(1)
