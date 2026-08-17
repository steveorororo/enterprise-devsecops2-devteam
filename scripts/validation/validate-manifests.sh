#!/usr/bin/env bash
# Renders and lints every deployment overlay.
# Run before opening a pull request that touches deploy/.
set -euo pipefail

cd "$(dirname "$0")/../.."

for tool in kustomize kube-linter; do
  command -v "${tool}" > /dev/null || {
    printf '%s is not installed\n' "${tool}" >&2
    exit 1
  }
done

for env in dev test prod; do
  echo "rendering and linting ${env}"
  kustomize build "deploy/overlays/${env}"     | kube-linter lint --config security/iac/.kube-linter.yaml -
done

echo "all overlays render and lint cleanly"
