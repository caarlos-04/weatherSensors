#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import json
import time
import sys
import logging
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from presets import make_sensor_id, sample_measurements, random_site, SITES
from topics import (data_topic, status_topic, ctrl_one_topic, ctrl_group_topic, CTRL_SEND_ALL,
                    belief_topic, belief_site_topic, alert_topic, feedback_topic,
                    reject_topic, assign_sector_topic)
from sensor_intelligence import SensorBrain

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SENSOR] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Sensor:
    """Class representing a weather sensor."""
    
    def __init__(self, sensor_type: str = None, site: str = None, broker: str = "localhost", port: int = 1883):
        """
        Initialize a weather sensor.
        
        Args:
            sensor_type: meteo
            site: Sensor location (will be assigned by monitor if None)
            broker: MQTT broker address
            port: MQTT broker port
        """
        # Generate default values if not specified (always meteo by default)
        self.sensor_type = sensor_type
        self.site = site  # Can be None, will be assigned by monitor
        self.sensor_id = make_sensor_id(self.sensor_type)
        self.sector_assigned = False  # Flag para saber si ya tenemos sector
        
        # MQTT broker configuration
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=self.sensor_id)
        
        # Callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        # Sensor state
        self.is_connected = False
        self.running = True
        
        # DAI - Autonomous Intelligence (The "Brain")
        self.brain = SensorBrain(sensor_id=self.sensor_id, history_size=10)
        self.publish_interval = 5  # Will be adapted dynamically

        if self.site:
            logger.info(f"Sensor created: {self.sensor_id} (type: {self.sensor_type}, site: {self.site})")
        else:
            logger.info(f"Sensor created: {self.sensor_id} (type: {self.sensor_type}, waiting for sector assignment...)")

    def on_connect(self, client, userdata, flags, rc):
        """Callback when connecting to the broker"""
        if rc == 0:
            self.is_connected = True
            logger.info(f"{self.sensor_id}: Connected to broker")
            
            # Subscribe to monitor control topics (assignment and rejection)
            self.client.subscribe(reject_topic(self.sensor_id), qos=2)
            self.client.subscribe(assign_sector_topic(self.sensor_id), qos=2)
            logger.info(f"{self.sensor_id}: Subscribed to monitor control topics")
            
            # Publish online status (no sector yet, will be assigned by monitor)
            status_payload = json.dumps({
                "sensor_id": self.sensor_id,
                "status": "online",
                "sensor_type": self.sensor_type,
                "timestamp": int(time.time())
            })
            # Use temporary site for topic (will be reassigned)
            temp_site = self.site or "pending"
            self.client.publish(status_topic(temp_site, self.sensor_type, self.sensor_id), status_payload, qos=1)
            
            # If we already have a site, subscribe to neighbor beliefs now
            if self.site:
                self.client.subscribe(belief_site_topic(self.site, self.sensor_type), qos=1)
                logger.info(f"{self.sensor_id}: Subscribed to neighbor beliefs at {self.site}")
            
            logger.info(f"{self.sensor_id}: Waiting for sector assignment from monitor...")

        else:
            logger.error(f"{self.sensor_id}: Connection error, code {rc}")

    def on_message(self, client, userdata, msg):
        """Callback when receiving a message"""
        topic = msg.topic
        
        try:
            # Handle monitor rejection (maximum priority)
            if "/reject/" in topic:
                self._handle_rejection(msg.payload)
                return
            
            # Handle sector assignment from monitor
            if "/assign/" in topic:
                self._handle_sector_assignment(msg.payload)
                return
            
            # Check if it's a belief from a neighbor sensor
            if "/belief/" in topic:
                self._handle_neighbor_belief(topic, msg.payload)
            
            # Check if it's feedback from monitor (for learning)
            elif "/feedback/" in topic:
                self._handle_feedback(msg.payload)
            
            # Control commands
            elif "/control/" in topic:
                self._handle_control_command(msg.payload)
            
            else:
                logger.debug(f"{self.sensor_id}: Unhandled message on {topic}")
                
        except Exception as e:
            logger.error(f"{self.sensor_id}: Error processing message from {topic}: {e}")
    
    def _handle_rejection(self, payload: bytes):
        """
        Maneja mensaje de rechazo del monitor.
        El sensor se apaga automáticamente.
        """
        try:
            rejection = json.loads(payload.decode())
            reason = rejection.get("reason", "Unknown")
            retry_after = rejection.get("retry_after", 0)
            
            logger.error("")
            logger.error("="*80)
            logger.error("CONNECTION REJECTED BY MONITOR")
            logger.error("="*80)
            logger.error(f"Sensor ID: {self.sensor_id}")
            logger.error(f"Reason: {reason}")
            if retry_after > 0:
                logger.error(f"Suggested retry: Wait {retry_after} seconds")
            logger.error("="*80)
            logger.error(f"Shutting down sensor {self.sensor_id}...")
            logger.error("="*80)
            logger.error("")
            
            # Apagar el sensor
            self.running = False
            self.disconnect()
        
        except Exception as e:
            logger.error(f"Error handling rejection: {e}")
            self.running = False
            self.disconnect()
    
    def _handle_sector_assignment(self, payload: bytes):
        """
        Maneja asignación de sector por parte del monitor.
        """
        try:
            assignment = json.loads(payload.decode())
            assigned_sector = assignment.get("sector")
            
            if not assigned_sector:
                logger.error("Received empty sector assignment!")
                return
            
            logger.info("")
            logger.info("="*80)
            logger.info(f"SECTOR ASSIGNED BY MONITOR: {assigned_sector}")
            logger.info("="*80)
            logger.info("")
            
            # Actualizar sector
            self.site = assigned_sector
            self.sector_assigned = True
            
            # Now subscribe to control and belief topics with correct sector
            self.client.subscribe(ctrl_one_topic(self.site, self.sensor_type, self.sensor_id), qos=1)
            self.client.subscribe(ctrl_group_topic(self.site, self.sensor_type), qos=1)
            self.client.subscribe(belief_site_topic(self.site, self.sensor_type), qos=1)
            self.client.subscribe(feedback_topic(self.site, self.sensor_type, self.sensor_id), qos=1)
            
            logger.info(f"{self.sensor_id}: Subscribed to topics for {self.site}")
            logger.info(f"{self.sensor_id}: Subscribed to neighbor beliefs: {belief_site_topic(self.site, self.sensor_type)}")
            logger.info(f"{self.sensor_id}: Ready to start publishing data")
            
        except Exception as e:
            logger.error(f"Error handling sector assignment: {e}")
    
    def _handle_neighbor_belief(self, topic: str, payload: bytes):
        """Process belief published by a neighbor sensor."""
        try:
            belief_data = json.loads(payload.decode())
            neighbor_id = belief_data.get("sensor_id")
            
            # Don't process own beliefs
            if neighbor_id == self.sensor_id:
                return
            
            neighbor_risk = belief_data.get("local_risk", 0.0)
            self.brain.update_neighbor_belief(neighbor_id, neighbor_risk)
            
            # Update count of active neighbors
            self.brain.active_neighbors_count = len(self.brain.neighbor_beliefs)
            
            logger.debug(f"{self.sensor_id}: Received belief from {neighbor_id}: risk={neighbor_risk:.2f}")
            
        except Exception as e:
            logger.error(f"{self.sensor_id}: Error parsing neighbor belief: {e}")
    
    def _handle_feedback(self, payload: bytes):
        """Process feedback from monitor for learning."""
        try:
            feedback_data = json.loads(payload.decode())
            feedback_type = feedback_data.get("type")  # 'false_alarm', 'missed_event', 'correct'
            
            self.brain.process_feedback(feedback_type)
            logger.info(f"{self.sensor_id}: Processed feedback: {feedback_type}")
            
        except Exception as e:
            logger.error(f"{self.sensor_id}: Error processing feedback: {e}")
    
    def _handle_control_command(self, payload: bytes):
        """Process control commands from monitor."""
        try:
            command = json.loads(payload.decode())
            cmd_type = command.get("command")
            
            if cmd_type == "adjust_interval":
                new_interval = command.get("interval", self.publish_interval)
                self.publish_interval = new_interval
                logger.info(f"{self.sensor_id}: Interval adjusted to {new_interval}s")
            
            elif cmd_type == "reset_learning":
                self.brain.sensitivity = 1.0
                self.brain.false_alarm_count = 0
                self.brain.missed_event_count = 0
                logger.info(f"{self.sensor_id}: Learning parameters reset")
            
            elif cmd_type == "SHUTDOWN":
                reason = command.get("reason", "Monitor shutdown")
                logger.warning(f"{self.sensor_id}: Received shutdown command - {reason}")
                self.running = False
                self.disconnect()
            
        except Exception as e:
            logger.error(f"{self.sensor_id}: Error processing control command: {e}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback when disconnecting"""
        self.is_connected = False
        logger.warning(f"{self.sensor_id}: Disconnected from broker")

    def connect(self):
        """Connect to the MQTT broker"""
        try:
            logger.info(f"{self.sensor_id}: Connecting to {self.broker}:{self.port}")

            # Configure Last Will Testament (LWT) for offline status
            # Si no tenemos sector asignado, usar "pending" temporalmente
            lwt_site = self.site or "pending"
            lwt_payload = json.dumps({
                "sensor_id": self.sensor_id,
                "status": "offline",
                "sector": lwt_site,
                "sensor_type": self.sensor_type,
                "timestamp": int(time.time()),
                "reason": "connection_lost"
            })
            self.client.will_set(
                status_topic(lwt_site, self.sensor_type, self.sensor_id), 
                lwt_payload, 
                qos=1, 
                retain=True
            )
            
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Wait for connection
            timeout = 5
            start = time.time()
            while not self.is_connected and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if not self.is_connected:
                raise ConnectionError("Timeout al conectar")
                
        except Exception as e:
            logger.error(f"{self.sensor_id}: Error al conectar - {e}")
            raise
    
    def publish_data(self):
        """
        Publish sensor data + beliefs + alerts (DAI autonomous behavior).
        
        This is the heart of the distributed intelligence:
        1. Measure environment
        2. Update internal state
        3. Calculate local risk
        4. Publish measurements (telemetry)
        5. Publish beliefs (for neighbors)
        6. Generate alerts if consensus reached
        """
        if not self.is_connected:
            logger.warning(f"{self.sensor_id}: Not connected, skipping data publish")
            return
        
        # 1. Get measurements
        measurements = sample_measurements(self.sensor_type)
        temp = measurements.get("temperature_c", 0)
        pressure = measurements.get("pressure_hpa", 0)
        humidity = measurements.get("humidity_pct", 0)
        
        # 2. Feed to brain (update internal state)
        self.brain.add_measurement(temp, pressure, humidity)
        
        # 3. Calculate local risk based on trends and patterns
        local_risk = self.brain.calculate_local_risk()
        
        # 4. Publish raw telemetry data
        data_payload = {
            "sensor_id": self.sensor_id,
            "timestamp": int(time.time()),
            **measurements
        }
        self.client.publish(
            data_topic(self.site, self.sensor_type, self.sensor_id),
            json.dumps(data_payload),
            qos=1
        )
        logger.info(f"{self.sensor_id}: Published data - T:{temp:.1f}°C P:{pressure:.1f}hPa H:{humidity:.0f}%")
        
        # 5. Publish belief (opinion about risk) for neighbors
        belief_payload = self.brain.get_belief_summary()
        belief_payload["timestamp"] = int(time.time())
        self.client.publish(
            belief_topic(self.site, self.sensor_type, self.sensor_id),
            json.dumps(belief_payload),
            qos=1
        )
        logger.info(f"{self.sensor_id}: Published belief - Risk:{local_risk:.2f} ({belief_payload['risk_level']})")
        
        # 6. Generate alert if consensus with neighbors
        if self.brain.should_alert():
            alert_payload = {
                "sensor_id": self.sensor_id,
                "timestamp": int(time.time()),
                "alert_type": "weather_risk",
                "risk_level": local_risk,
                "message": f"High risk detected (local:{local_risk:.2f}, neighbors agree)",
                "measurements": measurements
            }
            self.client.publish(
                alert_topic(self.site, self.sensor_type, self.sensor_id),
                json.dumps(alert_payload),
                qos=1
            )
            logger.warning(f"{self.sensor_id}: ALERT GENERATED - Risk:{local_risk:.2f}")
        
    
    def run(self, interval: int = 5):
        """
        Execute the sensor's main loop with adaptive interval (DAI coordination).
        
        Args:
            interval: Base interval in seconds between publications
        """
        self.publish_interval = interval
        self.brain.base_interval = interval
        
        logger.info(f"{self.sensor_id}: Starting autonomous loop (base interval: {interval}s)")
        
        # Wait for sector assignment (if not provided at startup)
        if not self.site:
            logger.info(f"{self.sensor_id}: Waiting for sector assignment from monitor...")
            timeout = 30  # 30 segundos de timeout
            elapsed = 0
            while not self.sector_assigned and self.running and elapsed < timeout:
                time.sleep(0.5)
                elapsed += 0.5
            
            if not self.sector_assigned:
                logger.error(f"{self.sensor_id}: Timeout waiting for sector assignment. Shutting down...")
                self.disconnect()
                return
        
        logger.info(f"{self.sensor_id}: Starting data publication loop...")
        
        try:
            while self.running:
                # Publish data only if we have assigned sector
                if self.sector_assigned or self.site:
                    # Publish data, beliefs, and alerts
                    self.publish_data()
                    
                    # DAI: Calculate adaptive interval based on neighbor activity
                    adaptive_interval = self.brain.calculate_adaptive_interval(self.publish_interval)
                    
                    if adaptive_interval != self.publish_interval:
                        logger.info(f"{self.sensor_id}: Adaptive interval: {adaptive_interval}s (neighbors: {self.brain.active_neighbors_count})")
                    
                    time.sleep(adaptive_interval)
                else:
                    time.sleep(1)  # Wait if no sector yet
                
        except KeyboardInterrupt:
            logger.info(f"{self.sensor_id}: Stopped by user")
        finally:
            self.disconnect()
    
    def disconnect(self):
        """Disconnect from the broker"""
        logger.info(f"{self.sensor_id}: Disconnecting...")
        
        # Publish offline status
        status_payload = json.dumps({
            "sensor_id": self.sensor_id,
            "status": "offline",
            "sector": self.site,
            "sensor_type": self.sensor_type,
            "timestamp": int(time.time())
        })
        self.client.publish(status_topic(self.site, self.sensor_type, self.sensor_id), status_payload, qos=1)
        
        self.client.loop_stop()
        self.client.disconnect()


def load_env_config():
    """
    Load configuration from .env file.
    Looks for .env in parent directory.
    
    Returns:
        dict: Configuration dictionary with broker and port
    """
    # Get the project root (parent of src/)
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    env_path = project_root / ".env"
    
    # Load .env file if it exists
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded configuration from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}, using defaults")
    
    return {
        "broker": os.getenv("MQTT_BROKER", "localhost"),
        "port": int(os.getenv("MQTT_PORT", "1883")),
    }


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Weather sensor MQTT publisher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "-s", "--site",
        type=str,
        choices=SITES,
        help="Sensor site/location. If not specified, monitor will auto-assign a sector."
    )
    
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=5,
        help="Interval in seconds between data publications"
    )
    
    # MQTT broker configuration (override .env values)
    parser.add_argument(
        "-b", "--broker",
        type=str,
        help="MQTT broker address (overrides .env)"
    )
    
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="MQTT broker port (overrides .env)"
    )
    
    # Logging
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)"
    )
    
    return parser.parse_args()


def main():
    """Main function to run the sensor"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Adjust logging level if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Load configuration from .env
    env_config = load_env_config()
    
    # Command line arguments override .env values
    broker = args.broker if args.broker else env_config["broker"]
    port = args.port if args.port else env_config["port"]
    
    logger.info(f"Configuration: broker={broker}, port={port}")
    logger.info(f"Publishing interval: {args.interval}s")
    
    # Create and run sensor
    sensor = Sensor(
        sensor_type="meteo",
        site=args.site,
        broker=broker,
        port=port
    )
    
    sensor.connect()
    sensor.run(interval=args.interval)


if __name__ == "__main__":
    main()