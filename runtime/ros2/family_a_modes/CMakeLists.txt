cmake_minimum_required(VERSION 3.16)
project(family_a_modes)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Wpedantic -Werror)

find_package(ament_cmake REQUIRED)
find_package(px4_ros2_cpp REQUIRED)
find_package(rclcpp REQUIRED)

add_executable(external_mode src/external_mode.cpp)
target_link_libraries(external_mode px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

add_executable(mode_executor src/mode_executor.cpp)
target_link_libraries(mode_executor px4_ros2_cpp::px4_ros2_cpp rclcpp::rclcpp)

install(TARGETS external_mode mode_executor DESTINATION lib/${PROJECT_NAME})
ament_package()
