#!/usr/bin/env python3

import math
import threading
import time
from pathlib import Path

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from stretch_nav2.robot_navigator import BasicNavigator, TaskResult
from trajectory_msgs.msg import JointTrajectoryPoint


def yaw_to_quaternion(yaw):
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class WaypointMissionController(Node):
    def __init__(self):
        super().__init__('waypoint_mission')

        self.declare_parameter('mission_file', '')
        self.declare_parameter('dry_run', False)
        self.declare_parameter('autostart', False)
        self.declare_parameter('autostart_delay_sec', 0.0)
        self.declare_parameter('inorbit_start_command', 'mission:start')
        self.declare_parameter('inorbit_cancel_command', 'mission:cancel')
        self.declare_parameter('publish_inorbit_status', True)

        self.mission_file = self.get_parameter('mission_file').value
        self.dry_run = bool(self.get_parameter('dry_run').value)
        self.autostart = bool(self.get_parameter('autostart').value)
        self.autostart_delay_sec = float(self.get_parameter('autostart_delay_sec').value)
        self.inorbit_start_command = self.get_parameter('inorbit_start_command').value
        self.inorbit_cancel_command = self.get_parameter('inorbit_cancel_command').value
        self.publish_inorbit_status_enabled = bool(
            self.get_parameter('publish_inorbit_status').value
        )

        self.navigator = BasicNavigator()
        self.arm_client = ActionClient(
            self,
            FollowJointTrajectory,
            '/stretch_controller/follow_joint_trajectory',
        )
        self.switch_to_navigation_client = self.create_client(
            Trigger, '/switch_to_navigation_mode'
        )
        self.switch_to_trajectory_client = self.create_client(
            Trigger, '/switch_to_trajectory_mode'
        )

        self.joint_state = None
        self.joint_state_lock = threading.Lock()
        self.cancel_requested = False
        self.mission_running = False
        self.mission_lock = threading.Lock()
        self.autostart_timer = None

        self.status_pub = self.create_publisher(String, 'status', 10)
        self.active_pub = self.create_publisher(Bool, 'active', 10)
        self.inorbit_status_pub = self.create_publisher(
            String, '/inorbit/custom_data/0', 10
        )
        self.start_sub = self.create_subscription(Bool, 'start', self.start_callback, 10)
        self.inorbit_command_sub = self.create_subscription(
            String,
            '/inorbit/custom_commands',
            self.inorbit_command_callback,
            10,
        )
        self.trigger_service = self.create_service(
            Trigger, 'trigger', self.trigger_callback
        )
        self.cancel_service = self.create_service(
            Trigger, 'cancel', self.cancel_callback
        )
        self.joint_states_sub = self.create_subscription(
            JointState,
            '/stretch/joint_states',
            self.joint_states_callback,
            10,
        )

        self.wait_for_client(self.arm_client, 'trajectory action server')
        self.wait_for_service(self.switch_to_navigation_client, '/switch_to_navigation_mode')
        self.wait_for_service(self.switch_to_trajectory_client, '/switch_to_trajectory_mode')

        self.mission = self.load_mission(self.mission_file)
        self.publish_active(False)
        self.publish_status(
            f"Mission loaded from {self.mission_file} with "
            f"{len(self.mission['waypoints'])} waypoints."
        )

        if self.autostart:
            self.autostart_timer = self.create_timer(
                self.autostart_delay_sec, self.autostart_once
            )

    def destroy_node(self):
        self.navigator.destroy_node()
        super().destroy_node()

    def wait_for_client(self, client, description):
        while not client.wait_for_server(timeout_sec=2.0):
            self.get_logger().info(f'Waiting for {description}...')

    def wait_for_service(self, client, service_name):
        while not client.wait_for_service(timeout_sec=2.0):
            self.get_logger().info(f'Waiting for {service_name}...')

    def wait_for_future(self, future, description):
        while rclpy.ok() and not future.done():
            time.sleep(0.05)
        result = future.result()
        if result is None:
            raise RuntimeError(f'No result returned for {description}.')
        return result

    def load_mission(self, mission_file):
        mission_path = Path(mission_file)
        if not mission_path.is_file():
            raise FileNotFoundError(f'Mission file not found: {mission_file}')

        with mission_path.open('r', encoding='utf-8') as stream:
            mission = yaml.safe_load(stream) or {}

        waypoints = mission.get('waypoints', [])
        if len(waypoints) < 3:
            self.get_logger().warn(
                'Mission contains fewer than 3 waypoints. '
                'The route is still valid, but update the config if you need 3+ stops.'
            )
        return mission

    def joint_states_callback(self, joint_state):
        with self.joint_state_lock:
            self.joint_state = joint_state

    def start_callback(self, msg):
        if msg.data:
            started, message = self.start_mission()
            self.get_logger().info(message if started else f'Start ignored: {message}')

    def inorbit_command_callback(self, msg):
        command = msg.data.strip()
        if command == self.inorbit_start_command:
            started, message = self.start_mission()
            self.get_logger().info(
                f'InOrbit start command processed: {message}'
                if started
                else f'InOrbit start command ignored: {message}'
            )
        elif command == self.inorbit_cancel_command:
            with self.mission_lock:
                if not self.mission_running:
                    self.get_logger().info('InOrbit cancel command ignored: mission is not running.')
                    return
                self.cancel_requested = True
            self.navigator.cancelTask()
            self.publish_status('Mission cancel requested from InOrbit command.')

    def trigger_callback(self, request, response):
        del request
        started, message = self.start_mission()
        response.success = started
        response.message = message
        return response

    def cancel_callback(self, request, response):
        del request
        with self.mission_lock:
            if not self.mission_running:
                response.success = False
                response.message = 'Mission is not running.'
                return response
            self.cancel_requested = True

        self.navigator.cancelTask()
        self.publish_status('Mission cancel requested.')
        response.success = True
        response.message = 'Mission cancel requested.'
        return response

    def autostart_once(self):
        self.autostart = False
        if self.autostart_timer is not None:
            self.autostart_timer.cancel()
        started, message = self.start_mission()
        self.get_logger().info(message if started else f'Autostart skipped: {message}')

    def start_mission(self):
        with self.mission_lock:
            if self.mission_running:
                return False, 'Mission is already running.'
            self.mission_running = True
            self.cancel_requested = False

        worker = threading.Thread(target=self.run_mission, daemon=True)
        worker.start()
        return True, 'Mission started.'

    def run_mission(self):
        try:
            self.publish_active(True)
            self.publish_status('Waiting for Nav2 to become active.')
            self.publish_inorbit_kv('mission=waypoint_mission')
            self.publish_inorbit_kv('mission-state=starting')
            if not self.dry_run:
                self.navigator.waitUntilNav2Active()

            for index, waypoint in enumerate(self.mission['waypoints'], start=1):
                self.raise_if_cancel_requested()

                waypoint_name = waypoint.get('name', f'waypoint_{index}')
                goal = self.make_pose(waypoint['pose'])

                self.switch_mode(self.switch_to_navigation_client, 'navigation')
                self.publish_status(f'Navigating to {waypoint_name}.')
                self.publish_inorbit_kv(f'mission-target={waypoint_name}')
                self.publish_inorbit_kv('mission-state=navigating')

                if self.dry_run:
                    self.get_logger().info(
                        f"[dry_run] Would navigate to {waypoint_name}: {waypoint['pose']}"
                    )
                else:
                    if not self.navigator.goToPose(goal):
                        raise RuntimeError(f'Navigation goal rejected for {waypoint_name}.')
                    self.wait_for_navigation_result(waypoint_name)

                actions = waypoint.get('actions', [])
                if actions:
                    self.switch_mode(self.switch_to_trajectory_client, 'trajectory')
                    for action in actions:
                        self.raise_if_cancel_requested()
                        self.execute_action(waypoint_name, action)

            self.publish_status('Mission completed successfully.')
            self.publish_inorbit_kv('mission-state=completed')
        except Exception as exc:
            self.get_logger().error(f'Mission failed: {exc}')
            self.publish_status(f'Mission failed: {exc}')
            failed_state = 'canceled' if self.cancel_requested else 'failed'
            self.publish_inorbit_kv(f'mission-state={failed_state}')
        finally:
            self.publish_active(False)
            self.publish_inorbit_kv('mission=idle')
            with self.mission_lock:
                self.mission_running = False

    def raise_if_cancel_requested(self):
        if self.cancel_requested:
            raise RuntimeError('Mission canceled.')

    def wait_for_navigation_result(self, waypoint_name):
        while not self.navigator.isTaskComplete():
            self.raise_if_cancel_requested()
            feedback = self.navigator.getFeedback()
            if feedback is not None:
                self.get_logger().debug(f'Navigation feedback received for {waypoint_name}.')
            time.sleep(0.1)

        result = self.navigator.getResult()
        if result != TaskResult.SUCCEEDED:
            raise RuntimeError(f'Navigation to {waypoint_name} ended with result {result}.')

    def execute_action(self, waypoint_name, action):
        joints = action.get('joints', {})
        duration = float(action.get('duration', 3.0))
        wait_sec = float(action.get('wait_sec', 0.0))
        action_name = action.get('name', 'unnamed_action')

        if not joints:
            raise ValueError(f'Action {action_name} in {waypoint_name} is missing joints.')

        self.publish_status(f'Executing {action_name} at {waypoint_name}.')
        self.publish_inorbit_kv(f'mission-action={action_name}')
        self.publish_inorbit_kv('mission-state=acting')
        if self.dry_run:
            self.get_logger().info(
                f"[dry_run] Would execute {action_name} with joints={joints}"
            )
        else:
            self.send_joint_goal(joints, duration)

        if wait_sec > 0.0:
            time.sleep(wait_sec)

    def send_joint_goal(self, joints, duration):
        with self.joint_state_lock:
            joint_state = self.joint_state

        if joint_state is None:
            raise RuntimeError('No joint state received yet.')

        joint_names = list(joints.keys())
        goal = FollowJointTrajectory.Goal()
        goal.goal_time_tolerance = Duration(seconds=1.0).to_msg()
        goal.trajectory.joint_names = joint_names

        point0 = JointTrajectoryPoint()
        point0.time_from_start = Duration(seconds=0.0).to_msg()
        point1 = JointTrajectoryPoint()
        point1.time_from_start = Duration(seconds=duration).to_msg()

        for joint_name in joint_names:
            try:
                joint_index = joint_state.name.index(joint_name)
            except ValueError as exc:
                raise RuntimeError(f'Joint {joint_name} not found in joint state.') from exc
            point0.positions.append(joint_state.position[joint_index])
            point1.positions.append(float(joints[joint_name]))

        goal.trajectory.points = [point0, point1]

        send_goal_future = self.arm_client.send_goal_async(goal)
        goal_handle = self.wait_for_future(send_goal_future, 'trajectory goal submission')
        if goal_handle is None or not goal_handle.accepted:
            raise RuntimeError('Trajectory goal was rejected.')

        result_future = goal_handle.get_result_async()
        result = self.wait_for_future(result_future, 'trajectory goal result')
        if result is None or result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f'Trajectory action failed with status {result.status if result else "unknown"}.')

    def switch_mode(self, client, mode_name):
        if self.dry_run:
            self.get_logger().info(f'[dry_run] Would switch to {mode_name} mode.')
            return

        future = client.call_async(Trigger.Request())
        response = self.wait_for_future(future, f'{mode_name} mode switch')
        if response is None or not response.success:
            raise RuntimeError(
                f'Failed to switch to {mode_name} mode: '
                f'{response.message if response else "no response"}'
            )

    def make_pose(self, pose_data):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()
        pose.pose.position.x = float(pose_data['x'])
        pose.pose.position.y = float(pose_data['y'])
        pose.pose.position.z = 0.0
        qx, qy, qz, qw = yaw_to_quaternion(float(pose_data.get('yaw', 0.0)))
        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        pose.pose.orientation.w = qw
        return pose

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def publish_active(self, is_active):
        msg = Bool()
        msg.data = is_active
        self.active_pub.publish(msg)

    def publish_inorbit_kv(self, text):
        if not self.publish_inorbit_status_enabled:
            return
        msg = String()
        msg.data = text
        self.inorbit_status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = WaypointMissionController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
