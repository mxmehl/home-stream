# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Home Stream Web Application"""

import argparse
import logging
import os

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from home_stream.forms import LoginForm
from home_stream.helpers import (
    file_type,
    get_stream_token,
    load_config,
    secure_path,
    truncate_secret,
    validate_user,
)


def create_app(config_path: str) -> Flask:
    """Create a Flask application instance."""
    app = Flask(__name__)
    load_config(app, config_path)

    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

    # Trust headers from reverse proxy (1 layer by default)
    app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Secure session cookie config
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax"
    )

    # Set up rate limiting
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["50 per 10 minutes"],
        storage_uri="memory://",
    )

    # Enable CSRF protection
    CSRFProtect(app)

    init_routes(app, limiter)
    return app


def init_routes(app: Flask, limiter: Limiter):
    """Initialize routes for the Flask application."""

    @app.context_processor
    def inject_auth():
        return {
            "stream_token": get_stream_token(session["username"]) if "username" in session else "",
        }

    def is_authenticated():
        return session.get("username") in app.config["USERS"]

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("2 per 10 seconds")
    def login():
        form = LoginForm()
        error = None
        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data
            if validate_user(username, password):
                app.logger.info(
                    f"Login success for user '{username}' from IP {request.remote_addr}"
                )
                session.clear()
                session["username"] = username
                return redirect(request.args.get("next") or url_for("index"))

            app.logger.warning(f"Login failed for user '{username}' from IP {request.remote_addr}")
            error = "Invalid credentials"
        return render_template("login.html", form=form, error=error)

    @app.route("/logout")
    def logout():
        user = session.get("username")
        if user:
            app.logger.info(f"User '{user}' logged out from IP {request.remote_addr}")
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        if not is_authenticated():
            return redirect(url_for("login", next=request.full_path))
        return redirect(url_for("browse", subpath=""))

    @app.route("/browse/", defaults={"subpath": ""})
    @app.route("/browse/<path:subpath>")
    def browse(subpath):
        if not is_authenticated():
            return redirect(url_for("login", next=request.full_path))

        current_path = secure_path(subpath)
        if not os.path.isdir(current_path):
            abort(404)

        folders, files = [], []
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            rel = os.path.join(subpath, entry)
            if os.path.isdir(full) and not entry.startswith("."):
                folders.append((entry, rel))
            elif os.path.isfile(full):
                ext = os.path.splitext(entry)[1].lower().strip(".")
                if ext in app.config["MEDIA_EXTENSIONS"]:
                    files.append((entry, rel))

        folders.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())

        return render_template(
            "browse.html",
            path=subpath,
            folders=folders,
            files=files,
            username=session.get("username"),
            protocol=app.config["PROTOCOL"],
        )

    @app.route("/play/<path:filepath>")
    def play(filepath):
        if not is_authenticated():
            return redirect(url_for("login", next=request.full_path))

        secure_path(filepath)
        return render_template(
            "play.html",
            path=filepath,
            mediatype=file_type(filepath),
            username=session.get("username"),
        )

    @app.route("/dl-token/<username>/<token>/<path:filepath>")
    def download_token_auth(username, token, filepath):
        expected = get_stream_token(username)
        if token != expected:
            app.logger.info(
                f"Invalid dl-token for user '{username}'. "
                f"Expected '{truncate_secret(expected)}', got '{token}'"
            )
            abort(403)
        full_path = secure_path(filepath)
        if os.path.isfile(full_path):
            return send_file(full_path)
        abort(404)

    # ERROR HANDLERS
    @app.errorhandler(429)
    def ratelimit_handler(e):
        ip = request.remote_addr
        endpoint = request.endpoint
        app.logger.warning(f"Rate limit exceeded from IP {ip} on {endpoint}: {e.description}")

        # Nice error message for login route
        if endpoint == "login":
            form = LoginForm()
            return (
                render_template(
                    "login.html", error="Too many login attempts. Try again soon.", form=form
                ),
                429,
            )

        # Default response for other rate-limited routes
        return "Too many requests. Please slow down.", 429


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-c", "--config-file", required=True, help="Path to the app's config file (YAML format)"
    )
    parser.add_argument("--host", default="localhost", help="Hostname of the server")
    parser.add_argument("-p", "--port", type=int, default=8000, help="Port of the server")
    parser.add_argument(
        "-vv",
        "--debug",
        action="store_true",
        help="Enable debug mode",
        default=False,
    )

    args = parser.parse_args()

    # Create the app instance with the Flask development server
    app = create_app(config_path=os.path.abspath(args.config_file))
    app.run(debug=args.debug, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
