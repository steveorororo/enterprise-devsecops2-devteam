#!/usr/bin/env python3
"""Set one named image digest in a Kustomize overlay and verify the rendered result."""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class PromotionError(RuntimeError):
    pass


def render(path: Path) -> str:
    kustomize = shutil.which("kustomize")
    if kustomize is None:
        raise PromotionError("kustomize not found on PATH; cannot verify the promoted digest")

    result = subprocess.run(
        [kustomize, "build", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PromotionError(f"kustomize build failed for {path}:\n{result.stderr}")
    return result.stdout


def update_digest(overlay: Path, digest: str, image_name: str) -> None:
    if not DIGEST.fullmatch(digest):
        raise PromotionError(
            f"malformed digest {digest!r}, expected sha256: followed by 64 lowercase hex characters"
        )

    kfile = overlay / "kustomization.yaml"
    if not kfile.is_file():
        raise PromotionError(f"kustomization file not found: {kfile}")

    original = kfile.read_text()
    try:
        doc = yaml.safe_load(original)
    except yaml.YAMLError as exc:
        raise PromotionError(f"invalid YAML in {kfile}: {exc}") from exc

    if not isinstance(doc, dict):
        raise PromotionError(f"{kfile} must contain a YAML mapping")

    images = doc.get("images")
    if not isinstance(images, list) or not images:
        raise PromotionError(f"no images: block in {kfile}")

    matches = [
        entry for entry in images
        if isinstance(entry, dict) and entry.get("name") == image_name
    ]
    if len(matches) != 1:
        raise PromotionError(
            f"{kfile} must contain exactly one images: entry named {image_name!r}; found {len(matches)}"
        )

    matches[0]["digest"] = digest
    matches[0].pop("newTag", None)

    kfile.write_text(yaml.safe_dump(doc, sort_keys=False))
    try:
        rendered = render(overlay)
        if digest not in rendered:
            raise PromotionError(
                f"{digest} is absent from rendered output; the images: entry is not being applied"
            )
    except Exception:
        kfile.write_text(original)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, help="overlay directory containing kustomization.yaml")
    parser.add_argument("--digest", required=True, help="registry digest, sha256:<64 lowercase hex>")
    parser.add_argument("--image-name", default="app", help="Kustomize images: name to update")
    args = parser.parse_args()

    try:
        update_digest(Path(args.path), args.digest, args.image_name)
    except (OSError, PromotionError) as exc:
        print(f"bump-gitops-digest: {exc}", file=sys.stderr)
        return 1

    print(f"{Path(args.path) / 'kustomization.yaml'} promoted to {args.digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
