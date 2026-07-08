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

        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._publisher = self.create_publisher(String, 'robot_description', qos)
        self._message = String()
        self._message.data = description

        self._publisher.publish(self._message)
        self.create_timer(5.0, self._republish)
        self.get_logger().info('已向 /robot_description 发布 URDF（RViz RobotModel 可自动加载）')

    def _republish(self):
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
