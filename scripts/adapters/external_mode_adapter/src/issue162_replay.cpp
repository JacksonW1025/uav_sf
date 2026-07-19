#include <Eigen/Core>

#include <chrono>
#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <px4_ros2/odometry/local_position.hpp>
#include <rclcpp/rclcpp.hpp>

namespace uav_sf {

namespace {
constexpr const char* kComponentName = "Issue 162 Custom RTL";
constexpr float kTargetHeightM = 5.f;
constexpr float kPositionToleranceM = 0.5f;
constexpr float kVelocityToleranceMps = 0.5f;
constexpr auto kStableDuration = std::chrono::seconds(1);
}

class Issue162CustomRtlMode final : public px4_ros2::ModeBase {
 public:
  explicit Issue162CustomRtlMode(rclcpp::Node& node)
      : ModeBase(node, Settings{kComponentName}
                           .replaceInternalMode(ModeBase::kModeIDRtl)
                           .preventArming(false))
  {
    modeRequirements().local_position = true;
    trajectory_setpoint_ = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
    local_position_ = std::make_shared<px4_ros2::OdometryLocalPosition>(*this);
    setSetpointUpdateRate(20.f);
  }

  void onActivate() override
  {
    ++activation_id_;
    sequence_ = 0;
    completion_reported_ = false;
    stable_since_.reset();
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"external_mode_activated\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"target_ned_m\":[0.0,0.0,-%.1f]}",
        kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_), kTargetHeightM);
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

    const Eigen::Vector3f target{0.f, 0.f, -kTargetHeightM};
    trajectory_setpoint_->updatePosition(target);

    const uint64_t current_sequence = sequence_++;
    const bool position_valid = local_position_->positionXYValid()
                                && local_position_->positionZValid();
    const bool velocity_valid = local_position_->velocityXYValid()
                                && local_position_->velocityZValid();
    float horizontal_error = NAN;
    float vertical_error = NAN;
    float speed = NAN;
    bool condition_met = false;
    if (position_valid && velocity_valid) {
      const Eigen::Vector3f position = local_position_->positionNed();
      const Eigen::Vector3f velocity = local_position_->velocityNed();
      horizontal_error = position.head<2>().norm();
      vertical_error = std::abs(position.z() - target.z());
      speed = velocity.norm();
      condition_met = horizontal_error <= kPositionToleranceM
                      && vertical_error <= kPositionToleranceM
                      && speed <= kVelocityToleranceMps;
    }

    const rclcpp::Time now = node().get_clock()->now();
    if (condition_met) {
      if (!stable_since_) stable_since_ = now;
    } else {
      stable_since_.reset();
    }

    if ((current_sequence % 20U) == 0U) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_setpoint\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"behavior_phase\":\"return_above_home\",\"setpoint_level\":\"position\",\"sequence\":%llu,\"horizontal_error_m\":%.6f,\"vertical_error_m\":%.6f,\"speed_m_s\":%.6f,\"completion_condition_met\":%s}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_),
          static_cast<unsigned long long>(current_sequence), horizontal_error, vertical_error,
          speed, condition_met ? "true" : "false");
    }

    if (!completion_reported_ && stable_since_
        && now - *stable_since_ >= rclcpp::Duration(kStableDuration)) {
      completion_reported_ = true;
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"external_mode_completed\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"result\":\"success\",\"horizontal_error_m\":%.6f,\"vertical_error_m\":%.6f,\"speed_m_s\":%.6f,\"stable_duration_ms\":1000}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_), horizontal_error, vertical_error,
          speed);
      completed(px4_ros2::Result::Success);
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

  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  std::shared_ptr<px4_ros2::OdometryLocalPosition> local_position_;
  std::optional<rclcpp::Time> stable_since_;
  uint64_t sequence_{0};
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  bool completion_reported_{false};
};

class Issue162Executor final : public px4_ros2::ModeExecutorBase {
 public:
  explicit Issue162Executor(px4_ros2::ModeBase& owned_mode)
      : ModeExecutorBase(Settings{}, owned_mode)
  {
  }

  void onActivate() override
  {
    log("executor_activated", "schedule_owned_custom_rtl");
    scheduleMode(ownedMode().id(), [this](px4_ros2::Result mode_result) {
      if (!requireSuccess("custom_rtl_complete", mode_result)) return;
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

  void onDeactivate(DeactivateReason reason) override
  {
    log("executor_deactivated",
        reason == DeactivateReason::FailsafeActivated ? "failsafe_activated" : "other");
  }

 private:
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
};

}  // namespace uav_sf

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  try {
    using Node =
        px4_ros2::NodeWithModeExecutor<uav_sf::Issue162Executor,
                                       uav_sf::Issue162CustomRtlMode>;
    auto node = std::make_shared<Node>("issue162_replay", true);
    RCLCPP_INFO(
        node->get_logger(),
        "{\"event_type\":\"mode_executor_registered\",\"component_name\":\"Issue 162 Custom RTL\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"scenario\":\"manual_rtl_replacement_completion_land_disarm\"}",
        node->getMode().id(),
        static_cast<unsigned long long>(node->getMode().registrationInstanceId()));
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
  } catch (const std::exception& exception) {
    std::cerr << "{\"event_type\":\"replay_exception\","
              << "\"stage\":\"node_construction_or_registration\",\"what\":"
              << std::quoted(exception.what()) << "}" << std::endl;
    rclcpp::shutdown();
    return 42;
  }
}
