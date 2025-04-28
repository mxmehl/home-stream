# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Configuration for pytest fixtures"""

import os
import tempfile
import uuid

import bcrypt
import pytest
import yaml

from home_stream.app import create_app
from home_stream.helpers import get_stream_token, slugify

MINIMAL_MP3 = bytes.fromhex(
    "494433030000000021764c414d4533322e39372e39000000"  # ID3 header for metadata
    "fffb90440000000000000000000000000000000000000000"  # Fake MPEG frame
)


@pytest.fixture(name="config_file")
def fixture_config_file():
    """Create a temporary config file for testing"""
    hashed_pw = bcrypt.hashpw("test".encode(), bcrypt.gensalt()).decode()
    config = {
        "users": {"testuser": hashed_pw},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "testsecret",
        "protocol": "http",
    }
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        yaml.dump(config, f)
        return f.name


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


@pytest.fixture(name="stream_token")
def fixture_stream_token():
    """Get the default stream token for 'testuser'"""
    return get_stream_token("testuser")


@pytest.fixture(name="media_file")
def fixture_media_file():
    """Create a minimal valid MP3 file inside MEDIA_ROOT with spaces in filename"""
    # Example: 'sample testfile 12ab34cd56ef.mp3'
    filename = f"sample testfile {uuid.uuid4().hex[:8]}.mp3"
    file_path = os.path.join("/tmp", filename)

    with open(file_path, "wb") as f:
        f.write(MINIMAL_MP3)
    yield file_path
    os.remove(file_path)


@pytest.fixture(name="media_file_slugs")
def fixture_media_file_slugs(media_file):
    """Provide both the real filename and its slugified version"""

    filename = os.path.basename(media_file)
    slugified_filename = slugify(filename)
    return filename, slugified_filename
