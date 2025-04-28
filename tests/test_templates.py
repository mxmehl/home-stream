# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream HTML templates"""

import os
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from home_stream.helpers import get_stream_token, get_version_info


def test_login_form_has_fields(client):
    """Ensure the login page renders a form with username and password fields"""
    response = client.get("/login")
    soup = BeautifulSoup(response.data, "html.parser")
    form = soup.find("form")
    assert form is not None
    assert form.find("input", {"name": "username"})
    assert form.find("input", {"name": "password"})


def test_browse_page_shows_file_actions(client, app, media_file):  # pylint: disable=unused-argument
    """Ensure browse.html shows download, play, and copy buttons for media files"""
    with client.session_transaction() as sess:
        sess["username"] = "testuser"

    response = client.get("/browse/")
    soup = BeautifulSoup(response.data, "html.parser")
    buttons = soup.find_all("button")
    labels = [btn.get_text(strip=True) for btn in buttons]

    assert any("Download" in label for label in labels)
    assert any("Play" in label for label in labels)
    assert any("Copy Stream URL" in label for label in labels)


def test_play_page_embeds_media(client):
    """Ensure /play/<file> renders the correct media tag"""
    with client.session_transaction() as sess:
        sess["username"] = "testuser"
    response = client.get("/play/sample.mp3")
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("audio") or soup.find("video")


def test_logout_button_shown_when_logged_in(client):
    """Logout button should be visible when user is authenticated"""
    with client.session_transaction() as sess:
        sess["username"] = "testuser"

    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")
    logout_form = soup.find("form", {"action": "/logout"})
    assert logout_form is not None
    assert "Logout" in logout_form.text


def test_logout_button_hidden_when_not_logged_in(client):
    """Logout button should not be present when not authenticated"""
    response = client.get("/login")
    soup = BeautifulSoup(response.data, "html.parser")
    logout_form = soup.find("form", {"action": "/logout"})
    assert logout_form is None


def test_play_page_has_correct_stream_url(client):
    """Ensure /play/<file> embeds the correct dl-token stream URL"""
    test_file = "song.mp3"

    with client.session_transaction() as sess:
        sess["username"] = "testuser"

    response = client.get(f"/play/{test_file}")
    soup = BeautifulSoup(response.data, "html.parser")
    source_tag = soup.find("source")
    assert source_tag is not None

    stream_url = unquote(source_tag["src"])
    expected_token = get_stream_token("testuser")
    assert stream_url.startswith(f"/dl-token/testuser/{expected_token}/{test_file}")


def test_browse_stream_url_copy_button(client, media_file):
    """Ensure the Copy Stream URL button includes full valid stream URL"""
    filename = os.path.basename(media_file)

    with client.session_transaction() as sess:
        sess["username"] = "testuser"

    response = client.get("/browse/")
    soup = BeautifulSoup(response.data, "html.parser")
    buttons = soup.find_all("button", string=lambda text: text and "Copy Stream URL" in text)
    assert buttons, "No Copy Stream URL button found"

    button = buttons[0]
    onclick = button.get("onclick")
    assert onclick and "copyToClipboard(" in onclick

    match = re.search(r"copyToClipboard\('([^']+)'", onclick)
    assert match, "Stream URL not found in onclick"

    stream_url = unquote(match.group(1))
    expected_token = get_stream_token("testuser")
    assert stream_url.startswith(f"http://localhost/dl-token/testuser/{expected_token}/{filename}")


def test_footer_version_displayed_when_logged_in(client):
    """Ensure footer shows version info when user is logged in"""
    with client.session_transaction() as sess:
        sess["username"] = "testuser"

    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")

    footer = soup.find("footer")
    assert footer is not None, "Footer not found"
    assert "home-stream" in footer.text
    assert get_version_info() in footer.text  # Version number appears


def test_footer_version_hidden_when_not_logged_in(client):
    """Ensure footer does not show version info when user is not logged in"""
    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")

    footer = soup.find("footer")
    assert footer is not None, "Footer not found"
    assert "home-stream" in footer.text
    assert get_version_info() not in footer.text  # Version number appears
