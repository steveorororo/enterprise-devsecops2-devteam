# Repository bootstrap

Provisioning and maintainer reference. Application teams do not need this document; the
README covers what they see. This describes how the `main` branch protection baseline is
applied to a repository created from the template.

## What it does

`scripts/bootstrap/configure-repository.sh` reads `.github/rulesets/main-branch.json` and
applies it through the GitHub repository rulesets API. The JSON file is the only definition
of the baseline. The script neither restates nor rewrites it; the file supplies both the
request body and the ruleset name used to decide between create and update.

Sequence:

1. Resolve the target repository from `GITHUB_REPOSITORY`, then the `origin` remote, or from
   `--repository OWNER/NAME`.
2. Confirm the credential has admin on the repository.
3. Look for an existing ruleset with the name in the JSON file.
4. Create it when absent, update that same ruleset in place when present.
5. Read the applied ruleset back and confirm enforcement is `active` and that exactly one
   ruleset carries the name.

Any failure exits non-zero. A repository whose bootstrap did not succeed is not fully
initialized, and `main` is unprotected until it does.

## Invocation

**Provisioning process, preferred.** Run the script directly after the repository is created:

```text
GH_TOKEN=<provisioning token> scripts/bootstrap/configure-repository.sh
```

`--dry-run` reports the action that would be taken, including the authorization check,
without writing.

**Manual dispatch.** For repositories initialized through the GitHub UI, the
`Repository Bootstrap` workflow wraps the same script. It is `workflow_dispatch` only, holds
`contents: read`, and reads the credential from the `BOOTSTRAP_ADMIN_TOKEN` repository secret.
It never runs on `push` or `pull_request`, and it does not modify application source.

Requires `gh` and `jq`, both present on GitHub-hosted runners.

## Required privilege

A credential scoped to the single repository with:

| Permission | Level | Used for |
|---|---|---|
| Administration | Write | Creating and updating the ruleset |
| Contents | Read | Reading the ruleset definition from the checkout |

Preference order is a GitHub App installation token or an enterprise provisioning identity,
then a fine-grained personal access token as a fallback.

The default `GITHUB_TOKEN` cannot be used. Its permission set has no `administration` key, so
no workflow-level grant makes it capable of managing rulesets. This is why the dispatch
workflow requires a separately provisioned secret rather than widening workflow permissions.

No credential is stored in this repository. The token is supplied by the environment at run
time.

## Re-running

Re-running is safe and is the supported way to reapply the baseline after the JSON file
changes. The existing ruleset is updated in place, so repeated runs do not accumulate
duplicate rulesets. The final check fails if more than one ruleset carries the expected name.

## Failure triage

| Message | Cause |
|---|---|
| `GH_TOKEN is not set` | No credential supplied by the provisioning environment |
| `authentication failed` | Token invalid, expired, or revoked |
| `does not have admin on <repo>` | Credential lacks Administration: write |
| `not authorized to manage rulesets` | Token cannot see the repository, or the organization restricts ruleset management |
| `applied with enforcement "<value>"` | The ruleset exists but is not active, so protection is not in force |
| `expected exactly one ruleset named` | A second ruleset of the same name was created outside this process |

If an organization policy prevents the provisioning identity from managing repository
rulesets, escalate to the organization owners rather than reducing the baseline. Lowering
`enforcement` or adding bypass actors to make the bootstrap succeed defeats the control.
