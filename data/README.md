# Data Layout

- `raw/`: repository-storable raw evidence only; large raw ULogs are externally archived and indexed.
- `processed/`: derived data; historical processed artifacts remain at stable paths and are mapped by the experiment index.
- `manifests/`: raw/external provenance manifests, including historical ignored artifacts and nested build-cache backup files.

Raw artifacts are never overwritten in place.
