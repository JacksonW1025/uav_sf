#pragma once

#include <Eigen/Core>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>

namespace uav_sf {

class RouteTransitionMode final : public px4_ros2::ModeBase {
 public:
  explicit RouteTransitionMode(rclcpp::Node& node)
      : ModeBase(node, Settings{"Route Transition"}.preventArming(false))
  {
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
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"external_mode_activated\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu}",
                id(), static_cast<unsigned long long>(registration_instance_id_),
                static_cast<unsigned long long>(activation_id_));
  }

  void onDeactivate() override
  {
    // Channel gating is scoped to the active P3 observation window. Restore
    // replies before the later graceful unregister handshake.
    setArmingCheckReplyEnabled(true);
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"external_mode_deactivated\",\"mode_id\":%u,\"registration_instance_id\":%llu,\"activation_id\":%llu,\"sequence\":%llu}",
                id(), static_cast<unsigned long long>(registration_instance_id_),
                static_cast<unsigned long long>(activation_id_),
                static_cast<unsigned long long>(sequence_));
  }

  uint64_t registrationInstanceId() const { return registration_instance_id_; }

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      reportFailure("invalid_update_dt");
      return;
    }
    const double elapsed_s = (node().get_clock()->now() - activation_time_).seconds();
    const char* selected_context = std::getenv("UAV_SF_BEHAVIOR_CONTEXT");
    if (selected_context == nullptr && std::getenv("UAV_SF_HOVER_ONLY") != nullptr) {
      selected_context = "hover";
    }
    const char* duration_value = std::getenv("UAV_SF_ACTIVE_DURATION_S");
    const double completion_s = duration_value == nullptr ? 16.0 : std::strtod(duration_value, nullptr);
    const bool explicit_completion_duration = duration_value != nullptr;
    const bool context_active = contextMarkerActive();
    const bool log_every_setpoint = std::getenv("UAV_SF_LOG_EVERY_SETPOINT") != nullptr;
    const bool health_reply_enabled = channelEnabled("health_reply.off");
    const bool setpoint_enabled = channelEnabled("setpoint.off");
    setArmingCheckReplyEnabled(health_reply_enabled);
    if (controlMarkerExists("stop")) {
      if (!completion_reported_) {
        completion_reported_ = true;
        RCLCPP_INFO(node().get_logger(),
                    "{\"event_type\":\"external_mode_completed\",\"result\":\"success\",\"reason\":\"controlled_cleanup\"}");
        completed(px4_ros2::Result::Success);
      }
      return;
    }
    if (health_reply_enabled != last_health_reply_enabled_
        || setpoint_enabled != last_setpoint_enabled_) {
      RCLCPP_INFO(node().get_logger(),
                  "{\"event_type\":\"external_mode_channel_state\",\"health_reply_enabled\":%s,\"setpoint_enabled\":%s,\"activation_id\":%llu}",
                  health_reply_enabled ? "true" : "false", setpoint_enabled ? "true" : "false",
                  static_cast<unsigned long long>(activation_id_));
      last_health_reply_enabled_ = health_reply_enabled;
      last_setpoint_enabled_ = setpoint_enabled;
    }
    Eigen::Vector3f velocity = Eigen::Vector3f::Zero();
    const char* phase = "hover";
    std::optional<float> yaw = 0.f;

    if (context_active && selected_context != nullptr && std::strcmp(selected_context, "straight") == 0) {
      velocity = Eigen::Vector3f{0.5f, 0.f, 0.f};
      phase = "straight_line";
    } else if (context_active && selected_context != nullptr && std::strcmp(selected_context, "turn") == 0) {
      const float selected_yaw = 0.15f * static_cast<float>(elapsed_s);
      velocity = Eigen::Vector3f{0.3f * std::cos(selected_yaw), 0.3f * std::sin(selected_yaw), 0.f};
      yaw = selected_yaw;
      phase = "low_speed_turn";
    } else if (context_active && selected_context != nullptr && std::strcmp(selected_context, "descent") == 0) {
      velocity = Eigen::Vector3f{0.f, 0.f, 0.2f};
      phase = "stable_descent";
    } else if (selected_context == nullptr && elapsed_s >= 3.0 && elapsed_s < 8.0) {
      velocity = Eigen::Vector3f{0.5f, 0.f, 0.f};
      phase = "straight_line";
    } else if (selected_context == nullptr && elapsed_s >= 8.0 && elapsed_s < 12.0) {
      const float selected_yaw = 0.15f * static_cast<float>(elapsed_s - 8.0);
      velocity = Eigen::Vector3f{0.3f * std::cos(selected_yaw), 0.3f * std::sin(selected_yaw), 0.f};
      yaw = selected_yaw;
      phase = "low_speed_turn";
    } else if (selected_context == nullptr && elapsed_s >= 12.0) {
      velocity = Eigen::Vector3f{0.f, 0.f, 0.2f};
      phase = "stable_descent";
    }

    if ((selected_context == nullptr || explicit_completion_duration) && elapsed_s >= completion_s) {
      if (!completion_reported_) {
        completion_reported_ = true;
        RCLCPP_INFO(node().get_logger(),
                    "{\"event_type\":\"external_mode_completed\",\"result\":\"success\"}");
        completed(px4_ros2::Result::Success);
      }
      return;
    }

    if (setpoint_enabled) {
      trajectory_setpoint_->update(velocity, {}, yaw, {});
    }
    const uint64_t current_sequence = sequence_++;
    if (log_every_setpoint || (current_sequence % 20U) == 0U) {
      RCLCPP_INFO(node().get_logger(),
                  "{\"event_type\":\"external_mode_setpoint\",\"behavior_phase\":\"%s\",\"setpoint_level\":\"velocity\",\"sequence\":%llu}",
                  phase, static_cast<unsigned long long>(current_sequence));
    }
  }

 private:
  bool channelEnabled(const char* disabled_marker) const
  {
    return !controlMarkerExists(disabled_marker);
  }

  bool contextMarkerActive() const
  {
    const char* directory = std::getenv("UAV_SF_CHANNEL_CONTROL_DIR");
    return directory == nullptr
           || std::filesystem::exists(std::filesystem::path(directory) / "context.active");
  }

  bool controlMarkerExists(const char* marker) const
  {
    const char* directory = std::getenv("UAV_SF_CHANNEL_CONTROL_DIR");
    return directory != nullptr
           && std::filesystem::exists(std::filesystem::path(directory) / marker);
  }

  void reportFailure(const char* reason)
  {
    if (completion_reported_) return;
    completion_reported_ = true;
    RCLCPP_ERROR(node().get_logger(),
                 "{\"event_type\":\"external_mode_failure\",\"reason\":\"%s\"}", reason);
    completed(px4_ros2::Result::ModeFailureOther);
  }

  rclcpp::Time activation_time_{};
  std::shared_ptr<px4_ros2::TrajectorySetpointType> trajectory_setpoint_;
  uint64_t sequence_{0};
  const uint64_t registration_instance_id_{
      static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count())};
  uint64_t activation_id_{0};
  bool completion_reported_{false};
  bool last_health_reply_enabled_{true};
  bool last_setpoint_enabled_{true};
};

}  // namespace uav_sf
