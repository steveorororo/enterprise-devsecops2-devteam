#!/usr/bin/env python3
"""Validate machine-readable security suppression records and scanner exception linkage.

Application-specific suppressions are time-bound records. A small set of repository-wide
Checkov checks are baseline design exclusions because they conflict with the OpenShift or
workload model documented in security/iac/.checkov.yaml. The validator fixes that set so a
new global skip cannot be added silently.
"""
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parents[2]
DIRECTORY = REPO / "security" / "suppressions"
TRIVY_IGNORE = REPO / "security" / "sca" / ".trivyignore"
CHECKOV_CONFIG = REPO / "security" / "iac" / ".checkov.yaml"
ID = re.compile(r"^SUPP-\d{4}-\d{3,}$")
# Trivy is the only application-specific scanner ignore mechanism this template currently
# links to a machine-validated record. Checkov's small repository-wide baseline is governed
# separately below. Other scanners intentionally have no template-level bypass until a
# concrete, enforceable linkage is implemented for their native exception mechanism.
TOOLS = {"trivy"}
REQUIRED = {
    "id",
    "tool",
    "finding",
    "justification",
    "owner",
    "approved_by",
    "issue",
    "scope",
    "created",
    "review_date",
    "expires",
}

# These are template-level design exclusions, not application finding suppressions. Their
# rationale is kept beside the actual skip-check entries. The exact set is enforced here so
# adding a new repository-wide Checkov bypass requires an explicit validation-code change.
BASELINE_CHECKOV_SKIPS = {"CKV_K8S_11", "CKV_K8S_23", "CKV_K8S_40", "CKV_DOCKER_2"}


def as_date(value, field, path):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{path}: {field} must be YYYY-MM-DD") from exc


def load_record(path: Path) -> tuple[dict | None, list[str]]:
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        return None, [f"{path}: cannot parse record: {exc}"]
    if not isinstance(doc, dict):
        return None, [f"{path}: suppression record must be a YAML mapping"]
    return doc, []


def validate(path: Path, doc: dict) -> list[str]:
    problems: list[str] = []
    missing = sorted(REQUIRED - set(doc))
    if missing:
        problems.append(f"{path}: missing required field(s): {', '.join(missing)}")
        return problems

    record_id = str(doc["id"]).strip()
    if not ID.fullmatch(record_id):
        problems.append(f"{path}: id must match SUPP-YYYY-NNN")
    if path.stem != record_id:
        problems.append(f"{path}: filename must match id ({record_id}.yaml)")

    tool = str(doc["tool"]).strip()
    if tool not in TOOLS:
        problems.append(f"{path}: unsupported tool {tool!r}; expected one of {sorted(TOOLS)}")

    for field in ("finding", "justification", "owner", "approved_by", "issue", "scope"):
        if not str(doc[field]).strip():
            problems.append(f"{path}: {field} must not be empty")

    issue = urlparse(str(doc["issue"]).strip())
    if issue.scheme != "https" or not issue.netloc:
        problems.append(f"{path}: issue must be an https URL")

    scope = str(doc["scope"]).strip().lower()
    if scope in {"*", "/", "all", "repository", "entire repository"}:
        problems.append(f"{path}: scope must be narrower than the whole repository")

    try:
        created = as_date(doc["created"], "created", path)
        review = as_date(doc["review_date"], "review_date", path)
        expires = as_date(doc["expires"], "expires", path)
        if expires < created:
            problems.append(f"{path}: expires is before created")
        if (expires - created).days > 90:
            problems.append(f"{path}: suppression lifetime exceeds 90 days")
        if not created <= review <= expires:
            problems.append(f"{path}: review_date must be between created and expires")
        if expires < date.today():
            problems.append(f"{path}: suppression expired on {expires.isoformat()}")
    except ValueError as exc:
        problems.append(str(exc))

    return problems


def validate_checkov_baseline() -> list[str]:
    try:
        cfg = yaml.safe_load(CHECKOV_CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"{CHECKOV_CONFIG}: cannot parse Checkov configuration: {exc}"]
    actual = {str(item) for item in (cfg.get("skip-check") or [])}
    if actual != BASELINE_CHECKOV_SKIPS:
        added = sorted(actual - BASELINE_CHECKOV_SKIPS)
        missing = sorted(BASELINE_CHECKOV_SKIPS - actual)
        parts = []
        if added:
            parts.append(f"unreviewed global skip(s): {', '.join(added)}")
        if missing:
            parts.append(f"expected documented baseline skip(s) missing: {', '.join(missing)}")
        return [f"{CHECKOV_CONFIG}: {'; '.join(parts)}"]
    return []


def validate_trivy_ignore(records: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    for number, raw in enumerate(TRIVY_IGNORE.read_text().splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        finding, sep, comment = stripped.partition("#")
        finding = finding.strip()
        record_id = comment.strip() if sep else ""
        if not ID.fullmatch(record_id):
            problems.append(
                f"{TRIVY_IGNORE}:{number}: active ignore must end with '# SUPP-YYYY-NNN'"
            )
            continue
        record = records.get(record_id)
        if record is None:
            problems.append(f"{TRIVY_IGNORE}:{number}: referenced record {record_id} does not exist")
            continue
        if str(record.get("tool", "")).strip() != "trivy":
            problems.append(f"{TRIVY_IGNORE}:{number}: {record_id} is not a Trivy suppression")
        if str(record.get("finding", "")).strip() != finding:
            problems.append(
                f"{TRIVY_IGNORE}:{number}: finding {finding!r} does not match {record_id}"
            )
    return problems


def main() -> int:
    problems: list[str] = []
    records: dict[str, dict] = {}
    for path in sorted(DIRECTORY.glob("*.yaml")):
        doc, load_problems = load_record(path)
        problems.extend(load_problems)
        if doc is None:
            continue
        problems.extend(validate(path, doc))
        record_id = str(doc.get("id", "")).strip()
        if record_id:
            records[record_id] = doc

    problems.extend(validate_checkov_baseline())
    problems.extend(validate_trivy_ignore(records))

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1

    print("suppression records and scanner exception linkage valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
