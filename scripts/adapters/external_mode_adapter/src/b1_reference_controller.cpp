#include "../include/b1_reference_controller.hpp"

#include <exception>
#include <memory>
#include <px4_ros2/components/node_with_mode.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  try {
    using Node = px4_ros2::NodeWithMode<uav_sf::B1ReferenceController>;
    auto node = std::make_shared<Node>("b1_reference_controller", true);
    RCLCPP_INFO(
        node->get_logger(),
        "{\"event_type\":\"b1_reference_registered\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"setpoint_type\":\"ATTITUDE\"}",
        uav_sf::B1ReferenceController::kComponentName, node->getMode().id(),
        static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(node);
    executor.spin();
    executor.remove_node(node);
    node.reset();
    rclcpp::shutdown();
    return 0;
  } catch (const std::exception& error) {
    if (rclcpp::ok()) rclcpp::shutdown();
    return error.what() == nullptr ? 1 : 2;
  }
}
