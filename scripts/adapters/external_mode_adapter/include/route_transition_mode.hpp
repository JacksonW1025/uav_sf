#pragma once

#include <Eigen/Core>
#include <chrono>
#include <cmath>
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
    sequence_ = 0;
    completion_reported_ = false;
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"external_mode_activated\",\"mode_id\":%u}", id());
  }

  void onDeactivate() override
  {
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"external_mode_deactivated\",\"mode_id\":%u,\"sequence\":%llu}",
                id(), static_cast<unsigned long long>(sequence_));
  }

  void updateSetpoint(float dt_s) override
  {
    if (!std::isfinite(dt_s) || dt_s < 0.f) {
      reportFailure("invalid_update_dt");
      return;
    }
    const double elapsed_s = (node().get_clock()->now() - activation_time_).seconds();
    Eigen::Vector3f velocity = Eigen::Vector3f::Zero();
    const char* phase = "hover";
    std::optional<float> yaw = 0.f;

    if (elapsed_s >= 3.0 && elapsed_s < 8.0) {
      velocity = Eigen::Vector3f{0.5f, 0.f, 0.f};
      phase = "straight_line";
    } else if (elapsed_s >= 8.0) {
      if (!completion_reported_) {
        completion_reported_ = true;
        RCLCPP_INFO(node().get_logger(),
                    "{\"event_type\":\"external_mode_completed\",\"result\":\"success\"}");
        completed(px4_ros2::Result::Success);
      }
      return;
    }

    trajectory_setpoint_->update(velocity, {}, yaw, {});
    if ((sequence_++ % 20U) == 0U) {
      RCLCPP_INFO(node().get_logger(),
                  "{\"event_type\":\"external_mode_setpoint\",\"behavior_phase\":\"%s\",\"setpoint_level\":\"velocity\",\"sequence\":%llu}",
                  phase, static_cast<unsigned long long>(sequence_ - 1U));
    }
  }

 private:
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
  bool completion_reported_{false};
};

}  // namespace uav_sf
