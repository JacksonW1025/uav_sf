#include "../include/route_transition_mode.hpp"

#include <px4_ros2/components/node_with_mode.hpp>

#include <atomic>
#include <chrono>
#include <csignal>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <thread>

namespace {
std::atomic_bool graceful_sigterm{false};

void handleSigterm(int)
{
  graceful_sigterm.store(true);
}
}  // namespace

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithMode<uav_sf::RouteTransitionMode>;
  auto node = std::make_shared<Node>("route_transition_external_mode", true);
  std::signal(SIGTERM, handleSigterm);
  RCLCPP_INFO(node->get_logger(),
              "{\"event_type\":\"external_mode_registered\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"setpoint_type\":\"trajectory\"}",
              node->getMode().id(),
              static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  bool shutdown_requested = false;
  auto shutdown_deadline = std::chrono::steady_clock::time_point::max();
  while (rclcpp::ok()) {
    executor.spin_some();
    if (graceful_sigterm.load() && !shutdown_requested) {
      shutdown_requested = true;
      shutdown_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
      node->getMode().requestGracefulShutdown();
    }
    if (shutdown_requested
        && (node->getMode().gracefulShutdownComplete()
            || std::chrono::steady_clock::now() >= shutdown_deadline)) {
      break;
    }
    // This mode replaces internal Hold. A successful mode completion alone
    // therefore cannot select Hold while this component remains registered:
    // PX4 maps the request straight back to this replacement mode. Destroy the
    // node while the FMU is still alive so Registration publishes the explicit
    // unregister message and PX4 can restore internal Hold before P0 cleanup.
    if (node->getMode().completionReported()) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  executor.remove_node(node);
  node.reset();
  rclcpp::shutdown();
  return 0;
}
