import React, { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE_URL = "http://127.0.0.1:5000";

const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
});

const initialSupplierForm = {
  supplier_name: "",
  contact_number: "",
  address: "",
  category_specialization: "",
};

const initialTransactionForm = {
  supplier_name: "",
  item_name: "",
  category: "",
  quantity: "",
  unit: "units",
  unit_price: "",
  total_amount: "",
  paid_amount: "",
  transaction_date: "",
  notes: "",
};

const initialPaymentForm = {
  supplier_transaction_id: "",
  paid_amount: "",
  payment_date: "",
  payment_note: "",
};

function App() {
  const [suppliers, setSuppliers] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [payments, setPayments] = useState([]);
  const [analytics, setAnalytics] = useState({
    summary: {
      total_purchase_value: 0,
      total_paid_value: 0,
      total_pending_value: 0,
      transaction_count: 0,
      supplier_count: 0,
    },
    category_breakdown: [],
    supplier_due_summary: [],
    top_items: [],
    pending_alerts: [],
  });
  const [supplierForm, setSupplierForm] = useState(initialSupplierForm);
  const [transactionForm, setTransactionForm] = useState(initialTransactionForm);
  const [predictedCategory, setPredictedCategory] = useState("");
  const [paymentForm, setPaymentForm] = useState(initialPaymentForm);
  const [editingPaymentId, setEditingPaymentId] = useState(null);
  const [file, setFile] = useState(null);
  const [supplierFilter, setSupplierFilter] = useState("All");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [searchText, setSearchText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const showMessage = (setter, message) => {
    setter(message);
    window.setTimeout(() => setter(""), 4000);
  };

  const fetchDashboard = async () => {
    const [suppliersResponse, transactionsResponse, analyticsResponse, ledgerResponse, paymentsResponse] =
      await Promise.all([
        fetch(`${API_BASE_URL}/suppliers`),
        fetch(`${API_BASE_URL}/transactions`),
        fetch(`${API_BASE_URL}/analytics`),
        fetch(`${API_BASE_URL}/supplier-ledger`),
        fetch(`${API_BASE_URL}/payments`),
      ]);

    if (
      !suppliersResponse.ok ||
      !transactionsResponse.ok ||
      !analyticsResponse.ok ||
      !ledgerResponse.ok ||
      !paymentsResponse.ok
    ) {
      throw new Error("Unable to load dashboard data.");
    }

    const [suppliersData, transactionsData, analyticsData, ledgerData, paymentsData] =
      await Promise.all([
        suppliersResponse.json(),
        transactionsResponse.json(),
        analyticsResponse.json(),
        ledgerResponse.json(),
        paymentsResponse.json(),
      ]);

    setSuppliers(suppliersData);
    setTransactions(transactionsData);
    setAnalytics(analyticsData);
    setLedger(ledgerData);
    setPayments(paymentsData);
  };

  useEffect(() => {
    fetchDashboard().catch((err) => {
      setError(err.message);
    });
  }, []);

  const handleSupplierFormChange = (field, value) => {
    setSupplierForm((current) => ({ ...current, [field]: value }));
  };

  const handleTransactionFormChange = (field, value) => {
    setTransactionForm((current) => ({ ...current, [field]: value }));
  };

  const handlePaymentFormChange = (field, value) => {
    setPaymentForm((current) => ({ ...current, [field]: value }));
  };

  const handlePredictCategory = async (itemName) => {
    if (!itemName.trim()) {
      setPredictedCategory("");
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/categories/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_name: itemName }),
      });
      const data = await response.json();
      if (response.ok) {
        setPredictedCategory(
          `${data.category} (${Math.round((data.confidence || 0) * 100)}% ${data.source})`
        );
        if (!transactionForm.category) {
          setTransactionForm((current) => ({
            ...current,
            category: data.category !== "Other" ? data.category : "",
          }));
        }
      }
    } catch {
      setPredictedCategory("");
    }
  };

  const handleCreateSupplier = async () => {
    if (!supplierForm.supplier_name.trim()) {
      setError("Supplier name is required.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/suppliers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(supplierForm),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to save supplier.");
      }

      showMessage(setSuccess, `Supplier saved: ${data.supplier_name}`);
      setSupplierForm(initialSupplierForm);
      setTransactionForm((current) => ({
        ...current,
        supplier_name: data.supplier_name,
      }));
      await fetchDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTransaction = async () => {
    const requiredFields = [
      transactionForm.supplier_name,
      transactionForm.item_name,
      transactionForm.quantity,
      transactionForm.total_amount,
      transactionForm.paid_amount,
      transactionForm.transaction_date,
    ];

    if (requiredFields.some((value) => value === "")) {
      setError("Please complete all required stock intake fields.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(transactionForm),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to save transaction.");
      }

      showMessage(
        setSuccess,
        `Recorded ${data.item_name} from ${data.supplier_name}. Pending balance: ${currencyFormatter.format(data.balance_amount)}`
      );
      setTransactionForm(initialTransactionForm);
      setPredictedCategory("");
      await fetchDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadCsv = async () => {
    if (!file) {
      setError("Please choose a CSV file.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE_URL}/upload_csv`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to process CSV.");
      }

      showMessage(
        setSuccess,
        `CSV processed: ${data.inserted_count} inserted, ${data.skipped_count} skipped.`
      );
      setFile(null);
      await fetchDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePayment = async () => {
    if (
      !paymentForm.supplier_transaction_id ||
      !paymentForm.paid_amount ||
      !paymentForm.payment_date
    ) {
      setError("Please complete all required payment fields.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const url = editingPaymentId
        ? `${API_BASE_URL}/payments/${editingPaymentId}`
        : `${API_BASE_URL}/payments`;
      const method = editingPaymentId ? "PUT" : "POST";

      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(paymentForm),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to save payment log.");
      }

      showMessage(
        setSuccess,
        editingPaymentId
          ? `Payment log updated. New balance: ${currencyFormatter.format(data.updated_transaction_balance)}`
          : `Payment added. New balance: ${currencyFormatter.format(data.updated_transaction_balance)}`
      );
      setPaymentForm(initialPaymentForm);
      setEditingPaymentId(null);
      await fetchDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleEditPayment = (payment) => {
    setEditingPaymentId(payment.id);
    setPaymentForm({
      supplier_transaction_id: String(payment.supplier_transaction_id),
      paid_amount: String(payment.paid_amount),
      payment_date: payment.payment_date,
      payment_note: payment.payment_note || "",
    });
  };

  const handleDeletePayment = async (paymentId) => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/payments/${paymentId}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to delete payment log.");
      }

      showMessage(
        setSuccess,
        `Payment deleted. New balance: ${currencyFormatter.format(data.updated_transaction_balance)}`
      );
      if (editingPaymentId === paymentId) {
        setEditingPaymentId(null);
        setPaymentForm(initialPaymentForm);
      }
      await fetchDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const categoryOptions = useMemo(() => {
    const options = new Set(transactions.map((transaction) => transaction.category));
    return ["All", ...Array.from(options)];
  }, [transactions]);

  const dashboardSummary = useMemo(() => {
    const totalPurchaseValue = transactions.reduce(
      (sum, transaction) => sum + Number(transaction.total_amount || 0),
      0
    );
    const totalPaidValue = transactions.reduce(
      (sum, transaction) => sum + Number(transaction.paid_amount || 0),
      0
    );
    const totalPendingValue = transactions.reduce(
      (sum, transaction) => sum + Number(transaction.balance_amount || 0),
      0
    );
    const pendingSupplierCount = new Set(
      transactions
        .filter((transaction) => Number(transaction.balance_amount || 0) > 0)
        .map((transaction) => transaction.supplier_name)
    ).size;

    return {
      totalPurchaseValue,
      totalPaidValue,
      totalPendingValue,
      supplierCount: suppliers.length,
      transactionCount: transactions.length,
      pendingSupplierCount,
    };
  }, [transactions, suppliers]);

  const filteredTransactions = useMemo(() => {
    return transactions.filter((transaction) => {
      const matchesSupplier =
        supplierFilter === "All" || transaction.supplier_name === supplierFilter;
      const matchesCategory =
        categoryFilter === "All" || transaction.category === categoryFilter;
      const query = searchText.trim().toLowerCase();
      const matchesSearch =
        !query ||
        transaction.item_name.toLowerCase().includes(query) ||
        transaction.supplier_name.toLowerCase().includes(query);

      return matchesSupplier && matchesCategory && matchesSearch;
    });
  }, [transactions, supplierFilter, categoryFilter, searchText]);

  return (
    <div className="app-shell">
      <div className="backdrop" />

      <header className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Supermarket Ledger</span>
          <h1>Supplier Intake & Payment Record Book</h1>
          <p>
            Record every supplier delivery, auto-categorize supermarket items,
            track partial payments, and monitor which agencies still need to be paid.
          </p>
        </div>
        <div className="hero-highlight card">
          <p className="mini-label">Total pending dues</p>
          <h2>{currencyFormatter.format(dashboardSummary.totalPendingValue || 0)}</h2>
          <p className="hero-stat">{dashboardSummary.supplierCount || 0} suppliers</p>
          <p className="helper-text">
            {dashboardSummary.transactionCount || 0} stock intake transaction
            {dashboardSummary.transactionCount === 1 ? "" : "s"} recorded.
          </p>
        </div>
      </header>

      {(success || error) && (
        <div className="message-stack">
          {success && <div className="message success">{success}</div>}
          {error && <div className="message error">{error}</div>}
        </div>
      )}

      <main className="dashboard-grid">
        <section className="stats-grid">
          <article className="metric-card card">
            <span className="mini-label">Purchase value</span>
            <strong>{currencyFormatter.format(dashboardSummary.totalPurchaseValue || 0)}</strong>
          </article>
          <article className="metric-card card">
            <span className="mini-label">Paid so far</span>
            <strong>{currencyFormatter.format(dashboardSummary.totalPaidValue || 0)}</strong>
          </article>
          <article className="metric-card card">
            <span className="mini-label">Pending balance</span>
            <strong>{currencyFormatter.format(dashboardSummary.totalPendingValue || 0)}</strong>
          </article>
          <article className="metric-card card">
            <span className="mini-label">Pending suppliers</span>
            <strong>{dashboardSummary.pendingSupplierCount || 0}</strong>
          </article>
        </section>

        <section className="content-grid">
          <div className="card supplier-panel">
            <h2>Add supplier</h2>
            <p className="section-text">
              Register an agency once, then reuse it for future stock intake entries.
            </p>

            <label className="field">
              <span>Supplier name</span>
              <input
                className="input-field"
                value={supplierForm.supplier_name}
                onChange={(event) =>
                  handleSupplierFormChange("supplier_name", event.target.value)
                }
              />
            </label>

            <div className="split-fields">
              <label className="field">
                <span>Contact number</span>
                <input
                  className="input-field"
                  value={supplierForm.contact_number}
                  onChange={(event) =>
                    handleSupplierFormChange("contact_number", event.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Category specialization</span>
                <input
                  className="input-field"
                  placeholder="Groceries, Dairy, Snacks..."
                  value={supplierForm.category_specialization}
                  onChange={(event) =>
                    handleSupplierFormChange("category_specialization", event.target.value)
                  }
                />
              </label>
            </div>

            <label className="field">
              <span>Address</span>
              <input
                className="input-field"
                value={supplierForm.address}
                onChange={(event) => handleSupplierFormChange("address", event.target.value)}
              />
            </label>

            <button className="btn btn-primary" onClick={handleCreateSupplier} disabled={loading}>
              {loading ? "Saving..." : "Save supplier"}
            </button>
          </div>

          <div className="card transaction-panel">
            <h2>Record stock intake</h2>
            <p className="section-text">
              Save item delivery, quantity, supplier payment, and remaining due.
            </p>

            <div className="split-fields">
              <label className="field">
                <span>Supplier</span>
                <input
                  className="input-field"
                  list="supplier-list"
                  value={transactionForm.supplier_name}
                  onChange={(event) =>
                    handleTransactionFormChange("supplier_name", event.target.value)
                  }
                />
                <datalist id="supplier-list">
                  {suppliers.map((supplier) => (
                    <option key={supplier.id} value={supplier.supplier_name} />
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span>Item name</span>
                <input
                  className="input-field"
                  placeholder="Rice, milk, biscuits, pepsi..."
                  value={transactionForm.item_name}
                  onChange={(event) => {
                    handleTransactionFormChange("item_name", event.target.value);
                    handlePredictCategory(event.target.value);
                  }}
                />
              </label>
            </div>

            <div className="split-fields">
              <label className="field">
                <span>Category</span>
                <input
                  className="input-field"
                  placeholder="Auto-fill or manual override"
                  value={transactionForm.category}
                  onChange={(event) =>
                    handleTransactionFormChange("category", event.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Quantity</span>
                <input
                  className="input-field"
                  type="number"
                  value={transactionForm.quantity}
                  onChange={(event) =>
                    handleTransactionFormChange("quantity", event.target.value)
                  }
                />
              </label>
            </div>

            <div className="split-fields">
              <label className="field">
                <span>Unit</span>
                <input
                  className="input-field"
                  placeholder="kg, litres, packets..."
                  value={transactionForm.unit}
                  onChange={(event) => handleTransactionFormChange("unit", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Unit price</span>
                <input
                  className="input-field"
                  type="number"
                  value={transactionForm.unit_price}
                  onChange={(event) =>
                    handleTransactionFormChange("unit_price", event.target.value)
                  }
                />
              </label>
            </div>

            <div className="split-fields">
              <label className="field">
                <span>Total amount (INR)</span>
                <input
                  className="input-field"
                  type="number"
                  value={transactionForm.total_amount}
                  onChange={(event) =>
                    handleTransactionFormChange("total_amount", event.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Paid amount (INR)</span>
                <input
                  className="input-field"
                  type="number"
                  value={transactionForm.paid_amount}
                  onChange={(event) =>
                    handleTransactionFormChange("paid_amount", event.target.value)
                  }
                />
              </label>
            </div>

            <div className="split-fields">
              <label className="field">
                <span>Transaction date</span>
                <input
                  className="input-field"
                  type="date"
                  value={transactionForm.transaction_date}
                  onChange={(event) =>
                    handleTransactionFormChange("transaction_date", event.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Notes</span>
                <input
                  className="input-field"
                  value={transactionForm.notes}
                  onChange={(event) => handleTransactionFormChange("notes", event.target.value)}
                />
              </label>
            </div>

            <button className="btn btn-primary" onClick={handleCreateTransaction} disabled={loading}>
              {loading ? "Saving..." : "Save stock entry"}
            </button>

            {predictedCategory && (
              <div className="prediction-box">
                <span className="mini-label">Suggested category</span>
                <strong>{predictedCategory}</strong>
              </div>
            )}
          </div>
        </section>

        <section className="content-grid">
          <div className="card upload-panel">
            <h2>Bulk CSV import</h2>
            <p className="section-text">
              Upload supplier records using columns like `supplier_name`, `item_name`,
              `quantity`, `total_amount`, `paid_amount`, and `transaction_date`.
            </p>

            <div className="upload-dropzone">
              <input
                id="file-input"
                type="file"
                accept=".csv"
                onChange={(event) => setFile(event.target.files[0])}
              />
              <label htmlFor="file-input">
                {file ? file.name : "Choose CSV file"}
              </label>
            </div>

            <button className="btn btn-secondary" onClick={handleUploadCsv} disabled={loading}>
              {loading ? "Uploading..." : "Upload CSV"}
            </button>
          </div>

          <div className="card alerts-panel">
            <h2>Pending due alerts</h2>
            <p className="section-text">
              Suppliers with outstanding balances are highlighted here.
            </p>

            {analytics.pending_alerts.length === 0 ? (
              <p className="empty-copy">No pending dues right now.</p>
            ) : (
              <div className="alert-list">
                {analytics.pending_alerts.slice(0, 5).map((alert) => (
                  <div className="alert-card" key={alert.supplier_name}>
                    <span>{alert.supplier_name}</span>
                    <strong>{currencyFormatter.format(alert.pending_balance)}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="content-grid">
          <div className="card payment-entry-panel">
            <h2>Update due payment</h2>
            <p className="section-text">
              Record an extra payment against an old supplier entry until the due balance becomes zero.
            </p>

            <label className="field">
              <span>Supplier transaction</span>
              <select
                className="input-field"
                value={paymentForm.supplier_transaction_id}
                onChange={(event) =>
                  handlePaymentFormChange("supplier_transaction_id", event.target.value)
                }
                disabled={Boolean(editingPaymentId)}
              >
                <option value="">Select a transaction</option>
                {transactions
                  .filter((transaction) => transaction.balance_amount > 0 || editingPaymentId)
                  .map((transaction) => (
                    <option key={transaction.id} value={transaction.id}>
                      {transaction.supplier_name} - {transaction.item_name} - Pending{" "}
                      {currencyFormatter.format(transaction.balance_amount)}
                    </option>
                  ))}
              </select>
            </label>

            <div className="split-fields">
              <label className="field">
                <span>Paid amount (INR)</span>
                <input
                  className="input-field"
                  type="number"
                  value={paymentForm.paid_amount}
                  onChange={(event) =>
                    handlePaymentFormChange("paid_amount", event.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Payment date</span>
                <input
                  className="input-field"
                  type="date"
                  value={paymentForm.payment_date}
                  onChange={(event) =>
                    handlePaymentFormChange("payment_date", event.target.value)
                  }
                />
              </label>
            </div>

            <label className="field">
              <span>Payment note</span>
              <input
                className="input-field"
                value={paymentForm.payment_note}
                onChange={(event) =>
                  handlePaymentFormChange("payment_note", event.target.value)
                }
              />
            </label>

            <div className="button-row">
              <button className="btn btn-primary" onClick={handleSavePayment} disabled={loading}>
                {loading ? "Saving..." : editingPaymentId ? "Update payment" : "Add payment"}
              </button>
              {editingPaymentId && (
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setEditingPaymentId(null);
                    setPaymentForm(initialPaymentForm);
                  }}
                  disabled={loading}
                >
                  Cancel edit
                </button>
              )}
            </div>
          </div>

          <div className="card due-panel">
            <h2>Open dues</h2>
            <p className="section-text">
              These supplier entries still have pending balances. Add payments here until they are fully cleared.
            </p>

            {transactions.filter((transaction) => transaction.balance_amount > 0).length === 0 ? (
              <p className="empty-copy">All supplier transactions are fully paid.</p>
            ) : (
              <div className="alert-list">
                {transactions
                  .filter((transaction) => transaction.balance_amount > 0)
                  .slice(0, 6)
                  .map((transaction) => (
                    <div className="alert-card" key={transaction.id}>
                      <div>
                        <strong>{transaction.supplier_name}</strong>
                        <span>
                          {transaction.item_name} | Pending{" "}
                          {currencyFormatter.format(transaction.balance_amount)}
                        </span>
                      </div>
                      <button
                        className="mini-action"
                        onClick={() =>
                          setPaymentForm({
                            supplier_transaction_id: String(transaction.id),
                            paid_amount: "",
                            payment_date: "",
                            payment_note: "",
                          })
                        }
                      >
                        Pay now
                      </button>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </section>

        <section className="insights-grid">
          <div className="card">
            <div className="section-heading">
              <h2>Category-wise purchases</h2>
              <p>Understand which supermarket categories cost the most.</p>
            </div>

            {analytics.category_breakdown.length === 0 ? (
              <p className="empty-copy">No category data yet.</p>
            ) : (
              <div className="bars">
                {analytics.category_breakdown.map((item) => {
                  const maxAmount = analytics.category_breakdown[0]?.amount || 0;
                  return (
                    <div className="bar-row" key={item.category}>
                      <div className="bar-head">
                        <span>{item.category}</span>
                        <span>{currencyFormatter.format(item.amount)}</span>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{
                            width: `${maxAmount ? (item.amount / maxAmount) * 100 : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="card">
            <div className="section-heading">
              <h2>Top received items</h2>
              <p>Quick view of the highest-volume stock intake items.</p>
            </div>

            {analytics.top_items.length === 0 ? (
              <p className="empty-copy">No intake quantities recorded yet.</p>
            ) : (
              <div className="trend-grid">
                {analytics.top_items.map((item) => (
                  <div className="trend-card" key={item.item_name}>
                    <span className="mini-label">{item.item_name}</span>
                    <strong>{item.quantity_received}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="card ledger-panel">
          <div className="history-header">
            <div>
              <h2>Supplier ledger</h2>
              <p>Track purchases, payments, and pending balances supplier-wise.</p>
            </div>
          </div>

          {ledger.length === 0 ? (
            <p className="empty-copy">No suppliers or ledger records found.</p>
          ) : (
            <div className="table-wrapper">
              <table className="transactions-table">
                <thead>
                  <tr>
                    <th>Supplier</th>
                    <th>Purchases</th>
                    <th>Paid</th>
                    <th>Pending</th>
                    <th>Entries</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.map((entry) => (
                    <tr key={entry.supplier_id}>
                      <td>{entry.supplier_name}</td>
                      <td>{currencyFormatter.format(entry.total_purchase)}</td>
                      <td>{currencyFormatter.format(entry.total_paid)}</td>
                      <td>{currencyFormatter.format(entry.total_pending)}</td>
                      <td>{entry.transaction_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card history-panel">
          <div className="history-header">
            <div>
              <h2>Stock intake history</h2>
              <p>Search and filter entries by supplier, category, or item.</p>
            </div>
            <div className="history-filters">
              <input
                className="input-field compact"
                placeholder="Search item or supplier"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
              />
              <select
                className="input-field compact"
                value={supplierFilter}
                onChange={(event) => setSupplierFilter(event.target.value)}
              >
                <option value="All">All suppliers</option>
                {suppliers.map((supplier) => (
                  <option key={supplier.id} value={supplier.supplier_name}>
                    {supplier.supplier_name}
                  </option>
                ))}
              </select>
              <select
                className="input-field compact"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                {categoryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {filteredTransactions.length === 0 ? (
            <p className="empty-copy">No stock entries match the current filters.</p>
          ) : (
            <div className="table-wrapper">
              <table className="transactions-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Supplier</th>
                    <th>Item</th>
                    <th>Category</th>
                    <th>Qty</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td>{transaction.transaction_date}</td>
                      <td>{transaction.supplier_name}</td>
                      <td>{transaction.item_name}</td>
                      <td>
                        <span className="category-pill">{transaction.category}</span>
                      </td>
                      <td>
                        {transaction.quantity} {transaction.unit}
                      </td>
                      <td>{currencyFormatter.format(transaction.total_amount)}</td>
                      <td>{currencyFormatter.format(transaction.paid_amount)}</td>
                      <td>{currencyFormatter.format(transaction.balance_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card payments-panel">
          <div className="history-header">
            <div>
              <h2>Payment history</h2>
              <p>Every payment made to a supplier is stored for audit and follow-up.</p>
            </div>
          </div>

          {payments.length === 0 ? (
            <p className="empty-copy">No payment history recorded yet.</p>
          ) : (
            <div className="table-wrapper">
              <table className="transactions-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Supplier</th>
                    <th>Item</th>
                    <th>Paid amount</th>
                    <th>Note</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.payment_date}</td>
                      <td>{payment.supplier_name}</td>
                      <td>{payment.item_name}</td>
                      <td>{currencyFormatter.format(payment.paid_amount)}</td>
                      <td>{payment.payment_note}</td>
                      <td>
                        <div className="table-actions">
                          <button
                            className="mini-action"
                            onClick={() => handleEditPayment(payment)}
                          >
                            Edit
                          </button>
                          <button
                            className="mini-action danger"
                            onClick={() => handleDeletePayment(payment.id)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
