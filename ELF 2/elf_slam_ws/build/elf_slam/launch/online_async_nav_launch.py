import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _resolve_config(elf_share: str, filename: str) -> str:
    ws_root = os.path.abspath(os.path.join(elf_share, '..', '..', '..', '..'))
    src_cfg = os.path.join(ws_root, 'src', 'elf_slam', 'config', filename)
    if os.path.isfile(src_cfg):
        return src_cfg
    return os.path.join(elf_share, 'config', filename)


def _resolve_rviz_config(elf_share: str) -> str:
    return _resolve_config(elf_share, 'nav2_online_slam.rviz')


def generate_launch_description():
    elf_share = get_package_share_directory('elf_slam')

    nav2_params = _resolve_config(elf_share, 'nav2_params_online_slam.yaml')
    diff_drive_params = _resolve_config(elf_share, 'diff_drive_params.yaml')
    rviz_config = _resolve_rviz_config(elf_share)

    use_rviz = LaunchConfiguration('use_rviz')
    use_diff_drive = LaunchConfiguration('use_diff_drive')
    enable_motor = LaunchConfiguration('enable_motor')

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(elf_share, 'launch', 'navigation_launch.py')
        ),
        launch_arguments={
            'use_sim_time': 'false',
            'autostart': 'true',
            'params_file': nav2_params,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_rviz', default_value='true'),
        DeclareLaunchArgument('use_diff_drive', default_value='true'),
        DeclareLaunchArgument('enable_motor', default_value='true'),
        DeclareLaunchArgument(
            'nav2_delay_sec',
            default_value='12.0',
            description='SLAM 发布 /map 后再启动 Nav2 的延迟秒数',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(elf_share, 'launch', 'online_async_launch.py')
            )
        ),
        TimerAction(
            period=LaunchConfiguration('nav2_delay_sec'),
            actions=[nav2_launch],
        ),
        Node(
            package='elf_slam',
            executable='diff_drive_controller',
            name='diff_drive_controller',
            output='screen',
            parameters=[
                diff_drive_params,
                {'enable_motor': ParameterValue(enable_motor, value_type=bool)},
            ],
            condition=IfCondition(use_diff_drive),
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', rviz_config],
            condition=IfCondition(use_rviz),
        ),
    ])
