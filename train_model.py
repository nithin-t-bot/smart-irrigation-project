# train_model.py
# Trains RandomForest and saves model.joblib and scaler.joblib
# Usage: python train_model.py

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
import joblib
import warnings
warnings.filterwarnings("ignore")

MODEL_PATH = "model.joblib"
SCALER_PATH = "scaler.joblib"
RANDOM_STATE = 42

def simulate_data(n=20000, seed=RANDOM_STATE):
    rng = np.random.RandomState(seed)
    temp = rng.normal(25, 6, size=n)
    humidity = np.clip(rng.normal(70, 18, size=n), 0, 100)
    pressure = np.clip(rng.normal(1013, 8, size=n), 980, 1040)
    wind = np.abs(rng.normal(2.5, 1.5, size=n))
    precip = np.abs(rng.exponential(0.3, size=n))
    cloud = np.clip(rng.normal(50 + precip*10, 30, size=n), 0, 100)

    prob_rain = (
        0.35 * (humidity/100.0) +
        0.25 * (cloud/100.0) +
        0.25 * (1.0 - (pressure - 980) / 60.0) +
        0.15 * np.tanh(precip)
    )
    prob_rain = np.clip(prob_rain, 0, 1)
    target = (rng.rand(n) < prob_rain).astype(int)

    df = pd.DataFrame({
        "temp_c": temp,
        "humidity_pct": humidity,
        "pressure_hpa": pressure,
        "wind_mps": wind,
        "precip_mm_last_hour": precip,
        "cloud_pct": cloud,
        "target_rain": target
    })
    return df

def load_or_simulate(csv_path="weather.csv"):
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        required = ["temp_c","humidity_pct","pressure_hpa","wind_mps","precip_mm_last_hour","cloud_pct","target_rain"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise RuntimeError(f"CSV present but missing columns: {missing}")
        return df
    else:
        return simulate_data()

def train_and_save():
    df = load_or_simulate()
    X = df.drop(columns=["target_rain"])
    y = df["target_rain"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=RANDOM_STATE, stratify=y)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1)
    clf.fit(X_train_s, y_train)

    preds = clf.predict(X_test_s)
    print("Accuracy:", accuracy_score(y_test, preds))
    print(classification_report(y_test, preds))

    joblib.dump(clf, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"Model trained and saved -> {MODEL_PATH}, {SCALER_PATH}")

if __name__ == "__main__":
    train_and_save()
