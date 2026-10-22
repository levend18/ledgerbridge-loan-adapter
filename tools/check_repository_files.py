"""Reject private datasets and credential files before publication."""

import pathlib
import re
import subprocess
import sys


def check(paths: list[str]) -> list[str]:
    rejected = []
    for name in paths:
        path = pathlib.PurePosixPath(name)
        fixture = name.startswith("tests/fixtures/")
        if (
            path.name == ".env"
            or path.suffix.lower() == ".docx"
            or (path.suffix.lower() == ".csv" and not fixture)
            or name.startswith("data/")
        ):
            rejected.append(name)
            continue
        file = pathlib.Path(name)
        if file.is_file() and file.stat().st_size < 2_000_000:
            content = file.read_bytes()
            if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content):
                rejected.append(name)
    return rejected


if __name__ == "__main__":
    paths = sys.argv[1:] or subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    failures = check([p for p in paths if p])
    if failures:
        print("Forbidden repository files: " + ", ".join(failures), file=sys.stderr)
        raise SystemExit(1)
