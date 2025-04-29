# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream application helpers"""

import os
import re
import tempfile

import pytest
import yaml
from flask import Flask, current_app, request

from home_stream.helpers import (
    REQUIRED_CONFIG_KEYS,
    compute_session_signature,
    deslugify,
    file_type,
    get_stream_token,
    get_version_info,
    load_config,
    prepare_path_context,
    secure_path,
    slugify,
    truncate_secret,
    validate_user,
    verify_password,
)


def test_get_stream_token_is_consistent(app):
    """Test that get_stream_token returns consistent output for same input"""
    with app.app_context():
        token1 = get_stream_token("testuser")
        token2 = get_stream_token("testuser")
        assert token1 == token2
        assert len(token1) == 16


def test_truncate_secret_behavior():
    """Ensure truncate_secret masks beyond the specified length"""
    original = "verylongsecret"
    truncated = truncate_secret(original, chars=4)
    assert truncated == "very**********"


def test_truncate_secret_short_value():
    """Truncation should not alter short secrets"""
    short = "abc"
    assert truncate_secret(short, chars=8) == "abc"


def test_secure_path_allows_normal_path(app):
    """Ensure secure_path returns resolved path for valid subpath"""
    with app.app_context():
        media_root = current_app.config["MEDIA_ROOT"]
        subpath = "example"
        os.makedirs(os.path.join(media_root, subpath), exist_ok=True)

        resolved = secure_path(subpath)
        assert resolved.startswith(media_root)
        assert resolved.endswith("example")


def test_secure_path_blocks_traversal(app):
    """Ensure secure_path blocks ../ path traversal attempts"""
    with app.app_context():
        with pytest.raises(Exception) as excinfo:
            secure_path("../etc/passwd")
        assert "403" in str(excinfo.value)


def test_validate_user_success(app):
    """Return True if username and password match config"""
    with app.app_context():
        assert validate_user("testuser", "test") is True


def test_validate_user_failure(app):
    """Return False for unknown user or wrong password"""
    with app.app_context():
        assert validate_user("nonexistent", "test") is False
        assert validate_user("testuser", "wrongpassword") is False


def test_file_type_detection(app):
    """Correctly detect audio vs video types based on extension"""
    with app.app_context():
        assert file_type("song.mp3") == "audio"
        assert file_type("video.mp4") == "video"
        assert file_type("unknown.xyz") == "video"  # fallback if not in audio list


def test_get_stream_token_missing_secret(app):
    """Raise KeyError if STREAM_SECRET is not set in config"""
    with app.app_context():
        del app.config["STREAM_SECRET"]
        with pytest.raises(KeyError):
            get_stream_token("testuser")


def test_load_config_raises_if_default_secret_used():
    """Raise ValueError if secret_key is left as the insecure default."""
    config = {
        "users": {"testuser": "fake"},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "CHANGE_ME_IN_FAVOUR_OF_A_LONG_PASSWORD",
        "protocol": "http",
    }

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        yaml.dump(config, f)
        f.flush()

        app = Flask("test")
        with pytest.raises(ValueError, match="default secret_key"):
            load_config(app, f.name)


@pytest.mark.parametrize("missing_key", REQUIRED_CONFIG_KEYS)
def test_load_config_raises_when_key_is_missing(missing_key):
    """Raise KeyError if any required config key is missing."""
    # Start with a valid config
    config = {
        "users": {"testuser": "fake"},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "supersecret",
        "protocol": "http",
    }

    config.pop(missing_key)

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        yaml.dump(config, f)
        f.flush()

        app = Flask("test")
        with pytest.raises(KeyError, match=f"Missing '{missing_key}'"):
            load_config(app, f.name)


def test_load_config_successfully_sets_flask_config(app):
    """Verify load_config populates Flask config properly"""

    with app.app_context():
        assert current_app.secret_key == "testsecret"
        assert current_app.secret_key == current_app.config["SECRET_KEY"]
        assert current_app.config["STREAM_SECRET"] == current_app.secret_key
        assert current_app.config["MEDIA_EXTENSIONS"] == ["mp4", "mp3"]


def test_verify_password_success(app, client):
    """verify_password should return the username if password matches"""
    with app.app_context():
        with client:
            result = verify_password("testuser", "test")
            assert result == "testuser"
            assert hasattr(request, "password")
            assert request.password == "test"


def test_verify_password_failure(app):
    """verify_password returns None if user or password is wrong"""
    with app.app_context():
        assert verify_password("unknown", "test") is None
        assert verify_password("testuser", "wrong") is None


def test_get_version_info():
    """Test that get_version_info returns the expected version format"""
    version_info = get_version_info()

    # Expect format like "0.4.3 (abc123)"
    assert re.match(
        r"^\d+\.\d+\.\d+ \([a-z0-9]+\)$", version_info
    ), f"Unexpected version format: {version_info}"


def test_get_version_info_git_failure(app, monkeypatch):
    """Test that get_version_info handles git failure gracefully"""
    # Simulate subprocess raising an exception
    monkeypatch.setattr(
        "subprocess.check_output", lambda cmd: (_ for _ in ()).throw(Exception("git error"))
    )

    with app.app_context():
        version_info = get_version_info()

    assert version_info.endswith(
        "(unknown commit)"
    ), f"Unexpected version info on git failure: {version_info}"


def test_deslugify_success(tmp_path):
    """deslugify should find and return the matching real filename"""
    # Create a file with spaces
    filename = "My Test File.mp3"
    file_path = tmp_path / filename
    file_path.write_text("dummy content")

    # Lookup using slugified name
    slug = slugify(filename)
    found = deslugify(slug, str(tmp_path))

    assert found == filename


def test_deslugify_raises_file_not_found(tmp_path):
    """deslugify should raise FileNotFoundError if no file matches the slug"""
    # Empty directory -> no match possible
    empty_dir = tmp_path

    with pytest.raises(FileNotFoundError) as excinfo:
        deslugify("nonexistent_slug", str(empty_dir))

    assert "No match for slug" in str(excinfo.value)


def test_prepare_path_context_generates_breadcrumbs():
    """Ensure prepare_path_context returns expected structure"""
    real_path = "/media/data/Shows/Battlestar Galactica/Season 1"
    slug_parts = ["Shows", "Battlestar_Galactica", "Season_1"]
    media_root = "/media/data"

    context = prepare_path_context(real_path, slug_parts, media_root)

    assert context["slugified_path"] == "Shows/Battlestar_Galactica/Season_1"
    assert context["display_path"] == "Shows/Battlestar Galactica/Season 1"
    assert context["current_name"] == "Season 1"
    assert context["breadcrumb_parts"] == [
        {"name": "Overview", "slug": ""},
        {"name": "Shows", "slug": "Shows"},
        {"name": "Battlestar Galactica", "slug": "Shows/Battlestar_Galactica"},
    ]


def test_stream_token_changes_when_password_changes(app):
    """Ensure that changing the user's password results in a new stream token"""
    with app.app_context():
        users = current_app.config["USERS"]

        # Original token
        original_token = get_stream_token("testuser")

        # Simulate password change
        users["testuser"] = "new_fake_password_hash"

        # New token after password change
        new_token = get_stream_token("testuser")

        assert original_token != new_token, "Stream token did not change after password update"


def test_get_stream_token_raises_for_missing_user(app):
    """Ensure get_stream_token raises ValueError if user does not exist"""
    with app.app_context():
        with pytest.raises(ValueError, match="User 'unknownuser' not found"):
            get_stream_token("unknownuser")


def test_compute_session_signature_changes_on_password_change():
    """Ensure that session signature changes when the password hash changes."""
    username = "testuser"
    secret = "testsecret"
    password_hash_old = "old_fake_hash"
    password_hash_new = "new_fake_hash"

    sig_old = compute_session_signature(username, password_hash_old, secret)
    sig_new = compute_session_signature(username, password_hash_new, secret)

    assert sig_old != sig_new, "Session signature did not change after password update"


def test_compute_session_signature_consistency():
    """Ensure the same inputs produce the same session signature."""
    username = "testuser"
    password_hash = "some_hash"
    secret = "testsecret"

    sig1 = compute_session_signature(username, password_hash, secret)
    sig2 = compute_session_signature(username, password_hash, secret)

    assert sig1 == sig2, "Session signature is not deterministic"
