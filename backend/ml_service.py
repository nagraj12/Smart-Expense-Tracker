from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import joblib


ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "ml_models" / "model.pkl"
VECTORIZER_PATH = ROOT_DIR / "ml_models" / "vectorizer.pkl"

FALLBACK_RULES = {
    "Groceries": ["rice", "atta", "dal", "sugar", "salt", "oil", "masala", "flour"],
    "Dairy": ["milk", "curd", "paneer", "butter", "cheese", "ghee"],
    "Beverages": ["pepsi", "coke", "sprite", "juice", "water", "drink", "soda"],
    "Snacks": ["chips", "biscuits", "cookies", "namkeen", "kurkure", "wafer"],
    "Household Items": ["soap", "detergent", "cleaner", "phenyl", "dishwash", "broom"],
    "Personal Care": ["shampoo", "toothpaste", "toothbrush", "face wash", "lotion", "deo"],
    "Frozen Foods": ["ice cream", "frozen peas", "frozen corn", "fries", "nuggets"],
    "Bakery": ["bread", "bun", "cake", "rusk", "toast", "muffin"],
}


class ExpenseClassifier:
    def __init__(self) -> None:
        self.model = joblib.load(MODEL_PATH)
        self.vectorizer = joblib.load(VECTORIZER_PATH)
        self.categories = list(getattr(self.model, "classes_", []))

    @staticmethod
    def normalize_text(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def fallback_category(self, description: str) -> str | None:
        normalized = self.normalize_text(description)
        for category, keywords in FALLBACK_RULES.items():
            if any(keyword in normalized for keyword in keywords):
                return category
        return None

    def predict(self, description: str) -> dict[str, Any]:
        clean_description = description.strip()
        if not clean_description:
            return {
                "category": "Other",
                "confidence": 0.0,
                "source": "fallback",
                "review_needed": True,
            }

        vector = self.vectorizer.transform([clean_description])
        prediction = self.model.predict(vector)[0]

        confidence = 0.0
        if hasattr(self.model, "predict_proba"):
            try:
                probabilities = self.model.predict_proba(vector)[0]
                confidence = float(max(probabilities))
            except (AttributeError, TypeError):
                # Handle scikit-learn version compatibility issues
                confidence = 0.0

        if confidence >= 0.25:
            return {
                "category": prediction,
                "confidence": round(confidence, 4),
                "source": "ml-model",
                "review_needed": confidence < 0.4,
            }

        fallback = self.fallback_category(clean_description)
        if fallback:
            return {
                "category": fallback,
                "confidence": round(max(confidence, 0.45), 4),
                "source": "fallback-rule",
                "review_needed": False,
            }

        category = prediction if confidence >= 0.35 else "Other"
        return {
            "category": category,
            "confidence": round(confidence, 4),
            "source": "ml-low-confidence" if category != "Other" else "fallback",
            "review_needed": category == "Other",
        }
