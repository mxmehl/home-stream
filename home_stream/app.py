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
    get_version_info,
    list_folder_entries,
    load_config,
    prepare_path_context,
    resolve_real_path_from_slugs,
    truncate_secret,
    validate_user,
)

from . import __version__


def create_app(config_path: str, debug: bool = False) -> Flask:
    """Create a Flask application instance."""
    app = Flask(__name__)
    app.debug = debug
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
        storage_uri=app.config.get("RATE_LIMIT_STORAGE_URI"),
    )
    if app.config.get("RATE_LIMIT_STORAGE_URI") == "memory://" and not app.debug:
        app.logger.warning(
            "Rate limiting is using in-memory storage. Limits may not work with multiple processes."
        )

    # Enable CSRF protection
    CSRFProtect(app)

    init_routes(app, limiter)
    return app


def init_routes(app: Flask, limiter: Limiter):
    """Initialize routes for the Flask application."""

    # Inject variables into templates
    @app.context_processor
    def inject_vars():
        return {
            "stream_token": get_stream_token(session["username"]) if "username" in session else "",
            "version_info": get_version_info(),
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

        # Build real and slug paths and breadcrumbs
        parts = [p for p in subpath.split("/") if p]
        real_path = resolve_real_path_from_slugs(parts)
        path_context = prepare_path_context(real_path, parts, app.config["MEDIA_ROOT"])

        if not os.path.isdir(real_path):
            abort(404)

        folders, files = list_folder_entries(real_path, parts)

        return render_template(
            "browse.html",
            slugified_path=path_context["slugified_path"],
            display_path=path_context["current_name"],
            breadcrumb_parts=path_context["breadcrumb_parts"],
            folders=folders,
            files=files,
            username=session.get("username"),
            protocol=app.config["PROTOCOL"],
        )

    @app.route("/play/<path:subpath>")
    def play(subpath):
        if not is_authenticated():
            return redirect(url_for("login", next=request.full_path))

        # Build real and slug paths and breadcrumbs
        parts = subpath.split("/")
        real_path = resolve_real_path_from_slugs(parts)
        path_context = prepare_path_context(real_path, parts, app.config["MEDIA_ROOT"])

        if not os.path.isfile(real_path):
            abort(404)

        return render_template(
            "play.html",
            slugified_path=path_context["slugified_path"],
            display_path=path_context["current_name"],
            breadcrumb_parts=path_context["breadcrumb_parts"],
            mediatype=file_type(real_path),
            username=session.get("username"),
        )

    @app.route("/dl-token/<username>/<token>/<path:subpath>")
    def download_token_auth(username, token, subpath):
        expected = get_stream_token(username)
        if token != expected:
            app.logger.info(
                f"Invalid dl-token for user '{username}'. "
                f"Expected '{truncate_secret(expected)}', got '{token}'"
            )
            abort(403)

        parts = subpath.split("/")
        real_path = resolve_real_path_from_slugs(parts)

        if os.path.isfile(real_path):
            return send_file(real_path)

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
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)

    args = parser.parse_args()

    # Create the app instance with the Flask development server
    app = create_app(config_path=os.path.abspath(args.config_file), debug=args.debug)
    app.run(debug=args.debug, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
