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

## Tag-prefix convention (post-monorepo split, sdk-v0.1.0+)

With the plugin platform split (Phase 2 of TASK-010), per-package release notes
use a prefix matching their CI workflow trigger:

- `sdk-v*` — `looker-extractor-sdk` releases (workflow: `release-sdk.yaml`)
- `core-v*` — `looker-extractor` core releases (workflow: `release-core.yaml`)
- `v*` — historical single-package releases (workflow: `release.yaml.disabled`, kept for audit)

File naming mirrors the tag: `releases/<tag>.md` (e.g. `releases/sdk-v0.1.0.md`).

## Index

| Version | Date | Theme |
|---|---|---|
| [v0.1.0](./v0.1.0.md) | 2026-05-22 | Initial release |
| [v0.1.1](./v0.1.1.md) | 2026-05-22 | PyPI rename to `looker-fields` + `lf` short alias |
| [v0.2.0](./v0.2.0.md) | 2026-05-22 | Manifest-native architecture: edit YAML, not Python |
| [v0.2.1](./v0.2.1.md) | 2026-05-22 | Definition Identity: surface the drift `seen_in_*` hid (`definition_hash` + cross-alias aggregation + F1 assertion + dynamic exclusion) |
| [sdk-v0.1.0](./sdk-v0.1.0.md) | 2026-05-23 | `looker-extractor-sdk` extracts from core as standalone PyPI package (Plugin ABC + `stamp_lineage` + entry-points group + `AUTHORING.md`); ships alongside `looker-extractor-plugin-roles` as worked example |
