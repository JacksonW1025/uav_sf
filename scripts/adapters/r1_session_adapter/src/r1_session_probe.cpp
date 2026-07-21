#include <Eigen/Core>

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <string>

namespace {

std::string environmentValue(const char* name, const char* fallback)
{
  const char* value = std::getenv(name);
  return value == nullptr ? std::string(fallback) : std::string(value);
}

const std::string& sessionRole()
{
  static const std::string value = environmentValue("UAV_SF_R1_SESSION_ROLE", "unknown");
  return value;
}

const std::string& producerSessionId()
{
  static const std::string value =
      environmentValue("UAV_SF_R1_PRODUCER_SESSION_ID", "r1-session-unknown");
  return value;
}

const std::string& componentName()
{
  static const std::string value = "R1 Session " + sessionRole();
  return value;
}

std::filesystem::path controlDirectory()
{
  return environmentValue("UAV_SF_R1_CONTROL_DIR", ".");
}

void writeMarker(const char* name)
{
  const auto path = controlDirectory() / name;
  std::ofstream marker(path, std::ios::out | std::ios::trunc);
  marker << producerSessionId() << '\n';
}

class R1SessionMode final : public px4_ros2::ModeBase {
 public:
  explicit R1SessionMode(rclcpp::Node& node)
      : ModeBase(node, Settings{componentName()}.preventArming(false))
  {
    modeRequirements().local_position = true;
    trajectory_setpoint_ = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
    setSetpointUpdateRate(20.f);
  }

  void onActivate() override
  {
    ++activation_id_;
    sequence_ = 0;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"external_mode_activated\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu}",
        componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(), id(),
        static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_));
  }

  void onDeactivate() override
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"external_mode_deactivated\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu}",
        componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(), id(),
        static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_),
        static_cast<unsigned long long>(sequence_));
  }

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      return;
    }
    trajectory_setpoint_->update(Eigen::Vector3f::Zero(), {}, 0.f, {});
    const uint64_t current_sequence = sequence_++;
    if ((current_sequence % 20U) == 0U) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_setpoint\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu,\"behavior_phase\":\"hover\",\"setpoint_level\":\"velocity\"}",
          componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(), id(),
          static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_),
          static_cast<unsigned long long>(current_sequence));
    }
  }

  uint64_t registrationInstanceId() const { return registration_instance_id_; }

 private:
  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  uint64_t sequence_{0};
};

class R1SessionExecutor final : public px4_ros2::ModeExecutorBase {
 public:
  explicit R1SessionExecutor(px4_ros2::ModeBase& owned_mode)
      : ModeExecutorBase(Settings{}.activate(Settings::Activation::ActivateImmediately), owned_mode)
  {
  }

  void onActivate() override
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"executor_activated\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
        componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(), id(),
        ownedMode().id());
    if (sessionRole() != "new" || completion_wait_armed_) {
      return;
    }
    completion_wait_armed_ = true;
    scheduleMode(ownedMode().id(), [this](px4_ros2::Result result) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"executor_result\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"stage\":\"new_owned_mode_completion\",\"result\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
          componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(),
          px4_ros2::resultToString(result), id(), ownedMode().id());
      if (result == px4_ros2::Result::Success) {
        writeMarker("new_lifecycle_progressed.marker");
        writeMarker("new_successor_requested.marker");
        RCLCPP_INFO(
            node().get_logger(),
            "{\"event_type\":\"executor_successor_requested\",\"component_name\":\"%s\",\"session_role\":\"new\",\"producer_session_id\":\"%s\",\"successor\":\"RTL\",\"successor_nav_state\":5,\"executor_id\":%d}",
            componentName().c_str(), producerSessionId().c_str(), id());
        rtl([this](px4_ros2::Result successor_result) {
          RCLCPP_INFO(
              node().get_logger(),
              "{\"event_type\":\"executor_successor_result\",\"component_name\":\"%s\",\"session_role\":\"new\",\"producer_session_id\":\"%s\",\"successor\":\"RTL\",\"successor_nav_state\":5,\"result\":\"%s\",\"executor_id\":%d}",
              componentName().c_str(), producerSessionId().c_str(),
              px4_ros2::resultToString(successor_result), id());
        });
      }
    });
    writeMarker("new_completion_wait_armed.marker");
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"new_completion_wait_armed\",\"component_name\":\"%s\",\"session_role\":\"new\",\"producer_session_id\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
        componentName().c_str(), producerSessionId().c_str(), id(), ownedMode().id());
  }

  void onDeactivate(DeactivateReason reason) override
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"executor_deactivated\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"reason\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
        componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(),
        reason == DeactivateReason::FailsafeActivated ? "failsafe_activated" : "other", id(),
        ownedMode().id());
  }

 private:
  bool completion_wait_armed_{false};
};

}  // namespace

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithModeExecutor<R1SessionExecutor, R1SessionMode>;
  auto node = std::make_shared<Node>("r1_session_" + sessionRole(), true);
  RCLCPP_INFO(
      node->get_logger(),
      "{\"event_type\":\"external_mode_registered\",\"component_name\":\"%s\",\"session_role\":\"%s\",\"producer_session_id\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu}",
      componentName().c_str(), sessionRole().c_str(), producerSessionId().c_str(),
      node->getMode().id(),
      static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
