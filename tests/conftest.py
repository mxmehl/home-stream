# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Configuration for pytest fixtures"""

import os
import shutil
import tempfile
import uuid

import bcrypt
import pytest
import yaml

from home_stream.app import create_app
from home_stream.helpers import compute_session_signature, get_stream_token, slugify

MINIMAL_MP3 = bytes.fromhex(
    "494433030000000021764c414d4533322e39372e39000000"  # ID3 header for metadata
    "fffb90440000000000000000000000000000000000000000"  # Fake MPEG frame
)


def create_temp_config(content: dict) -> str:
    """Write a temporary YAML config file and return its path."""
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        yaml.dump(content, f)
        f.flush()
        return f.name


@pytest.fixture(name="temp_media_root")
def fixture_temp_media_root():
    """Create a temporary directory to act as media_root"""
    tmp_dir = tempfile.mkdtemp(prefix="media_")
    yield tmp_dir
    shutil.rmtree(tmp_dir)


@pytest.fixture(name="config_file")
def fixture_config_file(temp_media_root):
    """Create a temporary config file for testing"""
    hashed_pw = bcrypt.hashpw("test".encode(), bcrypt.gensalt()).decode()
    config = {
        "users": {"testuser": hashed_pw},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": temp_media_root,
        "secret_key": "testsecret",
        "protocol": "http",
    }
    path = create_temp_config(config)
    yield path
    os.remove(path)


@pytest.fixture(name="app")
def fixture_app(config_file):
    """Create a Flask app for testing"""
    app = create_app(config_file, debug=True)
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,  # Disable CSRF in tests
        }
    )
    yield app


@pytest.fixture(name="client")
def fixture_client(app):
    """Create a test client for the app"""
    return app.test_client()


def login_session(sess, app, username="testuser"):
    """Helper to simulate a logged-in user inside a test session."""
    with app.app_context():
        users = app.config["USERS"]
        secret = app.config["STREAM_SECRET"]

        sess["username"] = username
        sess["auth_signature"] = compute_session_signature(username, users[username], secret)


@pytest.fixture(name="stream_token")
def fixture_stream_token():
    """Get the default stream token for 'testuser'"""
    return get_stream_token("testuser")


@pytest.fixture(name="media_file")
def fixture_media_file(app):
    """
    Create a minimal valid MP3 file inside MEDIA_ROOT with spaces in filename and parent directories
    """

    # Create a temporary directory with spaces for the media file
    media_root = app.config["MEDIA_ROOT"]
    folder = os.path.join(media_root, "test", "with spaces")
    os.makedirs(folder, exist_ok=True)

    # Example: 'sample testfile 12ab34cd56ef.mp3'
    filename = f"sample testfile {uuid.uuid4().hex[:8]}.mp3"
    file_path = os.path.join(folder, filename)
    with open(file_path, "wb") as f:
        f.write(MINIMAL_MP3)

    # Also create a non-media file inside the same folder
    non_media_file = os.path.join(folder, "non_media_file.txt")
    with open(non_media_file, "w", encoding="UTF-8") as f:
        f.write("This is not a media file.")

    yield file_path
    os.remove(file_path)


@pytest.fixture(name="media_file_slugs")
def fixture_media_file_slugs(media_file, app):
    """Return both real filename and full slugified path including folders"""
    rel_path = os.path.relpath(media_file, app.config["MEDIA_ROOT"])
    parts = rel_path.split(os.sep)
    slugified_parts = [slugify(p) for p in parts]
    return os.path.basename(media_file), "/".join(slugified_parts)
