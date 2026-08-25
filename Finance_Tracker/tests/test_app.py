"""Automated checks for the Student Finance Manager."""

import tempfile
import unittest
from pathlib import Path

import database
from app import app
from services.ocr_parser import parse_upi_text
from services.ai_assistant import handle_assistant_query


class FinanceManagerTests(unittest.TestCase):
    """Test key user journeys using a disposable SQLite database."""

    def setUp(self):
        self.temporary_folder = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temporary_folder.name) / "test-finance.db"
        database.initialize_database()
        app.config["TESTING"] = True
        self.client = app.test_client()

        # Register default user
        self.client.post(
            "/register",
            data={
                "username": "test-user",
                "password": "test-password-123",
                "confirmation": "test-password-123",
            },
        )

    def tearDown(self):
        database.DATABASE_PATH = self.original_database_path
        self.temporary_folder.cleanup()

    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student Finance Manager", response.data)
        self.assertIn(b"test-user", response.data)

    def test_transaction_can_be_saved_and_displayed(self):
        response = self.client.post(
            "/transactions",
            data={
                "transaction_type": "expense",
                "amount": "120",
                "transaction_date": "2026-08-24",
                "category": "Food",
                "payment_method": "UPI",
                "merchant": "College canteen",
                "note": "Lunch",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"College canteen", response.data)

        # Check that it appears on the dashboard with delete action
        dashboard_response = self.client.get("/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn(b"College canteen", dashboard_response.data)
        self.assertIn(b"Delete", dashboard_response.data)

    def test_transaction_can_be_deleted(self):
        # Create a transaction
        self.client.post(
            "/transactions",
            data={
                "transaction_type": "expense",
                "amount": "250",
                "transaction_date": "2026-08-25",
                "category": "Food",
                "payment_method": "UPI",
                "merchant": "Mistaken Expense",
                "note": "To be deleted",
            },
            follow_redirects=True,
        )

        with database.get_connection() as connection:
            txn = connection.execute(
                "SELECT id FROM transactions WHERE merchant = 'Mistaken Expense'"
            ).fetchone()
            self.assertIsNotNone(txn)
            txn_id = txn["id"]

        # Delete the transaction
        delete_response = self.client.post(
            f"/transactions/{txn_id}/delete",
            follow_redirects=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertNotIn(b"Mistaken Expense", delete_response.data)

    def test_multi_user_data_isolation(self):
        """Verify that User B cannot see or manipulate User A's financial data."""
        # User A adds a transaction
        self.client.post(
            "/transactions",
            data={
                "transaction_type": "income",
                "amount": "15000",
                "transaction_date": "2026-08-01",
                "category": "Other",
                "payment_method": "Bank",
                "merchant": "Secret Salary",
            },
            follow_redirects=True,
        )

        with database.get_connection() as connection:
            txn_a = connection.execute(
                "SELECT id FROM transactions WHERE merchant = 'Secret Salary'"
            ).fetchone()
            txn_a_id = txn_a["id"]

        # Log out User A
        self.client.get("/logout")

        # Register and log in User B
        self.client.post(
            "/register",
            data={
                "username": "user-b",
                "password": "password-456",
                "confirmation": "password-456",
            },
            follow_redirects=True,
        )

        # User B dashboard should be clean and not show User A's data
        response_b = self.client.get("/")
        self.assertEqual(response_b.status_code, 200)
        self.assertIn(b"user-b", response_b.data)
        self.assertNotIn(b"Secret Salary", response_b.data)
        self.assertIn(b"0.00", response_b.data)

        # User B attempts to delete User A's transaction (IDOR attempt)
        self.client.post(f"/transactions/{txn_a_id}/delete", follow_redirects=True)

        # Verify transaction still exists for User A in the database
        with database.get_connection() as connection:
            txn_still_there = connection.execute(
                "SELECT id FROM transactions WHERE id = ?", (txn_a_id,)
            ).fetchone()
            self.assertIsNotNone(txn_still_there)

    def test_transaction_export_contains_only_current_user_data(self):
        # User A adds transaction
        self.client.post(
            "/transactions",
            data={
                "transaction_type": "income",
                "amount": "5000",
                "transaction_date": "2026-08-01",
                "category": "Other",
                "payment_method": "Bank",
                "merchant": "UserA Earnings",
            },
            follow_redirects=True,
        )

        response = self.client.get("/transactions/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"UserA Earnings", response.data)
        self.assertIn(b"5000", response.data)

    def test_ocr_parser_gpay_receipt(self):
        raw_text = """
        Google Pay
        Paid to Swiggy
        ₹340.00
        Completed · 24 Aug 2026
        UPI transaction ID: 423847293847
        """
        parsed = parse_upi_text(raw_text)
        self.assertEqual(parsed["amount"], 340.0)
        self.assertEqual(parsed["transaction_type"], "expense")
        self.assertEqual(parsed["category"], "Food")
        self.assertEqual(parsed["transaction_date"], "2026-08-24")
        self.assertIn("Swiggy", parsed["merchant"])

    def test_ocr_parser_phonepe_uber_receipt(self):
        raw_text = """
        PhonePe
        Payment to Uber India
        ₹215.50
        25 Aug 2026, 09:30 AM
        Transaction Successful
        """
        parsed = parse_upi_text(raw_text)
        self.assertEqual(parsed["amount"], 215.5)
        self.assertEqual(parsed["category"], "Transport")
        self.assertIn("Uber", parsed["merchant"])

    def test_ocr_parse_endpoint(self):
        response = self.client.post(
            "/transactions/parse-ocr",
            json={"text": "Paid to Bescom ₹1,200 on 15 Aug 2026"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["amount"], 1200.0)
        self.assertEqual(data["category"], "Bills")
        self.assertEqual(data["transaction_date"], "2026-08-15")

    def test_ai_assistant_affordability_when_affordable(self):
        # Add income of ₹10,000
        self.client.post(
            "/transactions",
            data={
                "transaction_type": "income",
                "amount": "10000",
                "transaction_date": "2026-08-01",
                "category": "Other",
                "payment_method": "Bank",
            },
        )

        with database.get_connection() as connection:
            user = connection.execute("SELECT id FROM users WHERE username = 'test-user'").fetchone()
            user_id = user["id"]

        result = handle_assistant_query(user_id, "Can I afford ₹500 shoes?")
        self.assertIn("Yes, you can comfortably afford", result["reply"])
        self.assertIn("500.00", result["reply"])

    def test_ai_assistant_affordability_when_unaffordable(self):
        # User has ₹0 balance
        with database.get_connection() as connection:
            user = connection.execute("SELECT id FROM users WHERE username = 'test-user'").fetchone()
            user_id = user["id"]

        result = handle_assistant_query(user_id, "Can I buy 5000 laptop?")
        self.assertIn("Caution: Buying", result["reply"])
        self.assertIn("exceeds your safe-to-spend allowance", result["reply"])

    def test_ai_assistant_api_endpoint(self):
        response = self.client.post(
            "/api/assistant",
            json={"query": "Where did most of my money go this month?"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("reply", data)
        self.assertIn("suggestions", data)


if __name__ == "__main__":
    unittest.main()
