#!/bin/bash
cd /home/mars/catkin_ws
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source "/home/mars/catkin_ws/devel/setup.bash"
sudo chmod -R a+rw ~/cp1 ~/logs ~/.ros/log
exec "$@"
