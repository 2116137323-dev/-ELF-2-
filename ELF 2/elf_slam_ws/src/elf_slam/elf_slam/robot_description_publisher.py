"""
发布机器人 URDF 描述的辅助节点。

robot_state_publisher 通常通过参数读取 robot_description，
但 RViz 的 RobotModel 插件有时也会订阅 /robot_description。
该节点把 URDF 作为 latched 风格的话题周期性发布，方便 RViz 后启动时也能显示模型。
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


class RobotDescriptionPublisher(Node):
    """向 /robot_description 发布 URDF，供 RViz RobotModel 自动加载。"""

    def __init__(self):
        super().__init__('robot_description_publisher')
        self.declare_parameter('robot_description', '')

        description = str(self.get_parameter('robot_description').value)
        if not description.strip():
            self.get_logger().error('robot_description 参数为空，RViz 无法显示模型')
            return

        # TRANSIENT_LOCAL 相当于 ROS1 latched publisher：新订阅者能收到最后一次发布的 URDF。
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._publisher = self.create_publisher(String, 'robot_description', qos)
        self._message = String()
        self._message.data = description

        self._publisher.publish(self._message)
        # 周期性重发用于兼容部分 RViz/插件初始化较慢导致首次消息错过的情况。
        self.create_timer(5.0, self._republish)
        self.get_logger().info('已向 /robot_description 发布 URDF（RViz RobotModel 可自动加载）')

    def _republish(self):
        """重复发布缓存的 URDF 字符串。"""
        self._publisher.publish(self._message)


def main(args=None):
    rclpy.init(args=args)
    node = RobotDescriptionPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
