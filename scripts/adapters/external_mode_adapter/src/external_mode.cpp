#include "../include/route_transition_mode.hpp"

#include <px4_ros2/components/node_with_mode.hpp>

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithMode<uav_sf::RouteTransitionMode>;
  auto node = std::make_shared<Node>("route_transition_external_mode", true);
  RCLCPP_INFO(node->get_logger(),
              "{\"event_type\":\"external_mode_registered\",\"mode_id\":%u,\"setpoint_type\":\"trajectory\"}",
              node->getMode().id());
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
