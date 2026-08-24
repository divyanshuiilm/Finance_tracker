"""Basic automated checks for the Student Finance Manager."""

import tempfile
import unittest
from pathlib import Path

import database
from app import app


class FinanceManagerTests(unittest.TestCase):
    """Test key user journeys using a disposable SQLite database."""

    def setUp(self):
        self.temporary_folder = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temporary_folder.name) / "test-finance.db"
        database.initialize_database()
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.client.post(
            "/setup",
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

    def test_transaction_can_be_saved(self):
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

    def test_transaction_export_contains_saved_data(self):
        with database.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO transactions
                    (transaction_type, amount, transaction_date, category, payment_method)
                VALUES ('income', 5000, '2026-08-01', 'Other', 'Bank')
                """
            )

        response = self.client.get("/transactions/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Amount", response.data)
        self.assertIn(b"5000", response.data)


if __name__ == "__main__":
    unittest.main()
