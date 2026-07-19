#include <Eigen/Core>

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>

namespace uav_sf {

namespace {
constexpr const char* kComponentName = "Successor Baseline";
}

class SuccessorBaselineMode final : public px4_ros2::ModeBase {
 public:
  explicit SuccessorBaselineMode(rclcpp::Node& node)
      : ModeBase(node, Settings{kComponentName}.preventArming(false))
  {
    // This control is deliberately not an internal-mode replacement. It proves
    // the legal executor-owned completion -> Land lifecycle independently of
    // the Issue #162 trigger combination.
    modeRequirements().local_position = true;
    trajectory_setpoint_ = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
    setSetpointUpdateRate(20.f);
  }

  void onActivate() override
  {
    activation_time_ = node().get_clock()->now();
    ++activation_id_;
    sequence_ = 0;
    completion_reported_ = false;
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

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      reportFailure("invalid_update_dt");
      return;
    }
    if (completion_reported_) return;

    const double elapsed_s = (node().get_clock()->now() - activation_time_).seconds();
    const char* duration_value = std::getenv("UAV_SF_SUCCESSOR_ACTIVE_DURATION_S");
    const double completion_s = duration_value == nullptr ? 5.0 : std::strtod(duration_value, nullptr);
    if (!std::isfinite(completion_s) || completion_s <= 0.0) {
      reportFailure("invalid_completion_duration");
      return;
    }
    if (elapsed_s >= completion_s) {
      completion_reported_ = true;
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_completed\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"result\":\"success\"}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_));
      completed(px4_ros2::Result::Success);
      return;
    }

    trajectory_setpoint_->update(Eigen::Vector3f::Zero(), {}, 0.f, {});
    const uint64_t current_sequence = sequence_++;
    if ((current_sequence % 20U) == 0U) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_setpoint\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"behavior_phase\":\"hover\",\"setpoint_level\":\"velocity\",\"sequence\":%llu}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_),
          static_cast<unsigned long long>(current_sequence));
    }
  }

  uint64_t registrationInstanceId() const { return registration_instance_id_; }

 private:
  void reportFailure(const char* reason)
  {
    if (completion_reported_) return;
    completion_reported_ = true;
    RCLCPP_ERROR(
        node().get_logger(),
        "{\"event_type\":\"external_mode_failure\",\"component_name\":\"%s\",\"mode_id\":%u,\"reason\":\"%s\"}",
        kComponentName, id(), reason);
    completed(px4_ros2::Result::ModeFailureOther);
  }

  rclcpp::Time activation_time_{};
  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  uint64_t sequence_{0};
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  bool completion_reported_{false};
};

class SuccessorBaselineExecutor final : public px4_ros2::ModeExecutorBase {
 public:
  explicit SuccessorBaselineExecutor(px4_ros2::ModeBase& owned_mode)
      : ModeExecutorBase(Settings{}.activate(Settings::Activation::ActivateImmediately), owned_mode)
  {
  }

  void onActivate() override
  {
    if (started_) {
      log("executor_reactivated", "ignored_after_baseline_start");
      return;
    }
    started_ = true;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"executor_activated\",\"component_name\":\"%s\",\"stage\":\"wait_ready_to_arm\",\"executor_id\":%d,\"owned_mode\":%u}",
        kComponentName, id(), ownedMode().id());
    waitReadyToArm([this](px4_ros2::Result result) {
      if (!requireSuccess("ready_to_arm", result)) return;
      log("executor_transition", "arm");
      arm([this](px4_ros2::Result arm_result) {
        if (!requireSuccess("arm_complete", arm_result)) return;
        log("executor_transition", "takeoff");
        takeoff([this](px4_ros2::Result takeoff_result) { afterTakeoff(takeoff_result); });
      });
    });
  }

  void onDeactivate(DeactivateReason reason) override
  {
    log("executor_deactivated",
        reason == DeactivateReason::FailsafeActivated ? "failsafe_activated" : "other");
  }

 private:
  void afterTakeoff(px4_ros2::Result result)
  {
    if (!requireSuccess("takeoff_complete", result)) return;
    log("executor_transition", "successor_baseline_external_mode");
    scheduleMode(ownedMode().id(), [this](px4_ros2::Result mode_result) {
      if (!requireSuccess("external_mode_complete", mode_result)) return;
      log("executor_transition", "land");
      land([this](px4_ros2::Result land_result) {
        if (!requireSuccess("land_complete", land_result)) return;
        log("executor_transition", "wait_until_disarmed");
        waitUntilDisarmed([this](px4_ros2::Result wait_result) {
          requireSuccess("wait_until_disarmed_complete", wait_result);
        });
      });
    });
  }

  bool requireSuccess(const char* stage, px4_ros2::Result result)
  {
    const bool success = result == px4_ros2::Result::Success;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"executor_result\",\"component_name\":\"%s\",\"stage\":\"%s\",\"result\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
        kComponentName, stage, px4_ros2::resultToString(result), id(), ownedMode().id());
    return success;
  }

  void log(const char* event, const char* stage)
  {
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"%s\",\"component_name\":\"%s\",\"stage\":\"%s\",\"executor_id\":%d,\"owned_mode\":%u}",
        event, kComponentName, stage, id(), ownedMode().id());
  }

  bool started_{false};
};

}  // namespace uav_sf

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithModeExecutor<uav_sf::SuccessorBaselineExecutor,
                                               uav_sf::SuccessorBaselineMode>;
  auto node = std::make_shared<Node>("successor_baseline_executor", true);
  RCLCPP_INFO(
      node->get_logger(),
      "{\"event_type\":\"mode_executor_registered\",\"component_name\":\"Successor Baseline\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"scenario\":\"takeoff_nonreplacement_external_land_disarm\"}",
      node->getMode().id(),
      static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
