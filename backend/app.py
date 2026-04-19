from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import pandas as pd
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

try:
    from .database import create_connection, create_table
    from .ml_service import ExpenseClassifier
except ImportError:
    from database import create_connection, create_table
    from ml_service import ExpenseClassifier


app = Flask(__name__)
CORS(app)
create_table()
classifier = ExpenseClassifier()


def error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def serialize_supplier(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "supplier_name": row["supplier_name"],
        "contact_number": row["contact_number"],
        "address": row["address"],
        "category_specialization": row["category_specialization"],
        "created_at": row["created_at"],
    }


def serialize_transaction(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "supplier_id": row["supplier_id"],
        "supplier_name": row["supplier_name"],
        "item_name": row["item_name"],
        "category": row["category"],
        "quantity": float(row["quantity"]),
        "unit": row["unit"],
        "unit_price": float(row["unit_price"]) if row["unit_price"] is not None else None,
        "total_amount": float(row["total_amount"]),
        "paid_amount": float(row["paid_amount"]),
        "balance_amount": float(row["balance_amount"]),
        "transaction_date": row["transaction_date"],
        "due_date": row["due_date"],
        "notes": row["notes"],
        "category_confidence": round(float(row["category_confidence"] or 0), 4),
        "category_source": row["category_source"] or "rule-based",
        "created_at": row["created_at"],
    }


def serialize_payment(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "supplier_transaction_id": row["supplier_transaction_id"],
        "supplier_name": row["supplier_name"],
        "item_name": row["item_name"],
        "paid_amount": float(row["paid_amount"]),
        "payment_date": row["payment_date"],
        "payment_mode": row["payment_mode"],
        "payment_note": row["payment_note"],
        "created_at": row["created_at"],
    }


def detect_duplicate_transaction(cursor: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT st.*, s.supplier_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
        WHERE lower(s.supplier_name) = lower(?)
          AND lower(st.item_name) = lower(?)
          AND st.transaction_date = ?
          AND ABS(st.total_amount - ?) < 0.01
          AND ABS(st.quantity - ?) < 0.001
        ORDER BY st.id DESC
        LIMIT 1
        """,
        (
            payload["supplier_name"],
            payload["item_name"],
            payload["transaction_date"],
            payload["total_amount"],
            payload["quantity"],
        ),
    )
    return cursor.fetchone()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def recalculate_transaction_payment_state(
    cursor: Any, supplier_transaction_id: int
) -> dict[str, float]:
    """Calculate and update payment totals for a transaction."""
    cursor.execute(
        """
        SELECT total_amount FROM supplier_transactions WHERE id = ?
        """,
        (supplier_transaction_id,),
    )
    transaction = cursor.fetchone()
    if not transaction:
        return {"paid_amount": 0.0, "balance_amount": 0.0}

    total_amount = float(transaction["total_amount"])
    
    cursor.execute(
        """
        SELECT COALESCE(SUM(paid_amount), 0) AS total_paid
        FROM payments
        WHERE supplier_transaction_id = ?
        """,
        (supplier_transaction_id,),
    )
    payment = cursor.fetchone()
    paid_amount = float(payment["total_paid"] or 0)
    balance_amount = round(total_amount - paid_amount, 2)
    
    cursor.execute(
        """
        UPDATE supplier_transactions
        SET paid_amount = ?, balance_amount = ?
        WHERE id = ?
        """,
        (paid_amount, balance_amount, supplier_transaction_id),
    )
    
    return {"paid_amount": paid_amount, "balance_amount": balance_amount}


def create_payment_log(payload: dict[str, Any]) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT total_amount
        FROM supplier_transactions
        WHERE id = ?
        """,
        (supplier_transaction_id,),
    )
    transaction_row = cursor.fetchone()
    total_amount = float(transaction_row["total_amount"]) if transaction_row else 0.0

    cursor.execute(
        """
        SELECT COALESCE(SUM(paid_amount), 0) AS total_paid
        FROM payments
        WHERE supplier_transaction_id = ?
        """,
        (supplier_transaction_id,),
    )
    payment_row = cursor.fetchone()
    total_paid = round(float(payment_row["total_paid"] or 0), 2)
    balance_amount = round(total_amount - total_paid, 2)

    cursor.execute(
        """
        UPDATE supplier_transactions
        SET paid_amount = ?, balance_amount = ?
        WHERE id = ?
        """,
        (total_paid, balance_amount, supplier_transaction_id),
    )
    return {"paid_amount": total_paid, "balance_amount": balance_amount}


def get_or_create_supplier(
    supplier_name: str,
    contact_number: str = "",
    address: str = "",
    category_specialization: str = "",
) -> int:
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM suppliers WHERE lower(supplier_name) = lower(?)",
        (supplier_name,),
    )
    row = cursor.fetchone()
    if row:
        supplier_id = row["id"]
        cursor.execute(
            """
            UPDATE suppliers
            SET contact_number = COALESCE(NULLIF(?, ''), contact_number),
                address = COALESCE(NULLIF(?, ''), address),
                category_specialization = COALESCE(NULLIF(?, ''), category_specialization)
            WHERE id = ?
            """,
            (contact_number, address, category_specialization, supplier_id),
        )
        conn.commit()
        conn.close()
        return supplier_id

    cursor.execute(
        """
        INSERT INTO suppliers (supplier_name, contact_number, address, category_specialization)
        VALUES (?, ?, ?, ?)
        """,
        (supplier_name, contact_number or None, address or None, category_specialization or None),
    )
    supplier_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return supplier_id


def insert_supplier_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    supplier_id = get_or_create_supplier(
        payload["supplier_name"],
        payload.get("contact_number", ""),
        payload.get("address", ""),
        payload.get("category_specialization", ""),
    )

    category = str(payload.get("category", "")).strip()
    prediction = classifier.predict(payload["item_name"])
    final_category = category or prediction["category"]
    final_confidence = 1.0 if category else prediction["confidence"]
    final_source = "manual" if category else prediction["source"]

    quantity = float(payload["quantity"])
    total_amount = float(payload["total_amount"])
    paid_amount = float(payload["paid_amount"])
    balance_amount = round(total_amount - paid_amount, 2)
    if payload.get("unit_price") in (None, ""):
        unit_price = round(total_amount / quantity, 2) if quantity else None
    else:
        unit_price = float(payload["unit_price"])

    conn = create_connection()
    cursor = conn.cursor()
    duplicate_row = detect_duplicate_transaction(cursor, payload)
    duplicate_match = serialize_transaction(duplicate_row) if duplicate_row else None

    cursor.execute(
        """
        INSERT INTO supplier_transactions (
            supplier_id,
            item_name,
            category,
            quantity,
            unit,
            unit_price,
            total_amount,
            paid_amount,
            balance_amount,
            transaction_date,
            due_date,
            notes,
            category_confidence,
            category_source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            supplier_id,
            payload["item_name"].strip(),
            final_category,
            quantity,
            payload.get("unit", "units").strip() or "units",
            unit_price,
            total_amount,
            paid_amount,
            balance_amount,
            payload["transaction_date"],
            payload.get("due_date"),
            payload.get("notes", "").strip() or None,
            final_confidence,
            final_source,
        ),
    )
    transaction_id = cursor.lastrowid

    if paid_amount > 0:
        cursor.execute(
            """
            INSERT INTO payments (
                supplier_transaction_id, supplier_id, paid_amount, payment_date, payment_mode, payment_note
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                supplier_id,
                paid_amount,
                payload["transaction_date"],
                payload.get("payment_mode"),
                payload.get("payment_note", "Initial payment") or "Initial payment",
            ),
        )

    recalculate_transaction_payment_state(cursor, transaction_id)

    conn.commit()
    cursor.execute(
        """
        SELECT st.*, s.supplier_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
        WHERE st.id = ?
        """,
        (transaction_id,),
    )
    row = cursor.fetchone()
    conn.close()

    result = serialize_transaction(row)
    result["review_needed"] = False if category else prediction["review_needed"]
    result["duplicate_detected"] = duplicate_match is not None
    result["duplicate_match"] = duplicate_match
    return result


def create_payment_log(payload: dict[str, Any]) -> dict[str, Any]:
    supplier_transaction_id = int(payload["supplier_transaction_id"])
    paid_amount = round(float(payload["paid_amount"]), 2)

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT st.id, st.supplier_id, st.total_amount, s.supplier_name, st.item_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
        WHERE st.id = ?
        """,
        (supplier_transaction_id,),
    )
    transaction_row = cursor.fetchone()
    if not transaction_row:
        conn.close()
        raise ValueError("Supplier transaction not found.")

    cursor.execute(
        """
        INSERT INTO payments (
            supplier_transaction_id, supplier_id, paid_amount, payment_date, payment_mode, payment_note
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            supplier_transaction_id,
            transaction_row["supplier_id"],
            paid_amount,
            payload["payment_date"],
            payload.get("payment_mode"),
            payload.get("payment_note", "").strip() or None,
        ),
    )
    payment_id = cursor.lastrowid
    totals = recalculate_transaction_payment_state(cursor, supplier_transaction_id)
    conn.commit()

    cursor.execute(
        """
        SELECT p.*, s.supplier_name, st.item_name
        FROM payments p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN supplier_transactions st ON st.id = p.supplier_transaction_id
        WHERE p.id = ?
        """,
        (payment_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return {
        "id": row["id"],
        "supplier_transaction_id": row["supplier_transaction_id"],
        "supplier_name": row["supplier_name"],
        "item_name": row["item_name"],
        "paid_amount": float(row["paid_amount"]),
        "payment_date": row["payment_date"],
        "payment_note": row["payment_note"],
        "updated_transaction_paid_amount": totals["paid_amount"],
        "updated_transaction_balance": totals["balance_amount"],
    }


def update_payment_log(payment_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise ValueError("Payment record not found.")

    paid_amount = round(float(payload["paid_amount"]), 2)
    cursor.execute(
        """
        UPDATE payments
        SET paid_amount = ?, payment_date = ?, payment_mode = ?, payment_note = ?
        WHERE id = ?
        """,
        (
            paid_amount,
            payload["payment_date"],
            payload.get("payment_mode"),
            payload.get("payment_note", "").strip() or None,
            payment_id,
        ),
    )

    totals = recalculate_transaction_payment_state(cursor, existing["supplier_transaction_id"])
    conn.commit()

    cursor.execute(
        """
        SELECT p.*, s.supplier_name, st.item_name
        FROM payments p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN supplier_transactions st ON st.id = p.supplier_transaction_id
        WHERE p.id = ?
        """,
        (payment_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return {
        "id": row["id"],
        "supplier_transaction_id": row["supplier_transaction_id"],
        "supplier_name": row["supplier_name"],
        "item_name": row["item_name"],
        "paid_amount": float(row["paid_amount"]),
        "payment_date": row["payment_date"],
        "payment_note": row["payment_note"],
        "updated_transaction_paid_amount": totals["paid_amount"],
        "updated_transaction_balance": totals["balance_amount"],
    }


def delete_payment_log(payment_id: int) -> dict[str, Any]:
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, s.supplier_name, st.item_name
        FROM payments p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN supplier_transactions st ON st.id = p.supplier_transaction_id
        WHERE p.id = ?
        """,
        (payment_id,),
    )
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise ValueError("Payment record not found.")

    cursor.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    totals = recalculate_transaction_payment_state(cursor, existing["supplier_transaction_id"])
    conn.commit()
    conn.close()

    return {
        "deleted_payment_id": payment_id,
        "supplier_transaction_id": existing["supplier_transaction_id"],
        "supplier_name": existing["supplier_name"],
        "item_name": existing["item_name"],
        "updated_transaction_paid_amount": totals["paid_amount"],
        "updated_transaction_balance": totals["balance_amount"],
    }


def calculate_analytics(rows: list[Any]) -> dict[str, Any]:
    total_purchase_value = round(sum(float(row["total_amount"]) for row in rows), 2)
    total_paid_value = round(sum(float(row["paid_amount"]) for row in rows), 2)
    total_pending_value = round(sum(float(row["balance_amount"]) for row in rows), 2)
    category_totals: dict[str, float] = defaultdict(float)
    supplier_balances: dict[str, float] = defaultdict(float)
    inventory_totals: dict[str, float] = defaultdict(float)
    monthly_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "total_purchase": 0.0,
            "total_paid": 0.0,
            "total_pending": 0.0,
            "transaction_count": 0,
        }
    )
    category_counts: dict[str, int] = defaultdict(int)
    duplicate_groups: dict[tuple[str, str, str, float, float], list[Any]] = {}
    due_date_reminders: list[dict[str, Any]] = []

    for row in rows:
        category_totals[row["category"]] += float(row["total_amount"])
        supplier_balances[row["supplier_name"]] += float(row["balance_amount"])
        inventory_totals[row["item_name"]] += float(row["quantity"])

        month_key = "unknown"
        parsed_date = parse_date(row["transaction_date"])
        if parsed_date:
            month_key = parsed_date.strftime("%Y-%m")
        monthly_totals[month_key]["total_purchase"] += float(row["total_amount"])
        monthly_totals[month_key]["total_paid"] += float(row["paid_amount"])
        monthly_totals[month_key]["total_pending"] += float(row["balance_amount"])
        monthly_totals[month_key]["transaction_count"] += 1

        category_counts[row["category"]] += 1

        duplicate_key = (
            row["supplier_name"].strip().lower(),
            row["item_name"].strip().lower(),
            row["transaction_date"],
            round(float(row["total_amount"]), 2),
            round(float(row["quantity"]), 3),
        )
        duplicate_groups.setdefault(duplicate_key, []).append(row)

        due_date = parse_date(row["due_date"])
        if due_date and float(row["balance_amount"]) > 0:
            days_until_due = (due_date.date() - datetime.utcnow().date()).days
            if days_until_due <= 7:
                due_date_reminders.append(
                    {
                        "transaction_id": row["id"],
                        "supplier_name": row["supplier_name"],
                        "item_name": row["item_name"],
                        "balance_amount": round(float(row["balance_amount"]), 2),
                        "due_date": row["due_date"],
                        "status": "overdue" if days_until_due < 0 else "due_soon",
                        "days_until_due": days_until_due,
                    }
                )

    category_breakdown = sorted(
        (
            {"category": name, "amount": round(amount, 2)}
            for name, amount in category_totals.items()
        ),
        key=lambda item: item["amount"],
        reverse=True,
    )

    supplier_due_summary = sorted(
        (
            {"supplier_name": name, "pending_balance": round(amount, 2)}
            for name, amount in supplier_balances.items()
        ),
        key=lambda item: item["pending_balance"],
        reverse=True,
    )

    top_items = sorted(
        (
            {"item_name": name, "quantity_received": round(quantity, 2)}
            for name, quantity in inventory_totals.items()
        ),
        key=lambda item: item["quantity_received"],
        reverse=True,
    )[:5]

    monthly_insights = [
        {
            "month": month,
            "total_purchase": round(data["total_purchase"], 2),
            "total_paid": round(data["total_paid"], 2),
            "total_pending": round(data["total_pending"], 2),
            "transaction_count": data["transaction_count"],
        }
        for month, data in sorted(monthly_totals.items())
    ]

    category_avg = {
        category: (category_totals[category] / category_counts[category])
        for category in category_totals
        if category_counts[category] > 0
    }

    anomaly_alerts = []
    for row in rows:
        avg_amount = category_avg.get(row["category"], 0)
        amount = float(row["total_amount"])
        if avg_amount > 0 and amount >= avg_amount * 2.0:
            anomaly_alerts.append(
                {
                    "transaction_id": row["id"],
                    "supplier_name": row["supplier_name"],
                    "item_name": row["item_name"],
                    "category": row["category"],
                    "total_amount": amount,
                    "average_category_amount": round(avg_amount, 2),
                    "reason": "High amount compared to category average",
                }
            )

    duplicate_entries = [
        {
            "supplier_name": group[0]["supplier_name"],
            "item_name": group[0]["item_name"],
            "transaction_date": group[0]["transaction_date"],
            "total_amount": round(float(group[0]["total_amount"]), 2),
            "quantity": round(float(group[0]["quantity"]), 3),
            "count": len(group),
            "transaction_ids": [row["id"] for row in group],
        }
        for group in duplicate_groups.values()
        if len(group) > 1
    ]

    return {
        "summary": {
            "total_purchase_value": total_purchase_value,
            "total_paid_value": total_paid_value,
            "total_pending_value": total_pending_value,
            "transaction_count": len(rows),
            "supplier_count": len(supplier_balances),
        },
        "category_breakdown": category_breakdown,
        "supplier_due_summary": supplier_due_summary,
        "top_items": top_items,
        "pending_alerts": [item for item in supplier_due_summary if item["pending_balance"] > 0],
        "monthly_insights": monthly_insights,
        "due_date_reminders": sorted(due_date_reminders, key=lambda item: item["days_until_due"]),
        "anomaly_alerts": anomaly_alerts,
        "duplicate_entries": duplicate_entries,
    }


def normalize_csv_columns(df: pd.DataFrame) -> dict[str, str]:
    return {column.lower().strip(): column for column in df.columns}


@app.route("/")
def home():
    return jsonify(
        {
            "message": "Supermarket Supplier Ledger Backend Running",
            "endpoints": [
                "/suppliers",
                "/transactions",
                "/analytics",
                "/supplier-ledger",
                "/payments",
                "/categories/predict",
                "/upload_csv",
                "/export/supplier-statement?format=excel&supplier_id=<id>",
                "/export/supplier-statement?format=pdf&supplier_id=<id>",
            ],
        }
    )


@app.route("/suppliers", methods=["GET"])
def get_suppliers():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY supplier_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([serialize_supplier(row) for row in rows])


@app.route("/suppliers", methods=["POST"])
def create_supplier():
    data = request.get_json(silent=True) or {}
    supplier_name = str(data.get("supplier_name", "")).strip()
    if not supplier_name:
        return error_response("Supplier name is required.")

    supplier_id = get_or_create_supplier(
        supplier_name,
        str(data.get("contact_number", "")).strip(),
        str(data.get("address", "")).strip(),
        str(data.get("category_specialization", "")).strip(),
    )

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    row = cursor.fetchone()
    conn.close()
    return jsonify(serialize_supplier(row)), 201


@app.route("/categories/predict", methods=["POST"])
def predict_category():
    data = request.get_json(silent=True) or {}
    item_name = str(data.get("item_name", "")).strip()
    if not item_name:
        return error_response("Item name is required.")
    return jsonify(classifier.predict(item_name))


@app.route("/transactions", methods=["POST"])
def create_transaction():
    data = request.get_json(silent=True) or {}

    required_fields = {
        "supplier_name": "Supplier name is required.",
        "item_name": "Item name is required.",
        "quantity": "Quantity is required.",
        "total_amount": "Total amount is required.",
        "paid_amount": "Paid amount is required.",
        "transaction_date": "Transaction date is required.",
    }

    for field, message in required_fields.items():
        if data.get(field) in (None, ""):
            return error_response(message)

    try:
        quantity = float(data["quantity"])
        total_amount = float(data["total_amount"])
        paid_amount = float(data["paid_amount"])
    except (TypeError, ValueError):
        return error_response("Quantity, total amount, and paid amount must be valid numbers.")

    if quantity <= 0:
        return error_response("Quantity must be greater than zero.")
    if total_amount < 0 or paid_amount < 0:
        return error_response("Amounts cannot be negative.")
    if paid_amount > total_amount:
        return error_response("Paid amount cannot be greater than total amount.")

    transaction = insert_supplier_transaction(
        {
            **data,
            "quantity": quantity,
            "total_amount": total_amount,
            "paid_amount": paid_amount,
        }
    )
    return jsonify(transaction), 201


@app.route("/transactions", methods=["GET"])
def get_transactions():
    supplier_name = request.args.get("supplier_name")
    category = request.args.get("category")

    query = """
        SELECT st.*, s.supplier_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
    """
    filters = []
    params: list[Any] = []

    if supplier_name:
        filters.append("lower(s.supplier_name) = lower(?)")
        params.append(supplier_name)
    if category:
        filters.append("lower(st.category) = lower(?)")
        params.append(category)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY st.transaction_date DESC, st.id DESC"

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return jsonify([serialize_transaction(row) for row in rows])


@app.route("/supplier-ledger", methods=["GET"])
def get_supplier_ledger():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            s.id,
            s.supplier_name,
            COALESCE(SUM(st.total_amount), 0) AS total_purchase,
            COALESCE(SUM(st.paid_amount), 0) AS total_paid,
            COALESCE(SUM(st.balance_amount), 0) AS total_pending,
            COUNT(st.id) AS transaction_count
        FROM suppliers s
        LEFT JOIN supplier_transactions st ON st.supplier_id = s.id
        GROUP BY s.id, s.supplier_name
        ORDER BY total_pending DESC, s.supplier_name ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    ledger = [
        {
            "supplier_id": row["id"],
            "supplier_name": row["supplier_name"],
            "total_purchase": round(float(row["total_purchase"]), 2),
            "total_paid": round(float(row["total_paid"]), 2),
            "total_pending": round(float(row["total_pending"]), 2),
            "transaction_count": row["transaction_count"],
        }
        for row in rows
    ]
    return jsonify(ledger)


@app.route("/payments", methods=["GET"])
def get_payments():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, s.supplier_name, st.item_name
        FROM payments p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN supplier_transactions st ON st.id = p.supplier_transaction_id
        ORDER BY p.payment_date DESC, p.id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    return jsonify(
        [
            {
                "id": row["id"],
                "supplier_transaction_id": row["supplier_transaction_id"],
                "supplier_name": row["supplier_name"],
                "item_name": row["item_name"],
                "paid_amount": float(row["paid_amount"]),
                "payment_date": row["payment_date"],
                "payment_mode": row["payment_mode"],
                "payment_note": row["payment_note"],
            }
            for row in rows
        ]
    )


@app.route("/payments", methods=["POST"])
def create_payment():
    data = request.get_json(silent=True) or {}
    if data.get("supplier_transaction_id") in (None, ""):
        return error_response("Supplier transaction id is required.")
    if data.get("paid_amount") in (None, ""):
        return error_response("Paid amount is required.")
    if not str(data.get("payment_date", "")).strip():
        return error_response("Payment date is required.")

    try:
        supplier_transaction_id = int(data["supplier_transaction_id"])
        paid_amount = float(data["paid_amount"])
    except (TypeError, ValueError):
        return error_response("Supplier transaction id and paid amount must be valid numbers.")

    if paid_amount <= 0:
        return error_response("Paid amount must be greater than zero.")

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT total_amount, paid_amount
        FROM supplier_transactions
        WHERE id = ?
        """,
        (supplier_transaction_id,),
    )
    transaction_row = cursor.fetchone()
    conn.close()
    if not transaction_row:
        return error_response("Supplier transaction not found.", 404)

    remaining_balance = round(
        float(transaction_row["total_amount"]) - float(transaction_row["paid_amount"]), 2
    )
    if paid_amount > remaining_balance:
        return error_response("Paid amount cannot be greater than remaining balance.")

    try:
        payment = create_payment_log(
            {
                "supplier_transaction_id": supplier_transaction_id,
                "paid_amount": paid_amount,
                "payment_date": str(data["payment_date"]).strip(),
                "payment_mode": str(data.get("payment_mode", "")).strip() or None,
                "payment_note": str(data.get("payment_note", "")).strip(),
            }
        )
    except ValueError as exc:
        return error_response(str(exc), 404)

    return jsonify(payment), 201


@app.route("/payments/<int:payment_id>", methods=["PUT"])
def edit_payment(payment_id: int):
    data = request.get_json(silent=True) or {}
    if data.get("paid_amount") in (None, ""):
        return error_response("Paid amount is required.")
    if not str(data.get("payment_date", "")).strip():
        return error_response("Payment date is required.")

    try:
        paid_amount = float(data["paid_amount"])
    except (TypeError, ValueError):
        return error_response("Paid amount must be a valid number.")

    if paid_amount <= 0:
        return error_response("Paid amount must be greater than zero.")

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    existing_payment = cursor.fetchone()
    if not existing_payment:
        conn.close()
        return error_response("Payment record not found.", 404)

    cursor.execute(
        """
        SELECT total_amount
        FROM supplier_transactions
        WHERE id = ?
        """,
        (existing_payment["supplier_transaction_id"],),
    )
    transaction_row = cursor.fetchone()
    cursor.execute(
        """
        SELECT COALESCE(SUM(paid_amount), 0) AS total_paid
        FROM payments
        WHERE supplier_transaction_id = ? AND id != ?
        """,
        (existing_payment["supplier_transaction_id"], payment_id),
    )
    other_payments_row = cursor.fetchone()
    conn.close()

    other_payments_total = float(other_payments_row["total_paid"] or 0)
    if paid_amount + other_payments_total > float(transaction_row["total_amount"]):
        return error_response("Updated paid amount would exceed the transaction total.")

    try:
        payment = update_payment_log(
            payment_id,
            {
                "paid_amount": paid_amount,
                "payment_date": str(data["payment_date"]).strip(),
                "payment_mode": str(data.get("payment_mode", "")).strip() or None,
                "payment_note": str(data.get("payment_note", "")).strip(),
            },
        )
    except ValueError as exc:
        return error_response(str(exc), 404)

    return jsonify(payment)


@app.route("/payments/<int:payment_id>", methods=["DELETE"])
def remove_payment(payment_id: int):
    try:
        result = delete_payment_log(payment_id)
    except ValueError as exc:
        return error_response(str(exc), 404)
    return jsonify(result)


@app.route("/analytics", methods=["GET"])
def get_analytics():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT st.*, s.supplier_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
        ORDER BY st.transaction_date ASC, st.id ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return jsonify(calculate_analytics(rows))


@app.route("/export/supplier-statement", methods=["GET"])
def export_supplier_statement():
    supplier_id = request.args.get("supplier_id")
    supplier_name = request.args.get("supplier_name")
    export_format = str(request.args.get("format", "excel")).strip().lower()

    if not supplier_id and not supplier_name:
        return error_response("supplier_id or supplier_name is required for export.")

    conn = create_connection()
    cursor = conn.cursor()
    if supplier_id:
        cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    else:
        cursor.execute("SELECT * FROM suppliers WHERE lower(supplier_name) = lower(?)", (supplier_name,))
    supplier_row = cursor.fetchone()
    if not supplier_row:
        conn.close()
        return error_response("Supplier not found.", 404)

    supplier_id = supplier_row["id"]
    supplier_name = supplier_row["supplier_name"]

    cursor.execute(
        """
        SELECT st.*, s.supplier_name
        FROM supplier_transactions st
        JOIN suppliers s ON s.id = st.supplier_id
        WHERE s.id = ?
        ORDER BY st.transaction_date ASC, st.id ASC
        """,
        (supplier_id,),
    )
    transactions = cursor.fetchall()

    cursor.execute(
        """
        SELECT p.*, s.supplier_name, st.item_name
        FROM payments p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN supplier_transactions st ON st.id = p.supplier_transaction_id
        WHERE s.id = ?
        ORDER BY p.payment_date ASC, p.id ASC
        """,
        (supplier_id,),
    )
    payments = cursor.fetchall()
    conn.close()

    transaction_rows = [
        {
            "Transaction ID": row["id"],
            "Item Name": row["item_name"],
            "Category": row["category"],
            "Quantity": float(row["quantity"]),
            "Unit": row["unit"],
            "Unit Price": float(row["unit_price"]) if row["unit_price"] is not None else None,
            "Total Amount": float(row["total_amount"]),
            "Paid Amount": float(row["paid_amount"]),
            "Balance Amount": float(row["balance_amount"]),
            "Transaction Date": row["transaction_date"],
            "Due Date": row["due_date"],
            "Notes": row["notes"],
        }
        for row in transactions
    ]

    payment_rows = [
        {
            "Payment ID": row["id"],
            "Transaction ID": row["supplier_transaction_id"],
            "Item Name": row["item_name"],
            "Paid Amount": float(row["paid_amount"]),
            "Payment Date": row["payment_date"],
            "Payment Mode": row["payment_mode"],
            "Payment Note": row["payment_note"],
        }
        for row in payments
    ]

    if export_format == "pdf":
        if FPDF is None:
            return error_response("PDF export requires the fpdf package. Install it in requirements.")

        pdf = FPDF()
        pdf.set_auto_page_break(True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Supplier Statement: {supplier_name}", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
        pdf.ln(4)

        if transaction_rows:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, "Transactions", ln=True)
            pdf.set_font("Arial", "", 10)
            for row in transaction_rows:
                pdf.multi_cell(
                    0,
                    6,
                    f"#{row['Transaction ID']} | {row['Transaction Date']} | {row['Item Name']} | Total: {row['Total Amount']} | Paid: {row['Paid Amount']} | Balance: {row['Balance Amount']} | Due: {row['Due Date']}",
                )
                pdf.ln(1)
        else:
            pdf.cell(0, 8, "No transactions available.", ln=True)

        if payment_rows:
            pdf.ln(4)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, "Payments", ln=True)
            pdf.set_font("Arial", "", 10)
            for row in payment_rows:
                pdf.multi_cell(
                    0,
                    6,
                    f"#{row['Payment ID']} | {row['Payment Date']} | {row['Item Name']} | Amount: {row['Paid Amount']} | Mode: {row['Payment Mode'] or 'N/A'}",
                )
                pdf.ln(1)

        pdf_buffer = BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)
        filename = f"{supplier_name.replace(' ', '_')}_statement.pdf"
        return send_file(
            pdf_buffer,
            download_name=filename,
            as_attachment=True,
            mimetype="application/pdf",
        )

    report = pd.DataFrame(transaction_rows)
    report_writer = BytesIO()
    try:
        with pd.ExcelWriter(report_writer, engine="openpyxl") as writer:
            report.to_excel(writer, sheet_name="Transactions", index=False)
            if payment_rows:
                pd.DataFrame(payment_rows).to_excel(writer, sheet_name="Payments", index=False)
        report_writer.seek(0)
        filename = f"{supplier_name.replace(' ', '_')}_statement.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        report_writer = BytesIO()
        report.to_csv(report_writer, index=False)
        report_writer.seek(0)
        filename = f"{supplier_name.replace(' ', '_')}_statement.csv"
        mimetype = "text/csv"

    return send_file(
        report_writer,
        download_name=filename,
        as_attachment=True,
        mimetype=mimetype,
    )


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file:
        return error_response("CSV file is required.")

    df = pd.read_csv(file)
    columns = normalize_csv_columns(df)
    required_columns = {"supplier_name", "item_name", "quantity", "total_amount", "paid_amount", "transaction_date"}
    if not required_columns.issubset(columns):
        return error_response(
            "CSV must contain supplier_name, item_name, quantity, total_amount, paid_amount, and transaction_date columns."
        )

    inserted_count = 0
    skipped_rows = []

    for index, row in df.iterrows():
        payload = {
            "supplier_name": str(row[columns["supplier_name"]]).strip(),
            "item_name": str(row[columns["item_name"]]).strip(),
            "category": str(row[columns["category"]]).strip() if "category" in columns and pd.notna(row[columns["category"]]) else "",
            "quantity": row[columns["quantity"]],
            "unit": str(row[columns["unit"]]).strip() if "unit" in columns and pd.notna(row[columns["unit"]]) else "units",
            "unit_price": row[columns["unit_price"]] if "unit_price" in columns and pd.notna(row[columns["unit_price"]]) else None,
            "total_amount": row[columns["total_amount"]],
            "paid_amount": row[columns["paid_amount"]],
            "transaction_date": str(row[columns["transaction_date"]]).strip(),
            "due_date": str(row[columns["due_date"]]).strip() if "due_date" in columns and pd.notna(row[columns["due_date"]]) else None,
            "payment_mode": str(row[columns["payment_mode"]]).strip() if "payment_mode" in columns and pd.notna(row[columns["payment_mode"]]) else None,
            "notes": str(row[columns["notes"]]).strip() if "notes" in columns and pd.notna(row[columns["notes"]]) else "",
            "contact_number": str(row[columns["contact_number"]]).strip() if "contact_number" in columns and pd.notna(row[columns["contact_number"]]) else "",
            "address": str(row[columns["address"]]).strip() if "address" in columns and pd.notna(row[columns["address"]]) else "",
            "category_specialization": str(row[columns["category_specialization"]]).strip() if "category_specialization" in columns and pd.notna(row[columns["category_specialization"]]) else "",
        }

        if not payload["supplier_name"] or not payload["item_name"] or not payload["transaction_date"]:
            skipped_rows.append({"row": index + 2, "reason": "Missing required values"})
            continue

        try:
            payload["quantity"] = float(payload["quantity"])
            payload["total_amount"] = float(payload["total_amount"])
            payload["paid_amount"] = float(payload["paid_amount"])
            if payload["unit_price"] not in (None, ""):
                payload["unit_price"] = float(payload["unit_price"])
        except (TypeError, ValueError):
            skipped_rows.append({"row": index + 2, "reason": "Invalid numeric values"})
            continue

        if payload["quantity"] <= 0 or payload["paid_amount"] > payload["total_amount"]:
            skipped_rows.append({"row": index + 2, "reason": "Invalid quantity or paid amount"})
            continue

        insert_supplier_transaction(payload)
        inserted_count += 1

    return jsonify(
        {
            "message": "CSV processed successfully",
            "inserted_count": inserted_count,
            "skipped_count": len(skipped_rows),
            "skipped_rows": skipped_rows[:10],
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
