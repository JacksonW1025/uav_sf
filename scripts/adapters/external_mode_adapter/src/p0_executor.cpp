#include "../include/route_transition_mode.hpp"

#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>

namespace uav_sf {

class P0Executor final : public px4_ros2::ModeExecutorBase {
 public:
  explicit P0Executor(px4_ros2::ModeBase& owned_mode)
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
    log("executor_activated", "wait_ready_to_arm");
    waitReadyToArm([this](px4_ros2::Result ready_result) {
      if (!requireSuccess("ready_to_arm", ready_result)) return;
      log("executor_transition", "arm");
      arm([this](px4_ros2::Result arm_result) {
        if (!requireSuccess("arm_complete", arm_result)) return;
        log("executor_transition", "takeoff");
        takeoff([this](px4_ros2::Result result) { afterTakeoff(result); });
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
    log("executor_transition", "custom_external_mode");
    scheduleMode(ownedMode().id(), [this](px4_ros2::Result mode_result) {
      if (!requireSuccess("external_mode_complete", mode_result)) return;
      log("executor_transition", "rtl");
      rtl([this](px4_ros2::Result rtl_result) {
        if (!requireSuccess("rtl_complete", rtl_result)) return;
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
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"executor_result\",\"stage\":\"%s\",\"result\":\"%s\"}",
                stage, px4_ros2::resultToString(result));
    return success;
  }

  void log(const char* event, const char* stage)
  {
    RCLCPP_INFO(node().get_logger(),
                "{\"event_type\":\"%s\",\"stage\":\"%s\"}", event, stage);
  }

  bool started_{false};
};

}  // namespace uav_sf

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  using Node = px4_ros2::NodeWithModeExecutor<uav_sf::P0Executor, uav_sf::RouteTransitionMode>;
  auto node = std::make_shared<Node>("p0_external_mode_executor", true);
  RCLCPP_INFO(node->get_logger(),
              "{\"event_type\":\"mode_executor_registered\",\"scenario\":\"takeoff_external_rtl_disarm\"}");
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
