from flask import Flask
from flask_cors import CORS

from .config import Config
from .routes import register_routes
from .storage import ensure_buckets


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, resources={r"/*": {"origins": "*"}})

    ensure_buckets(app.config)
    register_routes(app)
    return app
