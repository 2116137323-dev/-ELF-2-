#!/usr/bin/python3
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
import os

def generate_launch_description():

    driver_dir = os.path.join(get_package_share_directory('lslidar_driver'), 'params','lidar_uart_ros2', 'lsn10.yaml')
                     
    driver_node = Node(
        package='lslidar_driver',
        executable='lslidar_driver_node',
        name='lslidar_driver_node',  # 设置激光数据 topic 名称
        output='screen',
        emulate_tty=True,
        namespace='',
        parameters=[driver_dir],
    )

    return LaunchDescription([
        driver_node,
    ])
