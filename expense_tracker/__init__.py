import os
from datetime import datetime

from flask import Flask
from .config import Config
from .extensions import mongo, bcrypt


def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    app = Flask(__name__, static_folder=static_dir, template_folder=template_dir)
    app.config.from_object(Config)

    # Initialize shared extensions
    mongo.init_app(app)
    bcrypt.init_app(app)

    # Context helpers
    @app.context_processor
    def inject_current_year():
        return {"current_year": datetime.utcnow().year}

    # Register blueprints
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .expenses import expenses_bp
    from .insights import insights_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(insights_bp)

    from flask import g

    @app.before_request
    def verify_mongo_connection():
        # Only check once per worker to avoid repeating pings on every request.
        if getattr(g, "mongo_checked", False):
            return
        try:
            mongo.cx.admin.command("ping")
            g.mongo_checked = True
        except Exception as exc:
            raise RuntimeError(
                "Unable to connect to MongoDB. Ensure MongoDB is running locally and MONGO_URI is correct."
            ) from exc

    return app
