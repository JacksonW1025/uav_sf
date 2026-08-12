#include <Eigen/Core>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <string>

using namespace std::chrono_literals;

class FamilyAExternalMode : public px4_ros2::ModeBase {
 public:
  explicit FamilyAExternalMode(rclcpp::Node& node)
      : ModeBase(node, Settings{"Family A External"})
  {
    node.declare_parameter("active_duration_s", 8.0);
    node.declare_parameter("stall_after_s", 3.0);
    node.declare_parameter("fault_mode", std::string{"normal"});
    node.declare_parameter("health_reply_enabled", true);
    node.declare_parameter("hover_altitude_m", 3.0);
    _active_duration_s = node.get_parameter("active_duration_s").as_double();
    _stall_after_s = node.get_parameter("stall_after_s").as_double();
    _fault_mode = node.get_parameter("fault_mode").as_string();
    _hover_altitude_m = node.get_parameter("hover_altitude_m").as_double();
    setArmingCheckReplyEnabled(node.get_parameter("health_reply_enabled").as_bool());
    if (_fault_mode != "normal" && _fault_mode != "setpoint_stall" &&
        _fault_mode != "process_exit") {
      throw std::runtime_error("unsupported fault_mode");
    }
    _trajectory = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
  }

  void onActivate() override
  {
    _activation_time = node().get_clock()->now();
    RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT external_mode_activated");
  }

  void onDeactivate() override
  {
    RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT external_mode_deactivated");
  }

  void updateSetpoint(float) override
  {
    if (_completion_sent) {
      return;
    }
    const double elapsed = (node().get_clock()->now() - _activation_time).seconds();
    if (_fault_mode == "process_exit" && elapsed >= _stall_after_s) {
      RCLCPP_ERROR(node().get_logger(), "FAMILY_A_EVENT external_mode_process_exit");
      std::_Exit(74);
    }
    if (_fault_mode != "setpoint_stall" || elapsed < _stall_after_s) {
      _trajectory->updatePosition(
          Eigen::Vector3f{0.f, 0.f, static_cast<float>(-_hover_altitude_m)});
    }
    if (elapsed >= _active_duration_s) {
      RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT external_mode_completed");
      _completion_sent = true;
      completed(px4_ros2::Result::Success);
    }
  }

 private:
  rclcpp::Time _activation_time{};
  double _active_duration_s{8.0};
  double _stall_after_s{3.0};
  double _hover_altitude_m{3.0};
  std::string _fault_mode{"normal"};
  bool _completion_sent{false};
  std::shared_ptr<px4_ros2::TrajectorySetpointType> _trajectory;
};

using FamilyAModeNode = px4_ros2::NodeWithMode<FamilyAExternalMode>;

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FamilyAModeNode>("family_a_external_mode", true));
  rclcpp::shutdown();
  return 0;
}
