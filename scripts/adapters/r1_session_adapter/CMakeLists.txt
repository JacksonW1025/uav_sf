cmake_minimum_required(VERSION 3.16)
project(r1_session_adapter)

find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(px4_ros2_cpp REQUIRED)
find_package(rclcpp REQUIRED)

add_executable(r1_session_probe src/r1_session_probe.cpp)
target_link_libraries(
  r1_session_probe
  PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp
)

install(TARGETS r1_session_probe DESTINATION lib/${PROJECT_NAME})

ament_package()
