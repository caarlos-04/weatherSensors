# Weather Sensors - Distributed AI System

A **Distributed Artificial Intelligence (DAI)** system for weather monitoring using autonomous sensors with MQTT communication. Each sensor has its own intelligence module ("brain") that makes local decisions, shares beliefs with neighbors, and generates alerts through distributed consensus.

## 🎯 Project Overview

This system demonstrates key DAI concepts:
- **Autonomous Agents**: Each sensor operates independently with its own decision-making logic
- **Distributed Consensus**: Sensors share beliefs and coordinate without central control
- **Emergent Behavior**: System-wide intelligence emerges from local interactions
- **Self-Organization**: Sensors adapt their behavior based on neighbor activity
- **Learning**: Sensors adjust their sensitivity based on feedback

## 🏗️ Architecture

### Components

1. **Monitor** (`monitor_mqtt.py`)
   - Observer and supervisor (not a central controller)
   - Manages sensor connections (max 6 sensors)
   - Auto-assigns sectors to connecting sensors
   - Logs telemetry, beliefs, and alerts
   - Provides feedback for sensor learning
   - Displays system statistics

2. **Sensors** (`sensor_mqtt.py`)
   - Autonomous weather sensors with local intelligence
   - Wait for sector assignment from monitor
   - Publish telemetry data (temperature, pressure, humidity)
   - Calculate local risk based on measurements
   - Share beliefs with neighbor sensors
   - Generate alerts through distributed consensus
   - Adapt publishing interval based on neighbor activity

3. **Sensor Brain** (`sensor_intelligence.py`)
   - Intelligence module for each sensor
   - Maintains measurement history
   - Detects trends (pressure drops, temperature changes)
   - Calculates local risk assessment
   - Processes neighbor beliefs
   - Makes autonomous decisions
   - Learns from monitor feedback

### Communication Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         MQTT Broker                         │
└─────────────────────────────────────────────────────────────┘
           ▲                    ▲                    ▲
           │                    │                    │
    ┌──────┴──────┐      ┌──────┴──────┐     ┌──────┴──────┐
    │  Sensor 1   │◄────►│  Sensor 2   │◄───►│  Sensor 3   │
    │  (sector1)  │      │  (sector2)  │     │  (sector3)  │
    └─────────────┘      └─────────────┘     └─────────────┘
           │                    │                    │
           │            Beliefs Sharing              │
           │   (Distributed Consensus Protocol)      │
           └────────────────────┬────────────────────┘
                                │
                         ┌──────┴──────┐
                         │   Monitor   │
                         │ (Observer)  │
                         └─────────────┘
```

## 📋 Features

### Sensor Management
- **Auto-Assignment**: Monitor automatically assigns sectors to connecting sensors
- **Connection Limiting**: Maximum 6 sensors allowed (fixed limit)
- **Rejection Protocol**: 7th sensor receives shutdown command with retry suggestion
- **Graceful Shutdown**: Monitor can shut down all connected sensors with `quit` command
- **Last Will Testament**: Automatic detection of unexpected sensor disconnections

### Distributed Intelligence
- **Risk Assessment**: Each sensor calculates local risk from measurement trends
- **Belief Sharing**: Sensors publish their risk opinions to neighbors
- **Consensus Building**: Alerts generated when multiple sensors agree on high risk
- **Adaptive Intervals**: Publishing frequency adjusts based on neighbor count
- **Learning**: Sensors adjust sensitivity based on false alarm/missed event feedback

### Monitoring & Visualization
- **Real-time Stats**: Periodic display of system state
- **Risk Distribution**: Visual representation of risk levels across sensors
- **Message Tracking**: Count of data, beliefs, alerts, and status messages
- **Connection Status**: List of active sensors with their sectors
- **Interactive Commands**: `status` for on-demand stats, `quit` for graceful shutdown

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for MQTT broker)
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
   ```bash
   cd WeatherSensors
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv weatherSensors
   source weatherSensors/bin/activate  # Linux/Mac
   # or
   weatherSensors\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start MQTT broker**
   ```bash
   docker compose up -d
   ```

5. **Configure environment** (optional)
   
   Create a `.env` file in the project root:
   ```env
   MQTT_BROKER= address of your broker
   MQTT_PORT= port of the broker
   ```

### Running the System

#### Option 1: Manual Start

1. **Start the monitor** (in terminal 1)
   ```bash
   python src/monitor_mqtt.py -s 30
   ```
   - `-s 30`: Display statistics every 30 seconds

2. **Start sensors** (in separate terminals)
   ```bash
   python src/sensor_mqtt.py -i 5
   python src/sensor_mqtt.py -i 5
   python src/sensor_mqtt.py -i 5
   ```
   - `-i 5`: Publish data every 5 seconds (base interval)
   - Sensors will automatically receive sector assignments

#### Option 2: VS Code Debug Configurations

Use the provided launch configurations:
- **Monitor**: Single monitor instance
- **Sensor**: Single sensor instance
- **Monitor + 3 Sensores**: Launch monitor + 3 sensors
- **Monitor + 6 Sensores**: Launch monitor + 6 sensors (full capacity)

#### Testing Rejection Protocol

To test the 7th sensor rejection:
1. Start monitor + 6 sensors using compound configuration
2. Try to start a 7th sensor manually
3. Observe rejection message and automatic shutdown

## 📡 MQTT Topics

### Status Topics
- `weather/status/{sector}/{sensor_type}/{sensor_id}` - Sensor online/offline status

### Data Topics
- `weather/data/{sector}/{sensor_type}/{sensor_id}` - Telemetry data (temp, pressure, humidity)

### Belief Topics (DAI)
- `weather/belief/{sector}/{sensor_type}/{sensor_id}` - Sensor risk beliefs for neighbors

### Alert Topics
- `weather/alert/{sector}/{sensor_type}/{sensor_id}` - Alerts from distributed consensus

### Control Topics
- `weather/control/reject/{sensor_id}` - Rejection notification to sensor
- `weather/control/assign/{sensor_id}` - Sector assignment to sensor
- `weather/control/{sector}/{sensor_type}/{sensor_id}` - Individual sensor commands
- `weather/control/{sector}/{sensor_type}` - Group commands for sensor type

### Feedback Topics
- `weather/feedback/{sector}/{sensor_type}/{sensor_id}` - Learning feedback from monitor

## 🧠 Intelligence & Decision Making

### Local Risk Calculation

Each sensor calculates risk based on:
1. **Pressure Trends**: Rapid drops indicate incoming storms
2. **Temperature Extremes**: Values outside normal range
3. **Humidity Patterns**: High humidity combined with other factors
4. **Historical Data**: Trends over the last 10 measurements

Risk formula:
```python
risk = (pressure_risk + temp_risk + humidity_risk) / 3 * sensitivity
```

### Distributed Consensus

Sensors generate alerts when:
- Local risk > 0.6 (threshold)
- At least one neighbor also reports high risk
- Creates emergent system-wide behavior

### Adaptive Coordination

Publishing interval adjusts based on neighbor count:
```python
adaptive_interval = base_interval * (1 + 0.1 * active_neighbors)
```
- More neighbors → slower publishing (less network congestion)
- Fewer neighbors → faster publishing (maintain coverage)

### Learning Mechanism

Monitor provides feedback:
- `false_alarm`: Decreases sensor sensitivity
- `missed_event`: Increases sensor sensitivity
- `correct`: Maintains current sensitivity

## 🛠️ Command Line Options

### Monitor
```bash
python src/monitor_mqtt.py [options]
```
- `-b, --broker`: MQTT broker address (default: localhost)
- `-p, --port`: MQTT broker port (default: 1883)
- `-s, --stats`: Stats display interval in seconds (default: 30)
- `-v, --verbose`: Enable debug logging

**Interactive Commands**:
- `status`: Display current system statistics
- `quit`: Gracefully shut down monitor and all connected sensors

### Sensor
```bash
python src/sensor_mqtt.py [options]
```
- `-s, --site`: Pre-assign sector (not recommended, let monitor assign)
- `-i, --interval`: Base publishing interval in seconds (default: 5)
- `-b, --broker`: MQTT broker address (default: localhost)
- `-p, --port`: MQTT broker port (default: 1883)
- `-v, --verbose`: Enable debug logging

## 📊 System Statistics

The monitor displays periodic statistics including:

```
╔════════════════════════════════════════════════════════════════════════╗
║                        WEATHER MONITORING SYSTEM                        ║
╠════════════════════════════════════════════════════════════════════════╣
║  Uptime: 00:05:23 | Active Sensors: 6/6                                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Connected Sensors:                                                     ║
║  [OK] meteo_abc123 (sector1)                                           ║
║  [!]  meteo_def456 (sector2)                                           ║
║  [!!] meteo_ghi789 (sector3)                                           ║
║                                                                          ║
║  Risk Distribution:                                                     ║
║    [OK]  Safe (0.0-0.3):      3 sensors                                ║
║    [!]   Low Risk (0.3-0.6):  2 sensors                                ║
║    [!!]  Warning (0.6-0.8):   1 sensor                                 ║
║    [!!!] Critical (0.8-1.0):  0 sensors                                ║
║                                                                          ║
║  Messages Received:                                                     ║
║    Data:   1234 | Beliefs: 987 | Alerts: 23 | Status: 45              ║
╚════════════════════════════════════════════════════════════════════════╝
```

Risk Level Indicators:
- `[OK]`: Safe (0.0-0.3)
- `[!]`: Low Risk (0.3-0.6)
- `[!!]`: Warning (0.6-0.8)
- `[!!!]`: Critical (0.8-1.0)

## 🔧 Configuration Files

### `.env`
Environment configuration for MQTT connection

### `docker-compose.yml`
MQTT broker (Eclipse Mosquitto) configuration:
- Port 1883: MQTT protocol
- Port 9001: WebSocket (for web clients)
- Persistent storage for data and logs

### `.vscode/launch.json`
Debug configurations for VS Code:
- Individual monitor/sensor launch
- Compound configurations for full system testing

## 🏷️ Sectors

The system supports 6 fixed sectors:
- `sector1`
- `sector2`
- `sector3`
- `sector4`
- `sector5`
- `sector6`

Each sector represents a geographic area monitored by one sensor.

## 📈 DAI Concepts Demonstrated

1. **Agent Autonomy**: Each sensor makes independent decisions
2. **Distributed Problem Solving**: No central controller for alerts
3. **Multi-Agent Coordination**: Sensors share beliefs and adapt behavior
4. **Emergent Intelligence**: System behavior emerges from local rules
5. **Reactive Agents**: Respond to environmental changes in real-time
6. **Learning Agents**: Adapt based on feedback
7. **Communication Protocols**: Structured message exchange via MQTT
8. **Consensus Mechanisms**: Agreement required for alert generation


## 📚 Project Structure

```
WeatherSensors/
├── src/
│   ├── monitor_mqtt.py           # Monitor/Observer component
│   ├── sensor_mqtt.py             # Autonomous sensor agent
│   ├── sensor_intelligence.py    # Sensor brain (DAI logic)
│   ├── topics.py                  # MQTT topic definitions
│   └── presets.py                 # Sensor presets and utilities
├── .vscode/
│   └── launch.json                # VS Code debug configurations
├── mosquitto/
│   ├── mosquitto.conf             # MQTT broker configuration
│   ├── data/                      # Persistent broker data
│   └── log/                       # Broker logs
├── weatherSensors/                # Python virtual environment
├── .env                           # Environment configuration
├── docker-compose.yml             # MQTT broker container
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## 🎓 Academic Context

This project demonstrates concepts from:
- **Distributed Artificial Intelligence (DAI)**
- **Multi-Agent Systems (MAS)**
- **IoT and Edge Computing**
- **Publish-Subscribe Patterns**
- **Consensus Algorithms**
- **Emergent Behavior**

Perfect for studying:
- Agent-based systems design
- Distributed decision making
- Real-time data processing
- MQTT protocol in practice
- Autonomous system coordination

## 📝 License

This is an academic project for educational purposes.