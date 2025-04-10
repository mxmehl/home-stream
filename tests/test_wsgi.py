# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream wsgi module"""

import sys
import tempfile

import yaml


def test_wsgi_app_initializes(monkeypatch):
    """Smoke test: Ensure wsgi.py loads the app without errors."""

    # Create a valid temp config file
    config = {
        "users": {"testuser": "fake"},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "testsecret",
        "protocol": "http",
    }
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        yaml.dump(config, f)
        f.flush()

        # Patch sys.argv to simulate a config file path
        monkeypatch.setattr(sys, "argv", ["wsgi.py", f.name])

        # Import the wsgi module
        import home_stream.wsgi as wsgi_module  # pylint: disable=import-outside-toplevel

        assert hasattr(wsgi_module, "app")
        assert wsgi_module.app is not None
