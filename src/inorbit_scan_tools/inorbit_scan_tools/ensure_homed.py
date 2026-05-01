#!/usr/bin/env python3

import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class EnsureHomed(Node):
    def __init__(self):
        super().__init__('ensure_homed')

        self.declare_parameter('auto_home', True)
        self.declare_parameter('startup_delay_sec', 2.0)
        self.declare_parameter('wait_for_homed_timeout_sec', 90.0)
        self.declare_parameter('exit_after_homing', True)

        self.auto_home = bool(self.get_parameter('auto_home').value)
        self.startup_delay_sec = float(self.get_parameter('startup_delay_sec').value)
        self.wait_for_homed_timeout_sec = float(
            self.get_parameter('wait_for_homed_timeout_sec').value
        )
        self.exit_after_homing = bool(self.get_parameter('exit_after_homing').value)

        self._homed = None
        self._homed_event = threading.Event()

        self.create_subscription(Bool, '/is_homed', self.is_homed_callback, 10)
        self.home_client = self.create_client(Trigger, '/home_the_robot')

        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def is_homed_callback(self, msg):
        self._homed = bool(msg.data)
        self._homed_event.set()

    def wait_for_service(self, client, service_name):
        while rclpy.ok() and not client.wait_for_service(timeout_sec=2.0):
            self.get_logger().info(f'Waiting for {service_name}...')

    def wait_for_first_homed_message(self):
        while rclpy.ok() and not self._homed_event.wait(timeout=0.5):
            self.get_logger().info('Waiting for /is_homed...')

    def wait_until_homed(self, timeout_sec):
        deadline = time.time() + timeout_sec
        while rclpy.ok() and time.time() < deadline:
            if self._homed is True:
                return True
            time.sleep(0.2)
        return self._homed is True

    def run(self):
        if self.startup_delay_sec > 0.0:
            time.sleep(self.startup_delay_sec)

        self.wait_for_first_homed_message()
        if not rclpy.ok():
            return

        if self._homed:
            self.get_logger().info('Robot is already homed.')
            return

        if not self.auto_home:
            self.get_logger().warn('Robot is not homed and auto_home is disabled.')
            return

        self.wait_for_service(self.home_client, '/home_the_robot')
        if not rclpy.ok():
            return

        self.get_logger().info('Robot is not homed. Calling /home_the_robot.')
        future = self.home_client.call_async(Trigger.Request())
        while rclpy.ok() and not future.done():
            time.sleep(0.1)

        response = future.result()
        if response is None or not response.success:
            message = response.message if response else 'no response'
            self.get_logger().error(f'Failed to home robot: {message}')
            return

        self.get_logger().info('Homing requested successfully. Waiting for /is_homed == true.')
        if self.wait_until_homed(self.wait_for_homed_timeout_sec):
            self.get_logger().info('Robot homing complete.')
        else:
            self.get_logger().warn(
                'Timed out waiting for robot to report /is_homed == true.'
            )


def main(args=None):
    rclpy.init(args=args)
    node = EnsureHomed()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
