#!/usr/bin/env python3

import math
import threading
import time
from pathlib import Path

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from hello_helpers.joint_qpos_conversion import JointStateMapping, get_Idx
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger


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
        self.declare_parameter('inorbit_status_topic', '/inorbit/custom_data_0')

        self.mission_file = self.get_parameter('mission_file').value
        self.dry_run = bool(self.get_parameter('dry_run').value)
        self.autostart = bool(self.get_parameter('autostart').value)
        self.autostart_delay_sec = float(self.get_parameter('autostart_delay_sec').value)
        self.inorbit_start_command = self.get_parameter('inorbit_start_command').value
        self.inorbit_cancel_command = self.get_parameter('inorbit_cancel_command').value
        self.publish_inorbit_status_enabled = bool(
            self.get_parameter('publish_inorbit_status').value
        )
        self.inorbit_status_topic = self.get_parameter('inorbit_status_topic').value

        self.nav_to_pose_client = ActionClient(
            self,
            NavigateToPose,
            'navigate_to_pose',
        )
        self.switch_to_navigation_client = self.create_client(
            Trigger, '/switch_to_navigation_mode'
        )
        self.switch_to_position_client = self.create_client(
            Trigger, '/switch_to_position_mode'
        )
        self.activate_streaming_position_client = self.create_client(
            Trigger, '/activate_streaming_position'
        )
        self.deactivate_streaming_position_client = self.create_client(
            Trigger, '/deactivate_streaming_position'
        )
        self.amcl_state_client = self.create_client(GetState, 'amcl/get_state')
        self.bt_navigator_state_client = self.create_client(
            GetState, 'bt_navigator/get_state'
        )
        self.joint_pose_pub = self.create_publisher(Float64MultiArray, '/joint_pose_cmd', 10)
        self.idx = get_Idx('tool_stretch_gripper')

        self.joint_state = None
        self.joint_state_lock = threading.Lock()
        self.cancel_requested = False
        self.mission_running = False
        self.mission_lock = threading.Lock()
        self.autostart_timer = None
        self.nav_goal_handle = None
        self.nav_result_future = None

        self.status_pub = self.create_publisher(String, 'status', 10)
        self.active_pub = self.create_publisher(Bool, 'active', 10)
        self.inorbit_status_pub = None
        if self.publish_inorbit_status_enabled and self.inorbit_status_topic:
            self.inorbit_status_pub = self.create_publisher(
                String, self.inorbit_status_topic, 10
            )
        self.start_sub = self.create_subscription(Bool, 'start', self.start_callback, 10)
        self.inorbit_command_sub = self.create_subscription(
            String,
            '/inorbit/custom_command',
            self.inorbit_command_callback,
            10,
        )
        self.inorbit_commands_sub = self.create_subscription(
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

        self.wait_for_client(self.nav_to_pose_client, 'navigate_to_pose action server')
        self.wait_for_service(self.switch_to_navigation_client, '/switch_to_navigation_mode')
        self.wait_for_service(self.switch_to_position_client, '/switch_to_position_mode')
        self.wait_for_service(
            self.activate_streaming_position_client, '/activate_streaming_position'
        )
        self.wait_for_service(
            self.deactivate_streaming_position_client, '/deactivate_streaming_position'
        )
        self.wait_for_service(self.amcl_state_client, 'amcl/get_state')
        self.wait_for_service(self.bt_navigator_state_client, 'bt_navigator/get_state')

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

    def wait_for_node_active(self, client, node_name):
        req = GetState.Request()
        state = 'unknown'
        while state != 'active':
            future = client.call_async(req)
            response = self.wait_for_future(future, f'{node_name} state')
            state = response.current_state.label
            if state != 'active':
                self.get_logger().info(f'Waiting for {node_name} to become active...')
                time.sleep(1.0)

    def wait_for_nav2_active(self):
        self.wait_for_node_active(self.amcl_state_client, 'amcl')
        self.wait_for_node_active(self.bt_navigator_state_client, 'bt_navigator')
        self.get_logger().info('Nav2 is ready for use!')

    def cancel_navigation_task(self):
        if self.nav_goal_handle is None:
            return
        future = self.nav_goal_handle.cancel_goal_async()
        self.wait_for_future(future, 'navigation cancel')

    def start_navigation(self, pose):
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = pose
        send_goal_future = self.nav_to_pose_client.send_goal_async(goal_msg)
        self.nav_goal_handle = self.wait_for_future(
            send_goal_future, 'navigation goal submission'
        )
        if self.nav_goal_handle is None or not self.nav_goal_handle.accepted:
            raise RuntimeError('Navigation goal was rejected.')
        self.nav_result_future = self.nav_goal_handle.get_result_async()

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
            self.cancel_navigation_task()
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

        self.cancel_navigation_task()
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
                self.wait_for_nav2_active()

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
                    self.start_navigation(goal)
                    self.wait_for_navigation_result(waypoint_name)

                actions = waypoint.get('actions', [])
                if actions:
                    self.switch_mode(self.switch_to_position_client, 'position')
                    self.set_streaming_position(True)
                    try:
                        for action in actions:
                            self.raise_if_cancel_requested()
                            self.execute_action(waypoint_name, action)
                    finally:
                        self.set_streaming_position(False)

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
        while self.nav_result_future is not None and not self.nav_result_future.done():
            self.raise_if_cancel_requested()
            time.sleep(0.1)

        if self.nav_result_future is None:
            raise RuntimeError(f'Navigation to {waypoint_name} did not start correctly.')

        result = self.wait_for_future(self.nav_result_future, 'navigation result')
        self.nav_result_future = None
        self.nav_goal_handle = None
        if result.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(
                f'Navigation to {waypoint_name} ended with status {result.status}.'
            )

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
            self.send_streaming_pose(joints, duration)

        if wait_sec > 0.0:
            time.sleep(wait_sec)

    def set_streaming_position(self, enabled):
        if self.dry_run:
            self.get_logger().info(
                f"[dry_run] Would {'activate' if enabled else 'deactivate'} streaming position."
            )
            return

        client = (
            self.activate_streaming_position_client
            if enabled
            else self.deactivate_streaming_position_client
        )
        action_name = 'activate' if enabled else 'deactivate'
        future = client.call_async(Trigger.Request())
        response = self.wait_for_future(future, f'{action_name} streaming position')
        if response is None or not response.success:
            raise RuntimeError(
                f'Failed to {action_name} streaming position: '
                f'{response.message if response else "no response"}'
            )

    def get_joint_positions(self):
        with self.joint_state_lock:
            joint_state = self.joint_state

        if joint_state is None:
            raise RuntimeError('No joint state received yet.')

        return {
            name: position
            for name, position in zip(joint_state.name, joint_state.position)
        }

    def make_qpos_from_joints(self, joints):
        current = self.get_joint_positions()
        qpos = [0.0] * self.idx.num_joints
        qpos[self.idx.ARM] = current.get(
            'wrist_extension',
            sum(current.get(joint, 0.0) for joint in JointStateMapping.ROS_ARM_JOINTS),
        )
        qpos[self.idx.LIFT] = current.get('joint_lift', 0.0)
        qpos[self.idx.WRIST_YAW] = current.get('joint_wrist_yaw', 0.0)
        qpos[self.idx.GRIPPER] = current.get('joint_gripper_finger_left', 0.0)
        qpos[self.idx.HEAD_PAN] = current.get('joint_head_pan', 0.0)
        qpos[self.idx.HEAD_TILT] = current.get('joint_head_tilt', 0.0)
        qpos[self.idx.BASE_TRANSLATE] = 0.0
        qpos[self.idx.BASE_ROTATE] = 0.0

        joint_to_idx = {
            'wrist_extension': self.idx.ARM,
            'joint_lift': self.idx.LIFT,
            'joint_wrist_yaw': self.idx.WRIST_YAW,
            'joint_gripper_finger_left': self.idx.GRIPPER,
            'joint_head_pan': self.idx.HEAD_PAN,
            'joint_head_tilt': self.idx.HEAD_TILT,
        }

        for joint_name, value in joints.items():
            if joint_name not in joint_to_idx:
                raise RuntimeError(f'Unsupported streaming joint: {joint_name}')
            qpos[joint_to_idx[joint_name]] = float(value)

        return qpos

    def wait_for_joint_targets(self, joints, timeout_sec):
        deadline = time.time() + timeout_sec
        tolerance = 0.03
        while time.time() < deadline:
            self.raise_if_cancel_requested()
            current = self.get_joint_positions()
            if all(
                abs(current.get(joint_name, 0.0) - float(target)) <= tolerance
                for joint_name, target in joints.items()
            ):
                return
            time.sleep(0.1)
        self.get_logger().warn('Timed out waiting for joint targets; continuing.')

    def send_streaming_pose(self, joints, duration):
        qpos = self.make_qpos_from_joints(joints)
        msg = Float64MultiArray()
        msg.data = qpos
        self.joint_pose_pub.publish(msg)
        self.wait_for_joint_targets(joints, duration + 2.0)

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
        pose.header.stamp = self.get_clock().now().to_msg()
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
        if not self.publish_inorbit_status_enabled or self.inorbit_status_pub is None:
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
