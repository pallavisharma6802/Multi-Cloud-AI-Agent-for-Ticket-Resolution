#!/usr/bin/env python3
"""Send the reviewed installer to an existing EC2 instance through SSM."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--key", default="releases/resolve.tar.gz")
    parser.add_argument("--profile", default="resolve-deploy")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually submit the SSM command; without this flag only a plan is printed",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"i-[a-f0-9]{8,17}", args.instance_id):
        parser.error("Expected an EC2 instance ID")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", args.bucket):
        parser.error("Expected a private S3 bucket name")
    if not re.fullmatch(r"releases/[A-Za-z0-9._/-]+", args.key):
        parser.error("Release key must be inside releases/")
    script = Path(__file__).with_name("install_release.sh").read_bytes()
    encoded = base64.b64encode(script).decode("ascii")
    commands = [
        "set -eu",
        "cloud-init status --wait",
        "printf '%s' " + shlex.quote(encoded) + " | base64 --decode > /tmp/resolve-install-release.sh",
        "chmod 700 /tmp/resolve-install-release.sh",
        "bash /tmp/resolve-install-release.sh " + shlex.quote(args.bucket) + " " + shlex.quote(args.key),
    ]
    if not args.send:
        print(
            json.dumps(
                {
                    "send": False,
                    "instance_id": args.instance_id,
                    "release": "s3://" + args.bucket + "/" + args.key,
                    "installer_bytes": len(script),
                    "build_order": ["backend", "frontend"],
                    "database": "existing Neon",
                },
                indent=2,
            )
        )
        return 0
    os.umask(0o077)
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as file:
            path = Path(file.name)
            json.dump({"commands": commands, "executionTimeout": ["3600"]}, file)
        result = subprocess.run(
            [
                "aws",
                "ssm",
                "send-command",
                "--document-name",
                "AWS-RunShellScript",
                "--instance-ids",
                args.instance_id,
                "--parameters",
                "file://" + str(path),
                "--timeout-seconds",
                "3600",
                "--comment",
                "Deploy reviewed Resolve MVP release",
                "--profile",
                args.profile,
                "--region",
                args.region,
                "--query",
                "Command.CommandId",
                "--output",
                "text",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            print(
                "SSM deployment command was not accepted. Check instance registration, AWS session, and SSM permissions."
            )
            return result.returncode
        command_id = result.stdout.strip()
        if not re.fullmatch(r"[a-fA-F0-9-]{36}", command_id):
            print("SSM returned an unexpected receipt; check the AWS Systems Manager command history.")
            return 1
        print(
            json.dumps(
                {"command_id": command_id, "instance_id": args.instance_id, "status": "submitted"}, indent=2
            )
        )
        return 0
    finally:
        if path:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
