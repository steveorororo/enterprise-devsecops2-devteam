# Enterprise DevSecOps Pipeline Template

A reusable GitHub Actions pipeline for applications deployed to OpenShift through GitOps and
Argo CD. The template provides security checks, immutable image promotion, software bill of
materials generation, and OpenShift deployment manifests without requiring application teams
to design the pipeline architecture themselves.

GitHub Actions performs CI only. It builds, tests, scans, publishes the approved image, and
opens a pull request against the GitOps repository. Argo CD performs deployment and
reconciliation. This repository does not run `oc apply`, `helm upgrade`, or `argocd app sync`.

Pull request security controls are executed by the central AppSec platform rather than
implemented here. This repository pins the platform release it consumes in
`config/platform.yaml`, and the pull request workflow calls that release at an immutable
commit. Scanner versions, verification and policy are maintained centrally, so adopting a
security fix is a reviewed pointer update rather than a re-implementation.

## Start here

### Prerequisites

- A GitHub repository created from this template.
- OpenShift namespaces for development, test, and production.
- Argo CD access for the target namespaces.
- A separate GitOps repository.
- Registry and GitOps credentials stored as GitHub secrets.

### Onboarding sequence

```text
1. Create repository from template
2. Repository bootstrap runs
3. main ruleset applied automatically
4. Configure the required application files
5. Create feature branch
6. Open pull request
7. Security validation and gate
8. Approval
9. Merge to main
10. Build, scan, publish, GitOps promotion
```

Steps 2 and 3 are repository initialization and are covered under Repository protection,
below. Steps 6 to 10 are the standing delivery path, detailed under Pipeline flow.

### Files you must configure

**Seven mandatory files.** Application teams should not edit `.github/workflows/` or
`scripts/` for normal adoption. Editing `config/pipeline.yaml`, `config/registry.yaml`,
`build/Dockerfile`, the three `deploy/overlays/*/kustomization.yaml` files, and
`.github/dependabot.yml` covers all seven.

Optional files, edited only when the matching capability applies, include
`.github/CODEOWNERS`, `security/sast/sonar-project.properties`,
`deploy/network-policies/allow-dns-egress.yaml`, `deploy/optional/*.yaml`, and
`deploy/base/deployment.yaml` (only if the application does not use port 3000 and
`/api/health`).

For the complete setup checklist, see `docs/configuration-checklist.md`.

### First pull request

1. Set `application.path` and the application build commands in `config/pipeline.yaml`.
2. Set the CodeQL languages for the application. Keep `actions` enabled.
3. Replace the build stage in `build/Dockerfile` and pin base images by digest.
4. Configure the target registry in `config/registry.yaml`.
5. Set the namespace and image values in all three overlays.
6. Enable the correct dependency ecosystem in `.github/dependabot.yml`.
7. Enable the GitHub security features listed below.
8. Set `gitops.repository` and `gitops.path` before the first merge to `main`.

Unresolved placeholders fail or skip with an explicit message rather than silently deploying
an incomplete configuration.

## Pipeline flow

```text
Pull request
  -> application build and tests
  -> gitleaks
  -> CodeQL
  -> dependency review
  -> Trivy dependency scan
  -> Checkov
  -> kube-linter
  -> gate

Merge to main
  -> build image once
  -> push image
  -> scan image by registry digest
  -> generate SBOM
  -> optional Sonar analysis
  -> optional image signing
  -> open GitOps pull request
  -> Argo CD deploys approved desired state
```

The registry-returned image digest is the identifier used for final-image scanning, SBOM
association, optional signing, and GitOps promotion. The same image is promoted through
development, test, and production. It is not rebuilt per environment.

## Platform releases

`config/platform.yaml` records the platform release this repository executes:

```text
platform_version   human readable release
platform_ref       the commit the workflows actually run
```

Both move together in one reviewed change, so this repository cannot execute one release
while reporting another. A repository keeps running its pinned commit until it adopts an
update, so a central fix reaches this repository when its update pull request is merged.

Do not edit these values by hand or point a workflow at a branch. The platform rejects a
consumer whose recorded release and pinned commits disagree.

## Repository protection

The standard `main` branch protection baseline ships in `.github/rulesets/main-branch.json`.
Repository initialization applies this ruleset automatically, so development teams do not
normally configure branch protection by hand.

The ruleset requires pull requests and the `gate` security check before changes reach `main`,
requires code owner review, and prevents force pushes and branch deletion. The included
High-or-higher CodeQL threshold is a starting position and must be confirmed with the owning
security team before broad use.

If initialization cannot apply the ruleset because the provisioning identity lacks the
required GitHub permissions, the bootstrap reports the failure and exits non-zero. The
repository must not be treated as fully initialized until the ruleset is active. Provisioning
detail is in `docs/repository-bootstrap.md`.

## GitHub configuration

Enable these repository security capabilities where licensed and available:

- Dependency graph
- Dependabot alerts and security updates
- Secret scanning
- Push protection

Configure real `.github/CODEOWNERS` entries before relying on code-owner approval. Example
rules are disabled so placeholder owners cannot block every pull request.

Required secrets and variables:

| Name | Type | Required when |
|---|---|---|
| `REGISTRY_TOKEN` | Secret | Image publication |
| `GITOPS_BOT_TOKEN` | Secret | GitOps promotion |
| `SONAR_TOKEN` | Secret | `sonar.enabled: true` |
| `ZAP_DEV_URL` | Variable | Optional development DAST |
| `ZAP_TEST_URL` | Variable | Optional scheduled test DAST |

The pipeline has no GitHub deployment job and therefore does not depend on GitHub
Environments for cluster deployment approval. Deployment approval belongs to the GitOps and
Argo CD path.

## Pull request security checks

The pull request workflow runs application tests and the following security controls:

- gitleaks for committed secrets
- CodeQL for static analysis
- dependency review for dependency changes
- Trivy for dependency vulnerabilities
- Checkov against rendered deployment manifests and the Dockerfile
- kube-linter against rendered deployment manifests

The `gate` job verifies that required jobs actually ran and succeeded. A required job that is
missing, cancelled, or unexpectedly skipped does not count as a pass. CodeQL findings are
merge-blocking through the repository code-scanning rule because a successful CodeQL job can
still publish alerts.

Scanner locations, result handling, and enforcement are documented in
`docs/security-controls.md`.

## Build, publish, and promotion

After merge, Buildah builds and pushes the image. Trivy then scans the final registry artifact
by digest, and Syft generates the SBOM. Optional controls run only when enabled.

Promotion renders the selected source overlay from `deploy/overlays/`, binds the approved
image digest, and replaces the configured environment directory in the GitOps repository
with generated desired state. Do not hand-edit the generated `manifests.yaml` in that
directory. Make deployment changes in this repository and promote them again.

The GitOps pull request is the deployment change request. Argo CD reconciles the approved
state. Production remains manual because the production Application example does not enable
automated sync.

## GitOps setup

Use sibling environment directories such as:

```text
apps/dev
apps/test
apps/prod
```

Set `gitops.repository` and set `gitops.path` to the development directory. The path must end
in `/dev`; test and production paths are derived from the same parent.

`gitops/examples/` contains parameterized Argo CD Application, AppProject, and optional
PostSync DAST manifests. Render them with:

```text
python3 scripts/utility/render-gitops.py --list-tokens
python3 scripts/utility/render-gitops.py --output ../gitops/argocd \
  --set APP_NAME=my-app \
  --set APP_PROJECT_NAME=my-app \
  --set GITOPS_REPO_URL=https://github.com/my-org/my-app-gitops.git \
  --set NAMESPACE_PREFIX=abc123 \
  --set GITHUB_REPO=my-org/my-app \
  --set SYNCED_REVISION=placeholder
```

The renderer validates supplied names, repository identifiers, clone URLs, revisions, and
rendered YAML before writing files.

## OpenShift workload baseline

The base workload includes:

- Deployment, Service, Route, ConfigMap, and ServiceAccount
- resource requests and limits
- startup, readiness, and liveness probes
- non-root container security settings
- dropped Linux capabilities
- deny-by-default NetworkPolicies with explicit router ingress and DNS egress

The default application contract is port 3000 with `/api/health` probes. Adjust
`deploy/base/deployment.yaml` when the application uses another contract.

HPA and PDB examples are optional under `deploy/optional/`. Persistent storage, additional
network access, topology controls, and other application-dependent objects are intentionally
not forced into the baseline.

Runtime secrets are referenced, not committed. Use the approved platform secret-management
mechanism for the target environment. If Vault or another managed service is expected,
confirm that it is provisioned before depending on it.

## Optional controls

| Feature | Default | Enable by |
|---|---|---|
| SonarQube Cloud | Off | Set `sonar.enabled: true` and configure `SONAR_TOKEN` |
| Image signing | Off | Set `signing.enabled: true` after verification policy is confirmed |
| HPA and PDB | Off | Add the required files from `deploy/optional/` |
| Development ZAP baseline | Not wired | Configure `ZAP_DEV_URL` and the PostSync integration |
| Scheduled full ZAP scan | Off | Configure `ZAP_TEST_URL` |

ACS, Sysdig, Loki, Argo CD, and other cluster services are platform capabilities. This
template does not create credentials or duplicate those runtime controls.

## Security exceptions

Trivy suppressions use the governed records under `security/suppressions/`. Records require
an owner, approver, reason, issue reference, narrow scope, review date, and expiry. Validation
fails when the record structure or linkage is invalid.

Do not add broad workflow-level scanner exclusions to get a green build. Use the approved
security exception process for controls that do not have a template-managed suppression
mechanism.

## Validation

`scripts/validation/validate-manifests.sh` renders every overlay and lints the result before
you open a pull request. It fetches the check configuration from the pinned platform release,
so local results match CI.

The broader regression suite used to validate changes to the template itself (not to an
application built from it) is maintained separately from this repository and is not part of
what an adopting team receives.

## Troubleshooting

**Build or dependency jobs are skipped**  
Set `application.path` and the `build:` commands in `config/pipeline.yaml`.

**The security gate fails**  
Open the failing required job. Unexpectedly skipped or cancelled required jobs fail the gate.

**Registry publication fails**  
Verify `config/registry.yaml` and confirm `REGISTRY_TOKEN` has the required registry access.

**GitOps promotion does not start**  
Confirm `gitops.repository`, `gitops.path`, and the repository-scoped `GITOPS_BOT_TOKEN`.

**A pod cannot pull the seeded image digest**  
The initial placeholder digest intentionally resolves to nothing. The first successful
promotion replaces it.

**Which image digest is actually deployed**  
Check the rendered `manifests.yaml` under the environment directory in the GitOps repository
(the `render-deployment.py` output committed by promotion), or open the Argo CD Application
for that environment and read the image reference in its live/rendered manifest. Both reflect
the digest that was actually promoted, not the tag in `deploy/overlays/`.

**Where application logs are**  
This template does not collect or ship logs; centralised logging is a platform capability
provided by Loki (see `docs/security-controls.md`). Use your platform's Loki access to view
application logs for the target namespace.

**A deployment is rejected because of the seccomp profile**  
Confirm the Security Context Constraint used by the target namespace and whether it accepts
`seccompProfile: RuntimeDefault`.

**DAST does not run**  
DAST is optional. Confirm the approved target variable is configured and that the GitOps
PostSync integration is enabled where required.

**Where scan findings appear**  
CodeQL, Trivy, and Checkov findings are SARIF-based and surface in the repository's Security
tab under Code scanning alerts (five categories: `codeql-<language>`, `trivy-fs`,
`trivy-image`, `trivy-scheduled`, `checkov`). gitleaks and kube-linter findings appear in the
failing job's log instead; see `docs/security-controls.md` for the full list.

## Platform confirmations

Before broad production adoption, confirm the items that belong to the target platform or
security policy rather than guessing them in this template:

- authoritative registry and retention requirements
- image-signing and admission-verification mechanism
- blocking vulnerability severities and unfixed-vulnerability policy
- GitOps repository ownership, naming, and branch protection
- AppProject ownership
- runtime secret-management service
- target-cluster SCC compatibility

`docs/decisions.md` records the architectural decisions and remaining open items.

## Support

Use the issue process in the application repository created from this template. For OpenShift,
Argo CD, Vault, ACS, Sysdig, registry, or namespace provisioning, contact the team that owns
the target platform service.
