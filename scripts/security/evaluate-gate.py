#!/usr/bin/env python3
"""Aggregate upstream job results into a single required status check.

Each scanner fails its own job when it exceeds its configured threshold. This turns those
job results into one check that branch protection can require, so adding a scanner does not
mean editing branch protection.

Only success passes. A skipped job passes only if it is named under skippable_jobs in
config/security-gate.yaml. A job listed in required_jobs but absent from the payload fails
the gate, so deleting a job from the workflow breaks the build rather than quietly removing
a control.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[2] / "config" / "security-gate.yaml"


def load_gate_config() -> tuple[set[str], set[str]]:
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    required = set(cfg.get("required_jobs") or [])
    skippable = set(cfg.get("skippable_jobs") or [])
    return required, skippable


def evaluate(needs: dict, required: set[str], skippable: set[str]) -> list[str]:
    problems = []

    for name in sorted(required - set(needs)):
        problems.append(f"{name}: required by the gate but absent from the workflow")

    for name, job in sorted(needs.items()):
        result = (job or {}).get("result")
        if result == "success":
            continue
        if result == "skipped" and name in skippable:
            continue
        if result == "skipped":
            problems.append(f"{name}: skipped, and not listed under skippable_jobs")
        else:
            problems.append(f"{name}: {result}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--needs", required=True, help="JSON of the workflow's needs context")
    args = parser.parse_args()

    required, skippable = load_gate_config()
    problems = evaluate(json.loads(args.needs), required, skippable)

    if problems:
        print("security gate failed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("security gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
