from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT_DIR / "data" / "ml_dataset.csv"


SUPERMARKET_ROWS = [
    ("rice", "Groceries"),
    ("milk", "Dairy"),
    ("pepsi", "Beverages"),
    ("chips", "Snacks"),
    ("soap", "Household Items"),
    ("shampoo", "Personal Care"),
    ("ice cream", "Frozen Foods"),
    ("bread", "Bakery"),
]


def main() -> None:
    dataframe = pd.DataFrame(SUPERMARKET_ROWS, columns=["Description", "Category"])
    dataframe.to_csv(OUTPUT_PATH, index=False)
    print("Starter supermarket ML dataset saved to:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
