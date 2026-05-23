# looker-extractor-plugin-roles

First third-party `looker-extractor` plugin — extracts one row per Looker role,
with nested `permission_set` + `model_set` structs preserved as passthru.

Proof-of-concept for the plugin platform (reference implementation for
`AUTHORING.md` in `looker-extractor-sdk`).

## Install

```bash
pip install looker-extractor looker-extractor-plugin-roles
```

## Run

```bash
looker-extractor extract --plugin roles -o roles.jsonl
```

Optional filters via repeated `--filter key=value` (not currently surfaced on the
CLI but supported by the Plugin contract — see filters convention in AUTHORING.md):

```python
plugin.extract(client, filters={"ids": "1,2,3"})
```

## Row shape

One row per Role. Schema mirrors Looker `/api/4.0/roles` response:

```jsonc
{
  "id": "1",                       // str (API 4.0 returns role ids as strings)
  "name": "Admin",
  "permission_set": {              // nested struct (full object on read)
    "id": "1",
    "name": "Admin",
    "permissions": ["administer", "..."],
    "all_access": true,
    "built_in": true,
    "url": "..."
  },
  "model_set": {                   // nested struct
    "id": "1",
    "name": "All",
    "models": ["thelook", "..."],
    "all_access": true,
    "built_in": true,
    "url": "..."
  },
  "internal": false,
  "url": "https://.../api/4.0/roles/1",
  "users_url": "https://.../api/4.0/roles/1/users",
  "_extract_role_id": "1",
  "_extract_role_name": "Admin"
}
```

Downstream warehouse can flatten or preserve struct.

## Source endpoint

`GET /api/4.0/roles` — single call, no pagination.

## Swagger schema regeneration

This plugin owns its swagger types (independent of core's lookml_fields swagger).
Regenerate via the shared script in core:

```bash
cd packages/looker-extractor
.venv/bin/python scripts/regen_schema.py --plugin roles
```

Writes to `packages/looker-extractor-plugin-roles/src/looker_extractor_plugin_roles/swagger/`.

License: Apache-2.0.
