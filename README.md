# hello_robot_awong

ROS 2 Humble workspace for a Hello Robot Stretch platform. This repository combines the upstream `stretch_ros2` stack with a small local package for InOrbit lidar visualization, plus a few workspace-specific maps, notes, and test scripts.

## Workspace Contents

- `src/stretch_ros2/`: upstream Hello Robot ROS 2 packages for Stretch, including drivers, description, calibration, navigation, demos, RTAB-Map, and helper libraries.
- `src/inorbit_scan_tools/`: local `ament_python` package that republishes `sensor_msgs/LaserScan` data into a forward-facing virtual lidar frame for InOrbit.
- `maps/`: saved occupancy grid maps such as `nav2_demo_map` and `rnexus_small_map2`.
- `docs/hello_robot/`: local reference notes copied from Hello Robot documentation.
- `test_scripts/`: small ad hoc scripts, including a simple `HelloNode` motion example.

## Prerequisites

- Ubuntu 22.04 with ROS 2 Humble
- A working Stretch software installation and robot configuration
- Standard ROS 2 build tools such as `colcon`

If the robot or workstation is not already set up for Stretch, start with the upstream documentation in [src/stretch_ros2/README.md](src/stretch_ros2/README.md).

## Build

From the workspace root:

```bash
colcon build --symlink-install
source install/setup.bash
```

If you are iterating on a single package, you can build that package selectively with `colcon build --packages-select <package_name> --symlink-install`.

## Key Packages

### `stretch_ros2`

The `src/stretch_ros2/` tree contains the main Hello Robot stack. Common areas you will likely touch:

- `stretch_core`: robot driver, cameras, lidar, teleop, diagnostics
- `stretch_nav2`: Nav2 bringup, online/offline mapping, navigation launch files, tuned config
- `stretch_description`: URDF/Xacro and RViz description assets
- `stretch_calibration`: calibration tools and launch files
- `stretch_demos`, `stretch_funmap`, `stretch_rtabmap`, `stretch_octomap`: higher-level examples and mapping/navigation workflows

See [src/stretch_ros2/README.md](src/stretch_ros2/README.md) for the upstream package overview.

### `inorbit_scan_tools`

This local package adapts a lidar scan for InOrbit visualization by:

- publishing a static transform from the original laser frame to a virtual forward-facing frame
- republishing the scan on a separate topic with the `frame_id` changed
- rotating the `ranges` and `intensities` arrays by 180 degrees so the scan aligns with the new frame

Launch it with:

```bash
ros2 launch inorbit_scan_tools inorbit_scan_fix.launch.py
```

Launch arguments:

- `input_topic` default: `/scan`
- `output_topic` default: `/scan_inorbit`
- `laser_frame` default: `laser`
- `output_frame` default: `laser_forward`

Example:

```bash
ros2 launch inorbit_scan_tools inorbit_scan_fix.launch.py \
  input_topic:=/scan \
  output_topic:=/scan_inorbit \
  laser_frame:=laser \
  output_frame:=laser_forward
```

## Maps And Navigation Assets

The `maps/` directory includes occupancy grid maps that can be reused with Nav2 workflows in `stretch_nav2`. Typical map pairs are:

- `maps/nav2_demo_map.yaml` with `maps/nav2_demo_map.pgm`
- `maps/rnexus_small_map2.yaml` with `maps/rnexus_small_map2.pgm`

Use the YAML file when launching localization or navigation workflows that expect a map server input.

## Notes And Examples

- [docs/hello_robot/developing_basics.md](docs/hello_robot/developing_basics.md): local reference material on the Stretch development environment
- [test_scripts/motion_example.py](test_scripts/motion_example.py): minimal example using `hello_helpers.hello_misc.HelloNode` to command a few joints

## Common Commands

```bash
source install/setup.bash
ros2 topic list
ros2 topic info /scan -v
ros2 launch stretch_core stretch_driver.launch.py
ros2 launch stretch_nav2 navigation.launch.py
```

Use the exact launch flow and safety procedure appropriate for the robot you are connected to.
