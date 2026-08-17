# Configuration checklist

Full configuration and platform confirmation. The README carries the short checklist covering
only what blocks the pipeline from running; everything here is needed before the pipeline can
be relied on in production, but not before it will run.

Items requiring confirmation map to the open decisions in `docs/decisions.md`. This file
states what to do; that file states why it is still open.

## Files you edit

Seven mandatory files, and nothing under `.github/workflows/` or `scripts/`:

1. `config/pipeline.yaml`
2. `config/registry.yaml`
3. `build/Dockerfile`
4. `deploy/overlays/dev/kustomization.yaml`
5. `deploy/overlays/test/kustomization.yaml`
6. `deploy/overlays/prod/kustomization.yaml`
7. `.github/dependabot.yml`

Optional, and not part of that count. Edit each only when the capability applies:
`.github/CODEOWNERS`, `security/sast/sonar-project.properties`,
`deploy/network-policies/allow-dns-egress.yaml`, `deploy/base/deployment.yaml` when the
application does not use port 3000 and `/api/health`, and the files in `deploy/optional/`.

## Placeholder styles

Two placeholder styles appear in this repository and they are filled in differently.

`<UPPER_SNAKE>` placeholders appear only in `gitops/examples/` and are substituted by
`scripts/utility/render-gitops.py`, which refuses to write output if any value is missing.
Do not hand-edit those files; render them.

`<lower-hyphen>` placeholders appear in `config/`, the overlays under `deploy/overlays/`, and
a few README examples. There is no script for these, so edit them directly.

## Application

- **Set `application.path` and the `build:` commands** in `config/pipeline.yaml`. The build
  and dependency-scanning jobs skip until these are set.
- **Set the CodeQL languages** to match your stack. Keep `actions` in the list so the
  workflows themselves continue to be analysed. The pipeline derives build mode and runner;
  Swift uses macOS and Go/Java-Kotlin use autobuild.
- **Replace the build stage** in `build/Dockerfile` with your application's build, and pin
  the base images by digest. Preserve the security properties its header describes.
- **Uncomment the ecosystem block** matching your stack in `.github/dependabot.yml` and set
  its `directory`, or application dependencies receive no version updates.

## Registry and image

- **Select a registry** in `config/registry.yaml`, set the username paired with
  `REGISTRY_TOKEN`, and replace every placeholder. `ghcr` is
  the default and needs no cluster route. For `openshift-internal`, the host must be the
  externally reachable route: a hosted runner cannot resolve an in-cluster service address,
  and the route differs per environment.
- **Create `REGISTRY_TOKEN`** with push access to the target.
- **Confirm the authoritative registry** for your organisation. Open decision.

## GitOps

- **Create the GitOps repository** and agree its ownership and branch protection. The
  convention is one repository per team, named `tenant-gitops-<licence-plate>`; confirm both
  the owning organisation and the naming standard with the platform team.
- **Set `gitops.repository` and `gitops.path`** in `config/pipeline.yaml`. `gitops.path` is the
  dev directory and must end in `/dev`; the renderer derives sibling test and prod paths.
  Promotion fails explicitly while the target is not configured, so set it before the first
  merge to `main`.
- **Create `GITOPS_BOT_TOKEN`**, a fine-grained token scoped to the GitOps repository alone.
- **Render the Argo CD manifests** with `scripts/utility/render-gitops.py` and commit them to
  the GitOps repository. See the README for the command.
- **Decide who owns the AppProject definitions**, your team or the platform team. Open
  decision.

## GitHub configuration

- **Confirm the branch ruleset is active.** Repository initialization applies
  `.github/rulesets/main-branch.json` automatically, so there is no manual import step. The
  ruleset requires the `gate` status check and separately blocks High/Critical CodeQL security
  alerts. Confirm the severity threshold with security owners before broad adoption. If the
  ruleset is absent under Settings, Rules, Rulesets, the repository was not fully initialized;
  see `docs/repository-bootstrap.md`.
- **Enable Dependency graph, Dependabot alerts, and secret scanning with push protection**
  under Settings, Code security. The `dependency-review` job fails without the dependency
  graph, and Dependabot security updates require alerts to be on.
- **Configure real `.github/CODEOWNERS` handles** before relying on code-owner approval for
  security-sensitive paths. Rules ship commented because unresolved placeholder owners would
  deadlock pull requests; the ruleset's code-owner requirement only applies where a real rule
  matches.

## Security gates

- **Agree the blocking severities** with your security owners. Critical and High is the
  starting position, not an agreed standard. Scanner thresholds live at their scanners;
  CodeQL's High-or-higher threshold lives in `.github/rulesets/main-branch.json`.
- **Decide whether ignoring unfixed vulnerabilities is acceptable.** Both Trivy jobs run with
  `ignore-unfixed: true`. Open decision.
- **Confirm `seccompProfile: RuntimeDefault` against your cluster's SCC.** The legacy
  `restricted` SCC rejects an explicitly set seccomp profile; `restricted-v2` accepts it.

## Optional controls

- **SonarQube Cloud** is off. To enable it, set `sonar.enabled: true`, set the project key, create
  `SONAR_TOKEN`, and set the paths and project key in
  `security/sast/sonar-project.properties`.
- **Image signing** is off. Before enabling it, confirm the approved signing mechanism, the
  admission controller that verifies the signature, and who owns the verification policy. A
  signature nothing verifies is not a control. Open decision.
- **Autoscaling and disruption budgets** are in `deploy/optional/`. See that directory's
  README.
- **DAST** runs only against maintainer-configured repository variables. Set `ZAP_DEV_URL`
  before wiring the optional Argo CD PostSync hook to `dast-dev.yml`; set `ZAP_TEST_URL` for
  the weekly active scan against test. Dispatch callers cannot supply a target URL.

## Secrets management

- **Confirm your runtime secret mechanism.** Check whether Vault is provisioned for your
  namespaces; if not, use the Secret reference pattern in the README.

## Summary of required secrets and variables

| Name | Type | Required when |
|---|---|---|
| `REGISTRY_TOKEN` | Secret | Always, for image push |
| `GITOPS_BOT_TOKEN` | Secret | Always, for promotion |
| `SONAR_TOKEN` | Secret | Only when `sonar.enabled` is true |
| `ZAP_DEV_URL` | Variable | Only when optional dev DAST is wired |
| `ZAP_TEST_URL` | Variable | Only for the weekly full DAST scan |

No GitHub Environment is used. Environments gate deployment jobs, and this pipeline has none:
it builds, scans, publishes, and opens a pull request, then stops. The gate that matters sits
on the GitOps pull request, where the deployment decision is actually made.
