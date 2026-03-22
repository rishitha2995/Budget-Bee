import re
from datetime import datetime
from flask import session, redirect, url_for


def login_required(view):
    """Simple decorator to require login for views."""

    from functools import wraps

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def normalize_text(text: str) -> str:
    return (text or "").strip().lower()


CATEGORY_KEYWORDS = {
    "Food": [
        "restaurant",
        "grocer",
        "coffee",
        "cafe",
        "dinner",
        "lunch",
        "breakfast",
        "meal",
        "snack",
        "uber eats",
        "grubhub",
        "doordash",
    ],
    "Transport": [
        "uber",
        "lyft",
        "taxi",
        "bus",
        "train",
        "metro",
        "gas",
        "fuel",
        "parking",
        "car",
    ],
    "Shopping": [
        "amazon",
        "mall",
        "store",
        "shopping",
        "walmart",
        "target",
        "online",
    ],
    "Bills": [
        "electric",
        "water",
        "internet",
        "rent",
        "mortgage",
        "phone",
        "utilities",
        "subscription",
    ],
    "Entertainment": [
        "netflix",
        "spotify",
        "movie",
        "concert",
        "game",
        "ticket",
        "twitch",
        "youtube",
    ],
    "Health": [
        "doctor",
        "medicine",
        "pharmacy",
        "gym",
        "appointment",
        "health",
    ],
    "Travel": [
        "hotel",
        "flight",
        "airbnb",
        "travel",
        "trip",
        "uber",
    ],
}


def categorize_transaction(description: str, category: str = None) -> str:
    """Automatically infer a category based on keywords."""

    if category:
        return category.title().strip()

    text = normalize_text(description)
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return cat
    return "Miscellaneous"


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_thresholds(user_doc):
    """Return user-adjustable budget thresholds for expense coloring.

    The thresholds are stored as percentages (0-1) in the user document
    under the "thresholds" key.

    Defaults:
      - low: 0.25
      - high: 0.75

    Returns a dict with keys: low, high
    """

    defaults = {"low": 0.25, "high": 0.75}
    thr = user_doc.get("thresholds") if user_doc else None
    if not isinstance(thr, dict):
        return defaults

    low = safe_float(thr.get("low"), defaults["low"])
    high = safe_float(thr.get("high"), defaults["high"])

    # Clamp values to reasonable range
    low = max(0.0, min(low, 1.0))
    high = max(low, min(high, 1.0))

    return {"low": low, "high": high}


def parse_date(date_str: str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def extract_amount_from_text(text: str):
    """Try to find a currency amount in a block of text."""
    if not text:
        return None

    # Look for patterns like 1,234.56 or 1234.56 or 1234
    match = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\b", text)
    if not match:
        match = re.search(r"\b([0-9]+(?:\.[0-9]{1,2})?)\b", text)
    if not match:
        return None

    amount_str = match.group(1).replace(",", "")
    try:
        return float(amount_str)
    except ValueError:
        return None


def analyze_spending(insights):
    """Generate simple rule-based insights for a user."""
    messages = []

    total = insights.get("monthly_expenses", 0)
    budget = insights.get("budget", 0)
    categories = insights.get("category_breakdown", [])

    # Show a budget warning
    if budget > 0 and total > 0:
        ratio = total / budget
        if ratio >= 1:
            messages.append("You have exceeded your monthly budget. Consider reviewing subscriptions and recurring expenses.")
        elif ratio >= 0.75:
            messages.append("You're over 75% of your budget. Keep an eye on upcoming expenses.")
        elif ratio >= 0.5:
            messages.append("You've used over 50% of your budget. Try to reduce discretionary spending.")

    # category insights
    if categories:
        top = categories[0]
        if top.get("_id") and top.get("total"):
            if top["_id"].lower() in ["shopping", "entertainment"] and top["total"] > total * 0.25:
                messages.append(f"You're spending a lot on {top['_id']}. Consider setting a limit for that category.")
            if top["_id"].lower() == "food" and top["total"] > total * 0.3:
                messages.append("Food is taking a large chunk of your spending — try meal planning or cooking more at home.")

    return messages


def parse_receipt_text(text: str):
    """Attempt to extract amount/date from OCR text."""
    if not text:
        return {}

    # Normalize line endings and split lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    # Try to locate a line that looks like total/amount
    amount = None
    for line in lines:
        low = line.lower()
        if any(k in low for k in ["total", "amount", "net", "payable", "balance"]):
            amount = extract_amount_from_text(line)
            if amount:
                break

    # fallback: pick the largest numeric amount found
    if not amount:
        matches = re.findall(r"[₹$]?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", joined)
        if matches:
            clean = [float(m.replace(",", "")) for m in matches if m]
            amount = max(clean) if clean else None

    # Attempt to extract common date formats
    date = None
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{2}-\d{2}-\d{4})",
        r"(\d{2}\.\d{2}\.\d{4})",
    ]
    for pat in date_patterns:
        match = re.search(pat, joined)
        if match:
            try:
                # Try multiple formats
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"]:
                    try:
                        date = datetime.strptime(match.group(1), fmt)
                        break
                    except ValueError:
                        continue
                if date:
                    break
            except Exception:
                continue

    return {"amount": amount, "date": date}
