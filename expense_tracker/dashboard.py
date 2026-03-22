from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from bson.objectid import ObjectId
from .extensions import mongo
from .utils import analyze_spending, get_thresholds, login_required, safe_float, safe_int


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="")


def _month_date_range(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _daily_date_range(date_obj: datetime):
    start = datetime(date_obj.year, date_obj.month, date_obj.day)
    end = start + timedelta(days=1)
    return start, end


@dashboard_bp.route("/")
@login_required
def home():
    user = session.get("user")
    user_id = ObjectId(user["id"])

    user_doc = mongo.db.users.find_one({"_id": user_id})
    budget = user_doc.get("budget", 0)
    thresholds = get_thresholds(user_doc)

    today = datetime.today()
    start_of_month, _ = _month_date_range(today.year, today.month)
    start_of_year, _ = _month_date_range(today.year, 1)
    start_of_day, end_of_day = _daily_date_range(today)

    # Totals
    # Support older documents without type field as expenses
    income_match = {"user_id": user_id, "type": "income"}
    expense_match = {"user_id": user_id, "$or": [{"type": "expense"}, {"type": {"$exists": False}}]}

    total_income = next(
        mongo.db.expenses.aggregate(
            [
                {"$match": income_match},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    total_expenses = next(
        mongo.db.expenses.aggregate(
            [
                {"$match": expense_match},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    month_income = next(
        mongo.db.expenses.aggregate(
            [
                {"$match": {"user_id": user_id, "type": "income", "date": {"$gte": start_of_month}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    month_expenses = next(
        mongo.db.expenses.aggregate(
            [
                {"$match": {"user_id": user_id, "$or": [{"type": "expense"}, {"type": {"$exists": False}}], "date": {"$gte": start_of_month}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    day_income = next(
        mongo.db.expenses.aggregate(
            [
                {
                    "$match": {
                        "user_id": user_id,
                        "type": "income",
                        "date": {"$gte": start_of_day, "$lt": end_of_day},
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    day_expenses = next(
        mongo.db.expenses.aggregate(
            [
                {
                    "$match": {
                        "user_id": user_id,
                        "$or": [{"type": "expense"}, {"type": {"$exists": False}}],
                        "date": {"$gte": start_of_day, "$lt": end_of_day},
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    year_income = next(
        mongo.db.expenses.aggregate(
            [
                {"$match": {"user_id": user_id, "type": "income", "date": {"$gte": start_of_year}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    year_expenses = next(
        mongo.db.expenses.aggregate(
            [
                {
                    "$match": {
                        "user_id": user_id,
                        "$or": [{"type": "expense"}, {"type": {"$exists": False}}],
                        "date": {"$gte": start_of_year},
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    # Savings
    savings_daily = day_income - day_expenses
    savings_monthly = month_income - month_expenses
    savings_yearly = year_income - year_expenses

    remaining_budget = budget - month_expenses

    # Use remaining budget as the baseline for threshold calculations
    baseline = max(remaining_budget, 1)
    low_value = baseline * thresholds.get("low", 0.25)
    high_value = baseline * thresholds.get("high", 0.75)

    # Determine budget usage for UI progress
    if budget and budget > 0:
        budget_usage_pct = min(max((month_expenses / budget) * 100, 0), 100)
    else:
        budget_usage_pct = 100

    alert_level = "normal"
    if budget > 0:
        ratio = month_expenses / budget
        if ratio >= 1:
            alert_level = "exceeded"
        elif ratio >= 0.75:
            alert_level = "high"
        elif ratio >= 0.5:
            alert_level = "medium"

    # Chart data
    # Monthly expenses comparison (last 6 months)
    months = []
    for i in range(5, -1, -1):
        year = today.year
        month_num = today.month - i
        while month_num <= 0:
            year -= 1
            month_num += 12
        months.append((year, month_num))

    month_labels = []
    month_expenses_data = []
    for year, month_num in months:
        month_labels.append(f"{year}-{month_num:02d}")
        start, end = _month_date_range(year, month_num)
        month_total_val = next(
            mongo.db.expenses.aggregate(
                [
                    {
                        "$match": {
                            "user_id": user_id,
                            "$or": [{"type": "expense"}, {"type": {"$exists": False}}],
                            "date": {"$gte": start, "$lt": end},
                        }
                    },
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]
            ),
            {},
        ).get("total", 0)
        month_expenses_data.append(month_total_val)

    # Daily spending trend (last 14 days)
    daily_labels = []
    daily_data = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        start, end = _daily_date_range(day)
        daily_labels.append(day.strftime("%b %d"))
        day_total = next(
            mongo.db.expenses.aggregate(
                [
                    {
                        "$match": {
                            "user_id": user_id,
                            "$or": [{"type": "expense"}, {"type": {"$exists": False}}],
                            "date": {"$gte": start, "$lt": end},
                        }
                    },
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]
            ),
            {},
        ).get("total", 0)
        daily_data.append(day_total)

    # Category breakdown
    category_breakdown = list(
        mongo.db.expenses.aggregate(
            [
                {"$match": {"user_id": user_id, "$or": [{"type": "expense"}, {"type": {"$exists": False}}]}},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
                {"$sort": {"total": -1}},
            ]
        )
    )

    insights = {
        "monthly_expenses": month_expenses,
        "budget": budget,
        "category_breakdown": category_breakdown,
    }
    ai_suggestions = analyze_spending(insights)

    return render_template(
        "dashboard.html",
        name=user.get("name"),
        total_income=total_income,
        total_expenses=total_expenses,
        monthly_income=month_income,
        monthly_expenses=month_expenses,
        remaining_budget=remaining_budget,
        savings_daily=savings_daily,
        savings_monthly=savings_monthly,
        savings_yearly=savings_yearly,
        alert_level=alert_level,
        thresholds=thresholds,
        baseline=baseline,
        level_low_value=low_value,
        level_high_value=high_value,
        budget_usage_pct=budget_usage_pct,
        month_labels=month_labels,
        month_expenses_data=month_expenses_data,
        daily_labels=daily_labels,
        daily_data=daily_data,
        category_breakdown=category_breakdown,
        ai_suggestions=ai_suggestions,
    )


@dashboard_bp.route("/dashboard/budget", methods=["POST"])
@login_required
def update_budget():
    user = session.get("user")
    user_id = ObjectId(user["id"])
    budget_value = safe_int(request.form.get("budget"))

    low_pct = safe_float(request.form.get("threshold_low"), None)
    high_pct = safe_float(request.form.get("threshold_high"), None)

    if budget_value < 0:
        flash("Budget must be a positive number.", "danger")
        return redirect(url_for("dashboard.home"))

    update_fields = {"budget": budget_value}

    if low_pct is not None and high_pct is not None:
        if low_pct < 0 or high_pct < 0 or low_pct > 100 or high_pct > 100 or low_pct > high_pct:
            flash("Thresholds must be valid percentages (0-100) and low <= high.", "danger")
            return redirect(url_for("dashboard.home"))

        update_fields["thresholds"] = {
            "low": low_pct / 100.0,
            "high": high_pct / 100.0,
        }

    mongo.db.users.update_one({"_id": user_id}, {"$set": update_fields})
    flash("Budget settings updated.", "success")
    return redirect(url_for("dashboard.home"))
