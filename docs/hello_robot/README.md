# Hello Robot Documentation Context

This folder contains selected local Markdown copies of Hello Robot Stretch documentation. These files are intended to give Codex and other coding agents reliable reference context when working on Stretch-related ROS 2 nodes, launch files, configuration files, scripts, and project documentation.

The original documentation source is:

https://docs.hello-robot.com/0.3/

## Purpose

Use these files as local reference material for Stretch-specific behavior, ROS 2 usage, navigation, TF, robot drivers, motion control, and development workflows.

These files are documentation context only. They should not be modified during normal development unless the specific task is to refresh or update the copied documentation.

## Files

- `developing_basics.md`  
  General development workflow, Linux/Ubuntu basics, file locations, environment variables, and common Stretch development concepts.

- `getting_started_stretch.md`  
  Initial Stretch setup and getting-started workflow.

- `hardware_overview.md`  
  Stretch hardware components, physical structure, sensors, joints, and robot platform overview.

- `stretch_driver.md`  
  Stretch robot driver behavior and ROS 2 driver-related information.

- `twist_control.md`  
  Velocity control behavior, command velocity usage, and base motion control concepts.

- `joint_trajectory_examples.md`  
  Examples for commanding joints and using trajectory-based motion.

- `writing_nodes.md`  
  Guidance and examples for writing ROS 2 nodes for Stretch.

- `nav2_basics.md`  
  Basic Nav2 concepts and Stretch navigation workflow.

- `navigation_simple_commander.md`  
  Nav2 Simple Commander examples and programmatic navigation workflows.

- `tf2_listener.md`  
  TF2 listener/broadcaster examples and transform-related development notes.

## How Codex should use this folder

Before making Stretch-specific changes, read the relevant files in this folder instead of relying on assumptions.

Recommended references by task:

- For ROS 2 driver behavior: `stretch_driver.md`
- For velocity command behavior: `twist_control.md`
- For navigation and missions: `nav2_basics.md` and `navigation_simple_commander.md`
- For TF or frame issues: `tf2_listener.md`
- For custom scripts or nodes: `writing_nodes.md`
- For joint movement examples: `joint_trajectory_examples.md`
- For hardware assumptions: `hardware_overview.md`
- For environment variables and file locations: `developing_basics.md`

## Development assumptions

Codex is expected to write and edit code in this repository only.

Codex should not connect to the robot over SSH, run commands on the robot, deploy files to the robot, or attempt to test against live hardware. The user will manually review, push, fetch, build, and test the code on the robot.

When writing code that may eventually interact with the robot:

- Make behavior explicit and easy to review.
- Avoid hidden side effects.
- Use launch arguments, parameters, and configuration files instead of hardcoded robot-specific values.
- Add dry-run or simulation-friendly behavior where practical.
- Do not include credentials, IP addresses, tokens, or private robot access details.
- Document any topic, service, action, or parameter that affects robot behavior.

## Local robot notes

Project-specific robot details should not be stored in these copied documentation files. Use a separate file such as:

```text