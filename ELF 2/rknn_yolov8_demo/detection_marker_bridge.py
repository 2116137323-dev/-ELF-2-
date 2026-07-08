"""
ROS2/RViz 检测标注桥接模块。

主程序识别到报警事件后，只需要调用 enqueue_detection_marker()。
本模块会在 ROS2 后台线程中查询机器人当前 map 坐标，发布 RViz 球体点、文字标注、
PoseStamped 定位点，并在报警时触发急停/取消导航。
"""

import queue
import threading
import time

# ROS2 相关依赖只在运行环境具备 ROS2 时可用；普通 Python 环境导入失败时不影响主程序启动。
ROS2_AVAILABLE = False
ROS2_IMPORT_ERROR = None
try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rclpy.time import Time as RosTime
    from geometry_msgs.msg import PoseStamped, Twist
    from std_msgs.msg import Bool
    from visualization_msgs.msg import Marker, MarkerArray
    from tf2_ros import Buffer, TransformListener
    from action_msgs.srv import CancelGoal
    ROS2_AVAILABLE = True
except Exception as ros2_import_exc:
    ROS2_IMPORT_ERROR = ros2_import_exc

# 坐标系与发布话题配置。
ROS2_MAP_FRAME = "map"
ROS2_BASE_FRAME = "base_footprint"
ROS2_DETECTION_MARKER_TOPIC = "/dual_detect_markers"
ROS2_DETECTION_POSE_TOPIC = "/dual_detect_pose"
ROS2_RVIZ_MARKER_TOPIC = "/visualization_marker"
ROS2_RVIZ_MARKER_ARRAY_TOPIC = "/visualization_marker_array"
ROS2_MAX_MARKERS = 100

# 报警停车相关配置：急停话题用于立即停车，Nav2 cancel 服务用于取消当前导航目标。
ROS2_CMD_VEL_TOPIC = "/cmd_vel"
ROS2_ESTOP_TOPIC = "/emergency_stop"
ROS2_NAV_CANCEL_SERVICE = "/navigate_to_pose/_action/cancel_goal"
STOP_NAV_ON_ALARM = True
STOP_CMD_VEL_REPEAT = 10

# 主线程通过该字典拿到 ROS2 节点引用；访问时必须配合 ros_bridge_lock。
ros_bridge_lock = threading.Lock()
ros_bridge = {
    'node': None,
    'executor': None,
    'thread': None,
}


def detection_status_to_label(status):
    """将内部报警状态码转换为中文业务标签。"""
    labels = {
        "dual_detected": "被困人员",
        "camera_detected": "死亡人员",
        "suspect_no_vital": "死亡人员",
        "amputated_limb_with_temperature": "被埋人员",
        "amputated_limb_no_temperature": "残肢",
    }
    return labels.get(status, status.upper())


def detection_status_to_rviz_text(status):
    """将内部报警状态码转换为 RViz 文本；优先使用 ASCII，避免中文字体缺失导致不显示。"""
    labels = {
        "dual_detected": "SURVIVOR",
        "camera_detected": "DECEASED",
        "suspect_no_vital": "DECEASED",
        "amputated_limb_with_temperature": "BURIED",
        "amputated_limb_no_temperature": "LIMB",
    }
    return labels.get(status, status.upper())


if ROS2_AVAILABLE:
    class DetectionMarkerBridge(Node):
        """ROS2 节点：接收检测事件，记录当前机器人位置并发布 RViz 标注。"""

        def __init__(self):
            super().__init__('dual_detect_marker_bridge')

            # Marker 使用 TRANSIENT_LOCAL，RViz 后启动也能收到最近一次标注。
            marker_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            # PoseStamped 只作为实时事件发布，不需要保留历史。
            pose_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.marker_pub = self.create_publisher(
                MarkerArray, ROS2_DETECTION_MARKER_TOPIC, marker_qos
            )
            self.rviz_marker_pub = self.create_publisher(
                Marker, ROS2_RVIZ_MARKER_TOPIC, marker_qos
            )
            self.rviz_marker_array_pub = self.create_publisher(
                MarkerArray, ROS2_RVIZ_MARKER_ARRAY_TOPIC, marker_qos
            )
            self.pose_pub = self.create_publisher(
                PoseStamped, ROS2_DETECTION_POSE_TOPIC, pose_qos
            )
            self.cmd_vel_pub = self.create_publisher(Twist, ROS2_CMD_VEL_TOPIC, 10)

            # 急停信号同样使用 TRANSIENT_LOCAL，让底盘控制节点后加入时也能拿到当前急停状态。
            estop_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self.estop_pub = self.create_publisher(Bool, ROS2_ESTOP_TOPIC, estop_qos)
            self.nav_cancel_client = self.create_client(CancelGoal, ROS2_NAV_CANCEL_SERVICE)

            # TF 用于查询 map -> base_footprint，得到报警发生时机器人的地图坐标。
            self.tf_buffer = Buffer()
            self.tf_listener = TransformListener(self.tf_buffer, self, spin_thread=False)

            # 主业务线程把事件放入队列，ROS2 执行器线程再取出处理，避免跨线程直接操作 ROS 对象。
            self.event_queue = queue.Queue()
            self.marker_lock = threading.Lock()
            self.marker_points = []
            self.next_marker_id = 0
            self.last_tf_warn_time = 0.0
            self._stop_requested = False
            self._stop_cmd_left = 0

            self.create_timer(0.2, self.process_detection_events)
            self.create_timer(1.0, self.publish_marker_array)
            self.create_timer(0.1, self._stop_navigation_tick)
            self.get_logger().info(
                f"识别定位点发布已启动: marker={ROS2_DETECTION_MARKER_TOPIC}, "
                f"pose={ROS2_DETECTION_POSE_TOPIC}, rviz={ROS2_RVIZ_MARKER_TOPIC}"
            )

        def enqueue_detection(self, status, timestamp):
            """接收一次报警事件；需要停车时先发布急停，再排队生成地图标注。"""
            if STOP_NAV_ON_ALARM:
                # 急停 publish 本身线程安全，先发 True 能最快锁定底盘停车。
                self.publish_estop(True)
                self._stop_requested = True
            self.event_queue.put((status, timestamp))

        def publish_estop(self, active):
            """发布/解除急停信号；True 表示急停锁定，False 表示允许恢复运动。"""
            try:
                self.estop_pub.publish(Bool(data=bool(active)))
            except Exception as exc:
                self.get_logger().warning(f"发布急停信号失败: {exc}")

        def _stop_navigation_tick(self):
            """在 ROS2 执行器线程内完成取消导航与重复下发零速。"""
            if self._stop_requested:
                self._stop_requested = False
                self._stop_cmd_left = STOP_CMD_VEL_REPEAT
                self._cancel_navigation()
            if self._stop_cmd_left > 0:
                self.cmd_vel_pub.publish(Twist())
                self._stop_cmd_left -= 1

        def _cancel_navigation(self):
            """调用 Nav2 cancel_goal 服务；空 CancelGoal.Request 表示取消当前所有目标。"""
            try:
                if self.nav_cancel_client.service_is_ready():
                    self.nav_cancel_client.call_async(CancelGoal.Request())
                    self.get_logger().info("报警触发：已请求取消 Nav2 导航目标并停车")
                else:
                    self.get_logger().warning("报警触发：Nav2 取消服务未就绪，已下发零速停车")
            except Exception as exc:
                self.get_logger().warning(f"取消导航目标失败: {exc}")

        def process_detection_events(self):
            """定时取出积压的检测事件，查询 TF 并记录为 RViz 标注点。"""
            updated = False
            while True:
                try:
                    status, timestamp = self.event_queue.get_nowait()
                except queue.Empty:
                    break
                self._record_detection_point(status, timestamp)
                updated = True
            if updated:
                self.publish_marker_array()

        def _record_detection_point(self, status, timestamp):
            """查询当前机器人位姿，发布 PoseStamped，并保存球体/文字 Marker 的历史记录。"""
            try:
                transform = self.tf_buffer.lookup_transform(
                    ROS2_MAP_FRAME, ROS2_BASE_FRAME, RosTime()
                )
            except Exception as exc:
                # TF 可能在 SLAM/Nav2 尚未启动时不可用，警告限频避免刷屏。
                now_sec = time.time()
                if now_sec - self.last_tf_warn_time >= 2.0:
                    self.get_logger().warning(
                        f"无法获取 {ROS2_MAP_FRAME}->{ROS2_BASE_FRAME} 变换，未发布定位点: {exc}"
                    )
                    self.last_tf_warn_time = now_sec
                return

            x = float(transform.transform.translation.x)
            y = float(transform.transform.translation.y)
            z = float(transform.transform.translation.z)
            label = detection_status_to_label(status)
            rviz_text = detection_status_to_rviz_text(status)

            pose = PoseStamped()
            pose.header.frame_id = ROS2_MAP_FRAME
            pose.header.stamp = self.get_clock().now().to_msg()
            pose.pose.position.x = x
            pose.pose.position.y = y
            pose.pose.position.z = z
            pose.pose.orientation = transform.transform.rotation
            self.pose_pub.publish(pose)

            with self.marker_lock:
                self.marker_points.append({
                    'id': self.next_marker_id,
                    'x': x,
                    'y': y,
                    'z': z,
                    'label': label,
                    'rviz_text': rviz_text,
                    'timestamp': timestamp,
                })
                self.next_marker_id += 1
                if len(self.marker_points) > ROS2_MAX_MARKERS:
                    self.marker_points = self.marker_points[-ROS2_MAX_MARKERS:]

            self.get_logger().info(
                f"已记录识别定位点: label={label}, x={x:.3f}, y={y:.3f}, ts={timestamp}"
            )
            self.publish_latest_marker(
                point_id=self.next_marker_id - 1, x=x, y=y, z=z, label=rviz_text
            )

        def build_point_marker(self, point_id, x, y, z):
            """构建红色球体 Marker，表示检测点位置。"""
            marker = Marker()
            marker.header.frame_id = ROS2_MAP_FRAME
            marker.header.stamp = self.get_clock().now().to_msg()
            marker.ns = "dual_detect_points"
            marker.id = int(point_id)
            marker.type = Marker.SPHERE
            marker.action = Marker.ADD
            marker.pose.position.x = x
            marker.pose.position.y = y
            marker.pose.position.z = z + 0.18
            marker.pose.orientation.w = 1.0
            marker.scale.x = 0.18
            marker.scale.y = 0.18
            marker.scale.z = 0.18
            marker.color.a = 1.0
            marker.color.r = 1.0
            marker.color.g = 0.0
            marker.color.b = 0.0
            return marker

        def build_text_marker(self, point_id, x, y, z, label):
            """构建始终面向 RViz 相机的黄色文字 Marker。"""
            text_marker = Marker()
            text_marker.header.frame_id = ROS2_MAP_FRAME
            text_marker.header.stamp = self.get_clock().now().to_msg()
            text_marker.ns = "dual_detect_labels"
            # 文本与球体使用不同 ID 区间，避免同 namespace/type 更新互相覆盖。
            text_marker.id = int(point_id) + 100000
            text_marker.type = Marker.TEXT_VIEW_FACING
            text_marker.action = Marker.ADD
            text_marker.pose.position.x = x
            text_marker.pose.position.y = y
            text_marker.pose.position.z = z + 0.55
            text_marker.pose.orientation.w = 1.0
            text_marker.scale.z = 0.42
            text_marker.color.a = 1.0
            text_marker.color.r = 1.0
            text_marker.color.g = 1.0
            text_marker.color.b = 0.0
            text_marker.text = label
            return text_marker

        def publish_latest_marker(self, point_id, x, y, z, label):
            """立即发布最新点位和文字，降低 RViz 看到报警标注的延迟。"""
            point_marker = self.build_point_marker(point_id, x, y, z)
            text_marker = self.build_text_marker(point_id, x, y, z, label)
            self.rviz_marker_pub.publish(point_marker)
            self.rviz_marker_pub.publish(text_marker)

        def publish_marker_array(self):
            """周期性发布完整历史 MarkerArray，确保 RViz 中标注不会丢失。"""
            with self.marker_lock:
                marker_points = list(self.marker_points)
            if not marker_points:
                return

            marker_array = MarkerArray()
            stamp = self.get_clock().now().to_msg()
            for point in marker_points:
                marker = self.build_point_marker(
                    point_id=point['id'], x=point['x'], y=point['y'], z=point['z']
                )
                marker.header.stamp = stamp
                marker_array.markers.append(marker)

                text_marker = self.build_text_marker(
                    point_id=point['id'],
                    x=point['x'],
                    y=point['y'],
                    z=point['z'],
                    label=point.get('rviz_text', point['label'])
                )
                text_marker.header.stamp = stamp
                marker_array.markers.append(text_marker)

            self.marker_pub.publish(marker_array)
            self.rviz_marker_array_pub.publish(marker_array)


def start_ros2_marker_bridge(is_running):
    """启动 ROS2 后台线程；is_running 回调由主程序提供，用于优雅退出。"""
    if not ROS2_AVAILABLE:
        print(f"ROS2 标注功能不可用，跳过启动: {ROS2_IMPORT_ERROR}")
        return

    def _ros_spin():
        node = None
        executor = None
        try:
            rclpy.init(args=None)
            node = DetectionMarkerBridge()
            executor = SingleThreadedExecutor()
            executor.add_node(node)
            with ros_bridge_lock:
                ros_bridge['node'] = node
                ros_bridge['executor'] = executor

            # spin_once 让线程能周期性检查主程序运行状态，而不是永久阻塞在 spin()。
            while is_running() and rclpy.ok():
                executor.spin_once(timeout_sec=0.2)
        except Exception as exc:
            print(f"ROS2 定位点线程异常: {exc}")
        finally:
            with ros_bridge_lock:
                ros_bridge['node'] = None
                ros_bridge['executor'] = None
            if executor is not None and node is not None:
                try:
                    executor.remove_node(node)
                except Exception:
                    pass
            if node is not None:
                try:
                    node.destroy_node()
                except Exception:
                    pass
            try:
                if rclpy.ok():
                    rclpy.shutdown()
            except Exception:
                pass

    bridge_thread = threading.Thread(target=_ros_spin, daemon=True)
    bridge_thread.start()
    with ros_bridge_lock:
        ros_bridge['thread'] = bridge_thread


def enqueue_detection_marker(status, timestamp):
    """供主程序调用：投递一次识别事件，异步生成地图定位点。"""
    if not ROS2_AVAILABLE:
        return
    with ros_bridge_lock:
        node = ros_bridge.get('node')
    if node is None:
        print("ROS2 定位点节点未就绪，本次识别未生成定位点")
        return
    node.enqueue_detection(status, timestamp)


def publish_emergency_stop(active):
    """供主程序调用：发布或解除急停；ROS2 不可用或节点未就绪时静默跳过。"""
    if not ROS2_AVAILABLE:
        return
    with ros_bridge_lock:
        node = ros_bridge.get('node')
    if node is None:
        return
    node.publish_estop(active)
