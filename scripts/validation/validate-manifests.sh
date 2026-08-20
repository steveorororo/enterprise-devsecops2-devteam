#!/usr/bin/env bash
# Renders and lints every deployment overlay using the same policy CI uses.
# Run before opening a pull request that touches deploy/.
#
# The check configuration is owned by the AppSec platform and is fetched at the platform
# commit this repository consumes, so local results match CI rather than drifting from it.
set -euo pipefail

cd "$(dirname "$0")/../.."

PLATFORM_REPO="steveorororo/enterprise-devsecops2-appsec"
PLATFORM_REF="64931c9e44aef687853962895f5a74cfd9d80395"

for tool in kustomize kube-linter curl; do
  command -v "${tool}" > /dev/null || {
    printf '%s is not installed\n' "${tool}" >&2
    exit 1
  }
done

config="$(mktemp)"
trap 'rm -f "${config}"' EXIT
curl -sSfL -o "${config}"   "https://raw.githubusercontent.com/${PLATFORM_REPO}/${PLATFORM_REF}/security/kube-linter.yaml"

for env in dev test prod; do
  echo "rendering and linting ${env}"
  kustomize build "deploy/overlays/${env}" | kube-linter lint --config "${config}" -
done

echo "all overlays render and lint cleanly"
