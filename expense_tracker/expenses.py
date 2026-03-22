import csv
import io
import os
import random
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from bson.objectid import ObjectId
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .extensions import mongo
from .utils import (
    categorize_transaction,
    get_thresholds,
    login_required,
    parse_date,
    parse_receipt_text,
    safe_float,
    safe_int,
)

MOTIVATIONAL_QUOTES = [
    "Great job staying on top of your spending! 💪",
    "Every small win counts — keep going! 🌟",
    "You're building better habits one transaction at a time. 🚀",
    "Smart moves today lead to big wins tomorrow. 💼",
    "Keep it up! Your future self will thank you. 🙌",
    "Money habits are built one choice at a time. 💡",
    "You've got this — stay focused and keep saving! 🧠",
    "Progress > perfection. Keep logging those expenses! ✅",
]


expenses_bp = Blueprint("expenses", __name__, url_prefix="/expenses")


def _build_query(user_id):
    query = {"user_id": user_id}

    term = request.args.get("q", "")
    if term:
        query["description"] = {"$regex": term, "$options": "i"}

    ttype = request.args.get("type")
    if ttype in ["income", "expense"]:
        query["type"] = ttype

    category = request.args.get("category", "").strip()
    if category:
        query["category"] = {"$regex": f"^{category}", "$options": "i"}

    date_from = parse_date(request.args.get("from", ""))
    date_to = parse_date(request.args.get("to", ""))

    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to

    return query


@expenses_bp.route("/", methods=["GET"])
@login_required
def list_expenses():
    user = session.get("user")
    user_id = ObjectId(user["id"])

    ctx = _budget_context(user_id)

    query = _build_query(user_id)
    all_transactions = list(
        mongo.db.expenses.find(query).sort("date", -1).limit(500)
    )

    incomes = []
    expenses = []
    for tx in all_transactions:
        if tx.get("type") == "income":
            tx["row_class"] = "table-success"
            incomes.append(tx)
        else:
            tx_amount = tx.get("amount", 0) or 0
            level = _expense_level(tx_amount, ctx["baseline"], ctx["thresholds"])
            tx["row_class"] = (
                "table-success"
                if level == "low"
                else "table-warning"
                if level == "moderate"
                else "table-danger"
            )
            expenses.append(tx)

    quote = session.pop("transaction_quote", None)

    return render_template(
        "expenses.html",
        incomes=incomes,
        expenses=expenses,
        transaction_quote=quote,
        **ctx,
    )


def _insert_transaction(user_id, ttype, amount, description, category, date_obj):
    category_final = categorize_transaction(description, category)
    mongo.db.expenses.insert_one(
        {
            "user_id": user_id,
            "type": ttype,
            "amount": amount,
            "description": description,
            "category": category_final,
            "date": date_obj,
            "created_at": datetime.utcnow(),
        }
    )


def _budget_context(user_id):
    """Return calculated budget/remaining budget context for the user."""

    user_doc = mongo.db.users.find_one({"_id": user_id})
    budget = user_doc.get("budget", 0)
    thresholds = get_thresholds(user_doc)

    today = datetime.today()
    start_of_month = datetime(today.year, today.month, 1)

    month_expenses = next(
        mongo.db.expenses.aggregate(
            [
                {
                    "$match": {
                        "user_id": user_id,
                        "$or": [{"type": "expense"}, {"type": {"$exists": False}}],
                        "date": {"$gte": start_of_month},
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    month_income = next(
        mongo.db.expenses.aggregate(
            [
                {
                    "$match": {
                        "user_id": user_id,
                        "type": "income",
                        "date": {"$gte": start_of_month},
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ),
        {},
    ).get("total", 0)

    remaining_budget = budget - month_expenses

    # Use remaining budget as the baseline for threshold calculations
    baseline = max(remaining_budget, 1)

    low_value = baseline * thresholds.get("low", 0.25)
    high_value = baseline * thresholds.get("high", 0.75)

    alert_level = "normal"
    if budget > 0:
        ratio = month_expenses / budget
        if ratio >= 1:
            alert_level = "exceeded"
        elif ratio >= 0.75:
            alert_level = "high"
        elif ratio >= 0.5:
            alert_level = "medium"

    return {
        "budget": budget,
        "remaining_budget": remaining_budget,
        "alert_level": alert_level,
        "thresholds": thresholds,
        "baseline": baseline,
        "month_income": month_income,
        "level_low_value": low_value,
        "level_high_value": high_value,
    }


def _expense_level(amount, baseline, thresholds):
    """Determine expense level (low/moderate/high/exceeded) for row highlighting."""

    try:
        amount = float(amount)
    except Exception:
        amount = 0

    if baseline <= 0:
        return "exceeded"

    ratio = amount / baseline
    if ratio <= thresholds.get("low", 0.25):
        return "low"
    if ratio <= thresholds.get("high", 0.75):
        return "moderate"
    return "high"


@expenses_bp.route("/add", methods=["POST"])
@login_required
def add_expense():
    user = session.get("user")
    user_id = ObjectId(user["id"])

    ttype = request.form.get("type", "expense")
    amount = safe_float(request.form.get("amount"))
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "")
    date_str = request.form.get("date")

    if amount <= 0 or not description or not date_str or ttype not in ["expense", "income"]:
        flash("Please enter valid transaction information.", "danger")
        return redirect(url_for("expenses.list_expenses"))

    date_obj = parse_date(date_str)
    if not date_obj:
        flash("Invalid date format. Use YYYY-MM-DD.", "danger")
        return redirect(url_for("expenses.list_expenses"))

    _insert_transaction(user_id, ttype, amount, description, category, date_obj)

    # Show an inspirational quote after each added transaction
    session["transaction_quote"] = random.choice(MOTIVATIONAL_QUOTES)

    flash("Transaction added.", "success")
    return redirect(url_for("expenses.list_expenses"))


@expenses_bp.route("/edit/<expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    user = session.get("user")
    user_id = ObjectId(user["id"])
    try:
        expense_obj = mongo.db.expenses.find_one({"_id": ObjectId(expense_id), "user_id": user_id})
    except Exception:
        expense_obj = None

    if not expense_obj:
        flash("Transaction not found.", "danger")
        return redirect(url_for("expenses.list_expenses"))

    if request.method == "POST":
        ttype = request.form.get("type", "expense")
        amount = safe_float(request.form.get("amount"))
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        date_str = request.form.get("date")

        if amount <= 0 or not description or not date_str or ttype not in ["expense", "income"]:
            flash("Please enter valid transaction information.", "danger")
            return redirect(url_for("expenses.edit_expense", expense_id=expense_id))

        date_obj = parse_date(date_str)
        if not date_obj:
            flash("Invalid date format. Use YYYY-MM-DD.", "danger")
            return redirect(url_for("expenses.edit_expense", expense_id=expense_id))

        category_final = categorize_transaction(description, category)

        mongo.db.expenses.update_one(
            {"_id": ObjectId(expense_id), "user_id": user_id},
            {
                "$set": {
                    "type": ttype,
                    "amount": amount,
                    "description": description,
                    "category": category_final,
                    "date": date_obj,
                }
            },
        )
        flash("Transaction updated.", "success")
        return redirect(url_for("expenses.list_expenses"))

    ctx = _budget_context(user_id)
    expense_obj["expense_level"] = _expense_level(expense_obj.get("amount", 0), ctx["remaining_budget"])

    return render_template(
        "expenses.html",
        expenses=[expense_obj],
        edit=expense_obj,
        **ctx,
    )


@expenses_bp.route("/delete/<expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    user = session.get("user")
    user_id = ObjectId(user["id"])

    result = mongo.db.expenses.delete_one({"_id": ObjectId(expense_id), "user_id": user_id})
    if result.deleted_count:
        flash("Transaction deleted.", "success")
    else:
        flash("Could not delete transaction.", "danger")
    return redirect(url_for("expenses.list_expenses"))


@expenses_bp.route("/export", methods=["GET"])
@login_required
def export_csv():
    user = session.get("user")
    user_id = ObjectId(user["id"])
    query = _build_query(user_id)
    cursor = mongo.db.expenses.find(query).sort("date", -1)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Type", "Category", "Description", "Amount"])

    for tx in cursor:
        writer.writerow([
            tx.get("date").strftime("%Y-%m-%d") if tx.get("date") else "",
            tx.get("type", ""),
            tx.get("category", ""),
            tx.get("description", ""),
            tx.get("amount", 0),
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="transactions.csv",
    )


@expenses_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload_receipt():
    if request.method == "GET":
        return render_template("upload_receipt.html")

    file = request.files.get("receipt")
    if not file:
        flash("Please select an image file to upload.", "danger")
        return redirect(url_for("expenses.upload_receipt"))

    try:
        import pytesseract
    except ImportError:
        flash(
            "OCR is not available. Install pytesseract and the Tesseract OCR engine to use receipt scanning.",
            "warning",
        )
        return redirect(url_for("expenses.list_expenses"))

    def _preprocess(image):
        # Normalize orientation using EXIF data if present
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        gray = image.convert("L")

        # Equalize histogram to improve contrast in uneven lighting
        gray = ImageOps.equalize(gray)

        # Reduce noise while preserving edges
        gray = gray.filter(ImageFilter.MedianFilter(size=3))

        # Boost contrast and sharpness for OCR readability
        gray = ImageEnhance.Contrast(gray).enhance(1.6)
        gray = ImageEnhance.Sharpness(gray).enhance(1.2)

        # Resize to improve OCR resolution
        multiplier = 2
        gray = gray.resize((int(gray.width * multiplier), int(gray.height * multiplier)), Image.LANCZOS)

        # Apply adaptive threshold-like binarization
        gray = gray.point(lambda x: 0 if x < 140 else 255, "1")
        return gray

    def _ocr_attempt(image, config):
        return pytesseract.image_to_string(image, config=config)

    try:
        image = Image.open(file.stream)

        candidates = []
        base = _preprocess(image)
        configs = ["--psm 6", "--psm 4", "--psm 11"]
        for cfg in configs:
            text = _ocr_attempt(base, cfg)
            candidates.append(text)

        # Pick the best candidate (longest output)
        best_text = max(candidates, key=lambda t: len(t or ""))

        parsed = parse_receipt_text(best_text)
        flash(
            "Receipt scanned. Review the detected values below and adjust if needed.",
            "success",
        )
        return render_template(
            "upload_receipt.html",
            preview_text=best_text,
            detected_amount=parsed.get("amount"),
            detected_date=parsed.get("date"),
        )
    except Exception as exc:
        # Common failure: tesseract is not installed or not on PATH
        msg = str(exc)
        if "TesseractNotFoundError" in msg or "tesseract" in msg.lower():
            flash(
                "Could not read receipt: Tesseract OCR is not installed or not available in your system PATH. "
                "Install Tesseract (https://tesseract-ocr.github.io/) and restart the app.",
                "danger",
            )
        else:
            flash(f"Could not read receipt: {exc}", "danger")
        return redirect(url_for("expenses.upload_receipt"))
