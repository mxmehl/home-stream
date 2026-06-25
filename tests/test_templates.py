# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream HTML templates."""

import re
from os.path import dirname
from urllib.parse import unquote

from bs4 import BeautifulSoup

from home_stream.helpers import get_version_info
from tests.conftest import login_session


def test_login_form_has_fields(client) -> None:
    """Ensure the login page renders a form with username and password fields."""
    response = client.get("/login")
    soup = BeautifulSoup(response.data, "html.parser")
    form = soup.find("form")
    assert form is not None
    assert form.find("input", {"name": "username"})
    assert form.find("input", {"name": "password"})


def test_browse_page_shows_file_actions(client, app, media_file) -> None:
    """Ensure browse.html shows download, play, and copy buttons for media files."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")
    buttons = soup.find_all("button")
    labels = [btn.get_text(strip=True) for btn in buttons]

    assert any("Download" in label for label in labels)
    assert any("Play" in label for label in labels)
    assert any("Copy Stream URL" in label for label in labels)


def test_play_page_embeds_media(client, app, media_file_slugs) -> None:
    """Ensure /play/<file> renders the correct media tag."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get(f"/play/{slugified_filename}")
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("audio") or soup.find("video")


def test_logout_button_shown_when_logged_in(client, app) -> None:
    """Logout button should be visible when user is authenticated."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")
    logout_form = soup.find("form", {"action": "/logout"})
    assert logout_form is not None
    assert "Logout" in logout_form.text


def test_logout_button_hidden_when_not_logged_in(client) -> None:
    """Logout button should not be present when not authenticated."""
    response = client.get("/login")
    soup = BeautifulSoup(response.data, "html.parser")
    logout_form = soup.find("form", {"action": "/logout"})
    assert logout_form is None


def test_play_page_has_correct_stream_url(client, app, media_file_slugs, stream_token) -> None:
    """Ensure /play/<file> embeds the correct dl-token stream URL."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get(f"/play/{slugified_filename}")
    soup = BeautifulSoup(response.data, "html.parser")
    source_tag = soup.find("source")
    assert source_tag is not None

    stream_url = unquote(source_tag["src"])

    assert stream_url.startswith(f"http://localhost/dl-token/testuser/{stream_token}/")


def test_play_page_stream_url_works(client, app, media_file_slugs, stream_token) -> None:
    """Ensure the stream URL embedded in /play works when fetched."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    # Load the play page
    response = client.get(f"/play/{slugified_filename}")
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    source_tag = soup.find("source")
    assert source_tag is not None

    stream_url = unquote(source_tag["src"])

    # Fetch the actual stream URL
    stream_response = client.get(stream_url)
    assert stream_token in stream_url
    assert stream_response.status_code == 200
    assert stream_response.data.startswith(b"ID3")


def test_browse_stream_url_copy_button(client, app, media_file_slugs, stream_token) -> None:
    """Ensure the Copy Stream URL button includes full valid stream URL."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")
    buttons = soup.find_all("button", string=lambda text: text and "Copy URL" in text)
    assert buttons, "No Copy URL button found"

    button = buttons[0]
    onclick = button.get("onclick")
    assert onclick
    assert "copyToClipboard(" in onclick

    match = re.search(r"copyToClipboard\('([^']+)'", onclick)
    assert match, "Stream URL not found in onclick"

    stream_url = unquote(match.group(1))
    assert stream_url.startswith(
        f"http://localhost/dl-token/testuser/{stream_token}/{slugified_filename}"
    )


def test_footer_version_displayed_when_logged_in(client, app) -> None:
    """Ensure footer shows version info when user is logged in."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")

    footer = soup.find("footer")
    assert footer is not None, "Footer not found"
    assert "home-stream" in footer.text
    assert get_version_info() in footer.text  # Version number appears


def test_footer_version_hidden_when_not_logged_in(client) -> None:
    """Ensure footer does not show version info when user is not logged in."""
    response = client.get("/", follow_redirects=True)
    soup = BeautifulSoup(response.data, "html.parser")

    footer = soup.find("footer")
    assert footer is not None, "Footer not found"
    assert "home-stream" in footer.text
    assert get_version_info() not in footer.text  # Version number appears


def test_browse_page_shows_breadcrumbs(client, app, media_file_slugs) -> None:
    """Ensure /browse/<subfolder> displays correct breadcrumbs and headline."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs
    response = client.get(f"/browse/{dirname(slugified_filename)}")

    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")

    breadcrumbs = soup.find("p", class_="breadcrumbs")
    assert breadcrumbs is not None
    assert "Overview" in breadcrumbs.text
    assert "test" in breadcrumbs.text
    # DO NOT expect "with spaces" inside breadcrumbs

    headline = soup.find("h1")
    assert headline is not None
    assert "with spaces" in headline.text


def test_play_page_shows_breadcrumbs(client, app, media_file_slugs) -> None:
    """Ensure /play/<file> displays breadcrumbs."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get(f"/play/{slugified_filename}")

    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")

    breadcrumbs = soup.find("p", class_="breadcrumbs")
    assert breadcrumbs is not None
    assert "Overview" in breadcrumbs.text
    assert "test" in breadcrumbs.text
    assert "with spaces" in breadcrumbs.text


def test_play_folder_renders_playlist_view(client, app, media_file_slugs) -> None:
    """Ensure /play/<folder> renders playlist player when path is a directory."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    # The fixture creates the file in /tmp/test/with spaces/
    response = client.get("/play/test/with_spaces")
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("ul", {"id": "playlist"}) is not None
    assert soup.find(id="media-player") is not None
    assert "Now Playing" in soup.text


def test_browse_page_playlist_url_present(client, app, stream_token, media_file_slugs) -> None:
    """Ensure the download playlist button uses the .m3u8 stream URL."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")

    assert soup.find_all("a", string=lambda t: "Download playlist" in t)
    assert any(
        b["href"].startswith(f"http://localhost/dl-token/testuser/{stream_token}")
        and "with_spaces" in b["href"]
        for b in soup.find_all("a", href=True)
    )


def test_browse_page_playlist_stream_url_button(
    client, app, media_file_slugs, stream_token
) -> None:
    """Ensure the playlist stream URL works when fetched."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_filename = media_file_slugs

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")

    buttons = soup.find_all(
        "button", string=lambda text: text and "Copy Stream URL for playlist" in text
    )
    assert buttons, "No Copy Stream URL for Playlist button found"

    button = buttons[0]
    onclick = button.get("onclick")
    assert onclick
    assert "copyToClipboard(" in onclick

    match = re.search(r"copyToClipboard\('([^']+)'", onclick)
    assert match, "Stream URL not found in onclick"

    stream_url = unquote(match.group(1))
    assert stream_url.startswith(
        f"http://localhost/dl-token/testuser/{stream_token}/{dirname(slugified_filename)}"
    )


def test_play_folder_with_multiple_files(client, app, media_file_slugs, stream_token) -> None:
    """Ensure /play/<folder> renders a playlist with correct stream URLs."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    _, slugified_path = media_file_slugs
    expected_url = f"http://localhost/dl-token/testuser/{stream_token}/{slugified_path}"

    # Access the folder-level play route
    response = client.get("/play/test/with_spaces")
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")

    # Check core playlist elements
    playlist = soup.find("ul", {"id": "playlist"})
    assert playlist is not None
    assert soup.find(id="media-player") is not None
    assert soup.find(id="now-playing") is not None

    items = playlist.find_all("li")
    assert len(items) >= 2, "Expected at least two playlist items"

    # Validate structure and content
    found_stream_url = False
    for li in items:
        track = li.find("span", class_="track")
        assert track is not None
        assert li.has_attr("data-src")
        url = li["data-src"]
        assert url.startswith("http")

        if expected_url in url:
            found_stream_url = True

    assert found_stream_url, "Expected stream URL not found in any playlist item"


# --- .nfo metadata rendering tests ---


def test_browse_shows_nfo_title(client, app, media_file) -> None:
    """A sibling .nfo title is rendered as the primary line, filename demoted below."""
    # Create a video file (routes to the .nfo reader) in the same browsable folder.
    folder = dirname(media_file)
    video_path = f"{folder}/episode.mp4"
    with open(video_path, "wb") as f:
        f.write(b"x")
    nfo_path = video_path.rsplit(".", 1)[0] + ".nfo"
    with open(nfo_path, "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0"?>\n'
            "<episodedetails><title>Real Episode Title</title>"
            "<season>2</season><episode>4</episode>"
            "<year>2018</year><rating>7.5</rating>"
            "<fileinfo><streamdetails><video>"
            "<durationinseconds>1325</durationinseconds>"
            "</video></streamdetails></fileinfo>"
            "<plot>Some plot.</plot></episodedetails>"
        )

    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")
    title = soup.find("span", class_="file-title")
    assert title is not None
    assert title.get_text(strip=True) == "Real Episode Title"
    # Plot is shown in a collapsible <details>, with the metadata line as the summary
    details = soup.find("details", class_="file-details")
    assert details is not None
    summary = details.find("summary", class_="file-name")
    assert summary is not None
    # Secondary (summary) line: SxxExx - year - rating - duration - filename, in that order
    text = " ".join(summary.get_text().split())
    assert text.startswith("S02E04 - 2018 - \u26057.5 - 22:05 - ")
    assert text.endswith(".mp4")
    # Plot is real DOM text (not a tooltip), inside the details
    plot = details.find("p", class_="file-plot")
    assert plot is not None
    assert plot.get_text(strip=True) == "Some plot."


def test_browse_shows_tvshow_header(client, app, media_file) -> None:
    """A tvshow.nfo in the folder renders a show metadata header."""
    folder = dirname(media_file)
    with open(f"{folder}/tvshow.nfo", "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0"?>\n'
            "<tvshow><title>My Show</title><year>2017</year>"
            "<rating>8.1</rating></tvshow>"
        )

    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")
    header = soup.find("p", class_="show-meta")
    assert header is not None
    text = header.get_text()
    assert "My Show" in text
    assert "2017" in text
    assert "8.1" in text


def test_browse_no_nfo_no_meta(client, app, media_file) -> None:
    """Without .nfo files, no metadata elements are rendered."""
    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("span", class_="file-title") is None
    assert soup.find("span", class_="file-name") is None
    assert soup.find("p", class_="show-meta") is None


def test_browse_nfo_disabled(client, app, media_file) -> None:
    """With the toggle off, .nfo metadata is not read or rendered."""
    app.config["SHOW_METADATA"] = False
    nfo_path = media_file.rsplit(".", 1)[0] + ".nfo"
    with open(nfo_path, "w", encoding="utf-8") as f:
        f.write("<episodedetails><title>Hidden</title></episodedetails>")

    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    assert b"Hidden" not in response.data


def test_browse_shows_audio_metadata(client, app, media_file) -> None:
    """Audio: primary 'NN. title', secondary 'duration - artist - album - filename'."""
    from mutagen.easyid3 import EasyID3

    # Replace the fixture's media file with a real tagged MP3 in the same folder.
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    with open(media_file, "wb") as f:
        f.write(frame * 8)
    tags = EasyID3()
    tags["title"] = "Bohemian Rhapsody"
    tags["artist"] = "Queen"
    tags["album"] = "A Night at the Opera"
    tags["tracknumber"] = "11/12"
    tags.save(media_file)

    with client.session_transaction() as sess:
        login_session(sess, app)

    response = client.get("/browse/test/with_spaces/")
    soup = BeautifulSoup(response.data, "html.parser")

    # Primary line: zero-padded track number + title
    title = soup.find("span", class_="file-title")
    assert title is not None
    assert title.get_text(strip=True) == "11. Bohemian Rhapsody"
    # Secondary line: artist - album - duration - filename
    name_line = soup.find("span", class_="file-name")
    assert name_line is not None
    text = " ".join(name_line.get_text().split())
    assert text.startswith("Queen - A Night at the Opera - ")
    assert text.endswith(".mp3")
