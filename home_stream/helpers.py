# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Helper functions for the media browser."""

import hashlib
import hmac
import os

import yaml
from bcrypt import checkpw
from flask import Flask, abort, current_app, request


def load_config(app: Flask, filename: str) -> None:
    """Load configuration from a YAML file."""
    with open(filename, encoding="UTF-8") as f:
        config = yaml.safe_load(f)

    # Error when using default secret key
    if config.get("secret_key") == "CHANGE_ME_IN_FAVOUR_OF_A_LONG_PASSWORD":
        raise ValueError("You must change the default secret_key in the config file.")

    # Check whether mandatory keys are filled
    for required_key in (
        "users",
        "video_extensions",
        "audio_extensions",
        "media_root",
        "secret_key",
        "protocol",
    ):
        if required_key not in config:
            raise KeyError(f"Missing '{required_key}' key in config file.")
    # Combine video and audio extensions
    config["media_extensions"] = config.get("video_extensions", []) + config.get(
        "audio_extensions", []
    )
    # Add the config file content to the Flask app config
    for key, value in config.items():
        # Secret key as built-in Flask config and also as the stream secret
        if key == "secret_key":
            app.secret_key = value
            app.config["STREAM_SECRET"] = value
        else:
            app.config[key.upper()] = value


def secure_path(subpath):
    """Secure the path to prevent directory traversal attacks."""
    full_path = os.path.realpath(os.path.join(current_app.config["MEDIA_ROOT"], subpath))
    if not full_path.startswith(os.path.realpath(current_app.config["MEDIA_ROOT"])):
        abort(403)
    return full_path


def file_type(filename):
    """Determine the file type based on its extension."""
    ext = os.path.splitext(filename)[1].lower().strip(".")
    return "audio" if ext in current_app.config["AUDIO_EXTENSIONS"] else "video"


def verify_password(username, password):
    """Verify the provided username and password."""
    if username in current_app.config["USERS"] and checkpw(
        password.encode("utf-8"), current_app.config["USERS"].get(username).encode("utf-8")
    ):
        request.password = password
        return username
    return None


def validate_user(username, password):
    """Used for session-based auth (login form)."""
    if username in current_app.config["USERS"]:
        return checkpw(
            password.encode("utf-8"), current_app.config["USERS"][username].encode("utf-8")
        )
    return False


def get_stream_token(username: str, chars: int = 16) -> str:
    """Generate a n-chars permanent token for streaming based on username and secret key."""
    secret = current_app.config["STREAM_SECRET"]
    return hmac.new(secret.encode(), username.encode(), hashlib.sha256).hexdigest()[:chars]


def truncate_secret(secret: str, chars: int = 8) -> str:
    """Truncate the secret key to a specified length"""
    if len(secret) > chars:
        return secret[:chars] + "*" * (len(secret) - chars)
    return secret
