from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    input_topic = LaunchConfiguration('input_topic')
    output_topic = LaunchConfiguration('output_topic')
    laser_frame = LaunchConfiguration('laser_frame')
    output_frame = LaunchConfiguration('output_frame')

    return LaunchDescription([
        DeclareLaunchArgument(
            'input_topic',
            default_value='/scan',
            description='Original laser scan topic',
        ),
        DeclareLaunchArgument(
            'output_topic',
            default_value='/scan_inorbit',
            description='Republished scan topic for InOrbit',
        ),
        DeclareLaunchArgument(
            'laser_frame',
            default_value='laser',
            description='Original lidar frame',
        ),
        DeclareLaunchArgument(
            'output_frame',
            default_value='laser_forward',
            description='Forward-facing virtual lidar frame',
        ),

        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='laser_forward_tf_pub',
            arguments=[
                '--x', '0',
                '--y', '0',
                '--z', '0',
                '--yaw', '3.14159265359',
                '--pitch', '0',
                '--roll', '0',
                '--frame-id', laser_frame,
                '--child-frame-id', output_frame,
            ],
            output='screen',
        ),

        Node(
            package='inorbit_scan_tools',
            executable='scan_frame_republisher',
            name='scan_frame_republisher',
            parameters=[{
                'input_topic': input_topic,
                'output_topic': output_topic,
                'output_frame': output_frame,
            }],
            output='screen',
        ),
    ])