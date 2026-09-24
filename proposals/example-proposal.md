# Example: Migrate Build Pipeline to Containers

This is a sample proposal so you can see how Proposal Presenter renders markdown. Delete it once you add your own files.

## Summary

We propose moving the build pipeline from long-lived build agents to ephemeral containers, so every build starts from a clean, reproducible environment.

## Motivation

- Build agents drift over time and produce "works on agent 3" failures.
- Onboarding a new toolchain version means touching every agent by hand.
- Ephemeral containers make builds reproducible and easier to scale.

## Proposal

| Phase | Scope | Owner | Target |
|-------|-------|-------|--------|
| 1 | Containerize backend builds | Platform team | Q4 |
| 2 | Containerize frontend builds | Web team | Q1 |
| 3 | Decommission old agents | Platform team | Q2 |

Example build step:

```yaml
build:
  image: python:3.12-slim
  script:
    - pip install -r requirements.txt
    - pytest
```

> **Note:** Existing pipelines keep working during the migration; each project opts in.

## Open questions

1. Where do we cache dependencies between builds?
2. Who owns the base images?

---

*Select any sentence above and click **Comment** to try inline comments.*
