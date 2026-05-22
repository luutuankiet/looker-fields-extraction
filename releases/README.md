# Release Notes Index

Append-only narrative release notes.

## Authoring

- **One file per release.** Name: `vX.Y.Z.md`. No overwrites.
- **Audience:** human first, then agents picking up context six months later.
- **Structure:** TL;DR → Why → Highlights table → Mermaid diagram → Before/After → Config → Upgrade notes → Files changed.
- **Voice:** pitch, not changelog. If a line could be a commit subject, cut it.
- **Diagrams:** Mermaid only — GitHub renders it natively in release bodies.

## Publishing

The `release.yaml` workflow reads `releases/${{ github.ref_name }}.md` via
`gh release create --notes-file` when a tag is pushed. Missing file → workflow fails loudly.

## Index

| Version | Date | Theme |
|---|---|---|
| [v0.1.0](./v0.1.0.md) | 2026-05-22 | Initial release |
| [v0.1.1](./v0.1.1.md) | 2026-05-22 | PyPI rename to `looker-fields` + `lf` short alias |
| [v0.2.0](./v0.2.0.md) | 2026-05-22 | Manifest-native architecture: edit YAML, not Python |
| [v0.2.1](./v0.2.1.md) | 2026-05-22 | Definition Identity: surface the drift `seen_in_*` hid (`definition_hash` + cross-alias aggregation + F1 assertion + dynamic exclusion) |
