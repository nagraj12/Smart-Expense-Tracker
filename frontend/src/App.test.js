import { render, screen } from "@testing-library/react";
import App from "./App";

beforeEach(() => {
  global.fetch = jest.fn((url) => {
    if (url.toString().includes("/suppliers")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }

    if (url.toString().includes("/transactions")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }

    if (url.toString().includes("/analytics")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
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
          }),
      });
    }

    if (url.toString().includes("/supplier-ledger")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }

    if (url.toString().includes("/payments")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }

    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    });
  });
});

afterEach(() => {
  jest.resetAllMocks();
});

test("renders supplier ledger heading", async () => {
  render(<App />);
  expect(await screen.findByText(/supplier intake & payment record book/i)).toBeInTheDocument();
});
