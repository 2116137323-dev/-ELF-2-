import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Quaternion, TransformStamped
from tf2_ros import TransformBroadcaster
import subprocess
import threading
import os
import math
from ament_index_python.packages import get_package_prefix
from rclpy.executors import ExternalShutdownException

def euler_to_quaternion(yaw):
    return Quaternion(x=0.0, y=0.0, z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))

class EncoderBridge(Node):
    def __init__(self):
        super().__init__('encoder_bridge')
        self.initialized = False
        self.declare_parameter('wheel_diameter', 0.153)
        self.declare_parameter('pulses_per_rev', 820.0)
        self.declare_parameter('no_encoder_warning_sec', 2.0)
        self.declare_parameter('allow_missing_encoder', True)
        self.declare_parameter('left_wheel_direction', 1.0)
        self.declare_parameter('right_wheel_direction', 1.0)
        
        # 1. 话题发布与 TF 广播器
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        
        # 2. 订阅 IMU 获取转向 (偏航角)
        self.imu_sub = self.create_subscription(Imu, '/imu/data', self.imu_callback, 10)
        
        # 3. 左右轮独立计数器
        self.left_count = 0
        self.right_count = 0
        self.last_left_count = 0
        self.last_right_count = 0
        
        # 4. 里程计全局坐标
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_yaw = 0.0
        self.last_encoder_change_ns = self.get_clock().now().nanoseconds
        self.encoder_stalled_warned = False
        
        # 5. [关键修改] 脉冲比例因子计算
        # 请务必将 wheel_diameter 和 pulses_per_rev 调整为真实底盘参数
        wheel_diameter = float(self.get_parameter('wheel_diameter').value)
        pulses_per_rev = float(self.get_parameter('pulses_per_rev').value)
        self.no_encoder_warning_sec = float(self.get_parameter('no_encoder_warning_sec').value)
        self.allow_missing_encoder = bool(self.get_parameter('allow_missing_encoder').value)
        self.left_wheel_direction = float(self.get_parameter('left_wheel_direction').value)
        self.right_wheel_direction = float(self.get_parameter('right_wheel_direction').value)
        self.m_per_tick = (math.pi * wheel_diameter) / pulses_per_rev
        self.get_logger().info(f"每个脉冲代表距离: {self.m_per_tick:.6f} 米")

        self.encoder_available = False
        self.c_executable = ''

        # 6. 动态获取 C 程序路径
        try:
            package_path = get_package_prefix('elf_slam')
            self.c_executable = os.path.join(package_path, 'lib', 'elf_slam', 'encoder_raw')
        except Exception as e:
            self.get_logger().error(f"路径获取失败: {e}")

        if self.c_executable and os.path.exists(self.c_executable):
            if not os.access(self.c_executable, os.X_OK):
                try:
                    st = os.stat(self.c_executable)
                    os.chmod(self.c_executable, st.st_mode | 0o111)
                except Exception as exc:
                    self.get_logger().error(f"编码器程序不可执行且修复失败: {exc}")
                    self.c_executable = ''

            if self.c_executable:
                self.encoder_available = True
                self.thread = threading.Thread(target=self.read_c_program, daemon=True)
                self.thread.start()
                self.get_logger().info(f"编码器程序已启动: {self.c_executable}")
        else:
            msg = (
                f"未找到编码器程序: {self.c_executable or '<unknown>'}。"
                " 将继续发布 odom->base_footprint TF（位移为 0，仅 IMU 航向）。"
            )
            if self.allow_missing_encoder:
                self.get_logger().warning(msg)
            else:
                self.get_logger().error(msg)
                return

        # 7. 30Hz 更新里程计并发布 TF（无论编码器是否可用都必须发布）
        self.create_timer(0.033, self.update_and_publish)
        self.initialized = True
        self.get_logger().info("ELF 里程计/TF 节点已就绪（odom -> base_footprint）")

    def imu_callback(self, msg):
        # 从 IMU 的四元数中提取 Yaw (偏航角)
        q = msg.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        self.yaw = math.atan2(siny_cosp, cosy_cosp)

    def read_c_program(self):
        """
        不断读取 C 程序的标准输出。
        期望格式: "左轮脉冲,右轮脉冲" (例如: "150,148")
        """
        if not self.c_executable:
            return

        try:
            process = subprocess.Popen(
                [self.c_executable],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            self.get_logger().error(f"启动编码器程序失败: {exc}")
            return

        if process.stdout is None:
            self.get_logger().error("编码器程序未提供可读取输出")
            return

        for line in iter(process.stdout.readline, ''):
            try:
                parts = line.strip().split(',')
                if len(parts) == 2:
                    self.left_count = int(parts[0])
                    self.right_count = int(parts[1])
            except ValueError:
                # 忽略解析错误的行
                continue
        self.get_logger().warning("编码器程序已退出，里程计数据将停止更新")

    def ready(self):
        return self.initialized

    def update_and_publish(self):
        now = self.get_clock().now().to_msg()
        
        # --- 运动学核心逻辑 ---
        
        # 1. 计算左右轮各自的脉冲增量
        delta_left = self.left_count - self.last_left_count
        delta_right = self.right_count - self.last_right_count
        
        # 2. 计算左右轮各自的实际移动距离
        dist_left = delta_left * self.m_per_tick * self.left_wheel_direction
        dist_right = delta_right * self.m_per_tick * self.right_wheel_direction

        # 3. 计算机器人中心点的实际位移
        # 在原地打转时，dist_left 和 dist_right 符号相反，distance 将完美趋近于 0
        distance = (dist_left + dist_right) / 2.0
        
        # 4. 更新累计值，供下一帧计算使用
        self.last_left_count = self.left_count
        self.last_right_count = self.right_count
        if delta_left != 0 or delta_right != 0:
            self.last_encoder_change_ns = self.get_clock().now().nanoseconds
            if self.encoder_stalled_warned:
                self.get_logger().info("编码器计数已恢复更新")
                self.encoder_stalled_warned = False
        elif self.encoder_available:
            idle_time = (self.get_clock().now().nanoseconds - self.last_encoder_change_ns) / 1e9
            if idle_time > self.no_encoder_warning_sec and not self.encoder_stalled_warned:
                self.get_logger().warning(
                    f"编码器计数已 {idle_time:.1f} 秒未变化，请检查 GPIO 计数和底盘是否在运动"
                )
                self.encoder_stalled_warned = True
        
        # 5. 结合 IMU 航向积分位置；无编码器时保持 x/y 不变
        if self.encoder_available:
            yaw_mid = self.last_yaw + 0.5 * (self.yaw - self.last_yaw)
            self.x += distance * math.cos(yaw_mid)
            self.y += distance * math.sin(yaw_mid)

        self.last_yaw = self.yaw
        
        quat = euler_to_quaternion(self.yaw)

        # --- A. 发布 /odom 话题 ---
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_footprint'
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation = quat
        self.odom_pub.publish(odom)

        # --- B. 发布 TF 变换 ---
        t = TransformStamped()
        t.header.stamp = now
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_footprint'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation = quat
        self.tf_broadcaster.sendTransform(t)

def main():
    rclpy.init()
    node = EncoderBridge()
    if not node.ready():
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
        return
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass

if __name__ == '__main__':
    main()
