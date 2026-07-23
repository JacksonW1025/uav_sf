variable "IMAGE_NAME" {
  default = "uav_sf/family-a-fuzzer-v0:jazzy-arm64"
}

variable "REPOSITORY_COMMIT" {
  default = "UNSET"
}

group "default" {
  targets = ["qualification"]
}

target "qualification" {
  context = "."
  dockerfile = "containers/family_a_fuzzer_v0/Dockerfile"
  tags = ["${IMAGE_NAME}"]
  platforms = ["linux/arm64"]
  pull = false
  no-cache-filter = []
  args = {
    BASE_IMAGE = "public.ecr.aws/docker/library/ros@sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd"
    BASE_INDEX_DIGEST = "sha256:31daab66eef9139933379fb67159449944f4e2dcf2e22c2d12cc715f29873e0f"
    BASE_PLATFORM_DIGEST = "sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd"
    REPOSITORY_COMMIT = "${REPOSITORY_COMMIT}"
  }
}
