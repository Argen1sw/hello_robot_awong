from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, EnvironmentVariable, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    map_file = LaunchConfiguration('map')
    mission_file = LaunchConfiguration('mission_file')
    home_robot_on_startup = LaunchConfiguration('home_robot_on_startup')
    home_start_delay_sec = LaunchConfiguration('home_start_delay_sec')
    home_wait_timeout_sec = LaunchConfiguration('home_wait_timeout_sec')
    inorbit_start_command = LaunchConfiguration('inorbit_start_command')
    inorbit_cancel_command = LaunchConfiguration('inorbit_cancel_command')
    inorbit_status_topic = LaunchConfiguration('inorbit_status_topic')

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
        DeclareLaunchArgument(
            'mission_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('inorbit_scan_tools'),
                'config',
                'waypoint_mission.yaml',
            ]),
            description='Full path to the mission YAML file.',
        ),
        DeclareLaunchArgument(
            'home_robot_on_startup',
            default_value='true',
            description='Home the robot once at startup if /is_homed is false.',
        ),
        DeclareLaunchArgument(
            'home_start_delay_sec',
            default_value='2.0',
            description='Delay before checking /is_homed and optionally calling /home_the_robot.',
        ),
        DeclareLaunchArgument(
            'home_wait_timeout_sec',
            default_value='90.0',
            description='How long to wait for /is_homed to become true after homing starts.',
        ),
        DeclareLaunchArgument(
            'inorbit_start_command',
            default_value='mission:start',
            description='String command on /inorbit/custom_commands that starts the mission.',
        ),
        DeclareLaunchArgument(
            'inorbit_cancel_command',
            default_value='mission:cancel',
            description='String command on /inorbit/custom_commands that cancels the mission.',
        ),
        DeclareLaunchArgument(
            'inorbit_status_topic',
            default_value='/inorbit/custom_data_0',
            description='ROS 2-valid topic for mission status key/value publishing.',
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
        Node(
            package='inorbit_scan_tools',
            executable='ensure_homed',
            name='ensure_homed',
            parameters=[{
                'auto_home': home_robot_on_startup,
                'startup_delay_sec': home_start_delay_sec,
                'wait_for_homed_timeout_sec': home_wait_timeout_sec,
                'exit_after_homing': True,
            }],
            output='screen',
        ),
        Node(
            package='inorbit_scan_tools',
            executable='waypoint_mission',
            name='waypoint_mission',
            parameters=[{
                'mission_file': mission_file,
                'dry_run': False,
                'autostart': False,
                'autostart_delay_sec': 0.0,
                'inorbit_start_command': inorbit_start_command,
                'inorbit_cancel_command': inorbit_cancel_command,
                'publish_inorbit_status': True,
                'inorbit_status_topic': inorbit_status_topic,
            }],
            output='screen',
        ),
    ])
