# Security

## Reporting a vulnerability

Report vulnerabilities in this template through GitHub's private vulnerability reporting on
this repository. Keep exploit detail, credentials, and production data out of public issues.

For a vulnerability in a deployed application built from this template, follow the incident
process of the team that owns that application. This repository has no visibility into
downstream deployments.

## What this template does and does not protect

Pull request controls cover static analysis, dependency risk, secrets, infrastructure as code,
manifest validation, and application tests. Most scanners fail their own job when configured
thresholds are exceeded. CodeQL is different: analysis can complete successfully while
publishing security alerts, so `.github/rulesets/main-branch.json` carries a separate
code-scanning rule that blocks High and Critical CodeQL security alerts.

The build scans the final pushed container image by immutable digest and generates an SBOM for
that same digest. Optional cosign signing and SBOM attestation are off by default until an
approved signing and admission-verification mechanism is confirmed. The template does not
claim SLSA provenance or signature enforcement that is not actually implemented.

These controls do not protect against every approved malicious change, a compromised
maintainer with sufficient review rights, a compromised runner, or a defect in a pinned
third-party dependency. Repository governance and platform controls remain part of the trust
boundary.

## Suppressions

Application-specific Trivy suppressions require a current record in `security/suppressions/`
with the fields and maximum lifetime documented there, plus a linked `.trivyignore` entry.
`scripts/security/validate-suppressions.py` rejects malformed, over-broad, over-90-day, expired,
or unlinked records during pull request validation. The fixed Checkov baseline is validated
separately. Other scanners do not have a generic template-level bypass wired to this registry.

Code owner rules in `.github/CODEOWNERS` ship disabled because placeholder owners can deadlock
pull requests. Configure real security owners before relying on CODEOWNERS as an approval
control. Until then, the record validator enforces record quality but cannot prove that the
approver is an authorized security owner.
