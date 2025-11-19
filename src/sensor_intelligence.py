"""
sensor_intelligence.py
----------------------
Intelligence module for autonomous sensors (DAI - Distributed Artificial Intelligence)

Each sensor has:
- Internal state (history of measurements)
- Risk assessment capabilities
- Trend detection
- Local decision making
- Learning from feedback
"""

from collections import deque
from typing import Dict, List, Optional
import statistics
import logging

logger = logging.getLogger(__name__)


class SensorBrain:
    """
    Autonomous intelligence for each sensor.
    Manages state, detects trends, calculates risk, learns from feedback.
    """
    
    def __init__(self, sensor_id: str, history_size: int = 10):
        """
        Initialize the sensor brain.
        
        Args:
            sensor_id: Unique sensor identifier
            history_size: Number of past measurements to keep
        """
        self.sensor_id = sensor_id
        self.history_size = history_size
        
        # Internal state - recent history
        self.temp_history = deque(maxlen=history_size)
        self.pressure_history = deque(maxlen=history_size)
        self.humidity_history = deque(maxlen=history_size)
        
        # Neighbor beliefs (from other sensors in same site)
        self.neighbor_beliefs: Dict[str, float] = {}  # {sensor_id: risk_level}
        
        # Risk assessment
        self.local_risk = 0.0  # Current risk level (0.0 - 1.0)
        self.risk_threshold = 0.6  # Threshold for generating alerts
        
        # Learning parameters
        self.sensitivity = 1.0  # Multiplier for risk calculation (adjustable)
        self.false_alarm_count = 0
        self.missed_event_count = 0
        
        # Coordination state
        self.active_neighbors_count = 0
        self.base_interval = 5  # Base publishing interval
        
        logger.info(f"SensorBrain initialized for {sensor_id}")
    
    def add_measurement(self, temp: float, pressure: float, humidity: float):
        """
        Add new measurement to history.
        
        Args:
            temp: Temperature in Celsius
            pressure: Pressure in hPa
            humidity: Humidity percentage
        """
        self.temp_history.append(temp)
        self.pressure_history.append(pressure)
        self.humidity_history.append(humidity)
        
        logger.debug(f"{self.sensor_id}: Added measurement - T:{temp}°C P:{pressure}hPa H:{humidity}%")
    
    def detect_pressure_drop(self) -> bool:
        """
        Detect rapid pressure drop (indicator of incoming storm).
        
        Returns:
            True if rapid drop detected
        """
        if len(self.pressure_history) < 3:
            return False
        
        # Check if pressure dropped more than 5 hPa in recent measurements
        recent = list(self.pressure_history)[-3:]
        drop = recent[0] - recent[-1]
        
        if drop > 5:
            logger.warning(f"{self.sensor_id}: Rapid pressure drop detected: {drop:.1f} hPa")
            return True
        return False
    
    def detect_high_humidity_low_temp(self) -> bool:
        """
        Detect combination of high humidity and low temperature (risk of ice/snow).
        
        Returns:
            True if risky combination detected
        """
        if not self.temp_history or not self.humidity_history:
            return False
        
        current_temp = self.temp_history[-1]
        current_humidity = self.humidity_history[-1]
        
        if current_temp < 2 and current_humidity > 80:
            logger.warning(f"{self.sensor_id}: Ice risk - T:{current_temp}°C H:{current_humidity}%")
            return True
        return False
    
    def detect_extreme_values(self) -> bool:
        """
        Detect extreme values in any parameter.
        
        Returns:
            True if extreme values detected
        """
        if not self.temp_history or not self.pressure_history:
            return False
        
        current_temp = self.temp_history[-1]
        current_pressure = self.pressure_history[-1]
        
        # Extreme temperature
        if current_temp < -10 or current_temp > 35:
            logger.warning(f"{self.sensor_id}: Extreme temperature: {current_temp}°C")
            return True
        
        # Extreme pressure (very low = storm)
        if current_pressure < 970:
            logger.warning(f"{self.sensor_id}: Very low pressure: {current_pressure} hPa")
            return True
        
        return False
    
    def calculate_local_risk(self) -> float:
        """
        Calculate local risk based on sensor's own observations.
        
        Returns:
            Risk level between 0.0 (safe) and 1.0 (high risk)
        """
        if len(self.temp_history) < 2:
            return 0.0
        
        risk = 0.0
        
        # Factor 1: Pressure drop (0.0 - 0.4)
        if self.detect_pressure_drop():
            risk += 0.4
        
        # Factor 2: High humidity + low temp (0.0 - 0.3)
        if self.detect_high_humidity_low_temp():
            risk += 0.3
        
        # Factor 3: Extreme values (0.0 - 0.3)
        if self.detect_extreme_values():
            risk += 0.3
        
        # Apply sensitivity multiplier (learning)
        risk = min(1.0, risk * self.sensitivity)
        
        self.local_risk = risk
        logger.debug(f"{self.sensor_id}: Local risk calculated: {risk:.2f}")
        
        return risk
    
    def update_neighbor_belief(self, neighbor_id: str, neighbor_risk: float):
        """
        Update belief received from a neighbor sensor.
        
        Args:
            neighbor_id: ID of the neighbor sensor
            neighbor_risk: Risk level reported by neighbor
        """
        self.neighbor_beliefs[neighbor_id] = neighbor_risk
        logger.debug(f"{self.sensor_id}: Updated belief from {neighbor_id}: risk={neighbor_risk:.2f}")
    
    def get_neighbors_average_risk(self) -> Optional[float]:
        """
        Calculate average risk from neighbor beliefs.
        
        Returns:
            Average risk from neighbors, or None if no neighbors
        """
        if not self.neighbor_beliefs:
            return None
        
        avg = statistics.mean(self.neighbor_beliefs.values())
        return avg
    
    def should_alert(self) -> bool:
        """
        Decide if an alert should be generated based on local + neighbor consensus.
        
        This is the core of distributed decision making!
        
        Returns:
            True if alert should be generated
        """
        # First check: local risk must be significant
        if self.local_risk < self.risk_threshold:
            return False
        
        # If no neighbors, decide alone
        neighbor_avg = self.get_neighbors_average_risk()
        if neighbor_avg is None:
            logger.info(f"{self.sensor_id}: High local risk ({self.local_risk:.2f}), no neighbors - ALERTING")
            return True
        
        # Consensus rule: alert only if neighbors also see elevated risk
        consensus_threshold = 0.4
        if neighbor_avg >= consensus_threshold:
            logger.info(f"{self.sensor_id}: Consensus reached - Local:{self.local_risk:.2f} Neighbors:{neighbor_avg:.2f} - ALERTING")
            return True
        else:
            logger.info(f"{self.sensor_id}: No consensus - Local:{self.local_risk:.2f} Neighbors:{neighbor_avg:.2f} - NOT alerting")
            return False
    
    def calculate_adaptive_interval(self, base_interval: int) -> int:
        """
        Calculate adaptive publishing interval based on neighbor activity.
        
        Coordination: If many neighbors active, reduce frequency to avoid congestion.
        
        Args:
            base_interval: Base interval in seconds
            
        Returns:
            Adjusted interval in seconds
        """
        
        if self.active_neighbors_count <= 2:
            # Few neighbors, normal frequency
            return base_interval
        
        elif self.active_neighbors_count <= 5:
            # Several neighbors, slightly reduce frequency
            return int(base_interval * 1.5)
        
        else:
            # Many neighbors, reduce frequency significantly
            return int(base_interval * 2)
    
    def process_feedback(self, feedback_type: str):
        """
        Learn from feedback provided by the monitor.
        
        Args:
            feedback_type: 'false_alarm' or 'missed_event' or 'correct'
        """
        if feedback_type == "false_alarm":
            self.false_alarm_count += 1
            # Too sensitive, reduce sensitivity
            self.sensitivity = max(0.5, self.sensitivity - 0.1)
            logger.info(f"{self.sensor_id}: False alarm feedback - Reducing sensitivity to {self.sensitivity:.2f}")
        
        elif feedback_type == "missed_event":
            self.missed_event_count += 1
            # Not sensitive enough, increase sensitivity
            self.sensitivity = min(1.5, self.sensitivity + 0.1)
            logger.info(f"{self.sensor_id}: Missed event feedback - Increasing sensitivity to {self.sensitivity:.2f}")
        
        elif feedback_type == "correct":
            # Good prediction - gradually move sensitivity back towards 1.0 (optimal)
            if self.sensitivity < 1.0:
                self.sensitivity = min(1.0, self.sensitivity + 0.05)
                logger.info(f"{self.sensor_id}: Correct feedback - Increasing sensitivity to {self.sensitivity:.2f}")
            elif self.sensitivity > 1.0:
                self.sensitivity = max(1.0, self.sensitivity - 0.05)
                logger.info(f"{self.sensor_id}: Correct feedback - Decreasing sensitivity to {self.sensitivity:.2f}")
            else:
                logger.info(f"{self.sensor_id}: Correct feedback - Maintaining optimal sensitivity {self.sensitivity:.2f}")
    
    def get_belief_summary(self) -> Dict:
        """
        Get current belief state for publishing.
        
        Returns:
            Dictionary with belief information
        """
        return {
            "sensor_id": self.sensor_id,
            "local_risk": round(self.local_risk, 3),
            "risk_level": self._risk_to_label(self.local_risk),
            "neighbor_count": len(self.neighbor_beliefs),
            "neighbor_avg_risk": round(self.get_neighbors_average_risk(), 3) if self.neighbor_beliefs else None,
            "sensitivity": round(self.sensitivity, 2),
            "false_alarm_count": self.false_alarm_count,
            "missed_event_count": self.missed_event_count,
            "would_alert": self.should_alert()
        }
    
    def _risk_to_label(self, risk: float) -> str:
        """Convert risk number to human-readable label."""
        if risk < 0.3:
            return "stable"
        elif risk < 0.6:
            return "moderate"
        elif risk < 0.8:
            return "high"
        else:
            return "critical"
    
    def get_stats(self) -> Dict:
        """Get statistics for monitoring/debugging."""
        return {
            "measurements_count": len(self.temp_history),
            "local_risk": round(self.local_risk, 3),
            "neighbors": len(self.neighbor_beliefs),
            "sensitivity": round(self.sensitivity, 2),
            "false_alarms": self.false_alarm_count,
            "missed_events": self.missed_event_count
        }
