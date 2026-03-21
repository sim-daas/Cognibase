#!/bin/bash
set -e

# Source ROS2 and workspace
source /opt/ros/humble/setup.bash
if [ -f /agenticros_ws/install/setup.bash ]; then
  source /agenticros_ws/install/setup.bash
fi
if [ -f /root/turtlebot3_ws/install/setup.bash ]; then
  source /root/turtlebot3_ws/install/setup.bash
fi

exec "$@"
