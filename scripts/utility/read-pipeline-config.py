#!/usr/bin/env python3
"""Emit validated GITHUB_OUTPUT values from config/pipeline.yaml.

Application teams configure paths, build commands, CodeQL languages, the GitOps target, and
optional controls here instead of editing workflow files.
"""
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config" / "pipeline.yaml"

PLACEHOLDER = re.compile(r"<[^>]+>")
UNSAFE = re.compile(r"[\x00-\x1f\x7f]")
REPO_SLUG = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

# CodeQL build mode and runner are selected centrally so a developer chooses a language, not
# workflow mechanics. Go, Java/Kotlin and Swift require a build-capable mode. Swift requires
# macOS. The remaining supported languages use no-build extraction.
CODEQL = {
    "actions": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "c-cpp": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "csharp": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "go": {"build_mode": "autobuild", "runner": "ubuntu-24.04"},
    "java-kotlin": {"build_mode": "autobuild", "runner": "ubuntu-24.04"},
    "javascript-typescript": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "python": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "ruby": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "rust": {"build_mode": "none", "runner": "ubuntu-24.04"},
    "swift": {"build_mode": "autobuild", "runner": "macos-15"},
}

# File extensions that decide whether a configured language has anything to analyse. A
# language configured before its source exists is a starter-template state, not a finding, and
# CodeQL has no mode that tolerates an empty database. Detection runs per pull request, so the
# first commit that adds matching source makes that language's analysis mandatory again with
# no configuration change.
SOURCE_EXTENSIONS = {
    "c-cpp": (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"),
    "csharp": (".cs", ".cshtml", ".razor"),
    "go": (".go",),
    "java-kotlin": (".java", ".kt", ".kts"),
    "javascript-typescript": (".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"),
    "python": (".py",),
    "ruby": (".erb", ".gemspec", ".rb"),
    "rust": (".rs",),
    "swift": (".swift",),
}

WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def fail(message: str) -> None:
    print(f"config/pipeline.yaml: {message}", file=sys.stderr)
    raise SystemExit(1)


def emit(name: str, value: str) -> None:
    if UNSAFE.search(value):
        fail(f"{name} contains a control character, which is not permitted")
    print(f"{name}={value}")


def safe_repository_slug(name: str, value: str) -> str:
    if UNSAFE.search(value) or not REPO_SLUG.fullmatch(value):
        fail(f"{name} {value!r} is not in owner/name form")
    owner, repository = value.split("/", 1)
    if owner in {".", ".."} or repository in {".", ".."}:
        fail(f"{name} must not contain '.' or '..' path segments")
    return value


def safe_relative_path(name: str, value: str, *, must_exist: bool) -> str:
    if UNSAFE.search(value) or "\\" in value:
        fail(f"{name} must be a clean POSIX relative path")
    if value.startswith("/") or value.endswith("/"):
        fail(f"{name} must be relative and must not end with a slash")

    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{name} must be a relative path without '.' or '..' components")

    if must_exist:
        candidate = (REPO_ROOT / Path(*path.parts)).resolve()
        try:
            candidate.relative_to(REPO_ROOT.resolve())
        except ValueError:
            fail(f"{name} resolves outside the repository")
        if not candidate.is_dir():
            fail(f"{name} does not exist as a directory: {value!r}")

    return value


def repository_extensions() -> set[str]:
    """Extensions of every file in the working tree, excluding .git."""
    found = set()
    for _root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in files:
            suffix = os.path.splitext(name)[1].lower()
            if suffix:
                found.add(suffix)
    return found


def source_present(language: str, extensions: set[str]) -> bool:
    # The whole working tree is searched rather than application.path, because application.path
    # is still a placeholder in an unconfigured template and source added at the repository
    # root would otherwise go unanalysed.
    if language == "actions":
        return WORKFLOWS.is_dir() and any(
            path.suffix in {".yml", ".yaml"} for path in WORKFLOWS.iterdir() if path.is_file()
        )
    return bool(set(SOURCE_EXTENSIONS[language]) & extensions)


def main() -> int:
    try:
        cfg = yaml.safe_load(CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        fail(f"cannot read configuration: {exc}")

    if not isinstance(cfg, dict):
        fail("top-level document must be a mapping")

    app = cfg.get("application", {}) or {}
    app_path = str(app.get("path") or "").strip()
    app_configured = bool(app_path) and not PLACEHOLDER.search(app_path)
    if app_configured:
        app_path = safe_relative_path("application.path", app_path, must_exist=True)
    emit("app_path", app_path if app_configured else "")
    emit("app_configured", str(app_configured).lower())

    build = cfg.get("build", {}) or {}
    for step in ("install", "lint", "test", "compile"):
        emit(f"build_{step}", str(build.get(step) or "").strip())
    any_build = any(str(build.get(step) or "").strip() for step in ("install", "lint", "test", "compile"))
    emit("build_configured", str(bool(app_configured and any_build)).lower())

    languages = cfg.get("languages", {}).get("codeql") or []
    if not isinstance(languages, list) or not languages:
        fail("languages.codeql must list at least one language")
    languages = [str(language) for language in languages]
    if len(set(languages)) != len(languages):
        fail("languages.codeql must not contain duplicate entries")
    unknown = sorted(set(languages) - set(CODEQL))
    if unknown:
        fail(f"unsupported CodeQL language(s) {unknown}. Supported: {sorted(CODEQL)}")

    extensions = repository_extensions()
    matrix = {
        "include": [
            {
                "language": language,
                "build_mode": CODEQL[language]["build_mode"],
                "runner": CODEQL[language]["runner"],
                "source_present": source_present(language, extensions),
            }
            for language in languages
        ]
    }
    emit("codeql_matrix", json.dumps(matrix, separators=(",", ":")))

    gitops = cfg.get("gitops", {}) or {}
    gitops_repository = str(gitops.get("repository") or "").strip()
    gitops_path = str(gitops.get("path") or "").strip()
    gitops_configured = (
        bool(gitops_repository)
        and not PLACEHOLDER.search(gitops_repository)
        and bool(gitops_path)
        and not PLACEHOLDER.search(gitops_path)
    )
    if gitops_configured:
        gitops_repository = safe_repository_slug("gitops.repository", gitops_repository)
        gitops_path = safe_relative_path("gitops.path", gitops_path, must_exist=False)
        if PurePosixPath(gitops_path).name != "dev":
            fail("gitops.path must identify the dev directory and end with '/dev'")

    emit("gitops_repository", gitops_repository if gitops_configured else "")
    emit("gitops_path", gitops_path if gitops_configured else "")
    emit("gitops_configured", str(gitops_configured).lower())

    emit("sonar_enabled", str(bool(cfg.get("sonar", {}).get("enabled"))).lower())
    emit("trivy_fs_enabled", str(bool(cfg.get("sca", {}).get("trivy_fs"))).lower())
    emit("signing_enabled", str(bool(cfg.get("signing", {}).get("enabled"))).lower())

    return 0


if __name__ == "__main__":
    sys.exit(main())
