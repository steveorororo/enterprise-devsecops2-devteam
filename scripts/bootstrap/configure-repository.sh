#!/usr/bin/env bash
# Applies the branch protection baseline in .github/rulesets/main-branch.json to this
# repository through the GitHub API.
#
# Repository initialization control, not part of application delivery. Run once when a
# repository is created from the template. Safe to re-run: an existing ruleset of the same
# name is updated in place rather than duplicated.
#
# Requires a token in GH_TOKEN with repository Administration: write and Contents: read.
# The default GITHUB_TOKEN cannot manage rulesets. See docs/repository-bootstrap.md.
set -euo pipefail

cd "$(dirname "$0")/../.."

RULESET_FILE=".github/rulesets/main-branch.json"
repository=""
dry_run=false

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap/configure-repository.sh [options]

Options:
  --repository OWNER/NAME  Target repository. Defaults to GITHUB_REPOSITORY, then the
                           origin remote.
  --dry-run                Report the action that would be taken without writing.
  --help                   Show this message.

Environment:
  GH_TOKEN                 Token with repository Administration: write and Contents: read.
EOF
}

fail() {
  printf 'bootstrap: %s\n' "$1" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repository)
      [ $# -ge 2 ] || fail "--repository requires a value"
      repository="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unknown argument: $1"
      ;;
  esac
done

for tool in gh jq; do
  command -v "${tool}" > /dev/null || fail "${tool} is not installed"
done

[ -f "${RULESET_FILE}" ] || fail "${RULESET_FILE} not found"
jq empty "${RULESET_FILE}" 2> /dev/null || fail "${RULESET_FILE} is not valid JSON"

# The file is the source of truth for both the request body and the name used to decide
# between create and update, so the definition is never restated here.
ruleset_name="$(jq -r '.name // empty' "${RULESET_FILE}")"
[ -n "${ruleset_name}" ] || fail "${RULESET_FILE} has no top-level name"

[ -n "${GH_TOKEN:-}" ] || fail "GH_TOKEN is not set. A token with repository Administration: write is required."

# GITHUB_REPOSITORY is set by Actions. Outside Actions, fall back to the origin remote so a
# provisioning process can run this from a fresh clone with no arguments.
if [ -z "${repository}" ]; then
  repository="${GITHUB_REPOSITORY:-}"
fi
if [ -z "${repository}" ]; then
  origin_url="$(git remote get-url origin 2> /dev/null || true)"
  [ -n "${origin_url}" ] || fail "cannot determine the target repository. Pass --repository OWNER/NAME."
  repository="$(printf '%s' "${origin_url}" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
fi

case "${repository}" in
  */*/*|*/) fail "repository must be OWNER/NAME, received: ${repository}" ;;
  */*) : ;;
  *) fail "repository must be OWNER/NAME, received: ${repository}" ;;
esac

printf 'Target repository: %s\n' "${repository}"
printf 'Ruleset source:    %s (name: %s)\n' "${RULESET_FILE}" "${ruleset_name}"

api() {
  # Surfaces the HTTP status so authorization failures are reported as such rather than as
  # a generic API error.
  local method="$1" path="$2"
  shift 2
  local response
  if response="$(gh api --method "${method}" \
    -H "Accept: application/vnd.github+json" \
    "${path}" "$@" 2>&1)"; then
    printf '%s' "${response}"
    return 0
  fi
  case "${response}" in
    *"HTTP 401"*)
      fail "authentication failed. GH_TOKEN is invalid or expired."
      ;;
    *"HTTP 403"*|*"HTTP 404"*)
      fail "not authorized to manage rulesets on ${repository}. The token needs repository Administration: write, and must be able to see the repository."
      ;;
    *)
      printf '%s\n' "${response}" >&2
      fail "GitHub API call failed: ${method} ${path}"
      ;;
  esac
}

# Ruleset management needs admin on the repository. Checking it up front reports the
# privilege problem before any write is attempted, and makes --dry-run meaningful.
admin="$(api GET "repos/${repository}" --jq '.permissions.admin // false')"
[ "${admin}" = "true" ] ||
  fail "the supplied credential does not have admin on ${repository}. Repository Administration: write is required to manage rulesets."

existing_id="$(api GET "repos/${repository}/rulesets" \
  --jq ".[] | select(.name == \"${ruleset_name}\") | .id" | head -n 1)"

if [ -n "${existing_id}" ]; then
  action="update existing ruleset ${existing_id}"
else
  action="create ruleset \"${ruleset_name}\""
fi

if [ "${dry_run}" = true ]; then
  printf 'Dry run: would %s.\n' "${action}"
  exit 0
fi

printf 'Applying: %s\n' "${action}"

if [ -n "${existing_id}" ]; then
  api PUT "repos/${repository}/rulesets/${existing_id}" --input "${RULESET_FILE}" > /dev/null
  ruleset_id="${existing_id}"
else
  ruleset_id="$(api POST "repos/${repository}/rulesets" --input "${RULESET_FILE}" --jq '.id')"
fi

# Confirm the applied state rather than trusting the write. A repository whose ruleset is
# not active is not fully initialized.
applied="$(api GET "repos/${repository}/rulesets/${ruleset_id}")"
enforcement="$(printf '%s' "${applied}" | jq -r '.enforcement')"
rule_types="$(printf '%s' "${applied}" | jq -r '[.rules[].type] | join(", ")')"

[ "${enforcement}" = "active" ] ||
  fail "ruleset ${ruleset_id} applied with enforcement \"${enforcement}\". The repository is not fully initialized until enforcement is active."

duplicates="$(api GET "repos/${repository}/rulesets" \
  --jq "[.[] | select(.name == \"${ruleset_name}\")] | length")"
[ "${duplicates}" = "1" ] ||
  fail "expected exactly one ruleset named \"${ruleset_name}\", found ${duplicates}"

printf 'Ruleset %s is active on %s\n' "${ruleset_id}" "${repository}"
printf 'Rules applied: %s\n' "${rule_types}"
printf 'Branch protection baseline is in place.\n'
