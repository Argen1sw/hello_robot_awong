from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, EnvironmentVariable, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    map_file = LaunchConfiguration('map')

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('stretch_nav2'),
                'launch',
                'navigation.launch.py',
            ])
        ),
        launch_arguments={
            'map': map_file,
            'use_rviz': 'false',
        }.items()
    )

    inorbit_scan_fix = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('inorbit_scan_tools'),
                'launch',
                'inorbit_scan_fix.launch.py',
            ])
        ),
        launch_arguments={
            'input_topic': '/scan',
            'output_topic': '/scan_inorbit',
            'laser_frame': 'laser',
            'output_frame': 'laser_forward',
        }.items()
    )

    return LaunchDescription([
        
        DeclareLaunchArgument(
            'map',
            default_value=[
                EnvironmentVariable('HELLO_FLEET_PATH'),
                '/maps/nav2_demo_map.yaml'
            ],
            description='Full path to the Nav2 map YAML file',
        ),
        DeclareLaunchArgument('initial_x', default_value='-0.389'),
        DeclareLaunchArgument('initial_y', default_value='1.714'),
        DeclareLaunchArgument('initial_yaw', default_value='3.032'),

        nav2_launch,
        inorbit_scan_fix,

        Node(
            package='inorbit_scan_tools',
            executable='initial_pose_publisher',
            name='initial_pose_publisher',
            parameters=[{
                'x': LaunchConfiguration('initial_x'),
                'y': LaunchConfiguration('initial_y'),
                'yaw': LaunchConfiguration('initial_yaw'),
                'delay_sec': 9.0,
            }],
            output='screen',
        ),
    ])