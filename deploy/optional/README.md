# Optional workload components

These are not part of the base. They are useful for some applications and unnecessary for
others, and a starter template that ships them to everyone makes every adopter reason about
objects they may not need.

Enable one by adding it to the `resources:` list in `deploy/base/kustomization.yaml`, or to
a single overlay if it should apply to one environment only:

```yaml
resources:
  - ../../base
  - ../../optional/hpa.yaml
```

| File | Adds | Consider it when |
|---|---|---|
| `hpa.yaml` | HorizontalPodAutoscaler, 2 to 5 replicas on 80% CPU | Load varies enough that a fixed replica count either wastes capacity or runs short |
| `poddisruptionbudget.yaml` | PodDisruptionBudget, `maxUnavailable: 1` | The service must stay available across node drains and cluster maintenance |

## Enabling the autoscaler

The autoscaler owns replica count at runtime. Remove `spec.replicas` from the Deployment when
HPA is enabled, and apply the Argo CD `ignoreDifferences` snippet shown below only to the
environments that actually use HPA.

## Enabling the disruption budget

A budget that can never be satisfied blocks node drains indefinitely. With `replicas: 2` and
`maxUnavailable: 1` there is room to evict one pod, which is the intent. Raising the replica
count is safe; lowering it to 1 means the budget prevents eviction entirely.

`unhealthyPodEvictionPolicy: AlwaysAllow` is set so a fully broken rollout cannot hold up
cluster maintenance.

## Other components

Persistent storage, topology spread constraints, pod anti-affinity, and additional
NetworkPolicies are deliberately absent. They depend on the application's architecture in
ways a template cannot guess. Add them to `deploy/base/` when the application needs them;
the same Checkov and kube-linter checks apply automatically.

## Argo CD when HPA is enabled

The default Argo CD Application examples do not ignore `Deployment.spec.replicas`, because HPA
is optional. If HPA is enabled, add this block to each environment Application that uses it
so Argo CD does not fight the autoscaler's replica changes:

```yaml
spec:
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
```

Do not add that exception to environments without HPA. In those environments Argo CD should
continue reconciling the replica count declared in the deployment source.
