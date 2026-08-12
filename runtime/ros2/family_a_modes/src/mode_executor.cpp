#include <chrono>
#include <cstdio>
#include <Eigen/Core>
#include <fcntl.h>
#include <memory>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <stdexcept>
#include <string>
#include <utility>
#include <unistd.h>

class LifecycleLog {
 public:
  LifecycleLog(const std::string& path, std::string run_id) : _run_id(std::move(run_id))
  {
    if (path.empty() || _run_id.empty()) {
      throw std::runtime_error("run_id and lifecycle_path are required");
    }
    _fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_APPEND, 0644);
    if (_fd < 0) {
      throw std::runtime_error("cannot create executor lifecycle log");
    }
  }

  ~LifecycleLog()
  {
    if (_fd >= 0) {
      ::fsync(_fd);
      ::close(_fd);
    }
  }

  void append(const char* kind, const char* fields = "")
  {
    const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(
                         std::chrono::steady_clock::now().time_since_epoch())
                         .count();
    char record[1024];
    const int length = std::snprintf(
        record, sizeof(record),
        "{\"kind\":\"%s\",\"received_monotonic_ns\":%lld,\"run_id\":\"%s\","
        "\"schema_version\":\"1.0\",\"sequence\":%u%s}\n",
        kind, static_cast<long long>(now), _run_id.c_str(), _sequence++, fields);
    if (length <= 0 || static_cast<std::size_t>(length) >= sizeof(record) ||
        ::write(_fd, record, static_cast<std::size_t>(length)) != length || ::fsync(_fd) != 0) {
      throw std::runtime_error("cannot append executor lifecycle record");
    }
  }

 private:
  int _fd{-1};
  std::string _run_id;
  unsigned int _sequence{0};
};

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
    if (!_completion_sent &&
        (node().get_clock()->now() - _activation_time).seconds() >= _duration_s) {
      _completion_sent = true;
      RCLCPP_INFO(node().get_logger(), "FAMILY_A_EVENT executor_mode_completed");
      completed(px4_ros2::Result::Success);
    }
  }

 private:
  rclcpp::Time _activation_time{};
  double _duration_s{8.0};
  bool _completion_sent{false};
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
    _node.declare_parameter<std::string>("run_id", "");
    _node.declare_parameter<std::string>("lifecycle_path", "");
    _lifecycle = std::make_unique<LifecycleLog>(
        _node.get_parameter("lifecycle_path").as_string(),
        _node.get_parameter("run_id").as_string());
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
          _lifecycle->append(
              "transition_requested",
              ",\"source_route\":\"px4_internal\",\"target_route\":\"mode_executor\"");
          scheduleMode(ownedMode().id(), [this](px4_ros2::Result mode_result) {
            RCLCPP_INFO(_node.get_logger(), "FAMILY_A_EVENT completion_delivered result=%s",
                        resultToString(mode_result));
            if (mode_result != px4_ros2::Result::Success) {
              return;
            }
            _lifecycle->append(
                "completion",
                ",\"delivery_owner\":\"family_a_mode_executor\",\"route\":\"mode_executor\"");
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
  std::unique_ptr<LifecycleLog> _lifecycle;
};

using FamilyAExecutorNode = px4_ros2::NodeWithModeExecutor<FamilyAExecutor, ExecutorOwnedMode>;

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FamilyAExecutorNode>("family_a_mode_executor", true));
  rclcpp::shutdown();
  return 0;
}
