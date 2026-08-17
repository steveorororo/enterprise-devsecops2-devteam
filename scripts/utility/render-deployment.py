#!/usr/bin/env python3
"""Render one deployment overlay with a verified immutable image digest.

The source tree is copied to a temporary directory before its digest is changed, so the
application repository remains the source of truth and is never modified by promotion.
When writing into a GitOps checkout, the configured environment directory is validated,
replaced as a generated unit, and receives only the rendered manifests file.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"
BUMP = REPO / "scripts" / "utility" / "bump-gitops-digest.py"
ENVIRONMENTS = {"dev", "test", "prod"}


def fail(message: str) -> int:
    print(f"render-deployment: {message}", file=sys.stderr)
    return 1


def safe_gitops_path(raw: str) -> PurePosixPath:
    if not raw or raw.startswith("/") or "\\" in raw or any(ord(ch) < 32 for ch in raw):
        raise ValueError("GitOps path must be a non-empty relative POSIX path")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("GitOps path must not contain empty, dot, or parent segments")
    return path


def write_gitops_target(checkout_raw: str, path_raw: str, rendered: str) -> Path:
    checkout = Path(checkout_raw).resolve()
    if not checkout.is_dir():
        raise ValueError("GitOps checkout directory does not exist")

    relative = safe_gitops_path(path_raw)
    candidate = checkout.joinpath(*relative.parts)

    # Reject symlink traversal even when the link resolves inside the checkout. The target
    # directory is deleted and regenerated as a unit, so following a symlink here could
    # delete or overwrite a different GitOps path than the configured one.
    current = checkout
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("GitOps path must not traverse symlinks")

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(checkout)
    except ValueError as exc:
        raise ValueError("GitOps path resolves outside the checkout") from exc
    if resolved == checkout:
        raise ValueError("GitOps path must not be the checkout root")

    # The configured environment path is generated desired state. Replacing it as a unit
    # prevents stale hand-maintained files from being applied alongside the scanned render.
    if candidate.is_symlink() or candidate.is_file():
        candidate.unlink()
    elif candidate.exists():
        shutil.rmtree(candidate)
    candidate.mkdir(parents=True, exist_ok=True)
    output = candidate / "manifests.yaml"
    output.write_text(rendered)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True, choices=sorted(ENVIRONMENTS))
    parser.add_argument("--digest", required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", help="file to receive rendered Kubernetes YAML")
    destination.add_argument(
        "--gitops-checkout",
        help="GitOps repository checkout whose generated environment directory will be replaced",
    )
    parser.add_argument(
        "--gitops-path",
        help="relative generated environment directory inside --gitops-checkout",
    )
    args = parser.parse_args()

    if args.gitops_checkout and not args.gitops_path:
        return fail("--gitops-path is required with --gitops-checkout")
    if args.output and args.gitops_path:
        return fail("--gitops-path is only valid with --gitops-checkout")

    kustomize = shutil.which("kustomize")
    if kustomize is None:
        return fail("kustomize not found on PATH")

    with tempfile.TemporaryDirectory(prefix="promotion-") as tmp:
        copied = Path(tmp) / "deploy"
        shutil.copytree(DEPLOY, copied)
        overlay = copied / "overlays" / args.environment

        bump = subprocess.run(
            [
                sys.executable,
                str(BUMP),
                "--path",
                str(overlay),
                "--digest",
                args.digest,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if bump.returncode != 0:
            return fail(bump.stderr.strip() or "digest update failed")

        rendered = subprocess.run(
            [kustomize, "build", str(overlay)],
            capture_output=True,
            text=True,
            check=False,
        )
        if rendered.returncode != 0:
            return fail(rendered.stderr.strip() or "kustomize build failed")
        if args.digest not in rendered.stdout:
            return fail("promoted digest is absent from rendered output")

        try:
            if args.gitops_checkout:
                output = write_gitops_target(args.gitops_checkout, args.gitops_path, rendered.stdout)
            else:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered.stdout)
        except (OSError, ValueError) as exc:
            return fail(str(exc))

    print(f"rendered {args.environment} to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
