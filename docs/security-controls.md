# Security controls

Each control, the tool that implements it, where it runs, and what it blocks. A control
absent from this table is not implemented by this template.

## In the pipeline

| Control | Tool | Where | Mandatory | Blocking |
|---|---|---|---|---|
| Source control and review | Branch ruleset, CODEOWNERS | `.github/rulesets/`, `.github/CODEOWNERS` | Ruleset yes; owner mapping requires configuration | Merge |
| Secret scanning | gitleaks CLI | `pr-validate.yml` (`secrets-scan`) | Yes | Pull request |
| Secret prevention | GitHub push protection | Repository setting | Yes | Push |
| Static analysis | CodeQL, including the `actions` language | `pr-validate.yml` (`codeql`), `security/sast/codeql-config.yml`, branch `code_scanning` rule | Yes | High/Critical security alerts and analysis errors block merge through ruleset |
| Static analysis, secondary | SonarQube Cloud | `build-scan-publish.yml` (`sonar`), reviewed `main` only | No, off by default | Blocks GitOps promotion when enabled |
| Dependency scanning | Trivy filesystem | `pr-validate.yml` (`sca-trivy-fs`), `security/sca/.trivyignore` | Yes | Pull request |
| Dependency introduction | dependency-review-action | `pr-validate.yml` (`dependency-review`) | Yes | Pull request |
| Dependency updates | Dependabot | `.github/dependabot.yml` | Yes | Raises pull requests |
| Infrastructure as code | Checkov, on rendered output | `pr-validate.yml` (`iac-checkov`), `security/iac/.checkov.yaml` | Yes | Pull request |
| Manifest validation | kube-linter | `pr-validate.yml` (`manifest-lint`), `security/iac/.kube-linter.yaml` | Yes | Pull request, at error level |
| Gate aggregation | `evaluate-gate.py` | `scripts/security/evaluate-gate.py`, `config/security-gate.yaml` | Yes | Pull request, single required check |
| Container build | Buildah | `build/Dockerfile`, `build-scan-publish.yml` | Yes | Build failure |
| Image scanning | Trivy image, by digest after push | `build-scan-publish.yml` | Yes | Before promotion |
| SBOM | Syft | `build-scan-publish.yml` | Yes | Build failure |
| Image signing and attestation | cosign keyless | `build-scan-publish.yml` | No, off by default | Dedicated signing job blocks promotion when enabled and unsuccessful |
| Registry | Configurable | `config/registry.yaml`, `scripts/utility/resolve-registry.py` | Yes | Placeholder validation fails the build |
| Immutable promotion | Digest-bound rendered desired state | `deploy/overlays/`, `scripts/utility/render-deployment.py`, `scripts/utility/bump-gitops-digest.py` | Yes | Promotion fails if the digest or scanned workload content is absent from rendered output |
| Network segmentation | NetworkPolicies, deny by default | `deploy/network-policies/` | Yes | Admission time |
| Container hardening | securityContext | `deploy/base/deployment.yaml` | Yes | Checkov and kube-linter flag regressions |
| Runtime secrets | `secretKeyRef`, or Vault where provisioned | `deploy/base/deployment.yaml` | Yes | Not applicable |
| DAST | OWASP ZAP baseline/full | `dast-dev.yml`, `scheduled-scans.yml`, `security/dast/zap-baseline.conf` | No | Targets trusted `ZAP_DEV_URL`/`ZAP_TEST_URL`; baseline can fail dev scan |
| Trivy exceptions | Validated suppression records linked to `.trivyignore` | `security/suppressions/`, `scripts/security/validate-suppressions.py` | Yes | Record schema, expiry, and linkage block PR; security-owner approval requires configured governance |

## Provided by the platform

These apply to any workload in the namespace and require nothing from this pipeline. They
are listed so a reader can tell the difference between a control this template implements
and one it inherits.

| Control | Provided by |
|---|---|
| Runtime threat detection | Red Hat ACS |
| Runtime monitoring and alerting | Sysdig |
| Centralised logging | Loki |
| Cluster vulnerability management | Platform services |
| Continuous delivery and reconciliation | Argo CD |
| Registry administration | Platform services |

Confirm with the platform team which of these are provisioned for your namespaces. The
template creates no credentials and no jobs for any of them.

## Where findings appear

| Tool | Location |
|---|---|
| CodeQL, Trivy, Checkov | Security tab, Code scanning alerts. Five SARIF categories: `codeql-<language>` (one per configured language), `trivy-fs`, `trivy-image`, `trivy-scheduled`, `checkov` |
| gitleaks | Job log, redacted |
| kube-linter | Job log |
| dependency-review | Pull request comment on failure |
| Dependabot | Security tab, Dependabot alerts, and pull requests |
| SonarQube Cloud | SonarQube Cloud project, when enabled |
| ZAP | Issue raised in this repository |
| SBOM | Build artifact on the run, retained 90 days |

## How the gate decides

Most scanners fail their own job when they exceed their threshold. The `gate` job turns those
job results into the single required status check. CodeQL is handled differently: analysis can
succeed while publishing alerts, so the branch ruleset's `code_scanning` rule enforces CodeQL
alert severity separately.

A configured CodeQL language is analysed once the repository contains source for it. Until
then that language reports no analysis, so a repository does not fail its first pull request
for having no application code yet. The first commit adding matching source makes analysis run
again with no configuration change, and a failure from that point blocks the pull request.
Workflow files are always present, so the `actions` language is always analysed.

The `code_scanning` rule in `.github/rulesets/main-branch.json` names CodeQL only; it does not
cover Trivy or Checkov, even though both also upload SARIF to the Security tab. Trivy and
Checkov are enforced through in-job failure instead: Trivy's `exit-code: "1"` at
CRITICAL/HIGH severity and Checkov's `soft_fail: false` in `pr-validate.yml`, both of which
also make the `gate` job fail through `required_jobs`. Adding a scanning tool that only
publishes SARIF, without also failing its own job or being added to the ruleset, would not be
merge-blocking.

Only `success` passes. A `skipped` job passes only if it is listed under `skippable_jobs` in
`config/security-gate.yaml`, because the straightforward way to defeat a required check is to
stop its jobs running. A job listed under `required_jobs` but absent from the payload also
fails, so deleting a job from the workflow breaks the build rather than quietly removing a
control. This behavior is covered by the template's internal regression suite, maintained
outside this repository.

Findings fall into four tiers:

- Informational: reported without blocking.
- Warning: reported without blocking unless a repository rule says otherwise.
- Pull request blocking: scanner job failure, dependency-review failure, or a CodeQL
  code-scanning ruleset violation.
- Publication blocking: final-image or build failure before GitOps promotion.

Severity thresholds are set at each scanner, not in `config/security-gate.yaml`. That file
names where each one lives.
