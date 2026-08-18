# Locked V8 repository-validation image

This ARM64 image runs the repository boundary validator in a digest-pinned
Noble/Jazzy environment. It is not a PX4 flight runtime, a source-preparation
image, or a formal experiment environment.

Build it from the repository root:

```bash
docker buildx build --platform linux/arm64 \
  --file containers/family_a/Dockerfile \
  --tag uav-sf-v8-validation:local .
```

The default entry point runs `./scripts/validation/validate_repo.sh`. A passing
image build establishes repository consistency only.
