#!/usr/bin/env python3
"""Render GitOps example manifests with validated adopter values.

Every adopter-specific value in gitops/examples is an <UPPER_SNAKE> token. Values are
validated before substitution and every rendered YAML document is parsed before any output
is written. This prevents a configuration value from changing YAML structure.
"""
import argparse
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "gitops" / "examples"

TOKEN = re.compile(r"<([A-Z][A-Z0-9_]*)>")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
REPO_SLUG = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@+-]{0,199}$")

TOKENS = {
    "APP_NAME": "Short application name used for Argo CD Application names.",
    "APP_PROJECT_NAME": "Argo CD AppProject name.",
    "GITOPS_REPO_URL": "Clone URL of the GitOps repository holding desired state.",
    "NAMESPACE_PREFIX": "Namespace prefix; -dev, -test and -prod are appended.",
    "GITHUB_REPO": "owner/repo of the application repository for workflow dispatch.",
    "SYNCED_REVISION": "Revision Argo CD synced, supplied when the hook is rendered.",
    "GITOPS_DEV_PATH": "Derived from gitops.path in config/pipeline.yaml.",
    "GITOPS_TEST_PATH": "Derived sibling path for test.",
    "GITOPS_PROD_PATH": "Derived sibling path for production.",
}
DERIVED_TOKENS = {"GITOPS_DEV_PATH", "GITOPS_TEST_PATH", "GITOPS_PROD_PATH"}

EXPECTED_KINDS = {
    "application-dev.yaml": ("argoproj.io/v1alpha1", "Application"),
    "application-test.yaml": ("argoproj.io/v1alpha1", "Application"),
    "application-prod.yaml": ("argoproj.io/v1alpha1", "Application"),
    "appproject.yaml": ("argoproj.io/v1alpha1", "AppProject"),
    "postsync-dast-hook.yaml": ("batch/v1", "Job"),
}


def fail(message: str) -> None:
    raise ValueError(message)


def validate_dns_label(name: str, value: str) -> None:
    if len(value) > 63 or not DNS_LABEL.fullmatch(value):
        fail(
            f"{name} must be a lowercase Kubernetes DNS label of at most 63 characters "
            "using letters, digits and hyphens."
        )



def validate_repository_slug(name: str, value: str) -> None:
    if not REPO_SLUG.fullmatch(value):
        fail(f"{name} must be in owner/repo form.")
    owner, repository = value.split("/", 1)
    if owner in {".", ".."} or repository in {".", ".."}:
        fail(f"{name} must not contain '.' or '..' path segments.")


def validate_repository_path(name: str, path_value: str) -> None:
    path = PurePosixPath(path_value.lstrip("/"))
    if not path_value or path_value in {"/", ".", ".."} or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        fail(f"{name} must identify a repository path without '.' or '..' segments.")


def validate_git_url(value: str) -> None:
    if CONTROL.search(value) or any(ch.isspace() for ch in value):
        fail("GITOPS_REPO_URL contains whitespace or control characters.")

    if value.startswith("git@"):
        match = re.fullmatch(r"git@[A-Za-z0-9.-]+:([A-Za-z0-9._/-]+(?:\.git)?)", value)
        if not match:
            fail("GITOPS_REPO_URL is not a valid SSH clone URL.")
        validate_repository_path("GITOPS_REPO_URL", match.group(1))
        return

    parsed = urlparse(value)
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        fail("GITOPS_REPO_URL must use https, ssh, or git@host:path syntax.")
    if parsed.username or parsed.password:
        fail("GITOPS_REPO_URL must not contain embedded credentials.")
    if not parsed.path or parsed.path in {"", "/"}:
        fail("GITOPS_REPO_URL must identify a repository path.")
    validate_repository_path("GITOPS_REPO_URL", parsed.path)


def validate_revision(value: str) -> None:
    if not REVISION.fullmatch(value):
        fail(
            "SYNCED_REVISION contains characters that are not permitted in the hook value."
        )
    if ".." in value or "@{" in value or value.endswith(("/", ".")) or "//" in value:
        fail("SYNCED_REVISION is not a safe revision value.")


def validate_values(values: dict[str, str]) -> None:
    missing = sorted(set(TOKENS) - set(values))
    if missing:
        fail(f"no value supplied for {', '.join(missing)}")

    for name, value in values.items():
        if not value:
            fail(f"{name} must not be empty.")
        if CONTROL.search(value):
            fail(f"{name} contains a control character, which is not permitted.")

    validate_dns_label("APP_NAME", values["APP_NAME"])
    validate_dns_label("APP_PROJECT_NAME", values["APP_PROJECT_NAME"])
    validate_dns_label("NAMESPACE_PREFIX", values["NAMESPACE_PREFIX"])

    validate_repository_slug("GITHUB_REPO", values["GITHUB_REPO"])

    validate_git_url(values["GITOPS_REPO_URL"])
    validate_revision(values["SYNCED_REVISION"])

    for name in DERIVED_TOKENS:
        value = values[name]
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            fail(f"{name} is not a safe relative GitOps path.")


def derived_path_values() -> dict[str, str]:
    config = REPO / "config" / "pipeline.yaml"
    loaded = yaml.safe_load(config.read_text()) or {}
    gitops_path = str((loaded.get("gitops", {}) or {}).get("path") or "").strip()
    if not gitops_path or "<" in gitops_path or ">" in gitops_path:
        fail("config/pipeline.yaml: gitops.path must be set before GitOps examples are rendered.")
    if CONTROL.search(gitops_path) or "\\" in gitops_path:
        fail("config/pipeline.yaml: gitops.path must be a clean POSIX relative path.")

    path = PurePosixPath(gitops_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail("config/pipeline.yaml: gitops.path must be a safe relative path.")
    if path.name != "dev":
        fail("config/pipeline.yaml: gitops.path must end with '/dev'.")

    parent = path.parent
    return {
        "GITOPS_DEV_PATH": str(parent / "dev"),
        "GITOPS_TEST_PATH": str(parent / "test"),
        "GITOPS_PROD_PATH": str(parent / "prod"),
    }


def load_values(path, overrides):
    values: dict[str, str] = derived_path_values()
    if path:
        loaded = yaml.safe_load(Path(path).read_text()) or {}
        if not isinstance(loaded, dict):
            fail(f"{path}: expected a mapping of token names to values")
        supplied = {str(k): str(v) for k, v in loaded.items()}
        forbidden = sorted(set(supplied) & DERIVED_TOKENS)
        if forbidden:
            fail(f"{', '.join(forbidden)} are derived from config/pipeline.yaml and cannot be overridden.")
        values.update(supplied)

    for item in overrides:
        if "=" not in item:
            fail(f"--set expects NAME=VALUE, got {item!r}")
        name, _, value = item.partition("=")
        name = name.strip()
        if name in DERIVED_TOKENS:
            fail(f"{name} is derived from config/pipeline.yaml and cannot be overridden.")
        values[name] = value

    unknown = sorted(set(values) - set(TOKENS))
    if unknown:
        fail(f"unknown token(s): {', '.join(unknown)}. Known: {', '.join(sorted(TOKENS))}")

    validate_values(values)
    return values


def validate_rendered(filename: str, text: str) -> None:
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        fail(f"{filename}: rendered YAML is invalid: {exc}")

    if len(documents) != 1 or not isinstance(documents[0], dict):
        fail(f"{filename}: expected exactly one YAML mapping document.")

    expected = EXPECTED_KINDS.get(filename)
    if expected is None:
        fail(f"{filename}: no expected apiVersion/kind is registered for this example.")

    doc = documents[0]
    if (doc.get("apiVersion"), doc.get("kind")) != expected:
        fail(
            f"{filename}: rendered apiVersion/kind changed unexpectedly; expected "
            f"{expected[0]} {expected[1]}."
        )


def render(values: dict[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for src in sorted(SOURCE.glob("*.yaml")):
        text = TOKEN.sub(lambda match: values.get(match.group(1), match.group(0)), src.read_text())
        leftover = sorted({match.group(1) for match in TOKEN.finditer(text)})
        if leftover:
            fail(f"{src.name}: unresolved token(s): {', '.join(leftover)}")
        validate_rendered(src.name, text)
        rendered[src.name] = text
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", help="YAML file mapping token names to values")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--output", help="directory to write rendered manifests to")
    parser.add_argument("--list-tokens", action="store_true", help="print the token list and exit")
    args = parser.parse_args()

    if args.list_tokens:
        for name in sorted(TOKENS):
            print(f"{name:20} {TOKENS[name]}")
        return 0

    if not args.output:
        parser.error("--output is required unless --list-tokens is given")

    try:
        values = load_values(args.values, args.set)
        rendered = render(values)
    except (OSError, ValueError) as exc:
        print(f"render-gitops: {exc}", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for filename, text in rendered.items():
        path = out / filename
        path.write_text(text)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
