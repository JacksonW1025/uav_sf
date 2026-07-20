#include "../include/freshness_probe_mode.hpp"

#include <px4_ros2/components/node_with_mode.hpp>

#include <rclcpp/executors/single_threaded_executor.hpp>

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithMode<uav_sf::FreshnessProbeMode>;
  auto node = std::make_shared<Node>("external_mode_freshness_probe", true);
  RCLCPP_INFO(
      node->get_logger(),
      "{\"event_type\":\"freshness_mode_registered\",\"mode_id\":%u,\"setpoint_type\":\"%s\"}",
      node->getMode().id(), node->getMode().setpointKindName());
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  executor.remove_node(node);
  node.reset();
  rclcpp::shutdown();
  return 0;
}
