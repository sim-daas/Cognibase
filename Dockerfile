FROM osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive

# 2. Install Remote PC ROS 2 Dependencies and CycloneDDS
RUN apt-get update && apt-get install -y \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-turtlebot3 \
    ros-humble-turtlebot3-msgs \
    ros-humble-navigation2 \
    ros-humble-nav2-bringup \
    ros-humble-slam-toolbox \
    ros-humble-rviz2 \
    python3-colcon-common-extensions \
    git \
    tmux \
    nano \
    ruby \
    ruby-dev \
    build-essential \
    wget \
    "~nros-humble-rqt*" \
    && rm -rf /var/lib/apt/lists/*

# 3. Match Robot Environment Variables EXACTLY
ENV ROS_DOMAIN_ID=184
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV TURTLEBOT3_MODEL=burger
ENV CYCLONEDDS_URI=file:///root/turtlebot3_ws/src/cyclonedds.xml

# 4. Source ROS 2 automatically
RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc
RUN echo 'source ~/turtlebot3_ws/install/setup.bash' >> ~/.bashrc

# 5. Directory setup
RUN mkdir -p ~/turtlebot3_ws/src \
    cd ~/turtlebot3_ws/src/

WORKDIR /root/turtlebot3_ws
CMD ["/bin/bash"]
