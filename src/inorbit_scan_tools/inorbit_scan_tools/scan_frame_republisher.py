#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class ScanFrameRepublisher(Node):
    def __init__(self):
        super().__init__('scan_frame_republisher')

        self.declare_parameter('input_topic', '/scan')
        self.declare_parameter('output_topic', '/scan_inorbit')
        self.declare_parameter('output_frame', 'laser_forward')

        input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.output_frame = self.get_parameter('output_frame').get_parameter_value().string_value

        self.publisher = self.create_publisher(LaserScan, output_topic, 10)
        self.subscription = self.create_subscription(
            LaserScan,
            input_topic,
            self.scan_callback,
            10,
        )

        self.get_logger().info(
            f"Republishing {input_topic} -> {output_topic} with frame_id='{self.output_frame}'"
        )

    def scan_callback(self, msg: LaserScan) -> None:
        n = len(msg.ranges)
        if n == 0:
            return

        shift = int(round(math.pi / msg.angle_increment)) % n

        out = LaserScan()
        out.header = msg.header
        out.header.frame_id = self.output_frame

        out.angle_min = msg.angle_min
        out.angle_max = msg.angle_max
        out.angle_increment = msg.angle_increment
        out.time_increment = msg.time_increment
        out.scan_time = msg.scan_time
        out.range_min = msg.range_min
        out.range_max = msg.range_max

        ranges = list(msg.ranges)
        out.ranges = ranges[shift:] + ranges[:shift]

        intensities = list(msg.intensities)
        out.intensities = intensities[shift:] + intensities[:shift] if intensities else []

        self.publisher.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = ScanFrameRepublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()