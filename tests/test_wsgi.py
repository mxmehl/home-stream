# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream wsgi module"""

import os
import sys
import tempfile

import yaml


def test_wsgi_app_initializes(monkeypatch):
    """Smoke test: Ensure wsgi.py loads the app without errors."""

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
        config_path = f.name

    try:
        monkeypatch.setattr(sys, "argv", ["wsgi.py", config_path])
        import home_stream.wsgi as wsgi_module  # pylint: disable=import-outside-toplevel

        assert hasattr(wsgi_module, "app")
        assert wsgi_module.app is not None
    finally:
        os.remove(config_path)
