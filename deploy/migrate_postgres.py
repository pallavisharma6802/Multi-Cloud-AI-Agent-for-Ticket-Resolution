#!/usr/bin/env python3
"""Copy the local ticket database to managed Postgres without deleting source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.db.models import Base  # noqa: E402


class MigrationError(ValueError):
    """A safe, user-facing migration error authored by this script."""


def canonical_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: canonical_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(val) for val in value]
    return value


def fingerprint(rows):
    digest = hashlib.sha256()
    encoded = [
        json.dumps(canonical_value(dict(row)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for row in rows
    ]
    for row in sorted(encoded):
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return {"rows": len(rows), "sha256": digest.hexdigest()}


def database_urls(env):
    target_value = env.get("CLOUD_DATABASE_URL_UNPOOLED") or env.get("CLOUD_DATABASE_URL")
    if not target_value:
        raise MigrationError("Set CLOUD_DATABASE_URL in the project .env before checking or migrating.")
    target = make_url(target_value)
    if target.get_backend_name() not in ("postgresql", "postgres"):
        raise MigrationError("CLOUD_DATABASE_URL must be a PostgreSQL connection string.")
    target = target.set(drivername="postgresql+psycopg2")
    # Never accept an unencrypted connection to the managed destination.
    target = target.update_query_dict({"sslmode": "require"})
    source_value = env.get("MIGRATION_SOURCE_DATABASE_URL")
    source = (
        make_url(source_value)
        if source_value
        else URL.create(
            "postgresql+psycopg2",
            username=env.get("POSTGRES_USER") or "ticket_admin",
            password=env.get("POSTGRES_PASSWORD") or "ticket_local_dev",
            host="127.0.0.1",
            port=5433,
            database=env.get("POSTGRES_DB") or "tickets_db",
        )
    )
    if source.get_backend_name() not in ("postgresql", "postgres"):
        raise MigrationError("The migration source must be PostgreSQL.")
    source = source.set(drivername="postgresql+psycopg2")
    # Compare destinations without printing URLs or passwords.
    def identity(url):
        return url.host, url.port or 5432, url.database

    if identity(source) == identity(target):
        raise MigrationError("Source and target must be different databases.")
    return source, target


def table_rows(connection, table):
    return [dict(row) for row in connection.execute(select(table)).mappings()]


def run_migration(source_engine, target_engine, apply=False):
    tables = list(Base.metadata.sorted_tables)
    with source_engine.connect().execution_options(isolation_level="REPEATABLE READ") as source:
        with source.begin():
            source.execute(text("SET TRANSACTION READ ONLY"))
            source_rows = {table.name: table_rows(source, table) for table in tables}
            source_summary = {name: fingerprint(rows) for name, rows in source_rows.items()}
            with target_engine.begin() as target:
                if apply:
                    # DDL and all row inserts are in this same target transaction.
                    Base.metadata.create_all(bind=target)
                existing = set(inspect(target).get_table_names())
                missing = [table.name for table in tables if table.name not in existing]
                if apply:
                    # Prevent application writes or another migration from racing verification.
                    for table in tables:
                        quoted_name = target.dialect.identifier_preparer.quote(table.name)
                        target.execute(text(f"LOCK TABLE {quoted_name} IN EXCLUSIVE MODE"))
                target_rows = {
                    table.name: table_rows(target, table) if table.name in existing else []
                    for table in tables
                }
                target_summary = {name: fingerprint(rows) for name, rows in target_rows.items()}
                identical = not missing and source_summary == target_summary
                any_existing_rows = any(summary["rows"] for summary in target_summary.values())
                if any_existing_rows and not identical:
                    raise MigrationError(
                        "The target contains different records. Migration refused; no records were overwritten."
                    )
                if apply and not identical:
                    for table in tables:
                        rows = source_rows[table.name]
                        for offset in range(0, len(rows), 500):
                            target.execute(table.insert(), rows[offset : offset + 500])
                    target_summary = {table.name: fingerprint(table_rows(target, table)) for table in tables}
                    if source_summary != target_summary:
                        raise MigrationError(
                            "Verification failed. The target transaction has been rolled back."
                        )
                    identical = True
                return {
                    "mode": "apply" if apply else "check-only",
                    "source": source_summary,
                    "target": target_summary,
                    "missing_target_tables": missing if not apply else [],
                    "verified_identical": identical,
                    "already_complete": identical and (any_existing_rows or not any(source_rows.values())),
                    "source_preserved": True,
                }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="Read connection/table status without writing (the default).",
    )
    mode.add_argument(
        "--apply", action="store_true", help="Create empty target tables and copy records transactionally."
    )
    args = parser.parse_args()
    engines = []
    try:
        # dotenv_values reads secrets without copying them into process logs or arguments.
        env = dotenv_values(PROJECT_ROOT / ".env")
        source_url, target_url = database_urls(env)
        engines = [
            create_engine(url, connect_args={"connect_timeout": 15}, pool_pre_ping=True)
            for url in (source_url, target_url)
        ]
        report = run_migration(*engines, apply=args.apply)
        print(json.dumps(report, indent=2))
        return 0
    except MigrationError as exc:
        # Only messages authored by this script are exposed; SQL driver errors may contain DSNs.
        print(f"Migration stopped: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Migration stopped ({type(exc).__name__}). Check credentials, network access, and database permissions. No connection string was logged.",
            file=sys.stderr,
        )
        return 1
    finally:
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
