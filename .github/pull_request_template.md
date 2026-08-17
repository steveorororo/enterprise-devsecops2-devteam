## What changed

## Why

## Security-relevant?
- [ ] Touches `security/`, `config/security-gate.yaml`, or a workflow's `permissions:`/secrets
- [ ] Adds or updates a dependency
- [ ] Adds or updates a supported Trivy suppression (link the entry in `security/suppressions/`)

## Checklist
- [ ] `pr-validate` checks pass, or failures are understood and tracked
- [ ] No new hardcoded credentials, tokens, or connection strings
- [ ] Deploy manifest changes reviewed against `deploy/base` security defaults (no loosened securityContext, no removed NetworkPolicy)
