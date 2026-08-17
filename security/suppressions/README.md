# Suppressions

The machine-linked application suppression mechanism in this template currently covers Trivy
only. A Trivy suppression is not complete until it has a time-bound record in this directory
and the matching `.trivyignore` entry references that record. The record documents the risk
decision; it does not replace approval by the repository's configured security owners.

`scripts/security/validate-suppressions.py` runs in pull request validation. It rejects
incomplete, over-broad, over-90-day, or expired records. It also verifies active Trivy ignore
entries point to matching records. Security-owner approval is enforced only after real owners
are configured in `.github/CODEOWNERS` or through an equivalent repository governance control.

## Entry format

One file per suppression, named exactly after its `id`, for example
`security/suppressions/SUPP-2026-001.yaml`:

```yaml
id: SUPP-2026-001
tool: trivy
finding: CVE-2026-00000
justification: >
  The affected code path is not reachable in the deployed configuration.
owner: owner@example.invalid
approved_by: appsec-team
issue: https://github.com/<org>/<repo>/issues/123
scope: path/to/component
created: 2026-08-11
review_date: 2026-09-10
expires: 2026-11-09
```

The supported `tool` value is `trivy`.

For Trivy, the active ignore entry must carry the record id on the same line:

```text
CVE-2026-00000 # SUPP-2026-001
```

## Baseline Checkov exclusions

The four `skip-check` entries in `security/iac/.checkov.yaml` are template-level design
exclusions, not application-specific accepted-risk records. Their rationale is documented
beside each entry because the generic checks conflict with the template's OpenShift or
workload model. The validator fixes that set exactly; adding any new repository-wide Checkov
skip fails pull request validation until the validation policy is deliberately changed.

The baseline exclusions still require confirmation by the responsible application security
and OpenShift platform owners before broad enterprise adoption. Application teams must not
add their own global Checkov skips to this baseline.

## Other scanners

CodeQL, ZAP, and kube-linter do not have an application-specific suppression mechanism wired
to this record validator. Do not add an ad hoc ignore and assume this directory makes it
governed. Fix the finding or use the exception process approved by the security owner for
that scanner. If a reusable template-level bypass is added later, its native ignore must be
machine-linked to a current record before it is treated as supported.

## Rules

- Maximum lifetime for an application suppression is 90 days from `created` to `expires`.
- `review_date` must fall between creation and expiry.
- `scope` must identify a path or component, not the whole repository.
- An expired record fails validation until the finding is fixed or a newly approved record
  replaces it.
- Do not add a scanner ignore without a corresponding current record.
- Do not expand the baseline Checkov skip set as an application-specific workaround.
