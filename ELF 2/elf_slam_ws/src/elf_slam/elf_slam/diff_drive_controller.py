"""
差速底盘离散命令控制节点。

该节点订阅 Nav2 输出的 /cmd_vel 速度指令，将连续速度转换成底盘驱动板能识别的
离散串口命令：w/s/a/d 表示方向，数字字符串表示占空比，p 表示停车。
同时订阅 /emergency_stop，在识别报警或上层急停时立即锁停底盘。
"""

import os
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class DiffDriveController(Node):
    """ROS2 节点：将 Nav2 /cmd_vel 映射为电机串口命令，并处理急停。"""

    def __init__(self):
        super().__init__('diff_drive_controller')

        # 串口设备路径通常由 udev 规则或 setup_motor_device.sh 映射到 /dev/my_serial。
        self.declare_parameter('device_path', '/dev/my_serial')
        # enable_motor=false 时只运行逻辑和日志，不实际写串口，便于无底盘环境调试。
        self.declare_parameter('enable_motor', True)
        # Nav2 速度归一化上限，用于把连续速度映射到占空比。
        self.declare_parameter('max_vel_x', 0.5)
        self.declare_parameter('max_vel_theta', 1.5)
        # 死区用于过滤 Nav2 输出的微小抖动，避免底盘在接近 0 速度时频繁轻微动作。
        self.declare_parameter('linear_deadzone', 0.01)
        self.declare_parameter('angular_deadzone', 0.05)
        # turn_bias 越小越容易优先转向；turn_duty 是原地转向时使用的固定占空比。
        self.declare_parameter('turn_bias', 0.45)
        self.declare_parameter('turn_duty', 40)
        # 直行/后退占空比范围，根据线速度大小在 min_duty 和 max_duty 之间插值。
        self.declare_parameter('min_duty', 20)
        self.declare_parameter('max_duty', 30)
        # 控制循环频率和最小写串口间隔，限制命令发送频率，避免驱动板处理不过来。
        self.declare_parameter('control_rate_hz', 8.0)
        self.declare_parameter('min_write_interval_sec', 0.11)
        # 急停时重复发送停车命令的次数，以及零速度持续多久后才真正下发停车。
        self.declare_parameter('stop_repeat', 1)
        self.declare_parameter('stop_hold_sec', 0.35)

        self.device_path = str(self.get_parameter('device_path').value)
        self.enable_motor = bool(self.get_parameter('enable_motor').value)
        self.max_vel_x = float(self.get_parameter('max_vel_x').value)
        self.max_vel_theta = float(self.get_parameter('max_vel_theta').value)
        self.linear_deadzone = float(self.get_parameter('linear_deadzone').value)
        self.angular_deadzone = float(self.get_parameter('angular_deadzone').value)
        self.turn_bias = float(self.get_parameter('turn_bias').value)
        self.turn_duty = int(self.get_parameter('turn_duty').value)
        self.min_duty = int(self.get_parameter('min_duty').value)
        self.max_duty = int(self.get_parameter('max_duty').value)
        self.min_write_interval_sec = float(self.get_parameter('min_write_interval_sec').value)
        self.stop_repeat = max(1, int(self.get_parameter('stop_repeat').value))
        self.stop_hold_sec = float(self.get_parameter('stop_hold_sec').value)

        control_rate_hz = min(float(self.get_parameter('control_rate_hz').value), 8.0)

        # 底层设备文件描述符；使用 os.write 直接写字符命令到驱动设备。
        self._device_fd = None
        # 记录上次写入时间，配合 min_write_interval_sec 做发送限频。
        self._last_write_monotonic = 0.0
        # 记录最近已发送的命令，避免重复发送完全相同的方向/占空比组合。
        self._last_sent = None
        # 底盘协议需要先发方向，再发速度占空比，因此这里暂存待发送的占空比。
        self._pending_direction = None
        self._pending_duty = None
        # 收到零速度后先等待 stop_hold_sec，避免 Nav2 短暂输出 0 导致频繁停车/启动。
        self._zero_vel_since = None

        self.emergency_stop = False
        self.cmd_vel = Twist()

        if self.enable_motor:
            self._open_device()
        else:
            self.get_logger().warn('enable_motor=false，底盘命令仅记录日志，不写串口')

        # /cmd_vel 来自 Nav2 或键盘遥控；/emergency_stop 来自识别报警或上层安全逻辑。
        self.create_subscription(Twist, '/cmd_vel', self._cmd_vel_callback, 10)
        self.create_subscription(Bool, '/emergency_stop', self._estop_callback, 10)
        # 定时控制循环负责把最新 cmd_vel 转换为串口命令，不在订阅回调里直接写设备。
        self.create_timer(1.0 / control_rate_hz, self._control_loop)

        self.get_logger().info(
            f'底盘驱动已启动: device={self.device_path}, rate={control_rate_hz:.1f}Hz'
        )

    def _open_device(self):
        """打开电机字符设备；失败时只记录错误，后续写命令时还会尝试重连。"""
        if not os.path.exists(self.device_path):
            self.get_logger().error(
                f'电机设备不存在: {self.device_path}。'
                ' 请先加载内核模块并执行 scripts/setup_motor_device.sh'
            )
            return

        try:
            self._device_fd = os.open(self.device_path, os.O_WRONLY)
            self.get_logger().info(f'已打开电机设备: {self.device_path}')
        except OSError as exc:
            self.get_logger().error(f'无法打开电机设备 {self.device_path}: {exc}')

    def _log_command(self, command: str):
        """统一记录实际下发给电机驱动的命令，便于调试运动行为。"""
        self.get_logger().info(f'电机命令: {command!r}')

    def _write_command(self, command: str, force: bool = False):
        """
        向电机设备写入 ASCII 命令。

        force=True 时忽略最小写入间隔，主要用于急停，保证停车命令能第一时间发出。
        """
        if not command:
            return False

        now = time.monotonic()
        if not force and (now - self._last_write_monotonic) < self.min_write_interval_sec:
            return False

        if self.enable_motor:
            if self._device_fd is None:
                self._open_device()
            if self._device_fd is None:
                return False
            try:
                # 驱动板协议使用简单 ASCII 字符，方向命令如 'w'，停车命令如 'p'。
                payload = command.encode('ascii')
                written = os.write(self._device_fd, payload)
                if written != len(payload):
                    return False
            except OSError as exc:
                self.get_logger().error(f'写入电机命令失败 ({command!r}): {exc}')
                try:
                    os.close(self._device_fd)
                except OSError:
                    pass
                self._device_fd = None
                return False

        self._last_write_monotonic = now
        return True

    def _duty_to_serial(self, duty_percent: int) -> str:
        """把占空比百分比转换为驱动板需要的数值字符串。"""
        duty = max(0, min(100, int(duty_percent)))
        # 当前电机协议中数值越小速度越高，因此用 100-duty 做反向映射。
        return str(100 - duty)

    def _resolve_target(self, linear_x: float, angular_z: float):
        """
        根据连续速度计算目标方向和占空比。

        返回值：
        - ('stop', 0)：线速度和角速度都处于死区内。
        - ('a'/'d', turn_duty)：角速度占主导，执行原地左/右转。
        - ('w'/'s', duty)：线速度占主导，执行前进/后退。
        """
        max_v = self.max_vel_x if self.max_vel_x > 0.0 else 1.0
        max_w = self.max_vel_theta if self.max_vel_theta > 0.0 else 1.0

        # 将速度归一化到 0~1 附近，便于比较线速度和角速度谁占主导。
        nv = abs(linear_x) / max_v
        nw = abs(angular_z) / max_w

        if nv < self.linear_deadzone and nw < self.angular_deadzone:
            return 'stop', 0

        if nw >= nv * self.turn_bias:
            direction = 'a' if angular_z > 0.0 else 'd'
            return direction, self.turn_duty

        direction = 'w' if linear_x >= 0.0 else 's'
        duty = self.min_duty + (self.max_duty - self.min_duty) * min(1.0, nv)
        return direction, int(duty)

    def _clear_pending(self):
        """清除等待发送的占空比命令。"""
        self._pending_direction = None
        self._pending_duty = None

    def _send_stop(self, force: bool = False):
        """发送停车命令 p，并清除方向/占空比的待发送状态。"""
        if self._last_sent == 'p':
            return True

        if self._write_command('p', force=force):
            self._last_sent = 'p'
            self._clear_pending()
            self._log_command('p')
            return True
        return False

    def _estop_callback(self, msg: Bool):
        """处理急停信号；急停开启后忽略后续 /cmd_vel，直到收到 False 解除。"""
        if msg.data:
            self.emergency_stop = True
            self.cmd_vel = Twist()
            # 清空 last_sent，确保即使上一条也是 p，也会强制重新下发停车。
            self._last_sent = None
            for _ in range(self.stop_repeat):
                if self._send_stop(force=True):
                    break
                time.sleep(0.11)
            self.get_logger().warn('收到急停信号，底盘已锁停')
            return

        self.emergency_stop = False
        self._zero_vel_since = None
        self.get_logger().info('急停解除，恢复 cmd_vel 控制')

    def _cmd_vel_callback(self, msg: Twist):
        """缓存最新速度指令；急停锁定期间直接丢弃，防止解除急停后继续执行旧速度。"""
        if not self.emergency_stop:
            self.cmd_vel = msg

    def _control_loop(self):
        """周期性将最新速度指令转换成底盘串口命令。"""
        if self.emergency_stop:
            self._send_stop(force=False)
            return

        direction, duty = self._resolve_target(
            self.cmd_vel.linear.x,
            self.cmd_vel.angular.z,
        )

        if direction == 'stop':
            now = time.monotonic()
            # 零速度保持一小段时间后再停车，滤掉 Nav2 在路径调整时的瞬时 0 速度。
            if self._zero_vel_since is None:
                self._zero_vel_since = now
            if now - self._zero_vel_since < self.stop_hold_sec:
                return
            self._send_stop(force=False)
            return

        self._zero_vel_since = None

        if self._pending_duty is not None:
            # 上一轮已经发出方向命令，本轮补发对应占空比；若方向变了则丢弃旧占空比。
            if direction != self._pending_direction:
                self._clear_pending()
            else:
                duty_cmd = self._duty_to_serial(self._pending_duty)
                desired = (self._pending_direction, duty_cmd)
                if desired == self._last_sent:
                    self._clear_pending()
                    return
                if self._write_command(duty_cmd, force=False):
                    self._last_sent = desired
                    self._clear_pending()
                    self._log_command(duty_cmd)
                return

        desired = (direction, self._duty_to_serial(duty))
        if desired == self._last_sent:
            return

        if self._write_command(direction, force=False):
            self._log_command(direction)
            # 方向命令发送成功后，下一次控制循环再发送速度数值，满足驱动板协议时序。
            self._pending_direction = direction
            self._pending_duty = duty


def main(args=None):
    """ROS2 节点入口：初始化、spin，并在退出时关闭设备文件。"""
    rclpy.init(args=args)
    node = DiffDriveController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node._device_fd is not None:
            try:
                os.close(node._device_fd)
            except OSError:
                pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
