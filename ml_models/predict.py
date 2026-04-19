from __future__ import annotations

from pathlib import Path

import joblib


ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "ml_models" / "model.pkl"
VECTORIZER_PATH = ROOT_DIR / "ml_models" / "vectorizer.pkl"


def predict_description(description: str) -> None:
    model = joblib.load(MODEL_PATH)
    vectorizer = joblib.load(VECTORIZER_PATH)

    vector = vectorizer.transform([description])
    prediction = model.predict(vector)[0]
    confidence = float(max(model.predict_proba(vector)[0])) if hasattr(model, "predict_proba") else None

    print(f"Description: {description}")
    print(f"Prediction: {prediction}")
    if confidence is not None:
        print(f"Confidence: {confidence:.2%}")


if __name__ == "__main__":
    for sample in ["rice bag", "milk packet", "pepsi bottle", "detergent powder"]:
        predict_description(sample)
        print("-" * 40)
