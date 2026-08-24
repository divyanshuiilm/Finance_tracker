"""Read-only finance calculations used by dashboard pages."""

from calendar import monthrange
from datetime import date, timedelta

from database import get_connection


def get_dashboard_data():
    """Return the figures needed to display the dashboard for today."""
    today = date.today()
    current_month = today.strftime("%Y-%m")
    last_day_of_month = date(today.year, today.month, monthrange(today.year, today.month)[1])

    with get_connection() as connection:
        lifetime = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount END), 0) AS expenses
            FROM transactions
            """
        ).fetchone()
        monthly = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN category = 'Investment' THEN amount END), 0) AS investments
            FROM transactions
            WHERE substr(transaction_date, 1, 7) = ?
            """,
            (current_month,),
        ).fetchone()
        today_spending = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense' AND transaction_date = ?
            """,
            (today.isoformat(),),
        ).fetchone()["total"]
        recent_transactions = connection.execute(
            """
            SELECT * FROM transactions
            ORDER BY transaction_date DESC, id DESC
            LIMIT 5
            """
        ).fetchall()
        category_summary = connection.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
              AND substr(transaction_date, 1, 7) = ?
            GROUP BY category
            ORDER BY total DESC
            LIMIT 5
            """,
            (current_month,),
        ).fetchall()
        settings = connection.execute(
            "SELECT emergency_buffer, monthly_savings_target FROM settings WHERE id = 1"
        ).fetchone()
        upcoming_recurring = connection.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM recurring_transactions
            WHERE is_active = 1
              AND transaction_type = 'expense'
              AND next_due_date <= ?
            GROUP BY category
            """,
            (last_day_of_month.isoformat(),),
        ).fetchall()
        goals = connection.execute(
            "SELECT target_amount, saved_amount, deadline FROM savings_goals WHERE deadline IS NOT NULL"
        ).fetchall()
        budgets = connection.execute(
            "SELECT category, amount FROM budgets WHERE budget_month = ?", (current_month,)
        ).fetchall()

    total_income = float(lifetime["income"])
    total_expenses = float(lifetime["expenses"])
    monthly_income = float(monthly["income"])
    monthly_expenses = float(monthly["expenses"])
    emergency_buffer = float(settings["emergency_buffer"]) if settings else 0
    savings_reserve = float(settings["monthly_savings_target"]) if settings else 0
    recurring_commitments = sum(float(row["total"]) for row in upcoming_recurring)
    investment_commitments = sum(
        float(row["total"]) for row in upcoming_recurring if row["category"] == "Investment"
    )

    goal_contributions = 0
    for goal in goals:
        deadline = date.fromisoformat(goal["deadline"])
        months_until_deadline = (
            (deadline.year - today.year) * 12 + deadline.month - today.month + 1
        )
        if months_until_deadline > 0:
            remaining = max(0, float(goal["target_amount"]) - float(goal["saved_amount"]))
            goal_contributions += remaining / months_until_deadline

    available_money = total_income - total_expenses
    raw_safe_to_spend = (
        available_money
        - recurring_commitments
        - goal_contributions
        - savings_reserve
        - emergency_buffer
    )
    safe_to_spend = max(0, raw_safe_to_spend)
    remaining_days = max(1, (last_day_of_month - today).days + 1)
    category_spending = {category["category"]: float(category["total"]) for category in category_summary}
    budget_alerts = []
    for budget in budgets:
        budget_amount = float(budget["amount"])
        spent = monthly_expenses if budget["category"] is None else category_spending.get(budget["category"], 0)
        percent_used = (spent / budget_amount * 100) if budget_amount else (100 if spent else 0)
        if percent_used >= 80:
            budget_alerts.append({
                "label": budget["category"] or "Overall monthly budget",
                "percent_used": percent_used,
                "is_exceeded": percent_used >= 100,
            })

    return {
        "available_money": available_money,
        "safe_to_spend": safe_to_spend,
        "safe_per_day": safe_to_spend / remaining_days,
        "safe_shortfall": max(0, -raw_safe_to_spend),
        "emergency_buffer": emergency_buffer,
        "savings_reserve": savings_reserve,
        "goal_contributions": goal_contributions,
        "recurring_commitments": recurring_commitments,
        "investment_commitments": investment_commitments,
        "remaining_days": remaining_days,
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
        "monthly_savings": monthly_income - monthly_expenses,
        "today_spending": float(today_spending),
        "monthly_investments": float(monthly["investments"]),
        "recent_transactions": recent_transactions,
        "category_summary": category_summary,
        "budget_alerts": budget_alerts,
        "month_label": today.strftime("%B %Y"),
    }


def get_analytics_data():
    """Return this month's spending figures and simple rule-based insights."""
    today = date.today()
    current_month = today.strftime("%Y-%m")
    previous_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    week_start = today - timedelta(days=today.weekday())

    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount END), 0) AS income,
              COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount END), 0) AS expenses
            FROM transactions WHERE substr(transaction_date, 1, 7) = ?
            """, (current_month,)
        ).fetchone()
        previous_expenses = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total FROM transactions
            WHERE transaction_type = 'expense' AND substr(transaction_date, 1, 7) = ?
            """, (previous_month,)
        ).fetchone()["total"]
        weekly_spending = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total FROM transactions
            WHERE transaction_type = 'expense' AND transaction_date BETWEEN ? AND ?
            """, (week_start.isoformat(), today.isoformat())
        ).fetchone()["total"]
        categories = connection.execute(
            """
            SELECT category, SUM(amount) AS total FROM transactions
            WHERE transaction_type = 'expense' AND substr(transaction_date, 1, 7) = ?
            GROUP BY category ORDER BY total DESC
            """, (current_month,)
        ).fetchall()
        monthly_trend_rows = connection.execute(
            """
            SELECT substr(transaction_date, 1, 7) AS month, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense' AND transaction_date >= ?
            GROUP BY substr(transaction_date, 1, 7)
            ORDER BY month
            """, ((today - timedelta(days=183)).isoformat(),)
        ).fetchall()

    income = float(current["income"])
    expenses = float(current["expenses"])
    savings = income - expenses
    savings_rate = (savings / income * 100) if income else 0
    previous_expenses = float(previous_expenses)
    insights = []
    if categories:
        insights.append(f"Your highest spending category this month is {categories[0]['category']} (₹{float(categories[0]['total']):,.2f}).")
    if previous_expenses and expenses > previous_expenses * 1.1:
        increase = (expenses - previous_expenses) / previous_expenses * 100
        insights.append(f"Your spending is {increase:.0f}% higher than last month so far.")
    elif previous_expenses and expenses < previous_expenses * 0.9:
        decrease = (previous_expenses - expenses) / previous_expenses * 100
        insights.append(f"Your spending is {decrease:.0f}% lower than last month so far.")
    if income and savings_rate >= 20:
        insights.append(f"Strong saving habit: you have saved {savings_rate:.0f}% of this month's income.")
    elif income and savings < 0:
        insights.append("You have spent more than you earned this month. Review discretionary categories.")
    if not insights:
        insights.append("Add more transactions to unlock personalised spending insights.")

    largest_category_total = max((float(category["total"]) for category in categories), default=0)
    category_breakdown = [
        {
            "name": category["category"],
            "total": float(category["total"]),
            "percent_of_largest": (float(category["total"]) / largest_category_total * 100)
            if largest_category_total else 0,
        }
        for category in categories
    ]
    largest_month_total = max((float(month["total"]) for month in monthly_trend_rows), default=0)
    monthly_trend = [
        {
            "label": date.fromisoformat(f"{month['month']}-01").strftime("%b %Y"),
            "total": float(month["total"]),
            "percent_of_largest": (float(month["total"]) / largest_month_total * 100)
            if largest_month_total else 0,
        }
        for month in monthly_trend_rows
    ]
    return {
        "month_label": today.strftime("%B %Y"), "weekly_spending": float(weekly_spending),
        "income": income, "expenses": expenses, "savings": savings,
        "savings_rate": savings_rate, "categories": category_breakdown,
        "monthly_trend": monthly_trend, "insights": insights,
    }
