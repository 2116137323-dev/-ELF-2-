import os
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class DiffDriveController(Node):
    """将 Nav2 /cmd_vel 映射为 /dev/my_serial 离散命令，并处理急停。"""

    def __init__(self):
        super().__init__('diff_drive_controller')

        self.declare_parameter('device_path', '/dev/my_serial')
        self.declare_parameter('enable_motor', True)
        self.declare_parameter('max_vel_x', 0.5)
        self.declare_parameter('max_vel_theta', 1.5)
        self.declare_parameter('linear_deadzone', 0.01)
        self.declare_parameter('angular_deadzone', 0.05)
        self.declare_parameter('turn_bias', 0.45)
        self.declare_parameter('turn_duty', 40)
        self.declare_parameter('min_duty', 20)
        self.declare_parameter('max_duty', 30)
        self.declare_parameter('control_rate_hz', 8.0)
        self.declare_parameter('min_write_interval_sec', 0.11)
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

        self._device_fd = None
        self._last_write_monotonic = 0.0
        self._last_sent = None
        self._pending_direction = None
        self._pending_duty = None
        self._zero_vel_since = None

        self.emergency_stop = False
        self.cmd_vel = Twist()

        if self.enable_motor:
            self._open_device()
        else:
            self.get_logger().warn('enable_motor=false，底盘命令仅记录日志，不写串口')

        self.create_subscription(Twist, '/cmd_vel', self._cmd_vel_callback, 10)
        self.create_subscription(Bool, '/emergency_stop', self._estop_callback, 10)
        self.create_timer(1.0 / control_rate_hz, self._control_loop)

        self.get_logger().info(
            f'底盘驱动已启动: device={self.device_path}, rate={control_rate_hz:.1f}Hz'
        )

    def _open_device(self):
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
        self.get_logger().info(f'电机命令: {command!r}')

    def _write_command(self, command: str, force: bool = False):
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
        duty = max(0, min(100, int(duty_percent)))
        return str(100 - duty)

    def _resolve_target(self, linear_x: float, angular_z: float):
        max_v = self.max_vel_x if self.max_vel_x > 0.0 else 1.0
        max_w = self.max_vel_theta if self.max_vel_theta > 0.0 else 1.0

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
        self._pending_direction = None
        self._pending_duty = None

    def _send_stop(self, force: bool = False):
        if self._last_sent == 'p':
            return True

        if self._write_command('p', force=force):
            self._last_sent = 'p'
            self._clear_pending()
            self._log_command('p')
            return True
        return False

    def _estop_callback(self, msg: Bool):
        if msg.data:
            self.emergency_stop = True
            self.cmd_vel = Twist()
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
        if not self.emergency_stop:
            self.cmd_vel = msg

    def _control_loop(self):
        if self.emergency_stop:
            self._send_stop(force=False)
            return

        direction, duty = self._resolve_target(
            self.cmd_vel.linear.x,
            self.cmd_vel.angular.z,
        )

        if direction == 'stop':
            now = time.monotonic()
            if self._zero_vel_since is None:
                self._zero_vel_since = now
            if now - self._zero_vel_since < self.stop_hold_sec:
                return
            self._send_stop(force=False)
            return

        self._zero_vel_since = None

        if self._pending_duty is not None:
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
            self._pending_direction = direction
            self._pending_duty = duty


def main(args=None):
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
