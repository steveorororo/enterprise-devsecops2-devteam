# Architecture decisions

This file records decisions that materially affect security, promotion, and developer
adoption. It is intentionally concise. Detailed procedures belong in the README or
configuration checklist.

## Settled decisions

### GitHub Actions is CI only

GitHub Actions builds, tests, scans, publishes the image, and opens the GitOps pull request.
It does not deploy directly to OpenShift. Argo CD owns deployment and reconciliation.

### Promotion uses the registry-returned digest

The digest returned by the registry after push is the identifier used for final-image
scanning, SBOM association, optional signing, and GitOps promotion. Images are built once and
the same digest is promoted through environments.

### Deployment source is owned here

`deploy/` is the reviewed and scanned source of truth for application deployment content.
Promotion renders the selected overlay into generated desired state in the GitOps repository.
The generated environment directory must not contain independently maintained Kubernetes
manifests beside the generated output.

### Overlays ship with a non-resolving placeholder digest

The seeded digest has a valid format but resolves to no image. This keeps a new repository
valid for static checks while failing closed until the first successful promotion replaces
it.

### Registry selection is configurable

`config/registry.yaml` supports GHCR, an externally reachable OpenShift internal-registry
route, or Artifactory. GHCR is the default because it does not depend on cluster routing.
The authoritative registry remains a platform confirmation.

### CodeQL is the primary SAST control

CodeQL is mandatory and publishes into GitHub security findings. Repository code-scanning
rules enforce alert severity independently of job success. SonarQube Cloud is complementary,
optional, and disabled by default.

### Checkov is the primary infrastructure-as-code scanner

Checkov scans rendered Kustomize output and the Dockerfile. kube-linter complements it for
workload checks. Trivy misconfiguration scanning is not duplicated over the same paths.

### Scanner thresholds are enforced where they are configured

`config/security-gate.yaml` defines required and legitimately skippable jobs. Vulnerability
severity thresholds remain with the scanner or repository rule that actually enforces them.
The `gate` job verifies required jobs ran and succeeded.

### Third-party workflow dependencies are pinned

Third-party GitHub Actions are pinned to commit SHA. Downloaded tools are verified using the
available upstream integrity mechanism before execution.

### Secret scanning uses gitleaks plus repository-native controls

The pull request workflow performs gitleaks scanning. GitHub secret scanning and push
protection are repository settings and must be enabled where available.

### The OpenShift baseline is intentionally small

The default workload includes the objects and security settings needed for a typical stateless
HTTP application. HPA and PDB are optional. Persistent storage, topology controls, and other
application-dependent resources are not forced into every repository.

### Network policy is deny by default

The template supplies deny-by-default policy, router ingress, and DNS egress. Additional
application connectivity must be added explicitly and remains subject to manifest scanning.

### GitOps applications use a scoped AppProject

The examples use a dedicated AppProject rather than the broad default project. Ownership of
AppProject definitions remains a platform decision.

### DAST targets trusted non-production endpoints

ZAP uses repository-configured target variables and does not accept an arbitrary dispatch URL.
The optional PostSync integration is intended for non-production validation.

### Runtime secrets are referenced, not committed

Application manifests reference secrets by name. The approved runtime secret-management
mechanism depends on the target platform and is not invented by this template.

### Issue templates are not shipped

Issue workflows are repository-specific and do not need to be inherited by every application
created from this template. An adopting team can add issue templates that match its own
support and delivery process.

### Apache License 2.0 is included

The repository ships with the Apache License 2.0 text in `LICENSE`.

## Open decisions

The following require platform or security-owner confirmation before broad production use:

- authoritative image registry, external route requirements, and retention policy
- approved image-signing mechanism, admission verification, accepted identity, and policy owner
- organization-approved vulnerability severity thresholds
- policy for unfixed container and dependency vulnerabilities
- GitOps repository ownership, naming, and branch-protection baseline
- whether AppProjects are team-owned or platform-owned
- approved runtime secret-management service and whether Vault is provisioned
- whether `seccompProfile: RuntimeDefault` is accepted by the target cluster SCC
- long-term template maintainership and the mechanism for propagating security fixes to copies

Until these are confirmed, keep the corresponding controls configurable and do not describe a
local default as an organization-wide standard.
