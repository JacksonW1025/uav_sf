#include <Eigen/Core>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>

class ExecutorOwnedMode : public px4_ros2::ModeBase {
 public:
  explicit ExecutorOwnedMode(rclcpp::Node& node)
      : ModeBase(node, Settings{"Family A Executor Mode"})
  {
    node.declare_parameter("mode_duration_s", 8.0);
    _duration_s = node.get_parameter("mode_duration_s").as_double();
    _trajectory = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
  }

  void onActivate() override
  {
    _activation_time = node().get_clock()->now();
    RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT executor_mode_activated");
  }

  void updateSetpoint(float) override
  {
    _trajectory->updatePosition(Eigen::Vector3f{0.f, 0.f, -3.f});
    if ((node().get_clock()->now() - _activation_time).seconds() >= _duration_s) {
      RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT executor_mode_completed");
      completed(px4_ros2::Result::Success);
    }
  }

 private:
  rclcpp::Time _activation_time{};
  double _duration_s{8.0};
  std::shared_ptr<px4_ros2::TrajectorySetpointType> _trajectory;
};

class FamilyAExecutor : public px4_ros2::ModeExecutorBase {
 public:
  explicit FamilyAExecutor(px4_ros2::ModeBase& owned_mode)
      : ModeExecutorBase(
            px4_ros2::ModeExecutorBase::Settings{}.activate(
                px4_ros2::ModeExecutorBase::Settings::Activation::ActivateImmediately),
            owned_mode),
        _node(owned_mode.node())
  {
  }

  void onActivate() override
  {
    RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT executor_activated");
    waitReadyToArm([this](px4_ros2::Result ready_result) {
      if (ready_result != px4_ros2::Result::Success) {
        RCLCPP_ERROR(_node.get_logger(), "FAMILY_A_EVENT ready_to_arm_failed");
        return;
      }
      arm([this](px4_ros2::Result arm_result) {
        if (arm_result != px4_ros2::Result::Success) {
          RCLCPP_ERROR(_node.get_logger(), "FAMILY_A_EVENT arm_failed");
          return;
        }
        takeoff([this](px4_ros2::Result result) {
          if (result != px4_ros2::Result::Success) {
            RCLCPP_ERROR(_node.get_logger(), "FAMILY_A_EVENT takeoff_failed");
            return;
          }
          scheduleMode(ownedMode().id(), [this](px4_ros2::Result mode_result) {
            RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT completion_delivered result=%s",
                        resultToString(mode_result));
            if (mode_result != px4_ros2::Result::Success) {
              return;
            }
            land([this](px4_ros2::Result land_result) {
              RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT land_completed result=%s",
                          resultToString(land_result));
              if (land_result == px4_ros2::Result::Success) {
                waitUntilDisarmed([this](px4_ros2::Result disarm_result) {
                  RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT disarm_completed result=%s",
                              resultToString(disarm_result));
                  if (disarm_result == px4_ros2::Result::Success) {
                    rclcpp::shutdown();
                  }
                });
              }
            });
          });
        });
      });
    });
  }

  void onDeactivate(DeactivateReason) override
  {
    RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT executor_deactivated");
  }

 private:
  rclcpp::Node& _node;
};

using FamilyAExecutorNode = px4_ros2::NodeWithModeExecutor<FamilyAExecutor, ExecutorOwnedMode>;

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FamilyAExecutorNode>("family_a_mode_executor", true));
  rclcpp::shutdown();
  return 0;
}
