#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <fcntl.h>
#include <functional>
#include <gz/msgs/clock.pb.h>
#include <gz/transport/Node.hh>
#include <thread>
#include <unistd.h>

namespace {
std::atomic_bool running{true};

void stop(int)
{
  running.store(false);
}

long long monotonic_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}
}  // namespace

int main(int argc, char* argv[])
{
  if (argc != 2) {
    std::fprintf(stderr, "usage: gazebo_clock_sidecar OUTPUT_JSONL\n");
    return 64;
  }
  const int fd =
      ::open(argv[1], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_APPEND, 0644);
  if (fd < 0) {
    std::perror("open clock sidecar");
    return 73;
  }
  std::signal(SIGINT, stop);
  std::signal(SIGTERM, stop);
  std::atomic<unsigned long long> sequence{0};
  gz::transport::Node node;
  std::function<void(const gz::msgs::Clock&)> callback =
      [fd, &sequence](const gz::msgs::Clock& message) {
        const long long source_ns =
            static_cast<long long>(message.sim().sec()) * 1000000000LL +
            static_cast<long long>(message.sim().nsec());
        const long long received_ns = monotonic_ns();
        const auto current = sequence.fetch_add(1);
        char record[512];
        const int length = std::snprintf(
            record, sizeof(record),
            "{\"analysis_projection_ns\":%lld,\"kind\":\"gazebo_clock_sample\","
            "\"received_monotonic_ns\":%lld,\"schema_version\":\"1.0\","
            "\"sequence\":%llu,\"source_domain\":\"px4_boot_ns\","
            "\"source_ns\":%lld}\n",
            received_ns, received_ns, current, source_ns);
        if (length > 0 && static_cast<std::size_t>(length) < sizeof(record)) {
          const auto ignored = ::write(fd, record, static_cast<std::size_t>(length));
          (void)ignored;
        }
      };
  const bool subscribed = node.Subscribe<gz::msgs::Clock>("/clock", callback);
  if (!subscribed) {
    std::fprintf(stderr, "failed to subscribe to Gazebo /clock\n");
    ::close(fd);
    return 69;
  }
  while (running.load()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  ::fsync(fd);
  ::close(fd);
  return 0;
}
