import os

from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.engine import Engine

import migrations
from config import Config
from models import db
from routes import BLUEPRINTS


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, _):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        migrations.upgrade()  # add columns introduced after the tables were first created

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"message": "Not found"}), 404

    @app.errorhandler(405)
    def not_allowed(_):
        return jsonify({"message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"message": "Something went wrong on the server"}), 500

    @app.cli.command("seed")
    def seed_command():
        """Insert career goals, skills and the admin account."""
        from seed import seed
        seed()
        print("Seeded career goals, skills and admin account.")

    @app.cli.command("migrate")
    def migrate_command():
        """Add any columns missing from an existing database (safe to re-run)."""
        added = migrations.upgrade()
        print("Added: " + ", ".join(added) if added else "Database schema is up to date.")

    @app.cli.command("reset-db")
    def reset_db_command():
        """Drop and recreate all tables, then seed."""
        from seed import seed
        db.drop_all()
        db.create_all()
        seed()
        print("Database reset and seeded.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
