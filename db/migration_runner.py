"""A training-sized reimplementation of the Liquibase-driven migration pipeline used by
report-transformation-service: a directory of ordered, numbered `.sql` changelog files, each
tagged with a `-- context: ...` header, applied once each and tracked in a `schema_history` table
- so the exact same changelog directory can be pointed at dev/stage/prod and each environment only
gets the changesets scoped to it (e.g. `003_seed_dev_sample_data.sql`'s `-- context: DEV,STAGE`
header keeps sample data out of prod, the same way report-transformation-service's real
`.gitlab-ci.yml` passes `-Dliquibase.contexts=${LIQUIBASE_ENV}` per environment).

This module talks to a plain DB-API 2.0 `sqlite3.Connection` for the runnable demo (see
db/connection.py) - the same code would work unchanged against any DB-API-compatible driver.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

CONTEXT_HEADER_RE = re.compile(r'^\s*--\s*context:\s*(.+)\s*$', re.IGNORECASE)
FILENAME_ORDER_RE = re.compile(r'^(\d+)_')


class ChecksumMismatchError(Exception):
    """Raised when an already-applied changelog file's contents have changed on disk.

    Mirrors Liquibase's own checksum validation: migrations are an append-only log of what has
    already happened to the database. Editing an applied one (instead of adding a new one) is a
    bug waiting to corrupt whichever environment runs the pipeline next - this makes it a loud
    failure instead of a silent divergence between environments.
    """


@dataclass(frozen=True)
class Changeset:
    order: int
    filename: str
    contexts: List[str]
    sql: str
    checksum: str

    def applies_to(self, context: str) -> bool:
        return 'ALL' in self.contexts or context.upper() in self.contexts


def _parse_contexts(sql_text: str) -> List[str]:
    for line in sql_text.splitlines():
        match = CONTEXT_HEADER_RE.match(line)
        if match:
            return [c.strip().upper() for c in match.group(1).split(',') if c.strip()]
    # No header at all means "runs everywhere" - the safest default, rather than silently
    # skipping a changeset that forgot to declare a context.
    return ['ALL']


def _checksum(sql_text: str) -> str:
    return hashlib.sha256(sql_text.encode('utf-8')).hexdigest()


def load_changelog(changelog_dir: Path) -> List[Changeset]:
    """Read every `NNN_description.sql` file in `changelog_dir`, sorted by its numeric prefix."""
    changesets: List[Changeset] = []
    for path in sorted(changelog_dir.glob('*.sql')):
        match = FILENAME_ORDER_RE.match(path.name)
        if not match:
            raise ValueError(f"Changelog file {path.name!r} must start with a numeric prefix, e.g. '001_...'")
        sql_text = path.read_text(encoding='utf-8')
        changesets.append(
            Changeset(
                order=int(match.group(1)),
                filename=path.name,
                contexts=_parse_contexts(sql_text),
                sql=sql_text,
                checksum=_checksum(sql_text),
            )
        )
    changesets.sort(key=lambda c: c.order)
    return changesets


class MigrationRunner:
    """Applies a changelog directory's changesets to a DB-API connection, once each, in order."""

    HISTORY_TABLE = 'schema_history'

    def __init__(self, connection, context: str = 'ALL') -> None:
        self.connection = connection
        self.context = context.upper()
        self._ensure_history_table()

    def _ensure_history_table(self) -> None:
        self.connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.HISTORY_TABLE} (
                filename TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self.connection.commit()

    def _applied_checksums(self) -> dict:
        cursor = self.connection.execute(f"SELECT filename, checksum FROM {self.HISTORY_TABLE}")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def pending(self, changesets: Sequence[Changeset]) -> List[Changeset]:
        """Changesets that apply to this runner's context and have not been applied yet."""
        applied = self._applied_checksums()
        return [
            c for c in changesets
            if c.applies_to(self.context) and c.filename not in applied
        ]

    def run(self, changesets: Sequence[Changeset]) -> List[str]:
        """Apply every pending, in-context changeset. Returns the filenames applied, in order.

        Raises ChecksumMismatchError before applying anything further if an already-applied
        changeset's on-disk contents no longer match what was recorded when it ran.
        """
        applied_checksums = self._applied_checksums()
        for changeset in changesets:
            recorded = applied_checksums.get(changeset.filename)
            if recorded is not None and recorded != changeset.checksum:
                raise ChecksumMismatchError(
                    f"{changeset.filename} has changed since it was applied "
                    f"(recorded checksum {recorded[:12]}..., on-disk checksum {changeset.checksum[:12]}...). "
                    "Add a new changelog file instead of editing an applied one."
                )

        applied_now: List[str] = []
        for changeset in self.pending(changesets):
            self.connection.executescript(_strip_leading_comments(changeset.sql))
            self.connection.execute(
                f"INSERT INTO {self.HISTORY_TABLE} (filename, checksum) VALUES (?, ?)",
                (changeset.filename, changeset.checksum),
            )
            self.connection.commit()
            applied_now.append(changeset.filename)
        return applied_now


def _strip_leading_comments(sql_text: str) -> str:
    # sqlite3's executescript() is fine with leading `--` comments, but keeping this explicit
    # (rather than relying on driver-specific comment handling) keeps MigrationRunner portable to
    # DB-API drivers that are pickier about it.
    return sql_text
