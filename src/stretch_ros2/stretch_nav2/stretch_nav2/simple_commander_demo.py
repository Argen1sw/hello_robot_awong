#! /usr/bin/env python3

# Adapted from the simple commander demo examples on 
# https://github.com/ros-planning/navigation2/blob/galactic/nav2_simple_commander/nav2_simple_commander/demo_security.py

from copy import deepcopy

from geometry_msgs.msg import PoseStamped
from stretch_nav2.robot_navigator import BasicNavigator, TaskResult
import hello_helpers.hello_misc as hm

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration


"""
Basic security route patrol demo. In this demonstration, we use the D435i camera
mounted on the robot to relay the camera feed back to us that can be monitored
using RViz.
"""

def make_pose(x, y, yaw=0.0, frame='map'):
    p = PoseStamped()
    p.header.frame_id = frame
    p.pose.position.x = x
    p.pose.position.y = y
    p.pose.orientation.w = 1.0                      # facing forward
    return p


def main():
    rclpy.init()

    navigator = BasicNavigator()
    # arm = hm.helloNode.quick_create('arm_node')


    # Security route, probably read in from a file for a real application
    # from either a map or drive and repeat.
    security_route = [
        [0.0, 0.0],
        [1.86111, -1.2777],
        [0.36101, -2.2544]]
    
    wrist = 0.20
    
    # Set our demo's initial pose
    initial_pose = PoseStamped()
    initial_pose.header.frame_id = 'map'
    initial_pose.header.stamp = navigator.get_clock().now().to_msg()
    initial_pose.pose.position.x = 0.0
    initial_pose.pose.position.y = 0.0
    initial_pose.pose.orientation.z = 0.0
    initial_pose.pose.orientation.w = 1.0
    navigator.setInitialPose(initial_pose)
    
    # Wait for navigation to fully activate
    navigator.waitUntilNav2Active()

    # arm.switch_to_trajectory_mode()                 # good hygiene
    navigator.get_logger().info("Waiting for arm to be ready...")
    
    # Do security route until dead
    while rclpy.ok():
        for (x, y) in security_route:
            goal = make_pose(x, y)
            navigator.goToPose(goal)
        
        nav_start = navigator.get_clock().now()
        
        i = 0
        while not navigator.isTaskComplete():
        #     rclpy.spin_once(arm, timeout_sec=0.1) # keep arm’s callbacks alive
            i += 1
            feedback = navigator.getFeedback()
            if feedback and i % 5 == 0:
                navigator.get_logger().info('Executing current waypoint: ')
                now = navigator.get_clock().now()

                # Some navigation timeout to demo cancellation
                if now - nav_start > Duration(seconds=600.0):
                    navigator.cancelTask()
                    
        # nav_start = navigator.get_clock().now()
        # navigator.followWaypoints(route_poses)

        if navigator.getResult() != TaskResult.SUCCEEDED:
            navigator.get_logger().warn("Nav failed, skipping body motion")
            continue
        
        # nav.get_logger().info("Reached (%.2f, %.2f) – moving lift" % (x, y))
        # arm.move_to_pose({'joint_lift': wrist}, blocking=True)
        # wrist *= -1                              # bounce up–down

        # move the wrist to a new position once it reaches the waypoint
        # node.move_to_pose({'joint_lift': wrist_motion_distance}, blocking=True)
        # wrist_motion_distance *= -1
        
        # If at end of route, reverse the route to restart
        security_route.reverse()

        result = navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            navigator.get_logger().info('Route complete! Restarting...')
        elif result == TaskResult.CANCELED:
            navigator.get_logger().info('Security route was canceled, exiting.')
            rclpy.shutdown()
        elif result == TaskResult.FAILED:
            navigator.get_logger().info('Security route failed! Restarting from other side...')

    rclpy.shutdown()


if __name__ == '__main__':
    main()