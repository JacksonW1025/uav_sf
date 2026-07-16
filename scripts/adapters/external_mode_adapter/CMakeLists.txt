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

add_executable(route_transition_external_mode src/external_mode.cpp)
target_link_libraries(route_transition_external_mode PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

add_executable(p0_external_mode_executor src/p0_executor.cpp)
target_link_libraries(p0_external_mode_executor PUBLIC Eigen3::Eigen px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

install(TARGETS route_transition_external_mode p0_external_mode_executor DESTINATION lib/${PROJECT_NAME})
ament_package()
