FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive

# 2. Install Remote PC ROS 2 Dependencies and CycloneDDS
RUN apt-get update && apt-get install -y \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-turtlebot3 \
    ros-jazzy-turtlebot3-msgs \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-slam-toolbox \
    ros-jazzy-rviz2 \
    ros-jazzy-ros-gz ros-jazzy-gz-sim-vendor \
    python3-colcon-common-extensions \
    git \
    tmux \
    nano \
    ruby \
    ruby-dev \
    build-essential \
    wget \
    curl lsb-release gnupg \
    "~nros-jazzy-rqt*" 

RUN curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
    && apt-get update \
    && apt-get install gz-harmonic -y \
    && rm -rf /var/lib/apt/lists/*

# 3. Match Robot Environment Variables EXACTLY
ENV ROS_DOMAIN_ID=184
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV TURTLEBOT3_MODEL=burger
ENV CYCLONEDDS_URI=file:///root/turtlebot3_ws/src/cyclonedds.xml

# 4. Source ROS 2 automatically
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
RUN echo 'source ~/turtlebot3_ws/install/setup.bash' >> ~/.bashrc

# 5. Directory setup
RUN mkdir -p ~/turtlebot3_ws/src
WORKDIR /root/turtlebot3_ws/src
RUN git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3_msgs.git && \
    git clone -b jazzy https://github.com/ROBOTIS-GIT/DynamixelSDK.git && \
    git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3.git

COPY cyclonedds.xml /root/turtlebot3_ws/src/cyclonedds.xml
# RUN . /opt/ros/jazzy/setup.sh && cd ~/turtlebot3_ws && \
#     colcon build --symlink-install

CMD ["/bin/bash"]
