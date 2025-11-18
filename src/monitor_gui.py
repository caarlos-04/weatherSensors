#!/usr/bin/env python3
"""
monitor_gui.py
--------------
Real-time GUI dashboard for the Distributed Weather Monitoring System.

This module provides a visual interface to monitor the system state by
subscribing to MQTT topics. It does NOT modify any existing files and
works alongside the existing monitor.

Features:
- Real-time sector status visualization
- Risk level monitoring per sector
- Disagreement detection between sensors
- Active alerts display
- Color-coded risk levels (green/yellow/red)
"""

import tkinter as tk
from tkinter import ttk, font
import paho.mqtt.client as mqtt
import json
import time
import threading
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict
from typing import Dict, List, Optional

# Color scheme for risk levels
COLORS = {
    'safe': '#27ae60',      # Green (0.0-0.3)
    'low': '#f39c12',       # Yellow (0.3-0.6)
    'warning': '#e67e22',   # Orange (0.6-0.8)
    'critical': '#e74c3c',  # Red (0.8-1.0)
    'inactive': '#bdc3c7',  # Gray (no sensor)
    'bg_dark': '#1a1a1a',   # Dark background
    'bg_light': '#f5f5f5',  # Light background (changed to light gray)
    'text_light': '#ffffff',
    'text_dark': '#2c3e50',
    'alert': '#c0392b'      # Dark red for alerts
}


class SectorState:
    """Represents the state of a single sector."""
    
    def __init__(self, sector_name: str):
        self.sector_name = sector_name
        self.active_sensors: Dict[str, float] = {}  # {sensor_id: risk_level}
        self.last_update: Dict[str, float] = {}     # {sensor_id: timestamp}
        self.alerts: List[Dict] = []                 # Active alerts
        self.sensor_status: Dict[str, str] = {}     # {sensor_id: "online"/"offline"}
        self.sensor_sensitivity: Dict[str, float] = {}  # {sensor_id: sensitivity}
        self.sensor_failures: Dict[str, int] = {}       # {sensor_id: total_failures}
        
    def add_belief(self, sensor_id: str, risk_level: float, sensitivity: float = None, 
                   false_alarms: int = None, missed_events: int = None):
        """Update sensor risk belief and learning parameters."""
        self.active_sensors[sensor_id] = risk_level
        self.last_update[sensor_id] = time.time()
        
        if sensitivity is not None:
            self.sensor_sensitivity[sensor_id] = sensitivity
        if false_alarms is not None and missed_events is not None:
            self.sensor_failures[sensor_id] = false_alarms + missed_events
        
    def add_alert(self, alert_data: Dict):
        """Add an alert to the sector."""
        alert_data['timestamp'] = time.time()
        self.alerts.append(alert_data)
        # Keep only recent alerts (last 60 seconds)
        current_time = time.time()
        self.alerts = [a for a in self.alerts if current_time - a['timestamp'] < 60]
        
    def update_status(self, sensor_id: str, status: str):
        """Update sensor online/offline status."""
        self.sensor_status[sensor_id] = status
        if status == "offline" and sensor_id in self.active_sensors:
            del self.active_sensors[sensor_id]
            
    def cleanup_stale_data(self, timeout: float = 30):
        """Remove sensors that haven't updated recently."""
        current_time = time.time()
        stale_sensors = [
            sid for sid, ts in self.last_update.items()
            if current_time - ts > timeout
        ]
        for sid in stale_sensors:
            if sid in self.active_sensors:
                del self.active_sensors[sid]
            if sid in self.last_update:
                del self.last_update[sid]
                
    def get_average_risk(self) -> Optional[float]:
        """Calculate average risk across active sensors."""
        if not self.active_sensors:
            return None
        return sum(self.active_sensors.values()) / len(self.active_sensors)
        
    def has_disagreement(self, threshold: float = 0.3) -> bool:
        """
        Detect disagreement between sensors.
        Disagreement = large variation in risk levels.
        """
        if len(self.active_sensors) < 2:
            return False
        risks = list(self.active_sensors.values())
        risk_range = max(risks) - min(risks)
        return risk_range > threshold
        
    def is_active(self) -> bool:
        """Check if any sensor is active in this sector."""
        return len(self.active_sensors) > 0
        
    def has_alerts(self) -> bool:
        """Check if there are active alerts."""
        return len(self.alerts) > 0


class MonitorGUI:
    """Main GUI application for monitoring the weather system."""
    
    def __init__(self, broker: str = "localhost", port: int = 1883):
        self.broker = broker
        self.port = port
        
        # Sector data
        self.sectors: Dict[str, SectorState] = {
            f"sector{i}": SectorState(f"sector{i}") 
            for i in range(1, 7)
        }
        
        # MQTT client
        self.client = mqtt.Client(client_id="monitor_gui")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # GUI setup
        self.root = tk.Tk()
        self.root.title("Weather Monitoring System - Dashboard")
        self.root.geometry("1200x800")
        self.root.configure(bg=COLORS['bg_dark'])
        
        # Make window responsive
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        self.setup_ui()
        
        # Start MQTT in background thread
        self.mqtt_thread = threading.Thread(target=self.mqtt_loop, daemon=True)
        self.mqtt_thread.start()
        
        # Schedule periodic UI updates
        self.update_ui()
        
    def setup_ui(self):
        """Create the user interface."""
        
        # Title bar
        title_frame = tk.Frame(self.root, bg=COLORS['bg_dark'], pady=20)
        title_frame.grid(row=0, column=0, sticky='ew')
        
        title_label = tk.Label(
            title_frame,
            text="🌦️  Weather Monitoring System  🌦️",
            font=('Arial', 24, 'bold'),
            bg=COLORS['bg_dark'],
            fg='#ffffff'
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            title_frame,
            text="Distributed AI Monitoring Dashboard",
            font=('Arial', 12),
            bg=COLORS['bg_dark'],
            fg='#ffffff'
        )
        subtitle_label.pack()
        
        # Main content area
        main_frame = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_frame.grid(row=1, column=0, sticky='nsew', padx=20, pady=10)
        
        # Configure grid for 2x3 layout
        for i in range(2):
            main_frame.grid_rowconfigure(i, weight=1)
        for i in range(3):
            main_frame.grid_columnconfigure(i, weight=1)
        
        # Create sector panels
        self.sector_panels = {}
        positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
        
        for idx, sector_name in enumerate(sorted(self.sectors.keys())):
            row, col = positions[idx]
            panel = self.create_sector_panel(main_frame, sector_name)
            panel.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
            self.sector_panels[sector_name] = panel
            
        # Status bar
        status_frame = tk.Frame(self.root, bg='#34495e', pady=10)
        status_frame.grid(row=2, column=0, sticky='ew')
        
        self.status_label = tk.Label(
            status_frame,
            text="🔌 Connecting to MQTT broker...",
            font=('Arial', 10),
            bg='#34495e',
            fg='#ffffff'
        )
        self.status_label.pack()
        
    def create_sector_panel(self, parent, sector_name: str) -> tk.Frame:
        """Create a panel for displaying sector information."""
        
        # Main container
        panel = tk.Frame(parent, bg=COLORS['bg_light'], relief=tk.RAISED, borderwidth=2)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        
        # Header
        header = tk.Frame(panel, bg='#34495e', height=40)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_propagate(False)
        
        sector_label = tk.Label(
            header,
            text=sector_name.upper(),
            font=('Arial', 14, 'bold'),
            bg='#34495e',
            fg=COLORS['text_light']
        )
        sector_label.pack(pady=8)
        
        # Content area
        content = tk.Frame(panel, bg=COLORS['bg_light'])
        content.grid(row=1, column=0, sticky='nsew', padx=15, pady=15)
        
        # Status indicator (large circle)
        canvas = tk.Canvas(content, width=80, height=80, bg=COLORS['bg_light'], highlightthickness=0)
        canvas.pack(pady=10)
        circle = canvas.create_oval(10, 10, 70, 70, fill=COLORS['inactive'], outline='')
        
        # Risk level text
        risk_label = tk.Label(
            content,
            text="INACTIVE",
            font=('Arial', 12, 'bold'),
            bg=COLORS['bg_light'],
            fg=COLORS['text_dark']
        )
        risk_label.pack(pady=5)
        
        # Sensor count
        sensor_count_label = tk.Label(
            content,
            text="No sensors",
            font=('Arial', 10),
            bg=COLORS['bg_light'],
            fg=COLORS['text_dark']
        )
        sensor_count_label.pack(pady=2)
        
        # Sensitivity info
        sensitivity_label = tk.Label(
            content,
            text="",
            font=('Arial', 8),
            bg=COLORS['bg_light'],
            fg=COLORS['text_dark']
        )
        sensitivity_label.pack(pady=1)
        
        # Failures info
        failures_label = tk.Label(
            content,
            text="",
            font=('Arial', 8),
            bg=COLORS['bg_light'],
            fg=COLORS['text_dark']
        )
        failures_label.pack(pady=1)
        
        # Disagreement indicator
        disagreement_label = tk.Label(
            content,
            text="",
            font=('Arial', 9, 'bold'),
            bg=COLORS['bg_light'],
            fg=COLORS['alert']
        )
        disagreement_label.pack(pady=2)
        
        # Alert indicator
        alert_label = tk.Label(
            content,
            text="",
            font=('Arial', 9, 'bold'),
            bg=COLORS['bg_light'],
            fg=COLORS['alert']
        )
        alert_label.pack(pady=2)
        
        # Store references for updating
        panel.canvas = canvas
        panel.circle = circle
        panel.risk_label = risk_label
        panel.sensor_count_label = sensor_count_label
        panel.sensitivity_label = sensitivity_label
        panel.failures_label = failures_label
        panel.disagreement_label = disagreement_label
        panel.alert_label = alert_label
        
        return panel
        
    def get_risk_color(self, risk: float) -> str:
        """Get color based on risk level."""
        if risk < 0.3:
            return COLORS['safe']
        elif risk < 0.6:
            return COLORS['low']
        elif risk < 0.8:
            return COLORS['warning']
        else:
            return COLORS['critical']
            
    def get_risk_text(self, risk: float) -> str:
        """Get text description of risk level."""
        if risk < 0.3:
            return "SAFE"
        elif risk < 0.6:
            return "LOW RISK"
        elif risk < 0.8:
            return "WARNING"
        else:
            return "CRITICAL"
            
    def update_sector_panel(self, sector_name: str):
        """Update the visual state of a sector panel."""
        if sector_name not in self.sector_panels:
            return
            
        panel = self.sector_panels[sector_name]
        sector = self.sectors[sector_name]
        
        # Cleanup stale data
        sector.cleanup_stale_data()
        
        # Update based on sector state
        if not sector.is_active():
            # Inactive sector
            panel.canvas.itemconfig(panel.circle, fill=COLORS['inactive'])
            panel.risk_label.config(text="INACTIVE", fg=COLORS['text_dark'])
            panel.sensor_count_label.config(text="No sensors", fg=COLORS['text_dark'])
            panel.sensitivity_label.config(text="")
            panel.failures_label.config(text="")
            panel.disagreement_label.config(text="")
            panel.alert_label.config(text="")
        else:
            # Active sector
            avg_risk = sector.get_average_risk()
            risk_color = self.get_risk_color(avg_risk)
            risk_text = self.get_risk_text(avg_risk)
            
            # Update circle color
            panel.canvas.itemconfig(panel.circle, fill=risk_color)
            
            # Update risk label
            panel.risk_label.config(
                text=f"{risk_text}\n{avg_risk:.2f}",
                fg=COLORS['text_dark']
            )
            
            # Update sensor count
            num_sensors = len(sector.active_sensors)
            sensor_text = f"{num_sensors} sensor{'s' if num_sensors > 1 else ''}"
            panel.sensor_count_label.config(text=sensor_text, fg=COLORS['text_dark'])
            
            # Update sensitivity info (average across sensors)
            if sector.sensor_sensitivity:
                avg_sensitivity = sum(sector.sensor_sensitivity.values()) / len(sector.sensor_sensitivity)
                sensitivity_text = f"Sensitivity: {avg_sensitivity:.2f}"
                panel.sensitivity_label.config(text=sensitivity_text, fg=COLORS['text_dark'])
            else:
                panel.sensitivity_label.config(text="")
            
            # Update failures info (total across sensors)
            if sector.sensor_failures:
                total_failures = sum(sector.sensor_failures.values())
                failures_text = f"Failures: {total_failures}"
                panel.failures_label.config(text=failures_text, fg=COLORS['text_dark'])
            else:
                panel.failures_label.config(text="")
            
            # Check for disagreement
            if sector.has_disagreement():
                panel.disagreement_label.config(text="⚠️ DISAGREEMENT")
            else:
                panel.disagreement_label.config(text="")
                
            # Check for alerts
            if sector.has_alerts():
                alert_text = f"🚨 {len(sector.alerts)} ALERT{'S' if len(sector.alerts) > 1 else ''}"
                panel.alert_label.config(text=alert_text)
            else:
                panel.alert_label.config(text="")
                
    def update_ui(self):
        """Periodic UI update (called every 500ms)."""
        # Update all sector panels
        for sector_name in self.sectors.keys():
            self.update_sector_panel(sector_name)
            
        # Update status bar
        total_sensors = sum(len(s.active_sensors) for s in self.sectors.values())
        total_alerts = sum(len(s.alerts) for s in self.sectors.values())
        
        status_text = f"🟢 Connected | Active Sensors: {total_sensors} | Active Alerts: {total_alerts}"
        self.status_label.config(text=status_text)
        
        # Schedule next update
        self.root.after(500, self.update_ui)
        
    def on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            print("✅ GUI connected to MQTT broker")
            
            # Subscribe to relevant topics
            self.client.subscribe("weather/belief/#", qos=1)
            self.client.subscribe("weather/alert/#", qos=1)
            self.client.subscribe("weather/status/#", qos=1)
            
            print("📡 Subscribed to belief, alert, and status topics")
        else:
            print(f"❌ Connection failed with code {rc}")
            
    def on_message(self, client, userdata, msg):
        """MQTT message callback."""
        topic = msg.topic
        
        try:
            # Parse topic to extract sector and sensor info
            parts = topic.split('/')
            
            if len(parts) < 4:
                return
                
            topic_type = parts[1]  # belief, alert, or status
            sector = parts[2]      # sector name
            sensor_id = parts[4] if len(parts) > 4 else None
            
            # Only process if it's a known sector
            if sector not in self.sectors:
                return
                
            payload = json.loads(msg.payload.decode())
            
            # Handle different message types
            if topic_type == "belief":
                # Update sensor belief (including sensitivity and failures if available)
                risk = payload.get("local_risk", 0.0)
                sensitivity = payload.get("sensitivity")
                false_alarms = payload.get("false_alarm_count")
                missed_events = payload.get("missed_event_count")
                if sensor_id:
                    self.sectors[sector].add_belief(sensor_id, risk, sensitivity, 
                                                   false_alarms, missed_events)
                    
            elif topic_type == "alert":
                # Add alert to sector
                self.sectors[sector].add_alert(payload)
                
            elif topic_type == "status":
                # Update sensor status
                status = payload.get("status", "unknown")
                if sensor_id:
                    self.sectors[sector].update_status(sensor_id, status)
                    
        except Exception as e:
            print(f"❌ Error processing message from {topic}: {e}")
            import traceback
            traceback.print_exc()
            
    def mqtt_loop(self):
        """Run MQTT client loop in background thread."""
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_forever()
        except Exception as e:
            print(f"❌ MQTT connection error: {e}")
            
    def run(self):
        """Start the GUI application."""
        print("🚀 Starting Weather Monitor GUI...")
        print(f"📡 Connecting to MQTT broker at {self.broker}:{self.port}")
        self.root.mainloop()


def load_env_config():
    """Load configuration from .env file."""
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded configuration from {env_path}")
    
    return {
        "broker": os.getenv("MQTT_BROKER", "localhost"),
        "port": int(os.getenv("MQTT_PORT", "1883")),
    }


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Weather Monitoring GUI Dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
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
    
    return parser.parse_args()


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_arguments()
    
    # Load .env configuration
    env_config = load_env_config()
    
    # Command line arguments override .env
    broker = args.broker if args.broker else env_config["broker"]
    port = args.port if args.port else env_config["port"]
    
    # Create and run GUI
    gui = MonitorGUI(broker=broker, port=port)
    gui.run()


if __name__ == "__main__":
    main()
