"""The starting point for the Student Finance Manager web application."""

import csv
import os
import secrets
from datetime import date, datetime
from functools import wraps
from io import StringIO

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, initialize_database
from services.calculations import get_analytics_data, get_dashboard_data
from services.ocr_parser import parse_upi_text
from services.ai_assistant import handle_assistant_query


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "student-finance-manager-secure-key-2026"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Make sure the local database and its tables exist before the app is used.
initialize_database()


@app.context_processor
def inject_globals():
    """Provide CSRF token and logged-in user information to all templates."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {
        "csrf_token": session["csrf_token"],
        "current_user": session.get("username"),
    }


def login_required(view):
    """Redirect visitors to the login page unless they have an active session."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def validate_csrf():
    """Verify CSRF token on POST requests."""
    if app.config.get("TESTING"):
        return
    token = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRFToken")
        or (request.is_json and (request.get_json(silent=True) or {}).get("csrf_token"))
    )
    if not token or token != session.get("csrf_token"):
        abort(400, description="Invalid or missing CSRF token.")


@app.before_request
def check_csrf():
    """Enforce CSRF verification for all state-changing requests."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        validate_csrf()


@app.post("/transactions/parse-ocr")
@login_required
def parse_ocr():
    """Accept OCR text and return structured transaction candidate fields."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return {"error": "No OCR text provided."}, 400

    parsed_result = parse_upi_text(text)
    return parsed_result


@app.post("/api/assistant")
@login_required
def api_assistant():
    """Process user natural language financial inquiries and return data-backed explanations."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return {"error": "Query cannot be empty."}, 400

    user_id = session["user_id"]
    response = handle_assistant_query(user_id, query)
    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user account."""
    if "user_id" in session:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")

        if len(username) < 3:
            error = "Choose a username with at least 3 characters."
        elif len(password) < 8:
            error = "Choose a password with at least 8 characters."
        elif password != confirmation:
            error = "The passwords do not match."
        else:
            try:
                with get_connection() as connection:
                    cursor = connection.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, generate_password_hash(password)),
                    )
                    user_id = cursor.lastrowid
                session.clear()
                session["user_id"] = user_id
                session["username"] = username
                return redirect(url_for("home"))
            except Exception:
                error = f"The username '{username}' is already taken. Please choose another."

    return render_template("register.html", error=error)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Alias for initial registration."""
    return redirect(url_for("register"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Sign in to an existing account."""
    if "user_id" in session:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_connection() as connection:
            user = connection.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Incorrect username or password."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("home"))

    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    """End the current browser session."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    """Show the application's first page."""
    user_id = session["user_id"]
    return render_template("index.html", dashboard=get_dashboard_data(user_id))


@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    """Create a transaction and display the saved transaction history."""
    user_id = session["user_id"]
    error = None

    if request.method == "POST":
        transaction_type = request.form.get("transaction_type", "")
        amount_text = request.form.get("amount", "").strip()
        transaction_date = request.form.get("transaction_date", "")
        category = request.form.get("category", "")
        payment_method = request.form.get("payment_method", "")
        merchant = request.form.get("merchant", "").strip()
        note = request.form.get("note", "").strip()

        allowed_types = {"income", "expense"}
        allowed_categories = {
            "Food", "Transport", "College", "Entertainment", "Shopping",
            "Bills", "Health", "Investment", "Savings", "Other",
        }
        allowed_payment_methods = {"UPI", "Cash", "Card", "Bank", "Other"}

        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0

        if transaction_type not in allowed_types:
            error = "Choose whether this is income or an expense."
        elif amount <= 0:
            error = "Enter an amount greater than ₹0."
        elif not transaction_date:
            error = "Choose the transaction date."
        elif category not in allowed_categories:
            error = "Choose a valid category."
        elif payment_method not in allowed_payment_methods:
            error = "Choose a valid payment method."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO transactions
                        (user_id, transaction_type, amount, transaction_date, category,
                         payment_method, merchant, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, transaction_type, amount, transaction_date, category,
                     payment_method, merchant or None, note or None),
                )
            return redirect(url_for("transactions"))

    filters = {
        "search": request.args.get("search", "").strip(),
        "transaction_type": request.args.get("transaction_type", ""),
        "category": request.args.get("category", ""),
        "payment_method": request.args.get("payment_method", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
    }
    where_clauses = ["user_id = ?"]
    query_values = [user_id]

    if filters["search"]:
        search_value = f"%{filters['search']}%"
        where_clauses.append("(merchant LIKE ? OR note LIKE ? OR category LIKE ?)")
        query_values.extend([search_value, search_value, search_value])
    if filters["transaction_type"] in {"income", "expense"}:
        where_clauses.append("transaction_type = ?")
        query_values.append(filters["transaction_type"])
    if filters["category"] in {
        "Food", "Transport", "College", "Entertainment", "Shopping",
        "Bills", "Health", "Investment", "Savings", "Other",
    }:
        where_clauses.append("category = ?")
        query_values.append(filters["category"])
    if filters["payment_method"] in {"UPI", "Cash", "Card", "Bank", "Other"}:
        where_clauses.append("payment_method = ?")
        query_values.append(filters["payment_method"])
    if filters["date_from"]:
        where_clauses.append("transaction_date >= ?")
        query_values.append(filters["date_from"])
    if filters["date_to"]:
        where_clauses.append("transaction_date <= ?")
        query_values.append(filters["date_to"])

    query = "SELECT * FROM transactions WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY transaction_date DESC, id DESC"

    with get_connection() as connection:
        saved_transactions = connection.execute(query, query_values).fetchall()

    return render_template(
        "transactions.html",
        transactions=saved_transactions,
        today=date.today().isoformat(),
        error=error,
        filters=filters,
    )


@app.post("/transactions/<int:transaction_id>/delete")
@login_required
def delete_transaction(transaction_id):
    """Remove one transaction belonging to the logged-in user."""
    user_id = session["user_id"]
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id),
        )

    # Return to the previous page (dashboard or transactions page)
    return redirect(request.referrer or url_for("transactions"))


@app.get("/transactions/export")
@login_required
def export_transactions():
    """Download a portable CSV backup of the logged-in user's transactions."""
    user_id = session["user_id"]
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT transaction_type, amount, transaction_date, category,
                   payment_method, merchant, note
            FROM transactions
            WHERE user_id = ?
            ORDER BY transaction_date DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    csv_file = StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(["Type", "Amount", "Date", "Category", "Payment method", "Merchant/person", "Note"])
    for row in rows:
        writer.writerow([
            row["transaction_type"],
            row["amount"],
            row["transaction_date"],
            row["category"],
            row["payment_method"],
            row["merchant"] or "",
            row["note"] or "",
        ])

    return Response(
        csv_file.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=student-finance-transactions.csv"},
    )


@app.route("/transactions/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    """Display and update one saved transaction belonging to the user."""
    user_id = session["user_id"]
    with get_connection() as connection:
        transaction = connection.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id),
        ).fetchone()

    if transaction is None:
        abort(404)

    error = None
    if request.method == "POST":
        transaction_type = request.form.get("transaction_type", "")
        amount_text = request.form.get("amount", "").strip()
        transaction_date = request.form.get("transaction_date", "")
        category = request.form.get("category", "")
        payment_method = request.form.get("payment_method", "")
        merchant = request.form.get("merchant", "").strip()
        note = request.form.get("note", "").strip()

        allowed_types = {"income", "expense"}
        allowed_categories = {
            "Food", "Transport", "College", "Entertainment", "Shopping",
            "Bills", "Health", "Investment", "Savings", "Other",
        }
        allowed_payment_methods = {"UPI", "Cash", "Card", "Bank", "Other"}

        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0

        if transaction_type not in allowed_types:
            error = "Choose whether this is income or an expense."
        elif amount <= 0:
            error = "Enter an amount greater than ₹0."
        elif not transaction_date:
            error = "Choose the transaction date."
        elif category not in allowed_categories:
            error = "Choose a valid category."
        elif payment_method not in allowed_payment_methods:
            error = "Choose a valid payment method."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE transactions
                    SET transaction_type = ?, amount = ?, transaction_date = ?,
                        category = ?, payment_method = ?, merchant = ?, note = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (transaction_type, amount, transaction_date, category,
                     payment_method, merchant or None, note or None, transaction_id, user_id),
                )
            return redirect(url_for("transactions"))

        transaction = {
            "id": transaction_id,
            "transaction_type": transaction_type,
            "amount": amount_text,
            "transaction_date": transaction_date,
            "category": category,
            "payment_method": payment_method,
            "merchant": merchant,
            "note": note,
        }

    return render_template("edit_transaction.html", transaction=transaction, error=error)


@app.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    """Set monthly budgets and show how much has been used."""
    user_id = session["user_id"]
    current_month = date.today().strftime("%Y-%m")
    selected_month = request.args.get("month", current_month)
    error = None
    categories = [
        "Food", "Transport", "College", "Entertainment", "Shopping",
        "Bills", "Health", "Investment", "Savings", "Other",
    ]

    if request.method == "POST":
        budget_month = request.form.get("budget_month", "")
        category = request.form.get("category", "") or None
        amount_text = request.form.get("amount", "").strip()

        try:
            amount = float(amount_text)
        except ValueError:
            amount = -1

        if len(budget_month) != 7 or budget_month[4] != "-":
            error = "Choose a valid budget month."
        elif category is not None and category not in categories:
            error = "Choose a valid category."
        elif amount < 0:
            error = "Enter a budget amount of ₹0 or more."
        else:
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM budgets WHERE user_id = ? AND budget_month = ? AND category IS ?",
                    (user_id, budget_month, category),
                )
                connection.execute(
                    "INSERT INTO budgets (user_id, budget_month, category, amount) VALUES (?, ?, ?, ?)",
                    (user_id, budget_month, category, amount),
                )
            return redirect(url_for("budgets", month=budget_month))

    with get_connection() as connection:
        saved_budgets = connection.execute(
            "SELECT category, amount FROM budgets WHERE user_id = ? AND budget_month = ?",
            (user_id, selected_month),
        ).fetchall()
        spending_rows = connection.execute(
            """
            SELECT category, SUM(amount) AS spent
            FROM transactions
            WHERE user_id = ?
              AND transaction_type = 'expense'
              AND substr(transaction_date, 1, 7) = ?
            GROUP BY category
            """,
            (user_id, selected_month),
        ).fetchall()

    spending_by_category = {row["category"]: float(row["spent"]) for row in spending_rows}
    overall_spending = sum(spending_by_category.values())
    budget_rows = []
    for budget in saved_budgets:
        spent = overall_spending if budget["category"] is None else spending_by_category.get(budget["category"], 0)
        amount = float(budget["amount"])
        percent_used = (spent / amount * 100) if amount else (100 if spent else 0)
        budget_rows.append({
            "label": budget["category"] or "Overall monthly budget",
            "amount": amount,
            "spent": spent,
            "remaining": amount - spent,
            "percent_used": percent_used,
        })

    return render_template(
        "budgets.html",
        categories=categories,
        selected_month=selected_month,
        current_month=current_month,
        budgets=budget_rows,
        error=error,
    )


@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    """Create savings goals and display their progress."""
    user_id = session["user_id"]
    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        target_text = request.form.get("target_amount", "").strip()
        saved_text = request.form.get("saved_amount", "").strip()
        deadline = request.form.get("deadline", "")

        try:
            target_amount = float(target_text)
            saved_amount = float(saved_text or 0)
        except ValueError:
            target_amount = -1
            saved_amount = -1

        if not name:
            error = "Enter a name for your savings goal."
        elif target_amount <= 0:
            error = "Enter a target amount greater than ₹0."
        elif saved_amount < 0:
            error = "Saved amount cannot be negative."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO savings_goals (user_id, name, target_amount, saved_amount, deadline)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, name, target_amount, saved_amount, deadline or None),
                )
            return redirect(url_for("goals"))

    with get_connection() as connection:
        saved_goals = connection.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY deadline IS NULL, deadline, id DESC",
            (user_id,),
        ).fetchall()

    displayed_goals = []
    today = date.today()
    for goal in saved_goals:
        target_amount = float(goal["target_amount"])
        saved_amount = float(goal["saved_amount"])
        remaining_amount = max(0, target_amount - saved_amount)
        percent_complete = min(100, (saved_amount / target_amount) * 100) if target_amount > 0 else 0
        suggested_monthly = None
        deadline_label = "No deadline set"

        if goal["deadline"]:
            deadline_date = datetime.strptime(goal["deadline"], "%Y-%m-%d").date()
            months_remaining = (
                (deadline_date.year - today.year) * 12
                + deadline_date.month - today.month + 1
            )
            if months_remaining > 0:
                suggested_monthly = remaining_amount / months_remaining
                deadline_label = deadline_date.strftime("%d %b %Y")
            else:
                deadline_label = f"Deadline passed: {deadline_date.strftime('%d %b %Y')}"

        displayed_goals.append({
            "id": goal["id"],
            "name": goal["name"],
            "target_amount": target_amount,
            "saved_amount": saved_amount,
            "remaining_amount": remaining_amount,
            "percent_complete": percent_complete,
            "suggested_monthly": suggested_monthly,
            "deadline_label": deadline_label,
        })

    return render_template("goals.html", goals=displayed_goals, error=error)


@app.post("/goals/<int:goal_id>/contributions")
@login_required
def add_goal_contribution(goal_id):
    """Add a saved amount to one goal's progress."""
    user_id = session["user_id"]
    amount_text = request.form.get("amount", "").strip()
    try:
        amount = float(amount_text)
    except ValueError:
        amount = 0

    if amount > 0:
        with get_connection() as connection:
            connection.execute(
                "UPDATE savings_goals SET saved_amount = saved_amount + ? WHERE id = ? AND user_id = ?",
                (amount, goal_id, user_id),
            )

    return redirect(url_for("goals"))


@app.route("/recurring", methods=["GET", "POST"])
@login_required
def recurring_transactions():
    """Create and display recurring income and expense commitments."""
    user_id = session["user_id"]
    error = None
    categories = [
        "Food", "Transport", "College", "Entertainment", "Shopping",
        "Bills", "Health", "Investment", "Savings", "Other",
    ]
    payment_methods = ["UPI", "Cash", "Card", "Bank", "Other"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        transaction_type = request.form.get("transaction_type", "")
        amount_text = request.form.get("amount", "").strip()
        category = request.form.get("category", "")
        payment_method = request.form.get("payment_method", "")
        next_due_date = request.form.get("next_due_date", "")

        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0

        if not name:
            error = "Enter a name, such as Spotify or monthly SIP."
        elif transaction_type not in {"income", "expense"}:
            error = "Choose income or expense."
        elif amount <= 0:
            error = "Enter an amount greater than ₹0."
        elif category not in categories or payment_method not in payment_methods:
            error = "Choose a valid category and payment method."
        elif not next_due_date:
            error = "Choose the next due date."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO recurring_transactions
                        (user_id, name, transaction_type, amount, category, payment_method,
                         frequency, next_due_date)
                    VALUES (?, ?, ?, ?, ?, ?, 'monthly', ?)
                    """,
                    (user_id, name, transaction_type, amount, category, payment_method, next_due_date),
                )
            return redirect(url_for("recurring_transactions"))

    with get_connection() as connection:
        recurring_items = connection.execute(
            "SELECT * FROM recurring_transactions WHERE user_id = ? ORDER BY is_active DESC, next_due_date, id DESC",
            (user_id,),
        ).fetchall()

    return render_template(
        "recurring.html",
        recurring_items=recurring_items,
        categories=categories,
        payment_methods=payment_methods,
        today=date.today().isoformat(),
        error=error,
    )


@app.post("/recurring/<int:recurring_id>/toggle")
@login_required
def toggle_recurring_transaction(recurring_id):
    """Pause or reactivate a recurring commitment."""
    user_id = session["user_id"]
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE recurring_transactions
            SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
            WHERE id = ? AND user_id = ?
            """,
            (recurring_id, user_id),
        )
    return redirect(url_for("recurring_transactions"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Store the financial guardrails used in safe-to-spend planning."""
    user_id = session["user_id"]
    error = None

    if request.method == "POST":
        buffer_text = request.form.get("emergency_buffer", "").strip()
        savings_text = request.form.get("monthly_savings_target", "").strip()
        try:
            emergency_buffer = float(buffer_text)
            monthly_savings_target = float(savings_text)
        except ValueError:
            emergency_buffer = -1
            monthly_savings_target = -1

        if emergency_buffer < 0 or monthly_savings_target < 0:
            error = "Enter ₹0 or more for both settings."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO settings (user_id, emergency_buffer, monthly_savings_target)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        emergency_buffer = excluded.emergency_buffer,
                        monthly_savings_target = excluded.monthly_savings_target
                    """,
                    (user_id, emergency_buffer, monthly_savings_target),
                )
            return redirect(url_for("settings"))

    with get_connection() as connection:
        saved_settings = connection.execute(
            "SELECT emergency_buffer, monthly_savings_target FROM settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return render_template(
        "settings.html",
        settings=saved_settings or {"emergency_buffer": 0, "monthly_savings_target": 0},
        error=error,
    )


@app.route("/debts", methods=["GET", "POST"])
@login_required
def debts():
    """Record money lent to others or borrowed from others."""
    user_id = session["user_id"]
    error = None
    if request.method == "POST":
        debt_type = request.form.get("debt_type", "")
        person = request.form.get("person", "").strip()
        amount_text = request.form.get("amount", "").strip()
        due_date = request.form.get("due_date", "")
        note = request.form.get("note", "").strip()
        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0

        if debt_type not in {"lent", "borrowed"}:
            error = "Choose lent or borrowed."
        elif not person:
            error = "Enter the person's name."
        elif amount <= 0:
            error = "Enter an amount greater than ₹0."
        else:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO debts (user_id, debt_type, person, amount, due_date, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, debt_type, person, amount, due_date or None, note or None),
                )
            return redirect(url_for("debts"))

    with get_connection() as connection:
        saved_debts = connection.execute(
            "SELECT * FROM debts WHERE user_id = ? ORDER BY status = 'paid', due_date IS NULL, due_date, id DESC",
            (user_id,),
        ).fetchall()

    lent_outstanding = sum(
        float(item["amount"]) for item in saved_debts
        if item["debt_type"] == "lent" and item["status"] != "paid"
    )
    borrowed_outstanding = sum(
        float(item["amount"]) for item in saved_debts
        if item["debt_type"] == "borrowed" and item["status"] != "paid"
    )
    return render_template(
        "debts.html",
        debts=saved_debts,
        lent_outstanding=lent_outstanding,
        borrowed_outstanding=borrowed_outstanding,
        error=error,
    )


@app.post("/debts/<int:debt_id>/mark-paid")
@login_required
def mark_debt_paid(debt_id):
    """Mark a debt as settled without altering ordinary spending history."""
    user_id = session["user_id"]
    with get_connection() as connection:
        connection.execute(
            "UPDATE debts SET status = 'paid' WHERE id = ? AND user_id = ?",
            (debt_id, user_id),
        )
    return redirect(url_for("debts"))


@app.get("/analytics")
@login_required
def analytics():
    """Show monthly financial summaries and rule-based insights."""
    user_id = session["user_id"]
    return render_template("analytics.html", analytics=get_analytics_data(user_id))


if __name__ == "__main__":
    app.run(debug=True)
