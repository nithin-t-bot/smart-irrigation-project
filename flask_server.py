# flask_server.py
# Robust /predict endpoint for Smart Irrigation
# - Loads model.joblib and scaler.joblib (if present)
# - Accepts POST JSON from ESP with fields:
#     soil_moisture, temperature, humidity, rainfall, light, water_flow (optional)
# - Returns JSON with: rain_probability, rain_prediction, irrigation_needed,
#   irrigation_decision, reason, features
#
# Usage:
#   python flask_server.py
# (Run from the project folder that contains model.joblib and scaler.joblib)

from flask import Flask, request, jsonify
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Filenames (must be in same folder as this script)
MODEL_PATH = "model.joblib"
SCALER_PATH = "scaler.joblib"

# Try to load model + scaler; if missing, server will still run using heuristic
clf = None
scaler = None
if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
    try:
        clf = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
        app.logger.info(f"Loaded model from {MODEL_PATH} and scaler from {SCALER_PATH}")
    except Exception as e:
        app.logger.exception("Failed to load model/scaler; continuing without model")
        clf = None
        scaler = None
else:
    app.logger.warning("model.joblib or scaler.joblib not found. Server will use heuristic-only mode.")

# Model feature names (must match training)
MODEL_FEATURE_NAMES = [
    "temp_c",
    "humidity_pct",
    "pressure_hpa",
    "wind_mps",
    "precip_mm_last_hour",
    "cloud_pct",
]

# Safety controls
last_irrigation_time = None
MIN_INTERVAL_BETWEEN_IRRIGATIONS = timedelta(minutes=30)

def build_features(payload):
    """Convert incoming payload into a pandas DataFrame with the model feature names."""
    temp = float(payload.get("temperature", 25.0))
    humidity = float(payload.get("humidity", 60.0))
    raw_rain = float(payload.get("rainfall", 0.0))
    raw_light = float(payload.get("light", 2000.0))

    # Convert raw sensor ADCs into approximate model units:
    # - Map rainfall ADC (0..4095) -> 0..5 mm (example)
    precip_mm = (raw_rain / 4095.0) * 5.0
    # - Map light ADC to cloud percent (simple invert)
    cloud_pct = float(max(0.0, min(100.0, 100.0 * (1.0 - (raw_light / 4095.0)))))

    pressure = float(payload.get("pressure_hpa", 1013.0))
    wind = float(payload.get("wind_mps", 2.0))

    features = {
        "temp_c": temp,
        "humidity_pct": humidity,
        "pressure_hpa": pressure,
        "wind_mps": wind,
        "precip_mm_last_hour": precip_mm,
        "cloud_pct": cloud_pct,
    }

    df = pd.DataFrame([features], columns=MODEL_FEATURE_NAMES)
    return df, features

def heuristic_rain_probability(payload):
    """A very small heuristic fallback for rain probability (0..1)."""
    # Use humidity & cloud & recent precip to guess
    humidity = float(payload.get("humidity", 60.0))
    raw_light = float(payload.get("light", 2000.0))
    cloud_pct = max(0.0, min(100.0, 100.0 * (1.0 - (raw_light / 4095.0))))
    raw_rain = float(payload.get("rainfall", 0.0))
    precip_mm = (raw_rain / 4095.0) * 5.0
    prob = 0.4 * (humidity / 100.0) + 0.4 * (cloud_pct / 100.0) + 0.2 * min(1.0, precip_mm / 5.0)
    return float(np.clip(prob, 0.0, 1.0))

def decide_irrigation(payload, rain_prob, rain_pred):
    """Combine model output and heuristics to produce final irrigation decision and reason."""
    global last_irrigation_time

    soil_adc = float(payload.get("soil_moisture", 0.0))
    soil_norm = min(max(soil_adc / 4095.0, 0.0), 1.0)

    SOIL_DRY_THRESHOLD = 0.7          # tune for your sensor
    RAIN_PROB_BLOCK = 0.35
    NIGHT_SKIP = True
    HOUR_START, HOUR_END = 6, 18      # allowed irrigation hours (UTC here; adjust to local)

    now = datetime.utcnow()

    # Safety: prevent frequent watering
    if last_irrigation_time and (now - last_irrigation_time) < MIN_INTERVAL_BETWEEN_IRRIGATIONS:
        return 0, f"Skipped: recent irrigation at {last_irrigation_time.isoformat()}"

    # If high rain probability or model predicted rain => skip
    if rain_prob is not None and rain_prob >= RAIN_PROB_BLOCK:
        return 0, f"Skipped: rain probability {rain_prob:.2f} >= {RAIN_PROB_BLOCK}"
    if rain_pred == 1:
        return 0, "Skipped: model predicted rain"

    # Skip at night optionally
    if NIGHT_SKIP:
        hour = now.hour
        if hour < HOUR_START or hour >= HOUR_END:
            return 0, f"Skipped: outside allowed hours ({HOUR_START}-{HOUR_END} UTC)"

    # If soil is dry, irrigate
    if soil_norm >= SOIL_DRY_THRESHOLD:
        last_irrigation_time = now
        return 1, f"Irrigating: soil_norm={soil_norm:.2f} >= {SOIL_DRY_THRESHOLD}"

    return 0, f"Skipped: soil_norm={soil_norm:.2f} < {SOIL_DRY_THRESHOLD}"

@app.route("/predict", methods=["POST"])
def predict():
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "invalid json", "details": str(e)}), 400

    app.logger.info(f"Received payload: {payload}")

    # Build features for model/scaler
    try:
        features_df, features_info = build_features(payload)
    except Exception as e:
        app.logger.exception("Feature build failed")
        return jsonify({"error": "feature build failed", "details": str(e)}), 400

    prob = None
    pred = None

    # If we have a trained model, use it; otherwise compute heuristic prob
    if clf is not None and scaler is not None:
        try:
            scaled = scaler.transform(features_df)
            prob = float(clf.predict_proba(scaled)[0, 1])
            pred = int(clf.predict(scaled)[0])
        except Exception:
            app.logger.exception("Model prediction failed; falling back to heuristic")
            prob = heuristic_rain_probability(payload)
            pred = None
    else:
        # model not loaded: use heuristic probability
        prob = heuristic_rain_probability(payload)
        pred = None

    irrigation, reason = decide_irrigation(payload, prob, pred if pred is not None else 0)

    # Always include the full fields in response (so ESP sees them)
    response = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "rain_probability": round(prob, 4) if prob is not None else None,
        "rain_prediction": int(pred) if pred is not None else None,
        "irrigation_needed": int(irrigation),
        "irrigation_decision": int(irrigation),
        "reason": reason if reason is not None else "no reason",
        "features": features_info
    }

    app.logger.info(f"Responding: {response}")
    return jsonify(response), 200

if __name__ == "__main__":
    # Run on all interfaces so ESP can reach it; in production use a WSGI server
    app.run(host="0.0.0.0", port=5000)
