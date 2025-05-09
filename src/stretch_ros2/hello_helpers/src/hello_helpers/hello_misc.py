#!/usr/bin/env python3

import time
import os
import sys
import glob
import math

import rclpy
from rclpy.duration import Duration
from rclpy.time import Time
from rclpy.clock import Clock
from rclpy.node import Node
import tf2_ros
# import ros_numpy  TODO(dlu): Fix https://github.com/eric-wieser/ros_numpy/issues/20
import numpy as np
import cv2
import ros2_numpy

import pyquaternion
from statistics import mean

from rclpy.action import ActionClient
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import Transform
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from sensor_msgs.msg import PointCloud2
from std_srvs.srv import Trigger
from std_msgs.msg import String
import threading
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import JointState

#######################
# initial code copied from stackoverflow.com on 10/20/2019
# https://stackoverflow.com/questions/45225474/find-nearest-white-pixel-to-a-given-pixel-location-opencv
def find_nearest_nonzero(img, target):
    nonzero = cv2.findNonZero(img)
    distances = np.sqrt((nonzero[:,:,0] - target[0]) ** 2 + (nonzero[:,:,1] - target[1]) ** 2)
    nearest_index = np.argmin(distances)
    nearest_x, nearest_y = nonzero[nearest_index][0]
    nearest_label = img[nearest_y, nearest_x]
    return nearest_x, nearest_y, nearest_label
#######################


def get_wrist_state(joint_states):
    telescoping_joints = ['joint_arm_l0', 'joint_arm_l1', 'joint_arm_l2', 'joint_arm_l3']
    wrist_velocity = 0.0
    wrist_position = 0.0
    wrist_effort = 0.0
    for joint_name in telescoping_joints:
        i = joint_states.name.index(joint_name)
        wrist_position += joint_states.position[i]
        wrist_velocity += joint_states.velocity[i]
        wrist_effort += joint_states.effort[i]

    wrist_effort = wrist_effort / len(telescoping_joints)
    return [wrist_position, wrist_velocity, wrist_effort]

def get_lift_state(joint_states):
    joint_name = 'joint_lift'
    i = joint_states.name.index(joint_name)
    lift_position = joint_states.position[i]
    lift_velocity = joint_states.velocity[i]
    lift_effort = joint_states.effort[i]
    return [lift_position, lift_velocity, lift_effort]

def get_left_finger_state(joint_states):
    joint_name =  'joint_gripper_finger_left'
    i = joint_states.name.index(joint_name)
    left_finger_position = joint_states.position[i]
    left_finger_velocity = joint_states.velocity[i]
    left_finger_effort = joint_states.effort[i]
    return [left_finger_position, left_finger_velocity, left_finger_effort]

def get_robot_floor_pose_xya(tf2_buffer, floor_frame='odom'):
    # Returns the current estimated x, y position and angle of the
    # robot on the floor. This is typically called with respect to
    # the odom frame or the map frame. x and y are in meters and
    # the angle is in radians.
        
    # Navigation planning is performed with respect to a height of
    # 0.0, so the heights of transformed points are 0.0. The
    # simple method of handling the heights below assumes that the
    # frame is aligned such that the z axis is normal to the
    # floor, so that ignoring the z coordinate is approximately
    # equivalent to projecting a point onto the floor.
        
    # Query TF2 to obtain the current estimated transformation
    # from the robot's base_link frame to the frame.
    robot_to_odom_mat, timestamp = get_p1_to_p2_matrix('base_link', floor_frame, tf2_buffer)
    print('robot_to_odom_mat =', robot_to_odom_mat)
    print('timestamp =', timestamp)

    # Find the robot's current location in the frame.
    r0 = np.array([0.0, 0.0, 0.0, 1.0])
    print('r0 =', r0)
    r0 = np.matmul(robot_to_odom_mat, r0)[:2]

    # Find the current angle of the robot in the frame.
    r1 = np.array([1.0, 0.0, 0.0, 1.0])
    r1 = np.matmul(robot_to_odom_mat, r1)[:2]
    robot_forward = r1 - r0
    r_ang = np.arctan2(robot_forward[1], robot_forward[0])

    return [r0[0], r0[1], r_ang], timestamp

class HelloNode(Node):
    def __init__(self):
        self.joint_state = JointState()
        self.point_cloud = PointCloud2()
        self.tool = String()
        self.mode = String()
        self.dryrun = False

    @classmethod
    def quick_create(cls, name, wait_for_first_pointcloud=False):
        i = cls()
        i.main(name, name, wait_for_first_pointcloud)
        return i
    
    def spin_thread(self, executor):
        executor.spin()

    def joint_states_callback(self, joint_state):
        self.joint_state = joint_state

    def mode_callback(self, mode):
        self.mode = mode

    def point_cloud_callback(self, point_cloud):
        self.point_cloud = point_cloud

    def tool_callback(self, tool_string):
        self.tool = tool_string.data
    
    def get_robot_floor_pose_xya(self, floor_frame='odom'):
        # Returns the current estimated x, y position and angle of the
        # robot on the floor. This is typically called with respect to
        # the odom frame or the map frame. x and y are in meters and
        # the angle is in radians.
        
        # Navigation planning is performed with respect to a height of
        # 0.0, so the heights of transformed points are 0.0. The
        # simple method of handling the heights below assumes that the
        # frame is aligned such that the z axis is normal to the
        # floor, so that ignoring the z coordinate is approximately
        # equivalent to projecting a point onto the floor.
        
        # Query TF2 to obtain the current estimated transformation
        # from the robot's base_link frame to the frame.
        robot_to_odom_mat, timestamp = get_p1_to_p2_matrix('base_link', floor_frame, self.tf2_buffer)
        print('robot_to_odom_mat =', robot_to_odom_mat)
        print('timestamp =', timestamp)

        # Find the robot's current location in the frame.
        r0 = np.array([0.0, 0.0, 0.0, 1.0])
        print('r0 =', r0)
        r0 = np.matmul(robot_to_odom_mat, r0)[:2]

        # Find the current angle of the robot in the frame.
        r1 = np.array([1.0, 0.0, 0.0, 1.0])
        r1 = np.matmul(robot_to_odom_mat, r1)[:2]
        robot_forward = r1 - r0
        r_ang = np.arctan2(robot_forward[1], robot_forward[0])

        return [r0[0], r0[1], r_ang], timestamp
    
    def move_to_pose(self, pose, blocking=True, custom_contact_thresholds=False, duration=2.0):
        if self.dryrun:
            return
        
        if self.mode.data not in ['trajectory', 'position']:
            self.get_logger().warn("Currently in {} mode. Recommend switching either to position or trajectory mode".format(self.mode.data))
            self.get_logger().warn("Commanding joint trajectory server in position mode")
        
        joint_names = [key for key in pose]
        point1 = JointTrajectoryPoint()
        point1.time_from_start = Duration(seconds=0).to_msg()

        trajectory_goal = FollowJointTrajectory.Goal()
        trajectory_goal.goal_time_tolerance = Duration(seconds=1.0).to_msg()
        trajectory_goal.trajectory.joint_names = joint_names

        if self.mode.data == 'trajectory':
            point0 = JointTrajectoryPoint()
            point0.time_from_start = Duration(seconds=0).to_msg()
            
            for joint in joint_names:
                point0.positions.append(self.joint_state.position[self.joint_state.name.index(joint)])

            trajectory_goal.trajectory.points.append(point0)
            point1.time_from_start = Duration(seconds=duration).to_msg()

        if not custom_contact_thresholds: 
            joint_positions = [pose[key] for key in joint_names]
            point1.positions = joint_positions
            trajectory_goal.trajectory.points.append(point1)
        else:
            pose_correct = all([len(pose[key])==2 for key in joint_names])
            if not pose_correct:
                self.get_logger().error("HelloNode.move_to_pose: Not sending trajectory due to improper pose. custom_contact_thresholds requires 2 values (pose_target, contact_threshold_effort) for each joint name, but pose = {0}".format(pose))
                return
            joint_positions = [pose[key][0] for key in joint_names]
            joint_efforts = [pose[key][1] for key in joint_names]
            point1.positions = joint_positions
            point1.effort = joint_efforts
            trajectory_goal.trajectory.points = [point1]
        
        if blocking:
            return self.trajectory_client.send_goal(trajectory_goal)
        else:
            return self.trajectory_client.send_goal_async(trajectory_goal)

    def get_tf(self, from_frame, to_frame):
        """Get current transform between 2 frames. Blocking for 2 secs at worst.
        """
        try:
            return self.tf2_buffer.lookup_transform(from_frame, to_frame, Time(), timeout=Duration(seconds=2.0))
        except:
            self.get_logger().warn("Could not find the transform between frames {} and {}".format(from_frame, to_frame))

    def home_the_robot(self):
        if self.dryrun:
            return

        trigger_request = Trigger.Request()
        trigger_result = self.home_the_robot_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.home_the_robot: got message {trigger_result.done()}")
        return trigger_result.done()

    def stow_the_robot(self):
        if self.dryrun:
            return

        trigger_request = Trigger.Request()
        trigger_result = self.stow_the_robot_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.stow_the_robot: got message {trigger_result.done()}")
        return trigger_result.done()

    def stop_the_robot(self):
        trigger_request = Trigger.Request()
        trigger_result = self.stop_the_robot_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.stop_the_robot: got message {trigger_result.done()}")
        return trigger_result.done()
    
    def switch_to_trajectory_mode(self):
        trigger_request = Trigger.Request()
        trigger_result = self.switch_to_trajectory_mode_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.switch_to_trajectory_mode: got message {trigger_result.done()}")
        return trigger_result.done()
    
    def switch_to_position_mode(self):
        trigger_request = Trigger.Request()
        trigger_result = self.switch_to_position_mode_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.switch_to_position_mode: got message {trigger_result.done()}")
        return trigger_result.done()
    
    def switch_to_navigation_mode(self):
        trigger_request = Trigger.Request()
        trigger_result = self.switch_to_navigation_mode_service.call_async(trigger_request)
        while not trigger_result.done():
            time.sleep(0.2)
        self.get_logger().debug(f"{self.node_name}'s HelloNode.switch_to_navigation_mode: got message {trigger_result.done()}")
        return trigger_result.done()

    # def get_logger(self):
    #     return self.get_logger()
    
    def get_tool(self):
        assert(self.tool is not None)
        return self.tool
    
    def main(self, node_name, node_topic_namespace, wait_for_first_pointcloud=True):
        rclpy.init()
        super().__init__(node_name, allow_undeclared_parameters=True, automatically_declare_parameters_from_overrides=True)
        
        self.node_name = node_name
        self.get_logger().info("{0} started".format(self.node_name))
        
        executor = MultiThreadedExecutor()
        executor.add_node(self)
        
        self.new_thread = threading.Thread(target=self.spin_thread, args=(executor, ), daemon=True)
        self.new_thread.start()

        reentrant_cb = ReentrantCallbackGroup()

        self.trajectory_client = ActionClient(self, FollowJointTrajectory, '/stretch_controller/follow_joint_trajectory', callback_group=reentrant_cb)
        server_reached = self.trajectory_client.wait_for_server(timeout_sec=60.0)
        if not server_reached:
            self.get_logger().error('Unable to connect to arm action server. Timeout exceeded.')
            sys.exit()
        
        self.tf2_buffer = tf2_ros.Buffer()
        self.tf2_listener = tf2_ros.TransformListener(self.tf2_buffer, self)
        
        self.tool_subscriber = self.create_subscription(String, '/tool', self.tool_callback, 10, callback_group=reentrant_cb)

        self.joint_states_subscriber = self.create_subscription(JointState, '/stretch/joint_states', self.joint_states_callback, 10, callback_group=reentrant_cb)
        self.mode_subscriber = self.create_subscription(String, '/mode', self.mode_callback, 10, callback_group=reentrant_cb)
        
        self.point_cloud_subscriber = self.create_subscription(PointCloud2, '/camera/depth/color/points', self.point_cloud_callback, 10, callback_group=reentrant_cb)
        self.point_cloud_pub = self.create_publisher(PointCloud2, '/' + node_topic_namespace + '/point_cloud2', 10, callback_group=reentrant_cb)

        self.home_the_robot_service = self.create_client(Trigger, '/home_the_robot', callback_group=reentrant_cb)
        while not self.home_the_robot_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/home_the_robot' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /home_the_robot service.')

        self.stow_the_robot_service = self.create_client(Trigger, '/stow_the_robot', callback_group=reentrant_cb)
        while not self.stow_the_robot_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/stow_the_robot' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /stow_the_robot service.')
        
        self.stop_the_robot_service = self.create_client(Trigger, '/stop_the_robot', callback_group=reentrant_cb)
        while not self.stop_the_robot_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/stop_the_robot' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /stop_the_robot service.')

        self.switch_to_trajectory_mode_service = self.create_client(Trigger, '/switch_to_trajectory_mode', callback_group=reentrant_cb)
        while not self.switch_to_trajectory_mode_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/switch_to_trajectory_mode' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /switch_to_trajectory_mode service.')

        self.switch_to_position_mode_service = self.create_client(Trigger, '/switch_to_position_mode', callback_group=reentrant_cb)
        while not self.switch_to_position_mode_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/switch_to_position_mode' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /switch_to_position_mode service.')

        self.switch_to_navigation_mode_service = self.create_client(Trigger, '/switch_to_navigation_mode', callback_group=reentrant_cb)
        while not self.switch_to_navigation_mode_service.wait_for_service(timeout_sec=2.0):
            self.get_logger().info("Waiting on '/switch_to_navigation_mode' service...")
        self.get_logger().info('Node ' + self.node_name + ' connected to /switch_to_navigation_mode service.')
        
        if wait_for_first_pointcloud:
            # Do not start until a point cloud has been received
            point_cloud_msg = self.point_cloud
            self.get_logger().info('Node ' + node_name + ' waiting to receive first point cloud.')
            while point_cloud_msg is None:
                time.sleep(0.1)
                point_cloud_msg = self.point_cloud
            self.get_logger().info('Node ' + node_name + ' received first point cloud, so continuing.')


def create_time_string():
    t = time.localtime()
    time_string = str(t.tm_year) + str(t.tm_mon).zfill(2) + str(t.tm_mday).zfill(2) + str(t.tm_hour).zfill(2) + str(t.tm_min).zfill(2) + str(t.tm_sec).zfill(2)
    return time_string


def get_recent_filenames(filename_without_time_suffix, filename_extension, remove_extension=False): 
    filenames = glob.glob(filename_without_time_suffix + '_*[0-9]' + '.' + filename_extension)
    filenames.sort()
    if remove_extension:
        return [os.path.splitext(f)[0] for f in filenames]
    return filenames


def get_most_recent_filename(filename_without_time_suffix, filename_extension, remove_extension=False):
    filenames = get_recent_filenames(filename_without_time_suffix, filename_extension, remove_extension=remove_extension) 
    most_recent_filename = filenames[-1]
    return most_recent_filename


def angle_diff_deg(target_deg, current_deg):
    # I've written this type of function many times before, and it's
    # always been annoying and tricky. This time, I looked on the web:
    # https://stackoverflow.com/questions/1878907/the-smallest-difference-between-2-angles
    diff_deg = target_deg - current_deg
    diff_deg = ((diff_deg + 180.0) % 360.0) - 180.0
    return diff_deg


def angle_diff_rad(target_rad, current_rad):
    # I've written this type of function many times before, and it's
    # always been annoying and tricky. This time, I looked on the web:
    # https://stackoverflow.com/questions/1878907/the-smallest-difference-between-2-angles
    diff_rad = target_rad - current_rad
    diff_rad = ((diff_rad + math.pi) % (2.0 * math.pi)) - math.pi
    return diff_rad


def get_p1_to_p2_matrix(p1_frame_id, p2_frame_id, tf2_buffer, lookup_time=None, timeout_s=None):
    # If the necessary TF2 transform is successfully looked up, this
    # returns a 4x4 affine transformation matrix that transforms
    # points in the p1_frame_id frame to points in the p2_frame_id.
    try:
        if lookup_time is None:
            lookup_time = Time(seconds=0) # return most recent transform
        if timeout_s is None:
            timeout_ros = Duration(seconds=0.1)
        else:
            timeout_ros = Duration(seconds=timeout_s)
        stamped_transform =  tf2_buffer.lookup_transform(p2_frame_id, p1_frame_id, lookup_time, timeout_ros)

        # http://docs.ros.org/melodic/api/geometry_msgs/html/msg/TransformStamped.html

        p1_to_p2_mat = ros2_numpy.numpify(stamped_transform.transform)
        return p1_to_p2_mat, stamped_transform.header.stamp
    except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as e:
        print('WARNING: get_p1_to_p2_matrix failed to lookup transform from p1_frame_id =', p1_frame_id, ' to p2_frame_id =', p2_frame_id)
        print('         exception =', e)
        return None, None

def bound_ros_command(bounds, ros_pos, fail_out_of_range_goal, clip_ros_tolerance=1e-3):
    """Clip the command with clip_ros_tolerance, instead of
    invalidating it, if it is close enough to the valid ranges.
    """
    # Positions of joint limit values in the bounds tuple can be reversed for some joints; addressing them with tuple index 
    # introduces a bug where the left-hand value could be the positive upper bound and the right-hand value could be the negative
    # lower bound. Hence, it is best to compute the min and max values explicitly.
    l_bound = min(bounds) # lower bound
    u_bound = max(bounds) # upper bound

    if ros_pos < l_bound:
        if fail_out_of_range_goal:
            return l_bound if (l_bound - ros_pos) < clip_ros_tolerance else None
        else:
            return l_bound

    if ros_pos > u_bound:
        if fail_out_of_range_goal:
            return u_bound if (ros_pos - u_bound) < clip_ros_tolerance else None
        else:
            return u_bound

    return ros_pos

def to_sec(duration):
    """Given a message of type builtin_interfaces/Duration return the number of seconds as a float."""
    return duration.sec + duration.nanosec / 1e9


def transform_to_triple(transform):
    """Given a message of type geometry_msgs/Transform, return the equivalent x/y/theta triple."""
    x = transform.translation.x
    y = transform.translation.y

    quat = transform.rotation
    q = pyquaternion.Quaternion(x=quat.x, y=quat.y, z=quat.z, w=quat.w)
    yaw, pitch, roll = q.yaw_pitch_roll
    return x, y, yaw


def to_transform(d):
    """Given a dictionary with keys x y and theta, return the equivalent geometry_msgs/Transform."""
    t = Transform()
    t.translation.x = d['x']
    t.translation.y = d['y']
    quaternion = pyquaternion.Quaternion(axis=[0, 0, 1], angle=d['theta'])
    t.rotation.w = quaternion.w
    t.rotation.x = quaternion.x
    t.rotation.y = quaternion.y
    t.rotation.z = quaternion.z
    return t


def twist_to_pair(msg):
    """Given a message of type geometry_msgs/Twist, return the linear and angular components of the velocity."""
    return msg.linear.x, msg.angular.z

def compare_versions(v1, v2):
    """
    Compare two strings of versions.
    Returns 1  if v1>v2
            -1 if v1<v2
            0  if v1==v2
    """
    v1 = [int(v) for v in v1.split('.')]
    v2 = [int(v) for v in v2.split('.')]
    while len(v1) < len(v2):
        v1.append(0)
    while len(v2) < len(v1):
        v2.append(0)
    for i in range(len(v1)):
        if v1[i] < v2[i]:
            return -1
        elif v1[i] > v2[i]:
            return 1
    return 0

# Exceptions for dealing with FollowJointTrajectory
class FollowJointTrajectoryException(RuntimeError):
    """Parent class for all FollowJointTrajectory errors.
    Each subclass should define the CODE based on the constants in FollowJointTrajectory.Result.
    """

    CODE = -100  # Arbitrary constant for unknown error.


class InvalidGoalException(FollowJointTrajectoryException):
    CODE = FollowJointTrajectory.Result.INVALID_GOAL


class InvalidJointException(FollowJointTrajectoryException):
    CODE = FollowJointTrajectory.Result.INVALID_JOINTS


class PathToleranceException(FollowJointTrajectoryException):
    CODE = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED


class GoalToleranceException(FollowJointTrajectoryException):
    CODE = FollowJointTrajectory.Result.GOAL_TOLERANCE_VIOLATED


def merge_arm_joints(trajectory):
    new_trajectory = JointTrajectory()
    arm_indexes = []
    for index, name in enumerate(trajectory.joint_names):
        if 'joint_arm_l' in name:
            arm_indexes.append(index)
        else:
            new_trajectory.joint_names.append(name)

    # If individual arm joints are not present, the original trajectory is fine
    if not arm_indexes:
        return trajectory

    if 'wrist_extension' in trajectory.joint_names:
        raise InvalidJointException('Received a command for the wrist_extension joint and one or more '
                                    'telescoping_joints. These are mutually exclusive options. '
                                    f'The joint names in the received command = {trajectory.joint_names}')

    if len(arm_indexes) != 4:
        raise InvalidJointException('Commands with telescoping joints requires all telescoping joints to be present. '
                                    f'Only received {len(arm_indexes)} of 4 telescoping joints.')

    # Set up points and variables to track arm values
    total_extension = []
    arm_velocities = []
    arm_accelerations = []
    for point in trajectory.points:
        new_point = JointTrajectoryPoint()
        new_point.time_from_start = point.time_from_start
        new_trajectory.points.append(new_point)

        total_extension.append(0.0)
        arm_velocities.append([])
        arm_accelerations.append([])

    for index, name in enumerate(trajectory.joint_names):
        for point_index, point in enumerate(trajectory.points):
            x = point.positions[index]
            v = point.velocities[index] if index < len(point.velocities) else None
            a = point.accelerations[index] if index < len(point.accelerations) else None

            if index in arm_indexes:
                total_extension[point_index] += x
                if v is not None:
                    arm_velocities[point_index].append(v)
                if a is not None:
                    arm_accelerations[point_index].append(a)
            else:
                new_point = new_trajectory.points[point_index]
                new_point.positions.append(x)
                if v is not None:
                    new_point.velocities.append(v)
                if a is not None:
                    new_point.accelerations.append(a)

    # Now add the arm values
    new_trajectory.joint_names.append('wrist_extension')
    for point_index, new_point in enumerate(new_trajectory.points):
        new_point.positions.append(total_extension[point_index])
        vels = arm_velocities[point_index]
        accels = arm_accelerations[point_index]

        if vels:
            new_point.velocities.append(sum(vels) / len(vels))
        if accels:
            new_point.accelerations.append(sum(accels) / len(accels))

    return new_trajectory


def preprocess_gripper_trajectory(trajectory):
    gripper_joint_names = ['joint_gripper_finger_left', 'joint_gripper_finger_right', 'gripper_aperture']
    present_gripper_joints = list(set(gripper_joint_names) & set(trajectory.joint_names))

    # If no gripper joint names are present, no changes needed
    if not present_gripper_joints:
        return trajectory
    elif 'joint_gripper_finger_left' in present_gripper_joints and 'joint_gripper_finger_right' in present_gripper_joints:
        if (gripper_joint_names[0] in present_gripper_joints and gripper_joint_names[1] in present_gripper_joints):
            # Make sure that all the points are the same
            left_index = trajectory.joint_names.index(gripper_joint_names[0])
            right_index = trajectory.joint_names.index(gripper_joint_names[1])
            for pt in trajectory.points:
                if not np.isclose(pt.positions[left_index], pt.positions[right_index], atol=0.1):
                    raise InvalidGoalException('Recieved a command that includes both the left and right gripper '
                                               'joints and their commanded positions are not the same. '
                                               f'{pt.positions[left_index]} != {pt.positions[right_index]}')
                # Due dilligence would also check the velocity/acceleration, but leaving for now

            # If all the points are the same, then we can safely eliminate one
            trajectory.joint_names.pop(right_index)
            for pt in trajectory.points:
                pt.positions.pop(right_index)
                if pt.velocities:
                    pt.velocities.pop(right_index)
                if pt.accelerations:
                    pt.accelerations.pop(right_index)
            gripper_joint_names = ['joint_gripper_finger_left', 'gripper_aperture']
        else:
            raise InvalidJointException('Recieved a command that includes an odd combination of gripper joints: '
                                        f'{present_gripper_joints}')

    present_gripper_joints = list(set(gripper_joint_names) & set(trajectory.joint_names))
    if len(present_gripper_joints) != 1:
        raise InvalidJointException('Recieved a command that includes too many gripper joints: '
                                    f'{present_gripper_joints}')

    gripper_index = trajectory.joint_names.index(present_gripper_joints[0])
    trajectory.joint_names[gripper_index] = 'stretch_gripper'
    return trajectory


class LoopTimer:
    def __init__(self, name="Loop", print_debug = False, print_interval=.5):
        self.name = name
        self.print_interval = print_interval
        self.start_time = time.time()
        self.last_print_time = self.start_time
        self.iterations = 0
        self.print_debug = print_debug
        self.last_update_time = self.start_time
    
    def reset(self):
        self.iterations = 0
        self.start_time = time.time()

    def update(self):
        self.iterations += 1
        current_time = time.time()
        self.last_update_time = current_time
        elapsed_time = current_time - self.last_print_time
        total_elapsed_time = current_time - self.start_time
        avg_rate = self.iterations / total_elapsed_time
        if elapsed_time >= self.print_interval:
            if self.print_debug:
                print("-"*20)
                print(f"{self.name} \n"
                    f"Iteration: {self.iterations}\n"
                    f"Elapsed Time: {total_elapsed_time:.2f}s\n"
                    f"Average Rate: {avg_rate:.2f} Hz")
                print("-"*20)
            self.last_print_time = current_time