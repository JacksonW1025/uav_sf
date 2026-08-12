# Locked Family A validation and reference image

The image is fixed to the ARM64 platform digest recorded in
`config/dependencies.lock.json`. Every package installed by the Dockerfile has
an exact distribution version. The image contains repository validation,
evaluation, and reference-build tools; locked upstream source trees are
prepared with `scripts/setup/prepare_sources.sh`.

This image does not identify the formal experiment environment and a build on
the repository maintenance host produces no runtime evidence. Each formal run
must register its actual target environment in the experiment plan and attest
that identity in the collected trace.

Build from the repository root with the command in `README.md`. Do not replace
the digest or package versions with tags, ranges, or unversioned package names.
