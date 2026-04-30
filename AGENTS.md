Agent Instructions

This is a ROS 2 workspace used for robot integration, development, and deployment support.

Codex is allowed to inspect and modify files in this repository, but it must not connect to the robot, deploy to the robot, or run commands on the robot. The user will manually review changes, push them to a remote repository, fetch them on the robot, and test them.

## Main operating model

Codex should work as a repository coding assistant.

Codex may:

- Inspect files in this repository.
- Create or modify ROS 2 nodes, launch files, configuration files, scripts, tests, and documentation.
- Suggest commands for the user to run manually.
- Explain how to test changes on the robot.
- Add dry-run, mock, or simulation-friendly behavior.

Codex must not:

- SSH into the robot.
- Attempt to connect to the robot.
- Run commands on the robot.
- Publish ROS 2 topics to live hardware.
- Send navigation goals to live hardware.
- Restart robot services.
- Modify robot files directly.
- Deploy files directly to the robot.
- Assume live robot access is available.

## General behavior

- Inspect before editing.
- Explain the intended change before modifying files when the change is non-trivial.
- Prefer small, targeted changes over broad rewrites.
- Show or summarize the diff after editing.
- Do not modify unrelated files.
- Do not guess Stretch-specific behavior when local documentation exists.
- Prefer parameters and configuration over hardcoded deployment-specific values.
- Keep changes suitable for review in Git.

## Documentation context

Before making Hello Robot Stretch-specific changes, read:

- `docs/hello_robot/README.md`
- `docs/hello_robot/developing_basics.md`
- `docs/hello_robot/getting_started_stretch.md`
- `docs/hello_robot/hardware_overview.md`
- `docs/hello_robot/stretch_driver.md`
- `docs/hello_robot/twist_control.md`
- `docs/hello_robot/nav2_basics.md`
- `docs/hello_robot/navigation_simple_commander.md`
- `docs/hello_robot/tf2_listener.md`
- `docs/hello_robot/writing_nodes.md`
- `docs/hello_robot/joint_trajectory_examples.md`

Use these files as the source of truth for Stretch-specific development, ROS 2 behavior, driver usage, Nav2 workflows, TF examples, motion control, and hardware assumptions.

If project-specific robot notes exist, also read:

- `docs/robot_notes.md`

Do not modify copied vendor documentation under `docs/hello_robot/` unless the task is specifically to update documentation context.

## ROS 2 environment

Assume ROS 2 Humble unless the project states otherwise.

Common setup commands the user may run manually:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## Common development commands the user may run manually:

colcon build --symlink-install
ros2 topic list
ros2 topic info <topic> -v
ros2 node list
ros2 node info <node>
ros2 service list
ros2 action list
ros2 launch <package> <launch_file>.launch.py


## Repository safety rules

Codex should ask before making large or potentially destructive changes, including:

Deleting files or directories.
Renaming packages.
Changing package structure.
Rewriting launch architecture.
Changing dependency files.
Modifying CI/CD configuration.
Modifying files that appear to contain credentials.
Changing permissions with chmod, chown, or similar commands.

Codex should not modify secrets or credentials, including:

.env
*.pem
*.key
id_rsa
id_ed25519
config files containing tokens
API credentials
SSH credentials

## Launch file conventions

Prefer Python launch files.
Use DeclareLaunchArgument for values that may change by robot, map, site, or deployment.
Avoid hardcoded robot-specific paths when a launch argument, parameter, or environment variable is better.
Keep robot-specific values in config files when practical.
Use descriptive node names.
Avoid launching unnecessary nodes.
Explain any remappings clearly.
Be careful with command velocity remaps.
Do not add automatic motion behavior to launch files unless explicitly requested.
Include comments only when they clarify non-obvious behavior.

## ROS 2 node conventions

Use rclpy.
Keep node behavior explicit and parameter-driven.
Use clear node names.
Use meaningful logger messages.
Validate parameters where practical.
Handle shutdown cleanly.
Avoid side effects at import time.
Avoid hardcoded robot-specific values.
Use timers, publishers, subscriptions, clients, and action clients in clear, reviewable ways.
Add dry-run behavior for nodes that trigger missions, navigation, or motion when practical.

For scripts that interact with APIs, missions, robot commands, or file changes:

Use clear argument parsing.
Add dry-run mode when practical.
Do not print secrets.
Add useful error messages.
Prefer small functions that are easy to test.
Avoid hidden side effects at import time.
Configuration conventions
Prefer YAML configuration files for values that may change between robots or sites.
Keep map paths, frame names, topic names, mission names, and API endpoints configurable.
Do not hardcode credentials.
Do not hardcode private IP addresses unless the user explicitly requests it.
Use environment variables for sensitive values.
Document required environment variables.


## Testing and checks

Codex may recommend checks such as:

```bash
colcon build --symlink-install
python3 -m compileall .
ros2 launch <package> <launch_file>.launch.py --show-args
ros2 run <package> <node> --ros-args --help
```

## Git and review workflow

```bash
git status --short
rg --files
```
After editing, summarize:

What was inspected.
What was changed.
Why the change was made.
Files modified.
Commands run, if any.
Commands the user should run manually.
Any assumptions or risks.

Prefer output that helps the user review and test the code manually.

## Expected completion format

When completing a task, provide a concise summary with:

Inspected:
Changed:
Why:
Recommended checks:
Notes/Risks:

## Manual deployment workflow

The intended workflow is:

Codex writes or updates code in the local repository.
User reviews the diff.
User commits and pushes changes.
User fetches or pulls the changes on the robot.
User builds and tests manually on the robot.

Codex should not SSH into the robot or run deployment commands directly.
