#!/usr/bin/env python3
"""Migrate legacy resource-specific Cloudflare account keys without printing secrets."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path


LEGACY_PAIRS = (
    ("CLOUDFLARE_WORKERS_AI_EMBEDDING_SECONDARY_ACCOUNT_ID", "CLOUDFLARE_WORKERS_AI_GENERATION_SECONDARY_ACCOUNT_ID", "CLOUDFLARE_SECONDARY_ACCOUNT_ID"),
    ("CLOUDFLARE_WORKERS_AI_EMBEDDING_SECONDARY_API_TOKEN", "CLOUDFLARE_WORKERS_AI_GENERATION_SECONDARY_API_TOKEN", "CLOUDFLARE_SECONDARY_API_TOKEN"),
    ("CLOUDFLARE_WORKERS_AI_EMBEDDING_TERTIARY_ACCOUNT_ID", "CLOUDFLARE_WORKERS_AI_GENERATION_TERTIARY_ACCOUNT_ID", "CLOUDFLARE_TERTIARY_ACCOUNT_ID"),
    ("CLOUDFLARE_WORKERS_AI_EMBEDDING_TERTIARY_API_TOKEN", "CLOUDFLARE_WORKERS_AI_GENERATION_TERTIARY_API_TOKEN", "CLOUDFLARE_TERTIARY_API_TOKEN"),
)


def parse_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[2] / ".env")
    args = parser.parse_args()
    mode = stat.S_IMODE(args.env_file.stat().st_mode)
    if mode != 0o600:
        raise SystemExit("env file must already have mode 600")
    lines = args.env_file.read_text(encoding="utf-8").splitlines()
    values = parse_values(lines)
    replacements: dict[str, str] = {}
    legacy_names = {name for pair in LEGACY_PAIRS for name in pair[:2]}
    for first, second, canonical in LEGACY_PAIRS:
        candidates = [values[name] for name in (first, second) if values.get(name, "")]
        if len(set(candidates)) > 1:
            raise SystemExit(f"conflicting values for {canonical}")
        if values.get(canonical, "") and candidates and values[canonical] != candidates[0]:
            raise SystemExit(f"conflicting values for {canonical}")
        if candidates and not values.get(canonical, ""):
            replacements[canonical] = candidates[0]

    output: list[str] = []
    seen_canonical: set[str] = set()
    for line in lines:
        name = line.split("=", 1)[0] if "=" in line else ""
        if name in legacy_names:
            continue
        output.append(line)
        if name in {pair[2] for pair in LEGACY_PAIRS}:
            seen_canonical.add(name)
    for name, value in replacements.items():
        if name not in seen_canonical:
            output.append(f"{name}={value}")

    temporary = args.env_file.with_suffix(args.env_file.suffix + ".tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, args.env_file)
    os.chmod(args.env_file, 0o600)
    print("canonical Cloudflare environment migration complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
