#!/bin/bash

IMAGE="${1:-cognibase:humble}"
CONTAINER_NAME="${2:-tb3_remote_env}"
HOST_REPO_PATH="${3:-$(pwd)}"
CONTAINER_REPO_PATH="/root/turtlebot3_ws/src/"

# Build the image if it doesn't exist
if [[ "$(docker images -q ${IMAGE} 2> /dev/null)" == "" ]]; then
    echo "Image ${IMAGE} not found. Building it now..."
    docker build -f Dockerfile.remote -t "${IMAGE}" .
fi

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container ${CONTAINER_NAME} already exists."
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Executing into running container..."
        docker exec -it "${CONTAINER_NAME}" bash
    else
        echo "Starting and executing into stopped container..."
        docker start "${CONTAINER_NAME}"
        docker exec -it "${CONTAINER_NAME}" bash
    fi
    exit 0
fi

echo "Creating new container ${CONTAINER_NAME}..."

# X11 setup for GUI (RViz2/Gazebo)
XSOCK="/tmp/.X11-unix"
XAUTH="${XAUTHORITY:-$HOME/.Xauthority}"
xhost +local:docker # Temporarily allow docker to connect to X server

# Check for NVIDIA GPU to attach runtime
GPU_OPTS=""
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected. Enabling hardware acceleration."
    GPU_OPTS="--gpus all"
else
    echo "WARNING: NVIDIA GPU not detected. GUI applications may lag."
fi

# Run the container
docker run -it \
    --net=host \
    --ipc=host \
    --pid=host \
    -v "${HOST_REPO_PATH}:${CONTAINER_REPO_PATH}" \
    -v "${XSOCK}:${XSOCK}:rw" \
    -v "${XAUTH}:${XAUTH}:rw" \
    -e DISPLAY="${DISPLAY}" \
    -e XAUTHORITY="${XAUTH}" \
    -e QT_X11_NO_MITSHM=1 \
    --name "${CONTAINER_NAME}" \
    ${GPU_OPTS} \
    "${IMAGE}"
