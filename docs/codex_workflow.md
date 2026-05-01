# Codex Workflow

This document captures the current development and testing workflow for the
custom mission flow in this repository.

## Scope

This repository is used to write and update:

- ROS 2 nodes
- launch files
- package metadata
- mission configuration
- supporting documentation

Codex works only in this repository. Deployment and live testing happen
manually on the robot.

## Current Mission Architecture

The custom integration lives in `src/inorbit_scan_tools`.

Current components:

- `inorbit_with_nav2.launch.py`
  Launches Nav2, scan fixing, startup homing, initial pose publishing, and the
  mission node.
- `inorbit_scan_fix.launch.py`
  Republishes lidar scans and provides the corrected TF frame for the agent side.
- `ensure_homed.py`
  Checks `/is_homed` and calls `/home_the_robot` once at startup when needed.
- `initial_pose_publisher.py`
  Publishes `/initialpose` once to seed localization.
- `waypoint_mission.py`
  Waits for a trigger, drives the base through configured waypoints, and executes
  arm/gripper motions at each stop.
- `config/waypoint_mission.yaml`
  Stores waypoint coordinates and manipulator actions.

## Trigger Path

The mission node currently supports terminal and InOrbit-style triggering.

Accepted trigger interfaces:

- ROS service: `/waypoint_mission/trigger`
- ROS service: `/waypoint_mission/cancel`
- ROS topic: `/waypoint_mission/start` with `std_msgs/Bool`
- ROS topic: `/inorbit/custom_command` with `std_msgs/String`
- ROS topic: `/inorbit/custom_commands` with `std_msgs/String`

Current command strings:

- `mission:start`
- `mission:cancel`

In practice, the installed InOrbit agent on the robot was observed publishing on
`/inorbit/custom_command` (singular), so the mission node listens on both the
singular and plural topic names for compatibility.

## Mission Execution Model

The mission flow is:

1. Wait for the robot to be homed.
2. Wait for Nav2 to be active.
3. Switch the driver to `navigation` mode.
4. Navigate to a configured waypoint.
5. Switch the driver to `position` mode.
6. Activate streaming position control.
7. Publish a joint pose on `/joint_pose_cmd`.
8. Deactivate streaming position control.
9. Switch the driver back to `navigation`.
10. Repeat for the remaining waypoints.

## Why Streaming Position Is Used

The original arm/gripper implementation used
`/stretch_controller/follow_joint_trajectory`.

That failed on the robot because the deployed driver stack raised:

`Robot.follow_trajectory() got an unexpected keyword argument 'move_to_start_point'`

To avoid that version mismatch, the mission node now uses the driver's streaming
position interface instead:

- `/switch_to_position_mode`
- `/activate_streaming_position`
- `/joint_pose_cmd`
- `/deactivate_streaming_position`

This matches the current robot software better.

## Mission Configuration

Mission waypoints and manipulator steps are stored in:

- `src/inorbit_scan_tools/config/waypoint_mission.yaml`

Each waypoint contains:

- `name`
- `pose`
  - `x`
  - `y`
  - `yaw`
- `actions`
  - `name`
  - `duration`
  - `joints`

Current joint usage in the mission file is based on:

- `joint_lift`
- `wrist_extension`
- `joint_wrist_yaw`
- `joint_gripper_finger_left`

## Local Development Workflow

Typical development loop:

1. Edit code in this repository locally.
2. Review the diff.
3. Commit and push changes.
4. Pull changes on the robot.
5. Build the affected package on the robot.
6. Source the workspace.
7. Launch and test manually.

## Robot-Side Build

From the workspace root on the robot:

```bash
cd ~/hello_robot_awong
colcon build --symlink-install --packages-select inorbit_scan_tools
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## Robot-Side Launch

Launch the integrated stack:

```bash
ros2 launch inorbit_scan_tools inorbit_with_nav2.launch.py
```

Useful launch arguments:

- `map`
- `mission_file`
- `home_robot_on_startup`
- `home_start_delay_sec`
- `home_wait_timeout_sec`
- `inorbit_start_command`
- `inorbit_cancel_command`
- `inorbit_status_topic`

## Terminal Testing Without InOrbit

Trigger the mission by service:

```bash
ros2 service call /waypoint_mission/trigger std_srvs/srv/Trigger "{}"
```

Cancel the mission by service:

```bash
ros2 service call /waypoint_mission/cancel std_srvs/srv/Trigger "{}"
```

Trigger the mission by topic:

```bash
ros2 topic pub --once /inorbit/custom_command std_msgs/msg/String "{data: 'mission:start'}"
```

Cancel by topic:

```bash
ros2 topic pub --once /inorbit/custom_command std_msgs/msg/String "{data: 'mission:cancel'}"
```

## Useful Debug Commands

Check active nodes:

```bash
ros2 node list
```

Check trigger topic:

```bash
ros2 topic info /inorbit/custom_command
```

Watch mission status:

```bash
ros2 topic echo /waypoint_mission/status
```

Watch mission active flag:

```bash
ros2 topic echo /waypoint_mission/active
```

Watch optional mission key/value status:

```bash
ros2 topic echo /inorbit/custom_data_0
```

## Known Notes

- The InOrbit documentation referenced `/inorbit/custom_commands`, but the
  installed robot agent was observed using `/inorbit/custom_command`.
- The original `/inorbit/custom_data/0` example is not a valid ROS 2 topic name
  in Humble, so the mission node uses the ROS 2-valid topic
  `/inorbit/custom_data_0`.
- Nav2 base motion is working in the current flow.
- Arm/gripper actions currently execute through streaming position control.
- Startup homing is handled through the ROS-native `/home_the_robot` service and
  `/is_homed` topic rather than shelling out to `stretch_robot_home.py`.

## InOrbit Agent Environment

The local InOrbit documentation notes that environment variables required by
scripts executed by the agent should be placed in:

- `${HOME}/.inorbit/local/agent.env.sh`

That file is relevant if you later decide to have the InOrbit agent execute an
external script directly. The current repo workflow does not require that for
robot homing because bringup uses the ROS driver interfaces instead.

## Recommended Future Cleanup

- Make the actual InOrbit command topic configurable instead of subscribing to
  both singular and plural names.
- Replace placeholder package maintainer metadata in `inorbit_scan_tools`.
- Add explicit mission progress reporting if richer InOrbit dashboards are needed.
