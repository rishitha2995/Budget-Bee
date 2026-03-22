from datetime import datetime
from flask import Blueprint, render_template, session
from bson.objectid import ObjectId
from .extensions import mongo
from .utils import login_required


insights_bp = Blueprint("insights", __name__, url_prefix="")


@insights_bp.route("/insights")
@login_required
def insights():
    user = session.get("user")
    user_id = ObjectId(user["id"])

    today = datetime.today()
    start_month = datetime(today.year, today.month, 1)

    # Category breakdown (expenses only)
    category_agg = mongo.db.expenses.aggregate(
        [
            {"$match": {"user_id": user_id, "$or": [{"type": "expense"}, {"type": {"$exists": False}}]}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}},
        ]
    )
    categories = list(category_agg)
    top_category = categories[0]["_id"] if categories else None
    top_category_amount = categories[0]["total"] if categories else 0

    # Monthly comparison (last 6 months)
    months = []
    for i in range(5, -1, -1):
        year = today.year
        month_num = today.month - i
        while month_num <= 0:
            year -= 1
            month_num += 12
        months.append((year, month_num))

    month_labels = []
    month_values = []
    for year, month_num in months:
        month_labels.append(f"{year}-{month_num:02d}")
        start = datetime(year, month_num, 1)
        if month_num == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month_num + 1, 1)

        agg = mongo.db.expenses.aggregate(
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
        )
        month_values.append(next(agg, {}).get("total", 0))

    # Prediction (simple average of last 3 months)
    last_three = month_values[-3:]
    prediction = sum(last_three) / len(last_three) if last_three and any(last_three) else 0

    return render_template(
        "insights.html",
        category_breakdown=categories,
        top_category=top_category,
        top_category_amount=top_category_amount,
        month_labels=month_labels,
        month_values=month_values,
        predicted_next_month=round(prediction, 2),
    )
