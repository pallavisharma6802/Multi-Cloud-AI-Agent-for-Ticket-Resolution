#!/usr/bin/env python3
"""Build an ignored private AWS release from a strict application allowlist."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = set(
    """PROJECT_NAME AWS_REGION AWS_BEDROCK_MODEL_ID AZURE_TEXT_ANALYTICS_ENDPOINT
AZURE_TEXT_ANALYTICS_KEY AZURE_LOCATION PINECONE_API_KEY PINECONE_ENVIRONMENT PINECONE_INDEX_NAME
DOMAIN_PACK DOMAINS_ROOT KB_BACKEND KB_PATH LOG_LEVEL REQUEST_TIMEOUT_SECONDS
MAX_ITERATIONS MAX_WALL_CLOCK_SECONDS INTENT_NUM_SAMPLES RETRIEVAL_TOP_K MAX_QUERY_REWRITES
ENABLE_BIGQUERY GCP_PROJECT_ID GCP_REGION BIGQUERY_PROJECT_ID BIGQUERY_DATASET BIGQUERY_TABLE
BIGQUERY_CLIENT_EMAIL BIGQUERY_PRIVATE_KEY LANGSMITH_TRACING LANGSMITH_API_KEY LANGSMITH_PROJECT
CLOUD_DATABASE_URL""".split()
)
TOP_FILES = ("Dockerfile", ".dockerignore", "requirements.txt", "seed_kb.py")
DIRECTORIES = ("app", "domains", "frontend", "grafana")
DEPLOY_FILES = ("compose.yml", "compose.neon.yml", "Caddyfile", "install_release.sh")
EXCLUDED_PARTS = {
    ".git",
    ".next",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def quote_env(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def password_hash(password: str) -> str:
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    except ImportError:
        executable = shutil.which("htpasswd")
        if not executable:
            raise ValueError(
                "Install bcrypt in this Python environment or provide htpasswd; no release was uploaded."
            ) from None
        result = subprocess.run(
            [executable, "-niBC", "12", "demo"], input=password + "\n", text=True, capture_output=True
        )
        if result.returncode:
            raise ValueError("Could not generate the demo password hash.") from None
        value = result.stdout.strip().split(":", 1)[-1]
        if not value.startswith(("$2a$", "$2b$", "$2y$")):
            raise ValueError("Password tool did not produce a bcrypt hash.") from None
        return value


def application_files():
    for name in TOP_FILES:
        yield ROOT / name, name
    for name in DIRECTORIES:
        directory = ROOT / name
        if not directory.is_dir():
            raise ValueError(f"Missing application directory: {name}")
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(ROOT)
            if (
                any(part in EXCLUDED_PARTS for part in relative.parts)
                or path.name.startswith(".env")
                or path.name == ".DS_Store"
            ):
                continue
            if path.is_symlink():
                raise ValueError(f"Unexpected symlink in release: {relative}")
            if path.is_file():
                yield path, relative.as_posix()
    for name in DEPLOY_FILES:
        yield ROOT / "deploy/aws" / name, "deploy/aws/" + name


def metadata(info):
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mode = (
        0o600
        if info.name in (".env", "secrets/gcp-key.json")
        else (0o755 if info.name.endswith(".sh") else 0o644)
    )
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", required=True, help="Public hostname, such as the Terraform suggested_hostname output"
    )
    parser.add_argument("--check-only", action="store_true", help="Validate inputs without writing a release")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", args.host):
            raise ValueError("Host must be a DNS hostname without a scheme, port, or path.")
        source = dotenv_values(ROOT / ".env")
        required = (
            "CLOUD_DATABASE_URL",
            "AZURE_TEXT_ANALYTICS_ENDPOINT",
            "AZURE_TEXT_ANALYTICS_KEY",
            "PINECONE_API_KEY",
            "PINECONE_ENVIRONMENT",
        )
        if any(not source.get(name) for name in required):
            raise ValueError("The source .env is missing one or more required cloud settings.")
        database = urlsplit(source["CLOUD_DATABASE_URL"])
        if (
            database.scheme not in ("postgres", "postgresql")
            or not database.hostname
            or not database.hostname.endswith(".neon.tech")
        ):
            raise ValueError("Expected the verified Neon database URL; local PostgreSQL is not packaged.")
        key_value = source.get("GOOGLE_APPLICATION_CREDENTIALS") or "gcp-key.json"
        key_path = Path(key_value).expanduser()
        if not key_path.is_absolute():
            key_path = ROOT / key_path
        if not key_path.is_file():
            key_path = ROOT / "gcp-key.json"
        key = json.loads(key_path.read_text())
        if key.get("type") != "service_account" or not key.get("private_key"):
            raise ValueError("Expected the existing GCP service-account key file.")
        files = list(application_files())
        for path, name in files:
            if not path.is_file():
                raise ValueError(f"Missing release file: {name}")
        if args.check_only:
            print(
                json.dumps(
                    {
                        "inputs_valid": True,
                        "application_files": len(files),
                        "database": "existing Neon",
                        "uploaded": False,
                    }
                )
            )
            return 0
        os.umask(0o077)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "deploy/aws/.local" / (timestamp + "-" + secrets.token_hex(3))
        output.mkdir(parents=True, mode=0o700)
        demo_password = secrets.token_urlsafe(24)
        grafana_password = secrets.token_urlsafe(24)
        values = {
            name: str(value)
            for name, value in source.items()
            if value is not None and (name in ALLOWED or name.startswith("MODEL_"))
        }
        values.update(
            {
                "ENV": "production",
                "AWS_REGION": source.get("AWS_REGION") or "us-east-1",
                "APP_HOST": args.host,
                "DEMO_USER": "demo",
                "DEMO_PASSWORD_HASH": password_hash(demo_password),
                "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
                "GRAFANA_ADMIN_PASSWORD": grafana_password,
                "NEXT_PUBLIC_API_URL": "/backend",
                "NEXT_PUBLIC_GRAFANA_URL": "/grafana",
                "DATABASE_URL": source["CLOUD_DATABASE_URL"],
                "GOOGLE_APPLICATION_CREDENTIALS": "/srv/gcp-key.json",
                "BIGQUERY_DATASET": "ticket_analytics_live",
            }
        )
        if "BIGQUERY_PRIVATE_KEY" in values:
            values["BIGQUERY_PRIVATE_KEY"] = values["BIGQUERY_PRIVATE_KEY"].replace("\\n", "\n")
        env_file = output / "server.env"
        env_file.write_text(
            "\n".join(name + "=" + quote_env(value) for name, value in sorted(values.items())) + "\n"
        )
        env_file.chmod(0o600)
        parsed = dotenv_values(env_file)
        if any(parsed.get(name) != value for name, value in values.items()):
            raise ValueError("Environment round-trip validation failed.")
        credentials = output / "credentials.json"
        credentials.write_text(
            json.dumps(
                {
                    "url": "https://" + args.host,
                    "demo_user": "demo",
                    "demo_password": demo_password,
                    "grafana_url": "https://" + args.host + "/grafana/",
                    "grafana_admin_user": "admin",
                    "grafana_admin_password": grafana_password,
                },
                indent=2,
            )
            + "\n"
        )
        credentials.chmod(0o600)
        validation_env = dict(os.environ, APP_ENV_FILE=str(env_file))
        command = [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "deploy/aws/compose.yml"),
            "-f",
            str(ROOT / "deploy/aws/compose.neon.yml"),
            "config",
            "--quiet",
        ]
        result = subprocess.run(command, env=validation_env, capture_output=True, text=True)
        if result.returncode:
            raise ValueError("Production Compose configuration validation failed; no files were uploaded.")
        archive = output / "resolve.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for path, name in files:
                tar.add(path, arcname=name, recursive=False, filter=metadata)
            tar.add(env_file, arcname=".env", recursive=False, filter=metadata)
            tar.add(key_path, arcname="secrets/gcp-key.json", recursive=False, filter=metadata)
        archive.chmod(0o600)
        print(
            json.dumps(
                {
                    "archive": str(archive),
                    "private_credentials_file": str(credentials),
                    "application_files": len(files),
                    "compose_valid": True,
                    "uploaded": False,
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        # Do not print raw SDK/subprocess errors: they can contain connection details.
        print(
            "Packaging stopped: " + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
