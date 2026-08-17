#include <Eigen/Core>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <filesystem>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <string>
#include <system_error>

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
    node.declare_parameter("run_id", std::string{});
    node.declare_parameter("registration_handoff_path", std::string{});
    node.declare_parameter("workload_profile", std::string{"hover"});
    node.declare_parameter("motion_settle_s", 1.0);
    node.declare_parameter("motion_speed_m_s", 0.75);
    node.declare_parameter("motion_distance_m", 3.5);
    node.declare_parameter("stall_request_path", std::string{});
    _active_duration_s = node.get_parameter("active_duration_s").as_double();
    _stall_after_s = node.get_parameter("stall_after_s").as_double();
    _fault_mode = node.get_parameter("fault_mode").as_string();
    _hover_altitude_m = node.get_parameter("hover_altitude_m").as_double();
    _run_id = node.get_parameter("run_id").as_string();
    _registration_handoff_path =
        node.get_parameter("registration_handoff_path").as_string();
    _workload_profile = node.get_parameter("workload_profile").as_string();
    _motion_settle_s = node.get_parameter("motion_settle_s").as_double();
    _motion_speed_m_s = node.get_parameter("motion_speed_m_s").as_double();
    _motion_distance_m = node.get_parameter("motion_distance_m").as_double();
    _stall_request_path = node.get_parameter("stall_request_path").as_string();
    setArmingCheckReplyEnabled(node.get_parameter("health_reply_enabled").as_bool());
    if (_fault_mode != "normal" && _fault_mode != "setpoint_stall" &&
        _fault_mode != "process_exit") {
      throw std::runtime_error("unsupported fault_mode");
    }
    if (_workload_profile != "hover" && _workload_profile != "straight_line") {
      throw std::runtime_error("unsupported workload_profile");
    }
    _trajectory = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
  }

  const std::string& runId() const { return _run_id; }

  const std::string& registrationHandoffPath() const
  {
    return _registration_handoff_path;
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
    const bool scheduled_stall = _stall_request_path.empty()
        ? elapsed >= _stall_after_s
        : std::filesystem::exists(_stall_request_path);
    if (_fault_mode != "setpoint_stall" || !scheduled_stall) {
      const float target_x = _workload_profile == "straight_line"
          ? static_cast<float>(std::min(_motion_distance_m,
              std::max(0.0, elapsed - _motion_settle_s) * _motion_speed_m_s))
          : 0.f;
      _trajectory->updatePosition(
          Eigen::Vector3f{target_x, 0.f, static_cast<float>(-_hover_altitude_m)});
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
  double _motion_settle_s{1.0};
  double _motion_speed_m_s{0.75};
  double _motion_distance_m{3.5};
  std::string _fault_mode{"normal"};
  std::string _workload_profile{"hover"};
  std::string _run_id;
  std::string _registration_handoff_path;
  std::string _stall_request_path;
  bool _completion_sent{false};
  std::shared_ptr<px4_ros2::TrajectorySetpointType> _trajectory;
};

using FamilyAModeNode = px4_ros2::NodeWithMode<FamilyAExternalMode>;

void writeRegistrationHandoff(const FamilyAModeNode& node)
{
  const auto& mode = node.getMode();
  if (mode.registrationHandoffPath().empty()) {
    return;
  }
  if (mode.runId().empty()) {
    throw std::runtime_error("run_id is required with registration_handoff_path");
  }
  const std::string temporary_path = mode.registrationHandoffPath() + ".tmp";
  std::ofstream stream(temporary_path, std::ios::out | std::ios::trunc);
  if (!stream) {
    throw std::runtime_error("failed to create registration handoff");
  }
  stream << "{\n"
         << "  \"component_name\": \"Family A External\",\n"
         << "  \"mode_id\": " << static_cast<unsigned int>(mode.id()) << ",\n"
         << "  \"run_id\": \"" << mode.runId() << "\",\n"
         << "  \"schema_version\": \"1.0\"\n"
         << "}\n";
  stream.close();
  if (!stream) {
    throw std::runtime_error("failed to flush registration handoff");
  }
  if (std::rename(temporary_path.c_str(), mode.registrationHandoffPath().c_str()) != 0) {
    throw std::runtime_error("failed to publish registration handoff");
  }
}

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<FamilyAModeNode>("family_a_external_mode", true);
  writeRegistrationHandoff(*node);
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
