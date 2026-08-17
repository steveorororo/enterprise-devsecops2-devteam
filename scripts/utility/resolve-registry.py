#!/usr/bin/env python3
"""Emit GITHUB_OUTPUT lines for the registry selected in config/registry.yaml.

Keeps registry-specific branching out of workflow YAML: build-scan-publish.yml consumes
host, image_ref, and username without caring which registry type produced them.

Unreplaced <placeholder> values fail here rather than flowing into an image reference and
producing an unresolvable push target several steps later.
"""
import re
import sys
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[2] / "config" / "registry.yaml"

PLACEHOLDER = re.compile(r"<[^>]+>")
# GITHUB_OUTPUT is newline delimited, so a newline in a value would inject extra outputs.
UNSAFE = re.compile(r"[\r\n]")


def check(name: str, value: str) -> str:
    if PLACEHOLDER.search(value):
        sys.exit(
            f"config/registry.yaml: {name} is still the placeholder {value!r}. "
            "Replace it with the value for your environment before running this pipeline."
        )
    if UNSAFE.search(value):
        sys.exit(f"config/registry.yaml: {name} contains a newline, which is not permitted.")
    return value


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    registry_type = cfg["registry_type"]
    block = cfg.get(registry_type)
    if not block:
        sys.exit(f"config/registry.yaml: no configuration block for registry_type {registry_type!r}")

    host = check("host", str(block["host"]))

    username = check("username", str(block.get("username") or ""))
    if not username:
        sys.exit(f"config/registry.yaml: username is required for registry_type {registry_type!r}")

    if registry_type == "openshift-internal":
        namespace = check("namespace", str(block["namespace"]))
        image_ref = f"{host}/{namespace}/app"
    elif registry_type == "ghcr":
        org = check("org", str(block["org"]))
        image_ref = f"{host}/{org}/app"
    elif registry_type == "artifactory":
        repository = check("repository", str(block["repository"]))
        image_ref = f"{host}/{repository}/app"
    else:
        sys.exit(f"config/registry.yaml: unrecognised registry_type {registry_type!r}")

    print(f"host={host}")
    print(f"image_ref={image_ref}")
    print(f"username={username}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
