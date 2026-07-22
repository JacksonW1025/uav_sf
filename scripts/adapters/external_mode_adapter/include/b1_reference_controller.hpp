#pragma once

#include <Eigen/Core>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/attitude.hpp>
#include <px4_ros2/odometry/local_position.hpp>
#include <rclcpp/rclcpp.hpp>

namespace uav_sf {

class B1ReferenceController final : public px4_ros2::ModeBase {
 public:
  static constexpr const char* kComponentName = "B1 Reference";
  static constexpr float kHoverThrust = 0.50f;
  static constexpr float kAltitudeKp = 0.12f;
  static constexpr float kVerticalVelocityKd = 0.08f;
  static constexpr float kMinimumThrust = 0.35f;
  static constexpr float kMaximumThrust = 0.65f;

  explicit B1ReferenceController(rclcpp::Node& node)
      : ModeBase(node, Settings{kComponentName}.preventArming(false))
  {
    modeRequirements().local_position = true;
    local_position_ = std::make_shared<px4_ros2::OdometryLocalPosition>(*this);
    attitude_setpoint_ = std::make_shared<px4_ros2::AttitudeSetpointType>(*this);
    setSetpointUpdateRate(50.f);
  }

  void onActivate() override
  {
    ++activation_id_;
    sequence_ = 0;
    output_valid_ = false;
    failure_reported_ = false;
    if (!stateFiniteAndValid()) {
      reportFailure("invalid_state_at_activation");
      return;
    }
    const Eigen::Vector3f position = local_position_->positionNed();
    target_z_m_ = position.z();
    target_yaw_rad_ = local_position_->heading();
    active_ = true;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"b1_reference_activated\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"target_z_m\":%.9g,\"target_yaw_rad\":%.9g}",
        kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_), static_cast<double>(target_z_m_),
        static_cast<double>(target_yaw_rad_));
  }

  void onDeactivate() override
  {
    active_ = false;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"b1_reference_deactivated\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"last_sequence\":%llu,\"output_valid\":%s}",
        kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
        static_cast<unsigned long long>(activation_id_),
        static_cast<unsigned long long>(sequence_), output_valid_ ? "true" : "false");
  }

  void updateSetpoint(float dt_s) override
  {
    if (!active_) return;
    if (!std::isfinite(dt_s) || dt_s <= 0.f || !stateFiniteAndValid()) {
      reportFailure("nonfinite_update_or_state");
      return;
    }

    const Eigen::Vector3f position = local_position_->positionNed();
    const Eigen::Vector3f velocity = local_position_->velocityNed();
    const float altitude_error_ned = position.z() - target_z_m_;
    const float thrust = std::clamp(
        kHoverThrust + kAltitudeKp * altitude_error_ned
            + kVerticalVelocityKd * velocity.z(),
        kMinimumThrust, kMaximumThrust);
    if (!std::isfinite(thrust) || !std::isfinite(target_yaw_rad_)) {
      reportFailure("nonfinite_controller_output");
      return;
    }

    attitude_setpoint_->update(
        0.f, 0.f, target_yaw_rad_, Eigen::Vector3f{0.f, 0.f, -thrust});
    output_valid_ = true;
    const uint64_t now_ns = static_cast<uint64_t>(node().get_clock()->now().nanoseconds());
    const uint64_t current_sequence = sequence_++;
    if ((current_sequence % 5U) == 0U) {
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"b1_reference_output\",\"component_name\":\"%s\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu,\"ros_time_ns\":%llu,\"target_topic\":\"vehicle_attitude_setpoint\",\"target_z_m\":%.9g,\"position_z_m\":%.9g,\"velocity_z_m_s\":%.9g,\"thrust_body_z\":%.9g}",
          kComponentName, id(), static_cast<unsigned long long>(registration_instance_id_),
          static_cast<unsigned long long>(activation_id_),
          static_cast<unsigned long long>(current_sequence),
          static_cast<unsigned long long>(now_ns), static_cast<double>(target_z_m_),
          static_cast<double>(position.z()), static_cast<double>(velocity.z()),
          static_cast<double>(-thrust));
    }
  }

  uint64_t registrationInstanceId() const { return registration_instance_id_; }

 private:
  bool stateFiniteAndValid() const
  {
    if (!local_position_->positionZValid() || !local_position_->velocityZValid()) return false;
    const Eigen::Vector3f position = local_position_->positionNed();
    const Eigen::Vector3f velocity = local_position_->velocityNed();
    return std::isfinite(position.z()) && std::isfinite(velocity.z())
           && std::isfinite(local_position_->heading());
  }

  void reportFailure(const char* reason)
  {
    if (!active_ && failure_reported_) return;
    active_ = false;
    failure_reported_ = true;
    RCLCPP_ERROR(
        node().get_logger(),
        "{\"event_type\":\"b1_reference_failure\",\"component_name\":\"%s\",\"mode_id\":%u,\"activation_id\":%llu,\"reason\":\"%s\"}",
        kComponentName, id(), static_cast<unsigned long long>(activation_id_), reason);
    completed(px4_ros2::Result::ModeFailureOther);
  }

  std::shared_ptr<px4_ros2::OdometryLocalPosition> local_position_;
  std::shared_ptr<px4_ros2::AttitudeSetpointType> attitude_setpoint_;
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  uint64_t sequence_{0};
  float target_z_m_{NAN};
  float target_yaw_rad_{NAN};
  bool active_{false};
  bool output_valid_{false};
  bool failure_reported_{false};
};

}  // namespace uav_sf
