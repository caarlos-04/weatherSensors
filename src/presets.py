# src/common/presets.py
import os, random, time

SEED = os.getenv("SEED")
if SEED is not None:
    random.seed(int(SEED))

SITES = [
    "sector1", "sector2", "sector3", "sector4", "sector5", "sector6"
]

MEASURE_RANGES = {
    "meteo": {
        "temperature_c": (-15, 30),
        "humidity_pct": (20, 100),
        "pressure_hpa": (930, 1030)
    }
}

def make_sensor_id(sensor_type: str) -> str:

    suffix = f"{int(time.time()*1000)%100000}-{random.randint(100,999)}"
    return f"{sensor_type}-{suffix}"

def sample_measurements(sensor_type: str) -> dict:
    """Returns a dict with sample measurements for the given sensor type."""
    ranges = MEASURE_RANGES.get(sensor_type, {})
    out = {}
    for k, (min, max) in ranges.items():
        if "temperature" in k or "pressure" in k:
            out[k] = round(random.uniform(min, max), 1)
        else:
            out[k] = int(random.uniform(min, max))
    print(f"Sampled measurements for {sensor_type}: {out}")
    return out
