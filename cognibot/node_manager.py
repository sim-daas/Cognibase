#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import subprocess
import os
import signal
import sys
import json
from pathlib import Path


class NodeManager(Node):
    def __init__(self):
        super().__init__('node_manager')
        
        # Dictionary to keep track of running pipelines {node_name: process_object}
        self.running_nodes = {}
        
        # Determine pipeline scripts directory. By default assume /app/pipelines is mounted.
        self.pipelines_dir = Path(os.environ.get('PIPELINES_DIR', '/app/pipelines'))
        
        # Subscriptions and Publishers
        self.start_subscriber = self.create_subscription(
            String, '/start_node', self.start_callback, 10
        )
        self.kill_subscriber = self.create_subscription(
            String, '/kill_node', self.kill_callback, 10
        )
        self.status_publisher = self.create_publisher(
            String, '/node_manager/status', 10
        )
        self.alert_publisher = self.create_publisher(
            String, '/node_manager/alert', 10
        )
        
        self.get_logger().info('Node Manager initialized')
        self.get_logger().info(f'Pipeline scripts directory: {self.pipelines_dir}')
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Periodically check for finished child processes and emit telemetry
        self.process_check_timer = self.create_timer(2.0, self.check_and_publish_status)

    def get_available_nodes(self):
        if not self.pipelines_dir.exists():
            return []
        
        # Look for .py and .launch.py files
        available = []
        for file in self.pipelines_dir.iterdir():
            if file.is_file() and file.name.endswith('.py'):
                available.append(file.stem)
        return available
    
    def start_callback(self, msg):
        """Handle incoming start requests via JSON or raw string"""
        raw_msg = msg.data.strip()
        node_name = None
        if raw_msg.startswith('{'):
            try:
                payload = json.loads(raw_msg)
                node_name = payload.get("name")
            except json.JSONDecodeError:
                self.get_logger().error(f"Failed to decode JSON from /start_node: {raw_msg}")
                return
        else:
            # Fallback for plain string
            node_name = raw_msg
            
        if not node_name:
            self.get_logger().error("Start request missing or empty node name")
            return
            
        # Clean up name if Agent provides slightly wrong format
        node_name = node_name.lower().replace("_", "-")
        self.start_node(node_name)
            
    def kill_callback(self, msg):
        """Handle incoming kill requests via JSON or raw string"""
        raw_msg = msg.data.strip()
        node_name = None
        if raw_msg.startswith('{'):
            try:
                payload = json.loads(raw_msg)
                node_name = payload.get("name")
            except json.JSONDecodeError:
                self.get_logger().error(f"Failed to decode JSON from /kill_node: {raw_msg}")
                return
        else:
            node_name = raw_msg
            
        if not node_name:
            self.get_logger().error("Kill request missing or empty node name")
            return
            
        node_name = node_name.lower().replace("_", "-")
        self.stop_node(node_name)
    
    def start_node(self, node_name):
        """Start a module as a separate process"""
        if node_name in self.running_nodes:
            self.get_logger().warning(f'Node "{node_name}" is already running')
            return
        
        # Check if python script exists
        pipeline_script = self.pipelines_dir / f'{node_name}.py'
        if not pipeline_script.exists():
            self.get_logger().error(f'Node script not found: {pipeline_script}')
            return
        
        try:
            self.get_logger().info(f'Starting node "{node_name}"...')
            process = subprocess.Popen([
                sys.executable, str(pipeline_script)
            ])
            self.running_nodes[node_name] = process
            self.get_logger().info(f'Started node "{node_name}" with PID: {process.pid}')
            # Immediately publish an updated status
            self.publish_status()
            
        except Exception as e:
            self.get_logger().error(f'Failed to start node "{node_name}": {str(e)}')
            self.publish_alert(node_name, f"Failed to start: {str(e)}")
    
    def stop_node(self, node_name):
        """Stop a running node"""
        if node_name not in self.running_nodes:
            self.get_logger().warning(f'Node "{node_name}" is not running')
            return
        
        try:
            process = self.running_nodes[node_name]
            
            # Check if process is still running
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                    self.get_logger().info(f'Node "{node_name}" terminated gracefully')
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    self.get_logger().warning(f'Node "{node_name}" was force killed')
            else:
                self.get_logger().info(f'Node "{node_name}" was already terminated')
            
            # Remove from running pipelines
            del self.running_nodes[node_name]
            self.publish_status()
            
        except Exception as e:
            self.get_logger().error(f'Error stopping node "{node_name}": {str(e)}')
    
    def cleanup_all_nodes(self):
        self.get_logger().info('Stopping all running nodes...')
        for node_name in list(self.running_nodes.keys()):
            self.stop_node(node_name)
    
    def publish_status(self):
        status_msg = {
            "running": list(self.running_nodes.keys()),
            "available": self.get_available_nodes()
        }
        msg = String()
        msg.data = json.dumps(status_msg)
        self.status_publisher.publish(msg)

    def publish_alert(self, node_name, reason):
        alert_msg = {
            "node": node_name,
            "error": reason
        }
        msg = String()
        msg.data = json.dumps(alert_msg)
        self.alert_publisher.publish(msg)
        
    def check_and_publish_status(self):
        """Remove nodes from tracking if their process has exited unexpectedly."""
        crashed_nodes = []
        for name, proc in list(self.running_nodes.items()):
            if proc.poll() is not None:
                exit_code = proc.returncode
                self.get_logger().warning(f'Node "{name}" exited with code {exit_code}')
                crashed_nodes.append((name, exit_code))
                del self.running_nodes[name]
        
        for name, code in crashed_nodes:
            self.publish_alert(name, f"Process crashed or stopped externally with exit code {code}")
            
        self.publish_status()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.get_logger().info(f'Received signal {signum}, shutting down...')
        self.cleanup_all_nodes()
        rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node_manager = NodeManager()
    try:
        rclpy.spin(node_manager)
    except KeyboardInterrupt:
        node_manager.get_logger().info("KeyboardInterrupt received, shutting down")
        node_manager.cleanup_all_nodes()
    finally:
        if rclpy.ok():
            node_manager.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()
