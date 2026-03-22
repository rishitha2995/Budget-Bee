from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from bson.objectid import ObjectId
from .extensions import mongo, bcrypt
from .utils import normalize_text

auth_bp = Blueprint("auth", __name__, url_prefix="")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = normalize_text(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        existing = mongo.db.users.find_one({"email": email})
        if existing:
            flash("An account with that email already exists.", "danger")
            return render_template("register.html")

        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        user = {
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "budget": 1000,
            "thresholds": {"low": 0.25, "high": 0.75},
        }
        result = mongo.db.users.insert_one(user)

        session.clear()
        session["user"] = {
            "id": str(result.inserted_id),
            "name": name,
            "email": email,
        }

        flash("Registration successful. Welcome!", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = normalize_text(request.form.get("email", ""))
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("login.html")

        user = mongo.db.users.find_one({"email": email})
        if not user:
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if not bcrypt.check_password_hash(user.get("password_hash"), password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        session.clear()
        session["user"] = {
            "id": str(user.get("_id")),
            "name": user.get("name"),
            "email": user.get("email"),
        }

        flash("Logged in successfully.", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
