"""AI Financial Assistant engine with deterministic calculation grounding."""

import re
from datetime import date
from typing import Any, Dict, Optional

from services.calculations import get_analytics_data, get_dashboard_data
from database import get_connection


DISCLAIMER = "ℹ️ Guidance is for planning purposes only and does not constitute certified professional financial advice."


def handle_assistant_query(user_id: int, query: str) -> Dict[str, Any]:
    """Analyze the user's natural question and return a verified, data-backed explanation."""
    cleaned_query = query.strip()
    lower_query = cleaned_query.lower()

    dashboard = get_dashboard_data(user_id)
    analytics = get_analytics_data(user_id)

    # 1. Purchase Affordability Question (e.g. "Can I afford ₹500 shoes?", "Can I buy 1200 jacket?")
    afford_match = re.search(
        r"(?:can i afford|can i buy|can i spend|should i buy|afford to buy|can i get)\s*(?:a|an|the)?\s*(?:₹|rs\.?|inr)?\s*([0-9,]+(?:\.[0-9]{1,2})?)?\s*(?:on|for)?\s*([a-zA-Z\s]+)?\s*(?:for|costing|worth)?\s*(?:₹|rs\.?|inr)?\s*([0-9,]+(?:\.[0-9]{1,2})?)?",
        lower_query,
        re.IGNORECASE,
    )

    amount_val = None
    item_name = "this item"

    if afford_match:
        # Check if amount was captured before or after item name
        amt_str1 = afford_match.group(1)
        amt_str2 = afford_match.group(3)
        candidate_item = (afford_match.group(2) or "").strip()

        if amt_str1:
            try:
                amount_val = float(amt_str1.replace(",", ""))
            except ValueError:
                pass
        elif amt_str2:
            try:
                amount_val = float(amt_str2.replace(",", ""))
            except ValueError:
                pass

        if candidate_item and not any(w in candidate_item for w in ["rs", "rupee", "inr"]):
            # Clean item name
            candidate_item = re.sub(r"\b(today|now|this month|please|can|i|afford|buy)\b", "", candidate_item).strip()
            if candidate_item:
                item_name = candidate_item

    # Direct fallback regex for "₹500" anywhere in query if "afford" or "buy" is present
    if not amount_val and any(word in lower_query for word in ["afford", "buy", "spend"]):
        generic_amt = re.search(r"(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)", lower_query)
        if generic_amt:
            try:
                amount_val = float(generic_amt.group(1))
            except ValueError:
                pass

    if amount_val is not None and amount_val > 0:
        return evaluate_affordability(dashboard, item_name, amount_val)

    # 2. Top Spending Breakdown (e.g. "Where did my money go?", "What is my highest expense?")
    if any(phrase in lower_query for phrase in ["where did my money go", "where did most of my money go", "highest expense", "top category", "spending breakdown", "what did i spend"]):
        return explain_top_spending(dashboard, analytics)

    # 3. Weekly / Daily Allowance (e.g. "How much can I spend this week?", "What is my daily budget?")
    if any(phrase in lower_query for phrase in ["spend this week", "weekly budget", "daily budget", "safe per day", "daily limit", "spend per day"]):
        return explain_weekly_budget(dashboard)

    # 4. Savings Goals (e.g. "How much should I save for my goals?", "Goal progress", "Savings goals")
    if any(phrase in lower_query for phrase in ["goal", "goals", "save for", "savings target"]):
        return explain_goals(user_id, dashboard)

    # 5. Trend / Higher Spending (e.g. "Why am I spending more this month?", "Compare with last month")
    if any(phrase in lower_query for phrase in ["spending more", "why am i spending", "compare", "trend", "last month"]):
        return explain_trends(analytics)

    # 6. Fallback General Financial Summary
    return general_financial_summary(dashboard, analytics)


def evaluate_affordability(dashboard: Dict[str, Any], item_name: str, amount: float) -> Dict[str, Any]:
    """Evaluate whether a purchase is safe given current reserves."""
    safe_to_spend = dashboard["safe_to_spend"]
    remaining_days = dashboard["remaining_days"]
    emergency_buffer = dashboard["emergency_buffer"]
    recurring_commitments = dashboard["recurring_commitments"]

    if amount <= safe_to_spend:
        new_safe = safe_to_spend - amount
        new_daily = new_safe / remaining_days if remaining_days > 0 else new_safe
        reply = (
            f"✅ **Yes, you can comfortably afford {item_name} (₹{amount:,.2f})!**\n\n"
            f"• **Current Safe-to-Spend:** ₹{safe_to_spend:,.2f}\n"
            f"• **Remaining after purchase:** ₹{new_safe:,.2f}\n"
            f"• **Revised daily allowance:** ₹{new_daily:,.2f}/day for the next {remaining_days} days.\n\n"
            f"Your emergency buffer (₹{emergency_buffer:,.2f}) and upcoming commitments (₹{recurring_commitments:,.2f}) will remain 100% protected."
        )
    else:
        shortfall = amount - safe_to_spend
        reply = (
            f"⚠️ **Caution: Buying {item_name} (₹{amount:,.2f}) exceeds your safe-to-spend allowance.**\n\n"
            f"• **Current Safe-to-Spend:** ₹{safe_to_spend:,.2f}\n"
            f"• **Shortfall:** ₹{shortfall:,.2f}\n\n"
            f"If you buy this now, you would need to dip ₹{shortfall:,.2f} into your emergency buffer (₹{emergency_buffer:,.2f}) or planned savings/recurring commitments. "
            f"Consider waiting until next month or reducing discretionary expenses first."
        )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Where did most of my money go this month?",
            "How much can I spend this week?",
            "How are my savings goals doing?"
        ]
    }


def explain_top_spending(dashboard: Dict[str, Any], analytics: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize top spending categories and largest recent transactions."""
    categories = dashboard.get("category_summary", [])
    monthly_expenses = dashboard["monthly_expenses"]

    if not categories:
        reply = "You don't have any expenses recorded for this month yet! Once you log transactions, I'll break down your biggest spending areas."
    else:
        top_lines = []
        for cat in categories[:4]:
            pct = (float(cat["total"]) / monthly_expenses * 100) if monthly_expenses else 0
            top_lines.append(f"• **{cat['category']}:** ₹{float(cat['total']):,.2f} ({pct:.0f}% of total expenses)")

        reply = (
            f"📊 **Here is where your money went this month ({dashboard['month_label']}):**\n\n"
            f"Total spent so far: **₹{monthly_expenses:,.2f}**\n\n"
            + "\n".join(top_lines) +
            "\n\n💡 *Tip: Check the Budgets page to set spending limits on high-expense categories.*"
        )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Can I afford ₹500 shoes?",
            "How much can I spend this week?",
            "Why is my spending higher this month?"
        ]
    }


def explain_weekly_budget(dashboard: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate and explain weekly/daily spending limits."""
    safe_to_spend = dashboard["safe_to_spend"]
    safe_per_day = dashboard["safe_per_day"]
    remaining_days = dashboard["remaining_days"]
    days_this_week = min(7, remaining_days)
    weekly_allowance = safe_per_day * days_this_week

    reply = (
        f"📅 **Your spending allowances for {dashboard['month_label']}:**\n\n"
        f"• **Safe to spend for the rest of the month:** ₹{safe_to_spend:,.2f}\n"
        f"• **Safe allowance this week ({days_this_week} days):** **₹{weekly_allowance:,.2f}**\n"
        f"• **Daily limit:** **₹{safe_per_day:,.2f}/day**\n\n"
        f"Staying within ₹{safe_per_day:,.2f} per day ensures your upcoming commitments (₹{dashboard['recurring_commitments']:,.2f}) and goals remain fully funded."
    )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Can I afford ₹300 dinner?",
            "Where did most of my money go this month?",
            "How are my savings goals doing?"
        ]
    }


def explain_goals(user_id: int, dashboard: Dict[str, Any]) -> Dict[str, Any]:
    """Provide status and advice on all active savings goals."""
    with get_connection() as connection:
        goals = connection.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY deadline IS NULL, deadline, id DESC",
            (user_id,),
        ).fetchall()

    if not goals:
        reply = (
            "🎯 **You have no active savings goals yet!**\n\n"
            "Creating savings goals (like for a laptop, trip, or emergency fund) helps you set aside money automatically before spending. "
            "Visit the **Goals** page to create your first goal!"
        )
    else:
        goal_lines = []
        for g in goals:
            target = float(g["target_amount"])
            saved = float(g["saved_amount"])
            pct = min(100, (saved / target * 100)) if target > 0 else 0
            goal_lines.append(f"• **{g['name']}:** ₹{saved:,.2f} of ₹{target:,.2f} ({pct:.0f}% completed)")

        reply = (
            f"🎯 **Your Savings Goals Summary:**\n\n"
            + "\n".join(goal_lines) +
            f"\n\nPlanned monthly goal reserve: **₹{dashboard['goal_contributions']:,.2f}** (already protected from your safe-to-spend)."
        )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Can I afford ₹500 shoes?",
            "How much can I spend this week?",
            "Where did most of my money go this month?"
        ]
    }


def explain_trends(analytics: Dict[str, Any]) -> Dict[str, Any]:
    """Explain month-over-month comparisons and rule-based insights."""
    insights = analytics.get("insights", [])
    income = analytics["income"]
    expenses = analytics["expenses"]
    savings_rate = analytics["savings_rate"]

    insights_text = "\n".join([f"• {item}" for item in insights])

    reply = (
        f"📈 **Spending Trends & Observations ({analytics['month_label']}):**\n\n"
        f"• **Income:** ₹{income:,.2f}\n"
        f"• **Expenses:** ₹{expenses:,.2f}\n"
        f"• **Savings Rate:** {savings_rate:.1f}%\n\n"
        f"**Key Insights:**\n{insights_text}"
    )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Where did most of my money go this month?",
            "Can I afford ₹500 shoes?",
            "How much can I spend this week?"
        ]
    }


def general_financial_summary(dashboard: Dict[str, Any], analytics: Dict[str, Any]) -> Dict[str, Any]:
    """Provide a friendly financial overview snapshot."""
    reply = (
        f"👋 **Here is your financial snapshot for {dashboard['month_label']}:**\n\n"
        f"• **Available Money:** ₹{dashboard['available_money']:,.2f}\n"
        f"• **Safe to Spend:** **₹{dashboard['safe_to_spend']:,.2f}** (₹{dashboard['safe_per_day']:,.2f}/day)\n"
        f"• **Today's Spending:** ₹{dashboard['today_spending']:,.2f}\n"
        f"• **Monthly Savings Rate:** {analytics['savings_rate']:.1f}%\n\n"
        f"Ask me anything like *'Can I afford ₹500 shoes?'* or *'Where did most of my money go?'*!"
    )

    return {
        "reply": reply,
        "disclaimer": DISCLAIMER,
        "suggestions": [
            "Can I afford ₹500 shoes?",
            "Where did most of my money go this month?",
            "How much can I spend this week?",
            "How are my savings goals doing?"
        ]
    }
