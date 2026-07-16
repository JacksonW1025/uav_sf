# Active configuration

`dependencies.lock.yaml` is the source of truth for Family A dependency
revisions and environment identity. Family B-only configuration is isolated in
`family_b/config/` and is never loaded by the default profile.
