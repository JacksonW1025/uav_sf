cmake_minimum_required(VERSION 3.8)
project(route_transition_external_mode)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Wpedantic -Werror -Wno-unused-parameter)

find_package(ament_cmake REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(px4_ros2_cpp REQUIRED)
find_package(rclcpp REQUIRED)

option(UAV_SF_ISSUE162_ONLY "Build only the Issue #162 replay target" OFF)
option(UAV_SF_ISSUE162_HISTORICAL_API "Use the release/1.16 Mode Settings API" OFF)

set(install_targets issue162_replay)

if(NOT UAV_SF_ISSUE162_ONLY)
  add_executable(route_transition_external_mode src/external_mode.cpp)
  target_link_libraries(route_transition_external_mode PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

  add_executable(p0_external_mode_executor src/p0_executor.cpp)
  target_link_libraries(p0_external_mode_executor PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

  add_executable(successor_baseline_executor src/successor_baseline.cpp)
  target_link_libraries(successor_baseline_executor PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

  add_executable(external_mode_freshness_probe src/freshness_probe.cpp)
  target_link_libraries(external_mode_freshness_probe PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

  list(APPEND install_targets route_transition_external_mode p0_external_mode_executor successor_baseline_executor external_mode_freshness_probe)
endif()

add_executable(issue162_replay src/issue162_replay.cpp)
target_link_libraries(issue162_replay PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)
if(UAV_SF_ISSUE162_HISTORICAL_API)
  target_compile_definitions(issue162_replay PRIVATE UAV_SF_ISSUE162_HISTORICAL_API=1)
endif()

install(TARGETS ${install_targets} DESTINATION lib/${PROJECT_NAME})
ament_package()
