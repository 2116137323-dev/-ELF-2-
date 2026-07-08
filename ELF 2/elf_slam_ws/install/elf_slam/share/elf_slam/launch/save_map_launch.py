import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_map_path = os.path.join(os.path.expanduser('~'), 'elf_map')

    return LaunchDescription([
        DeclareLaunchArgument(
            'map_path',
            default_value=default_map_path,
            description='保存地图文件前缀（不含扩展名）',
        ),
        Node(
            package='nav2_map_server',
            executable='map_saver_cli',
            name='map_saver',
            output='screen',
            arguments=['-f', LaunchConfiguration('map_path')],
        ),
    ])
