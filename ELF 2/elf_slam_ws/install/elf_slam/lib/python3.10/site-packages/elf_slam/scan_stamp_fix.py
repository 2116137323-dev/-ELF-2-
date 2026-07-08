import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.duration import Duration
from sensor_msgs.msg import LaserScan


class ScanStampFix(Node):
    def __init__(self):
        super().__init__('scan_stamp_fix')

        self.declare_parameter('input_topic', '/scan')
        self.declare_parameter('output_topic', '/scan_fixed')
        self.declare_parameter('max_age_sec', 0.5)
        self.declare_parameter('future_tolerance_sec', 0.02)
        self.declare_parameter('output_time_offset_sec', 0.0)
        self.declare_parameter('fix_beam_count', True)
        self.declare_parameter('target_beams', 451)

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        self.max_age_sec = float(self.get_parameter('max_age_sec').value)
        self.future_tolerance_sec = float(self.get_parameter('future_tolerance_sec').value)
        self.output_time_offset_ns = int(float(self.get_parameter('output_time_offset_sec').value) * 1e9)
        self.fix_beam_count = bool(self.get_parameter('fix_beam_count').value)
        self.target_beams = int(self.get_parameter('target_beams').value)

        self.publisher = self.create_publisher(
            LaserScan, self.output_topic, qos_profile_sensor_data
        )
        self.subscription = self.create_subscription(
            LaserScan,
            self.input_topic,
            self.on_scan,
            qos_profile_sensor_data,
        )

    def _resample(self, src: LaserScan, target_beams: int) -> LaserScan:
        if target_beams <= 0:
            return src

        src_ranges = list(src.ranges)
        src_intensities = list(src.intensities)
        src_n = len(src_ranges)
        if src_n == 0 or src.angle_increment == 0.0:
            return src

        if src_n == target_beams:
            dst = LaserScan()
            dst.header = src.header
            dst.time_increment = src.time_increment
            dst.scan_time = src.scan_time
            dst.range_min = src.range_min
            dst.range_max = src.range_max
            dst.angle_min = src.angle_min
            dst.ranges = src_ranges
            dst.intensities = src_intensities
            dst.angle_increment = (
                (src.angle_max - src.angle_min) / float(target_beams - 1)
                if target_beams > 1
                else 0.0
            )
            dst.angle_max = dst.angle_min + dst.angle_increment * float(target_beams - 1)
            return dst

        dst = LaserScan()
        dst.header = src.header
        dst.time_increment = src.time_increment
        dst.scan_time = src.scan_time
        dst.range_min = src.range_min
        dst.range_max = src.range_max
        dst.angle_min = src.angle_min
        dst.angle_increment = (
            (src.angle_max - src.angle_min) / float(target_beams - 1)
            if target_beams > 1
            else 0.0
        )
        dst.angle_max = dst.angle_min + dst.angle_increment * float(target_beams - 1)

        dst_ranges = []
        has_intensity = len(src_intensities) == src_n
        dst_intensities = [] if has_intensity else []

        for i in range(target_beams):
            angle = dst.angle_min + dst.angle_increment * float(i)
            src_f = (angle - src.angle_min) / src.angle_increment

            if src_f <= 0.0:
                idx0 = 0
                idx1 = 0
                t = 0.0
            elif src_f >= float(src_n - 1):
                idx0 = src_n - 1
                idx1 = src_n - 1
                t = 0.0
            else:
                idx0 = int(src_f)
                idx1 = idx0 + 1
                t = src_f - float(idx0)

            r0 = src_ranges[idx0]
            r1 = src_ranges[idx1]
            if r0 != r0 and r1 != r1:
                r = float('nan')
            elif r0 != r0:
                r = r1
            elif r1 != r1:
                r = r0
            elif r0 == float('inf') or r1 == float('inf'):
                r = float('inf')
            else:
                r = (1.0 - t) * float(r0) + t * float(r1)

            dst_ranges.append(r)

            if has_intensity:
                i0 = src_intensities[idx0]
                i1 = src_intensities[idx1]
                if i0 != i0 and i1 != i1:
                    iv = float('nan')
                elif i0 != i0:
                    iv = i1
                elif i1 != i1:
                    iv = i0
                else:
                    iv = (1.0 - t) * float(i0) + t * float(i1)
                dst_intensities.append(iv)

        dst.ranges = dst_ranges
        if has_intensity:
            dst.intensities = dst_intensities

        return dst

    def _fix_angle_consistency(self, msg: LaserScan) -> LaserScan:
        beam_count = len(msg.ranges)
        if beam_count <= 1:
            return msg

        dst = LaserScan()
        dst.header = msg.header
        dst.time_increment = msg.time_increment
        dst.scan_time = msg.scan_time
        dst.range_min = msg.range_min
        dst.range_max = msg.range_max
        dst.angle_min = msg.angle_min
        dst.ranges = msg.ranges
        dst.intensities = msg.intensities
        span = msg.angle_max - msg.angle_min
        if abs(span) < 1e-9 and msg.angle_increment != 0.0:
            span = msg.angle_increment * float(beam_count - 1)
        dst.angle_increment = span / float(beam_count - 1)
        dst.angle_max = dst.angle_min + dst.angle_increment * float(beam_count - 1)
        return dst

    def on_scan(self, msg: LaserScan):
        now = self.get_clock().now()
        stamp = rclpy.time.Time.from_msg(msg.header.stamp)
        age = (now - stamp).nanoseconds / 1e9

        if msg.header.stamp.sec == 0 and msg.header.stamp.nanosec == 0:
            stamp = now
        elif age > self.max_age_sec:
            stamp = now
        elif age < -self.future_tolerance_sec:
            stamp = now

        if self.fix_beam_count and len(msg.ranges) != self.target_beams:
            msg = self._resample(msg, self.target_beams)

        msg = self._fix_angle_consistency(msg)

        if self.output_time_offset_ns < 0:
            if stamp > now:
                stamp = stamp + Duration(nanoseconds=self.output_time_offset_ns)

        if (now - stamp).nanoseconds / 1e9 > self.max_age_sec:
            stamp = now

        if stamp > now:
            ahead_sec = (stamp - now).nanoseconds / 1e9
            if ahead_sec <= self.future_tolerance_sec:
                stamp = now

        msg.header.stamp = stamp.to_msg()

        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ScanStampFix()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
