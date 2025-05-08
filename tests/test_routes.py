# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream application routes"""

import os

from tests.conftest import login_session


def test_login_page_loads(client):
    """Test that the login page loads correctly"""
    response = client.get("/login")
    assert response.status_code == 200
    assert b"<h2>Login</h2>" in response.data


def test_login_logout_flow(client):
    """Test the login and logout flow"""
    # Login with correct credentials
    response = client.post(
        "/login", data={"username": "testuser", "password": "test"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Overview" in response.data

    # Logout
    response = client.get("/logout", follow_redirects=True)
    assert b"Login" in response.data


def test_login_with_invalid_credentials(client):
    """Test login with invalid credentials"""
    response = client.post(
        "/login", data={"username": "testuser", "password": "wrong"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data


def test_login_rate_limit(client):
    """Trigger rate limiting on /login by making too many requests"""
    for _ in range(3):
        response = client.post("/login", data={"username": "testuser", "password": "wrong"})

    assert response.status_code == 429
    assert b"Too many login attempts" in response.data


def test_index_redirects_to_browse_when_logged_in(client, app):
    """Ensure / redirects to /browse/ for logged-in users"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/browse/")


def test_index_redirects_when_not_logged_in(client):
    """Test that the index page redirects to login when not logged in"""
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_404_on_invalid_browse_path(client, app):
    """Test that a 404 error is returned for an invalid browse path"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/non_existent_folder")
    assert response.status_code == 404


def test_browse_root_shows_page(client, app, media_file):  # pylint: disable=unused-argument
    """Access the root browse page when authenticated"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/")
    assert response.status_code == 200
    assert b"Folders" in response.data or b"Media Files" in response.data


def test_browse_existing_subdir(client, app):
    """Create a subfolder and confirm it shows up in browse view"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    media_root = app.config["MEDIA_ROOT"]
    subdir = os.path.join(media_root, "subfolder")
    os.makedirs(subdir, exist_ok=True)

    response = client.get("/browse/subfolder")
    assert response.status_code == 200
    assert b"subfolder" in response.data


def test_play_route_works(client, app, media_file_slugs):
    """Test that the /play/<filepath> route renders successfully when logged in"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get(f"/play/{slugified_filename}")
    assert response.status_code == 200
    assert b"Player" in response.data


def test_dl_token_for_invalid_token_returns_403(client, app):
    """Ensure /dl-token route returns 403 for invalid tokens"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/dl-token/testuser/badtoken/somefile.mp3")
    assert response.status_code == 403


def test_dl_token_valid_file_served(client, app, media_file_slugs, stream_token):
    """Ensure /dl-token with valid token returns a real MP3 file"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs
    url = f"/dl-token/testuser/{stream_token}/{slugified_filename}"

    response = client.get(url)

    assert response.status_code == 200
    assert response.data.startswith(b"ID3")


def test_dl_token_valid_but_file_missing(client, app, stream_token):
    """Return 404 if file is missing even with valid token."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    filename = "ghost.mp3"
    url = f"/dl-token/testuser/{stream_token}/{filename}"
    response = client.get(url)
    assert response.status_code == 404


def test_dl_token_playlist_m3u8_response(
    client, app, stream_token, media_file_slugs
):  # pylint: disable=unused-argument
    """Ensure .m3u8 playlist is returned for a folder with valid token"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    url = f"/dl-token/testuser/{stream_token}/test/with_spaces"
    response = client.get(url)

    assert response.status_code == 200
    assert response.mimetype == "audio/mpegurl"
    assert b"#EXTM3U" in response.data
    assert b"#EXTINF" in response.data
    assert b".mp3" in response.data
    assert b".txt" not in response.data


def test_dl_token_playlist_empty_folder(client, app, stream_token):
    """Ensure an empty folder returns a minimal .m3u8 playlist"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    empty_path = os.path.join(app.config["MEDIA_ROOT"], "empty_folder")
    os.makedirs(empty_path, exist_ok=True)

    url = f"/dl-token/testuser/{stream_token}/empty_folder"
    response = client.get(url)

    assert response.status_code == 200
    assert b"#EXTM3U" in response.data
    assert b"#EXTINF" not in response.data


def test_dl_token_playlist_invalid_path(client, app, stream_token):
    """Ensure a 404 is returned for an invalid folder path"""
    with client.session_transaction() as sess:
        login_session(sess, app)

    url = f"/dl-token/testuser/{stream_token}/nonexistent_folder"
    response = client.get(url)
    assert response.status_code == 404
