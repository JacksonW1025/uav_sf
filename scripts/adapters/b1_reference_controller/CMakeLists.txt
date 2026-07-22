cmake_minimum_required(VERSION 3.8)
project(b1_reference_controller)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Wpedantic -Werror -Wno-unused-parameter)

find_package(ament_cmake REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(px4_ros2_cpp REQUIRED)
find_package(rclcpp REQUIRED)

add_executable(
  b1_reference_controller
  ../external_mode_adapter/src/b1_reference_controller.cpp
)
target_link_libraries(
  b1_reference_controller
  PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp
)

install(TARGETS b1_reference_controller DESTINATION lib/${PROJECT_NAME})
ament_package()
