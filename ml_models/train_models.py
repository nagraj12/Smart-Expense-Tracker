from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split


ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT_DIR / "data" / "ml_dataset.csv"
MODEL_PATH = ROOT_DIR / "ml_models" / "model.pkl"
VECTORIZER_PATH = ROOT_DIR / "ml_models" / "vectorizer.pkl"

TEMPLATES = [
    "{item}",
    "{item} stock",
    "{item} delivery",
    "received {item}",
    "received {item} from supplier",
    "buy {item}",
    "purchased {item}",
    "{item} carton",
    "{item} packet",
    "{item} box",
    "{item} stock entry",
    "new stock of {item}",
]


def build_augmented_dataset(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, record in data.iterrows():
        item = str(record["Description"]).strip()
        category = str(record["Category"]).strip()
        for template in TEMPLATES:
            rows.append(
                {
                    "Description": template.format(item=item),
                    "Category": category,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    data = pd.read_csv(DATASET_PATH)
    data = data.dropna(subset=["Description", "Category"]).drop_duplicates()
    augmented = build_augmented_dataset(data)
    data = pd.concat([data, augmented], ignore_index=True).drop_duplicates()

    x = data["Description"].astype(str).str.strip()
    y = data["Category"].astype(str).str.strip()

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )

    x_train_vectorized = vectorizer.fit_transform(x_train)
    x_test_vectorized = vectorizer.transform(x_test)

    model = LogisticRegression(max_iter=3000, class_weight="balanced")
    model.fit(x_train_vectorized, y_train)

    predictions = model.predict(x_test_vectorized)
    accuracy = accuracy_score(y_test, predictions)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)

    print("Training rows:", len(x_train))
    print("Test rows:", len(x_test))
    print("Vocabulary size:", len(vectorizer.vocabulary_))
    print(f"Validation accuracy: {accuracy:.4f}")
    print("Categories:", ", ".join(sorted(y.unique())))
    print("\nClassification report:")
    print(classification_report(y_test, predictions))
    print("Artifacts saved to:")
    print(MODEL_PATH)
    print(VECTORIZER_PATH)


if __name__ == "__main__":
    main()
