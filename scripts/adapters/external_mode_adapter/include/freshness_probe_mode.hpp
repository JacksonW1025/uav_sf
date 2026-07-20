#pragma once

#include <Eigen/Core>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/attitude.hpp>
#include <px4_ros2/control/setpoint_types/experimental/rates.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <stdexcept>
#include <string>

namespace uav_sf {

class FreshnessProbeMode final : public px4_ros2::ModeBase {
 public:
  enum class SetpointKind { Trajectory, Attitude, Rate };

  explicit FreshnessProbeMode(rclcpp::Node& node)
      : ModeBase(node, Settings{"Freshness Probe"}.preventArming(false)),
        setpoint_kind_(parseSetpointKind()),
        trajectory_velocity_m_s_(environmentFloat("UAV_SF_TRAJECTORY_VX_M_S", 0.5f)),
        attitude_roll_rad_(environmentFloat("UAV_SF_ATTITUDE_ROLL_RAD", 0.17453293f)),
        rate_roll_rad_s_(environmentFloat("UAV_SF_RATE_ROLL_RAD_S", 0.35f)),
        thrust_body_z_(environmentFloat("UAV_SF_THRUST_BODY_Z", -0.55f))
  {
    switch (setpoint_kind_) {
      case SetpointKind::Trajectory:
        trajectory_setpoint_ = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
        break;
      case SetpointKind::Attitude:
        attitude_setpoint_ = std::make_shared<px4_ros2::AttitudeSetpointType>(*this);
        break;
      case SetpointKind::Rate:
        rates_setpoint_ = std::make_shared<px4_ros2::RatesSetpointType>(*this);
        break;
    }
  }

  void onActivate() override
  {
    activation_time_ = node().get_clock()->now();
    ++activation_id_;
    publish_sequence_ = 0;
    health_sequence_ = 0;
    last_publish_ros_ns_ = 0;
    last_setpoint_enabled_ = true;
    last_health_enabled_ = true;
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"freshness_mode_activated\",\"mode_id\":%u,\"activation_id\":%llu,\"setpoint_type\":\"%s\",\"trajectory_vx_m_s\":%.9g,\"attitude_roll_rad\":%.9g,\"rate_roll_rad_s\":%.9g,\"thrust_body_z\":%.9g}",
        id(), static_cast<unsigned long long>(activation_id_), setpointKindName(),
        static_cast<double>(trajectory_velocity_m_s_), static_cast<double>(attitude_roll_rad_),
        static_cast<double>(rate_roll_rad_s_), static_cast<double>(thrust_body_z_));
  }

  void onDeactivate() override
  {
    setArmingCheckReplyEnabled(true);
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"freshness_mode_deactivated\",\"mode_id\":%u,\"activation_id\":%llu,\"last_publish_sequence\":%llu,\"last_publish_ros_ns\":%llu}",
        id(), static_cast<unsigned long long>(activation_id_),
        static_cast<unsigned long long>(publish_sequence_),
        static_cast<unsigned long long>(last_publish_ros_ns_));
  }

  void checkArmingAndRunConditions(px4_ros2::HealthAndArmingCheckReporter&) override
  {
    const auto now_ns = static_cast<uint64_t>(node().get_clock()->now().nanoseconds());
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"freshness_health_reply\",\"sequence\":%llu,\"ros_time_ns\":%llu,\"activation_id\":%llu}",
        static_cast<unsigned long long>(health_sequence_++),
        static_cast<unsigned long long>(now_ns),
        static_cast<unsigned long long>(activation_id_));
  }

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      throw std::runtime_error("invalid setpoint update dt");
    }

    const bool health_enabled = channelEnabled("health_reply.off");
    const bool setpoint_enabled = channelEnabled("setpoint.off");
    setArmingCheckReplyEnabled(health_enabled);

    if (health_enabled != last_health_enabled_ || setpoint_enabled != last_setpoint_enabled_) {
      const auto now_ns = static_cast<uint64_t>(node().get_clock()->now().nanoseconds());
      RCLCPP_INFO(
          node().get_logger(),
          "{\"event_type\":\"freshness_channel_state\",\"setpoint_enabled\":%s,\"health_reply_enabled\":%s,\"ros_time_ns\":%llu,\"last_publish_sequence\":%llu,\"last_publish_ros_ns\":%llu}",
          setpoint_enabled ? "true" : "false", health_enabled ? "true" : "false",
          static_cast<unsigned long long>(now_ns),
          static_cast<unsigned long long>(publish_sequence_),
          static_cast<unsigned long long>(last_publish_ros_ns_));
      last_health_enabled_ = health_enabled;
      last_setpoint_enabled_ = setpoint_enabled;
    }

    if (!setpoint_enabled) {
      return;
    }

    switch (setpoint_kind_) {
      case SetpointKind::Trajectory:
        trajectory_setpoint_->update(
            Eigen::Vector3f{trajectory_velocity_m_s_, 0.f, 0.f}, {}, 0.f, {});
        break;
      case SetpointKind::Attitude:
        attitude_setpoint_->update(
            attitude_roll_rad_, 0.f, 0.f, Eigen::Vector3f{0.f, 0.f, thrust_body_z_});
        break;
      case SetpointKind::Rate:
        rates_setpoint_->update(
            Eigen::Vector3f{rate_roll_rad_s_, 0.f, 0.f},
            Eigen::Vector3f{0.f, 0.f, thrust_body_z_});
        break;
    }

    last_publish_ros_ns_ = static_cast<uint64_t>(node().get_clock()->now().nanoseconds());
    RCLCPP_INFO(
        node().get_logger(),
        "{\"event_type\":\"freshness_setpoint_published\",\"sequence\":%llu,\"ros_time_ns\":%llu,\"activation_id\":%llu,\"setpoint_type\":\"%s\",\"trajectory_vx_m_s\":%.9g,\"attitude_roll_rad\":%.9g,\"rate_roll_rad_s\":%.9g,\"thrust_body_z\":%.9g}",
        static_cast<unsigned long long>(publish_sequence_++),
        static_cast<unsigned long long>(last_publish_ros_ns_),
        static_cast<unsigned long long>(activation_id_), setpointKindName(),
        static_cast<double>(trajectory_velocity_m_s_), static_cast<double>(attitude_roll_rad_),
        static_cast<double>(rate_roll_rad_s_), static_cast<double>(thrust_body_z_));
  }

  const char* setpointKindName() const
  {
    switch (setpoint_kind_) {
      case SetpointKind::Trajectory: return "TRAJECTORY";
      case SetpointKind::Attitude: return "ATTITUDE";
      case SetpointKind::Rate: return "RATE";
    }
    return "UNKNOWN";
  }

 private:
  static SetpointKind parseSetpointKind()
  {
    const char* value = std::getenv("UAV_SF_SETPOINT_TYPE");
    if (value == nullptr || std::strcmp(value, "TRAJECTORY") == 0) {
      return SetpointKind::Trajectory;
    }
    if (std::strcmp(value, "ATTITUDE") == 0) {
      return SetpointKind::Attitude;
    }
    if (std::strcmp(value, "RATE") == 0) {
      return SetpointKind::Rate;
    }
    throw std::invalid_argument("UAV_SF_SETPOINT_TYPE must be TRAJECTORY, ATTITUDE, or RATE");
  }

  static float environmentFloat(const char* name, float default_value)
  {
    const char* value = std::getenv(name);
    if (value == nullptr) {
      return default_value;
    }
    char* end = nullptr;
    const float parsed = std::strtof(value, &end);
    if (end == value || *end != '\0' || !std::isfinite(parsed)) {
      throw std::invalid_argument(std::string(name) + " must be finite");
    }
    return parsed;
  }

  bool channelEnabled(const char* disabled_marker) const
  {
    const char* directory = std::getenv("UAV_SF_CHANNEL_CONTROL_DIR");
    return directory == nullptr
           || !std::filesystem::exists(std::filesystem::path(directory) / disabled_marker);
  }

  const SetpointKind setpoint_kind_;
  const float trajectory_velocity_m_s_;
  const float attitude_roll_rad_;
  const float rate_roll_rad_s_;
  const float thrust_body_z_;
  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  std::shared_ptr<px4_ros2::AttitudeSetpointType> attitude_setpoint_;
  std::shared_ptr<px4_ros2::RatesSetpointType> rates_setpoint_;
  rclcpp::Time activation_time_{};
  uint64_t activation_id_{0};
  uint64_t publish_sequence_{0};
  uint64_t health_sequence_{0};
  uint64_t last_publish_ros_ns_{0};
  bool last_setpoint_enabled_{true};
  bool last_health_enabled_{true};
};

}  // namespace uav_sf
