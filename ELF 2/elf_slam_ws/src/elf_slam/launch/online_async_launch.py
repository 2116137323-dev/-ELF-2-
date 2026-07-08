import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError

def _resolve_config(elf_share: str, filename: str) -> str:
    ws_root = os.path.abspath(os.path.join(elf_share, '..', '..', '..', '..'))
    src_cfg = os.path.join(ws_root, 'src', 'elf_slam', 'config', filename)
    if os.path.isfile(src_cfg):
        return src_cfg
    return os.path.join(elf_share, 'config', filename)


def _resolve_urdf(elf_share: str) -> str:
    ws_root = os.path.abspath(os.path.join(elf_share, '..', '..', '..', '..'))
    src_urdf = os.path.join(ws_root, 'src', 'elf_slam', 'urdf', 'elf_robot.urdf')
    if os.path.isfile(src_urdf):
        return src_urdf
    return os.path.join(elf_share, 'urdf', 'elf_robot.urdf')


def generate_launch_description():
    ld = LaunchDescription()
    pkg_name = 'elf_slam'
    elf_share = get_package_share_directory(pkg_name)
    has_lidar_pkg = False
    lidar_launch_file = ""
    mapper_config = _resolve_config(elf_share, 'mapper_params_online_async.yaml')
    robot_description_path = _resolve_urdf(elf_share)

    with open(robot_description_path, 'r', encoding='utf-8') as robot_description_file:
        robot_description = robot_description_file.read()
    
    # --- 1. 尝试获取 IMU 配置文件 (带报错保护) ---
    has_imu_pkg = False
    imu_filter_config = ""
    try:
        imu_pkg_share = get_package_share_directory('imu_ros2_device')
        imu_filter_config = os.path.join(imu_pkg_share, 'config', 'imu_filter_param.yaml')
        has_imu_pkg = True
    except PackageNotFoundError:
        print("\033[91m[警告]\033[0m 未找到 imu_ros2_device 包，相关节点将不启动！")

    try:
        lidar_pkg_share = get_package_share_directory('lslidar_driver')
        lidar_launch_file = os.path.join(lidar_pkg_share, 'launch', 'lsn10_launch.py')
        has_lidar_pkg = True
    except PackageNotFoundError:
        print("\033[91m[警告]\033[0m 未找到 lslidar_driver 包，雷达节点将不启动！")

    # --- 2. 机器人基础 TF (必需) ---
    ld.add_action(Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description}]
    ))

    ld.add_action(Node(
        package=pkg_name,
        executable='robot_description_publisher',
        name='robot_description_publisher',
        parameters=[{'robot_description': robot_description}],
        output='screen',
    ))

    # --- 3. 静态坐标变换 (保持原有建图 TF 结构) ---
    ld.add_action(Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_laser',
        arguments=['0', '0', '0.1', '0', '0', '0', 'base_footprint', 'laser']
    ))

    ld.add_action(Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_imu',
        arguments=['0', '0', '0.05', '0', '0', '0', 'base_footprint', 'imu_link']
    ))

    # --- 4. 传感器驱动与滤波 (仅在包存在时启动) ---
    if has_lidar_pkg:
        ld.add_action(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(lidar_launch_file)
        ))
        ld.add_action(Node(
            package=pkg_name,
            executable='scan_stamp_fix',
            name='scan_stamp_fix',
            parameters=[{
                'input_topic': '/scan',
                'output_topic': '/scan_fixed',
                'max_age_sec': 0.5,
                'fix_beam_count': True,
                'target_beams': 451,
                'output_time_offset_sec': 0.0,
            }],
            output='screen'
        ))

    if has_imu_pkg:
        ld.add_action(Node(
            package='imu_ros2_device',
            executable='ybimu_driver',
            name='ybimu_driver',
            parameters=[{'port': '/dev/ttyUSB0'}]
        ))
        
        ld.add_action(Node(
            package='imu_filter_madgwick',
            executable='imu_filter_madgwick_node',
            parameters=[imu_filter_config, {'publish_tf': False}]
        ))

    # --- 5. 编码器桥接 (当前包的功能) ---
    ld.add_action(Node(
        package=pkg_name,
        executable='encoder_bridge', 
        name='encoder_bridge',
        parameters=[{
            'allow_missing_encoder': True,
        }],
        output='screen'
    ))

    # --- 6. SLAM 核心 (Slam Toolbox) ---
    ld.add_action(Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        parameters=[mapper_config],
        output='screen'
    ))

    return ld
