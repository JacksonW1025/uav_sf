#include <Eigen/Core>

#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <thread>

namespace {

constexpr const char* kComponentName = "C1 Concurrency Probe";
std::atomic_bool release_requested{false};

void handleRelease(int)
{
  release_requested.store(true);
}

class C1ConcurrencyMode final : public px4_ros2::ModeBase {
 public:
  explicit C1ConcurrencyMode(rclcpp::Node& node)
      : ModeBase(node, Settings{kComponentName}.preventArming(false))
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
        "{\"event_type\":\"external_mode_activated\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu}",
        kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_));
  }

  void onDeactivate() override
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"external_mode_deactivated\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu}",
        kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_),
        static_cast<unsigned long long>(sequence_));
  }

  void checkArmingAndRunConditions(px4_ros2::HealthAndArmingCheckReporter&) override
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"c1_health_reply\",\"sequence\":%llu,\"activation_id\":%llu}",
        static_cast<unsigned long long>(health_sequence_++),
        static_cast<unsigned long long>(activation_id_));
  }

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      return;
    }
    trajectory_setpoint_->update(Eigen::Vector3f::Zero(), {}, 0.f, {});
    const uint64_t sequence = sequence_++;
    if ((sequence % 20U) == 0U) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_setpoint\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu,\"setpoint_level\":\"velocity\"}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_),
          static_cast<unsigned long long>(sequence));
    }
  }

  void pollControl(const std::filesystem::path& control_dir)
  {
    const bool health_enabled = !std::filesystem::exists(control_dir / "health_reply.off");
    setArmingCheckReplyEnabled(health_enabled);
    if (health_enabled != health_enabled_) {
      health_enabled_ = health_enabled;
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"c1_health_channel_state\",\"enabled\":%s,\"activation_id\":%llu}",
          health_enabled ? "true" : "false",
          static_cast<unsigned long long>(activation_id_));
    }
    if (!completion_reported_ && std::filesystem::exists(control_dir / "completion.request")) {
      completion_reported_ = true;
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_completed\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"result\":\"success\"}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_));
      completed(px4_ros2::Result::Success);
    }
  }

  uint64_t registrationInstanceId() const { return registration_instance_id_; }

 private:
  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  uint64_t sequence_{0};
  uint64_t health_sequence_{0};
  bool completion_reported_{false};
  bool health_enabled_{true};
};

}  // namespace

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  const char* control_value = std::getenv("UAV_SF_CHANNEL_CONTROL_DIR");
  if (control_value == nullptr) {
    return 2;
  }
  const std::filesystem::path control_dir{control_value};
  using Node = px4_ros2::NodeWithMode<C1ConcurrencyMode>;
  auto node = std::make_shared<Node>("c1_concurrency_probe", true);
  std::signal(SIGTERM, handleRelease);
  std::signal(SIGINT, handleRelease);
  RCLCPP_INFO(
      node->get_logger(),
      "{\"event_type\":\"external_mode_registered\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu}",
      kComponentName, node->getMode().id(),
      static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  while (rclcpp::ok() && !release_requested.load()) {
    executor.spin_some();
    node->getMode().pollControl(control_dir);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  RCLCPP_INFO(
      node->get_logger(),
      "{\"event_type\":\"external_release_processed\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu}",
      kComponentName, node->getMode().id(),
      static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
  executor.remove_node(node);
  node.reset();
  rclcpp::shutdown();
  return 0;
}
