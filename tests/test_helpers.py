# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Home Stream application helpers."""

import os
import re

import pytest
from flask import Flask, current_app, request

from home_stream.helpers import (
    REQUIRED_CONFIG_KEYS,
    _format_duration,
    build_file_download_response,
    compute_session_signature,
    deslugify,
    file_type,
    get_stream_token,
    get_version_info,
    load_config,
    prepare_path_context,
    read_audio_metadata,
    read_nfo_metadata,
    read_tvshow_metadata,
    sanitize_filename,
    secure_path,
    slugify,
    truncate_secret,
    validate_user,
    verify_password,
)
from tests.conftest import create_temp_config


def test_get_stream_token_is_consistent(app) -> None:
    """Test that get_stream_token returns consistent output for same input."""
    with app.app_context():
        token1 = get_stream_token("testuser")
        token2 = get_stream_token("testuser")
        assert token1 == token2
        assert len(token1) == 16


def test_truncate_secret_behavior() -> None:
    """Ensure truncate_secret masks beyond the specified length."""
    original = "verylongsecret"
    truncated = truncate_secret(original, chars=4)
    assert truncated == "very**********"


def test_truncate_secret_short_value() -> None:
    """Truncation should not alter short secrets."""
    short = "abc"
    assert truncate_secret(short, chars=8) == "abc"


def test_secure_path_allows_normal_path(app) -> None:
    """Ensure secure_path returns resolved path for valid subpath."""
    with app.app_context():
        media_root = current_app.config["MEDIA_ROOT"]
        subpath = "example"
        os.makedirs(os.path.join(media_root, subpath), exist_ok=True)

        resolved = secure_path(subpath)
        assert os.path.realpath(resolved).startswith(os.path.realpath(media_root))
        assert resolved.endswith("example")


def test_secure_path_blocks_traversal(app) -> None:
    """Ensure secure_path blocks ../ path traversal attempts."""
    with app.app_context():
        with pytest.raises(Exception) as excinfo:
            secure_path("../etc/passwd")
        assert "403" in str(excinfo.value)


def test_validate_user_success(app) -> None:
    """Return True if username and password match config."""
    with app.app_context():
        assert validate_user("testuser", "test") is True


def test_validate_user_failure(app) -> None:
    """Return False for unknown user or wrong password."""
    with app.app_context():
        assert validate_user("nonexistent", "test") is False
        assert validate_user("testuser", "wrongpassword") is False


def test_file_type_detection(app) -> None:
    """Correctly detect audio vs video types based on extension."""
    with app.app_context():
        assert file_type("song.mp3") == "audio"
        assert file_type("video.mp4") == "video"
        assert file_type("unknown.xyz") == "video"  # fallback if not in audio list


def test_get_stream_token_missing_secret(app) -> None:
    """Raise KeyError if STREAM_SECRET is not set in config."""
    with app.app_context():
        del app.config["STREAM_SECRET"]
        with pytest.raises(KeyError):
            get_stream_token("testuser")


def test_load_config_raises_if_default_secret_used() -> None:
    """Raise ValueError if secret_key is left as the insecure default."""
    config = {
        "users": {"testuser": "fake"},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "CHANGE_ME_IN_FAVOUR_OF_A_LONG_PASSWORD",
        "protocol": "http",
    }

    path = create_temp_config(config)
    try:
        app = Flask("test")
        with pytest.raises(ValueError, match="default secret_key"):
            load_config(app, path)
    finally:
        os.remove(path)


@pytest.mark.parametrize("missing_key", REQUIRED_CONFIG_KEYS)
def test_load_config_raises_when_key_is_missing(missing_key) -> None:
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

    path = create_temp_config(config)
    try:
        app = Flask("test")
        with pytest.raises(KeyError, match=f"Missing '{missing_key}'"):
            load_config(app, path)
    finally:
        os.remove(path)


def test_load_config_successfully_sets_flask_config(app) -> None:
    """Verify load_config populates Flask config properly."""
    with app.app_context():
        assert current_app.secret_key == "testsecret"
        assert current_app.secret_key == current_app.config["SECRET_KEY"]
        assert current_app.config["STREAM_SECRET"] == current_app.secret_key
        assert current_app.config["MEDIA_EXTENSIONS"] == ["mp4", "mp3"]


def _base_config() -> dict:
    """Return a minimal valid config dict for load_config tests."""
    return {
        "users": {"testuser": "fake"},
        "video_extensions": ["mp4"],
        "audio_extensions": ["mp3"],
        "media_root": "/tmp",
        "secret_key": "supersecret",
        "protocol": "http",
    }


def test_load_config_download_method_defaults() -> None:
    """download_method defaults to 'direct' and prefix to '/_protected'."""
    path = create_temp_config(_base_config())
    try:
        app = Flask("test")
        load_config(app, path)
        assert app.config["DOWNLOAD_METHOD"] == "direct"
        assert app.config["DOWNLOAD_INTERNAL_PREFIX"] == "/_protected"
    finally:
        os.remove(path)


@pytest.mark.parametrize("method", ["direct", "xaccel", "xsendfile", "XAccel"])
def test_load_config_download_method_valid(method) -> None:
    """Valid download_method values are accepted and normalized to lowercase."""
    config = _base_config()
    config["download_method"] = method
    path = create_temp_config(config)
    try:
        app = Flask("test")
        load_config(app, path)
        assert app.config["DOWNLOAD_METHOD"] == method.lower()
    finally:
        os.remove(path)


def test_load_config_download_method_invalid() -> None:
    """An invalid download_method raises a helpful ValueError."""
    config = _base_config()
    config["download_method"] = "ftp"
    path = create_temp_config(config)
    try:
        app = Flask("test")
        with pytest.raises(ValueError, match="Invalid download_method"):
            load_config(app, path)
    finally:
        os.remove(path)


def test_load_config_download_internal_prefix_trailing_slash() -> None:
    """A trailing slash on download_internal_prefix is stripped."""
    config = _base_config()
    config["download_internal_prefix"] = "/secure/"
    path = create_temp_config(config)
    try:
        app = Flask("test")
        load_config(app, path)
        assert app.config["DOWNLOAD_INTERNAL_PREFIX"] == "/secure"
    finally:
        os.remove(path)


def test_build_file_download_response_direct(app, media_file) -> None:
    """Direct mode streams the file content via send_file."""
    with app.test_request_context():
        app.config["DOWNLOAD_METHOD"] = "direct"
        response = build_file_download_response(media_file)
        response.direct_passthrough = False
        assert response.status_code == 200
        assert response.get_data().startswith(b"ID3")


def test_build_file_download_response_xaccel_nonascii(app, media_file_nonascii) -> None:
    """Xaccel mode URL-encodes non-ASCII paths and sets a UTF-8 Content-Disposition."""
    with app.test_request_context():
        app.config["DOWNLOAD_METHOD"] = "xaccel"
        app.config["DOWNLOAD_INTERNAL_PREFIX"] = "/_protected"
        # The route hands the helper a symlink-resolved path; mirror that here.
        response = build_file_download_response(os.path.realpath(media_file_nonascii))
        assert response.status_code == 200
        assert response.get_data() == b""
        redirect = response.headers["X-Accel-Redirect"]
        assert redirect.startswith("/_protected/Filme/")
        # en-dash (U+2013) must not appear raw in the header
        assert "\u2013" not in redirect
        disposition = response.headers["Content-Disposition"]
        assert "filename*=UTF-8''" in disposition


def test_build_file_download_response_xsendfile(app, media_file) -> None:
    """Xsendfile mode emits the absolute filesystem path."""
    with app.test_request_context():
        app.config["DOWNLOAD_METHOD"] = "xsendfile"
        response = build_file_download_response(media_file)
        assert response.status_code == 200
        assert response.get_data() == b""
        assert response.headers["X-Sendfile"] == media_file


def test_build_file_download_response_xaccel_symlinked_root(app, tmp_path) -> None:
    """Xaccel relpath stays clean when media_root is reached via a symlink.

    The route hands this helper a symlink-resolved real_path. If the relative path were
    computed against the raw (symlinked) media_root, it would produce a broken '../..' URI.
    """
    real_dir = tmp_path / "real_media"
    (real_dir / "Filme").mkdir(parents=True)
    media_file = real_dir / "Filme" / "movie.mp4"
    media_file.write_bytes(b"ID3")

    link_dir = tmp_path / "link_media"
    link_dir.symlink_to(real_dir)

    with app.test_request_context():
        app.config["DOWNLOAD_METHOD"] = "xaccel"
        app.config["DOWNLOAD_INTERNAL_PREFIX"] = "/_protected"
        app.config["MEDIA_ROOT"] = str(link_dir)  # configured as the symlink
        # real_path is resolved, as the route would pass it
        real_path = os.path.realpath(str(media_file))
        response = build_file_download_response(real_path)

        assert response.headers["X-Accel-Redirect"] == "/_protected/Filme/movie.mp4"


def test_verify_password_success(app, client) -> None:
    """verify_password should return the username if password matches."""
    with app.app_context(), client:
        result = verify_password("testuser", "test")
        assert result == "testuser"
        assert hasattr(request, "password")
        assert request.password == "test"


def test_verify_password_failure(app) -> None:
    """verify_password returns None if user or password is wrong."""
    with app.app_context():
        assert verify_password("unknown", "test") is None
        assert verify_password("testuser", "wrong") is None


def test_get_version_info() -> None:
    """Test that get_version_info returns the expected version format."""
    version_info = get_version_info()

    # Expect format like "0.4.3 (abc123)"
    assert re.match(r"^\d+\.\d+\.\d+ \([a-z0-9]+\)$", version_info), (
        f"Unexpected version format: {version_info}"
    )


def test_get_version_info_git_failure(app, monkeypatch) -> None:
    """Test that get_version_info handles git failure gracefully."""
    # Simulate subprocess raising an exception
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda _cmd: (_ for _ in ()).throw(Exception("git error")),
    )

    with app.app_context():
        version_info = get_version_info()

    assert version_info.endswith("(unknown commit)"), (
        f"Unexpected version info on git failure: {version_info}"
    )


def test_deslugify_success(tmp_path) -> None:
    """Deslugify should find and return the matching real filename."""
    # Create a file with spaces
    filename = "My Test File.mp3"
    file_path = tmp_path / filename
    file_path.write_text("dummy content")

    # Lookup using slugified name
    slug = slugify(filename)
    found = deslugify(slug, str(tmp_path))

    assert found == filename


def test_deslugify_raises_file_not_found(tmp_path) -> None:
    """Deslugify should raise FileNotFoundError if no file matches the slug."""
    # Empty directory -> no match possible
    empty_dir = tmp_path

    with pytest.raises(FileNotFoundError) as excinfo:
        deslugify("nonexistent_slug", str(empty_dir))

    assert "No match for slug" in str(excinfo.value)


def test_prepare_path_context_generates_breadcrumbs() -> None:
    """Ensure prepare_path_context returns expected structure."""
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


def test_stream_token_changes_when_password_changes(app) -> None:
    """Ensure that changing the user's password results in a new stream token."""
    with app.app_context():
        users = current_app.config["USERS"]

        # Original token
        original_token = get_stream_token("testuser")

        # Simulate password change
        users["testuser"] = "new_fake_password_hash"

        # New token after password change
        new_token = get_stream_token("testuser")

        assert original_token != new_token, "Stream token did not change after password update"


def test_get_stream_token_raises_for_missing_user(app) -> None:
    """Ensure get_stream_token raises ValueError if user does not exist."""
    with app.app_context(), pytest.raises(ValueError, match="User 'unknownuser' not found"):
        get_stream_token("unknownuser")


def test_compute_session_signature_changes_on_password_change() -> None:
    """Ensure that session signature changes when the password hash changes."""
    username = "testuser"
    secret = "testsecret"
    password_hash_old = "old_fake_hash"
    password_hash_new = "new_fake_hash"

    sig_old = compute_session_signature(username, password_hash_old, secret)
    sig_new = compute_session_signature(username, password_hash_new, secret)

    assert sig_old != sig_new, "Session signature did not change after password update"


def test_compute_session_signature_consistency() -> None:
    """Ensure the same inputs produce the same session signature."""
    username = "testuser"
    password_hash = "some_hash"
    secret = "testsecret"

    sig1 = compute_session_signature(username, password_hash, secret)
    sig2 = compute_session_signature(username, password_hash, secret)

    assert sig1 == sig2, "Session signature is not deterministic"


# --- sanitize_filename tests ---


def test_sanitize_filename_ascii_unchanged() -> None:
    """Plain ASCII filenames pass through unchanged."""
    assert sanitize_filename("hello.mp4") == "hello.mp4"


def test_sanitize_filename_valid_utf8_unchanged() -> None:
    """Valid UTF-8 non-ASCII filenames pass through unchanged."""
    assert sanitize_filename("The Movie \u2013 Part 2.mkv") == "The Movie \u2013 Part 2.mkv"


def test_sanitize_filename_replaces_surrogates() -> None:
    """Surrogate characters (from non-UTF-8 bytes on disk) are replaced with \ufffd."""
    # Simulate what os.listdir() produces for a Latin-1 en-dash (0x96) on an ASCII locale:
    # Python represents the raw byte as the surrogate \udc96
    name_with_surrogates = "The Movie \udc96 Part 2.mkv"
    result = sanitize_filename(name_with_surrogates)
    assert "\udc96" not in result
    assert "\ufffd" in result
    assert result == "The Movie \ufffd Part 2.mkv"


def test_sanitize_filename_mixed_surrogates() -> None:
    """Surrogate bytes that form valid UTF-8 are recovered to the original character."""
    # \udce2\udc80\udc93 are surrogates for the raw bytes E2 80 93,
    # which is valid UTF-8 for en-dash (U+2013). surrogateescape recovers them.
    name = "file\udce2\udc80\udc93name.mp4"
    result = sanitize_filename(name)
    assert result == "file\u2013name.mp4"


def test_sanitize_filename_truly_invalid_bytes() -> None:
    """A lone surrogate from genuinely invalid bytes is replaced with \ufffd."""
    # \udc96 represents raw byte 0x96 (Windows-1252 en-dash), not valid UTF-8
    name = "file\udc96name.mp4"
    result = sanitize_filename(name)
    assert "\udc96" not in result
    assert "\ufffd" in result


def test_prepare_path_context_with_surrogate_in_path() -> None:
    """Surrogate characters in display path parts are sanitized in breadcrumbs."""
    real_path = "/media/data/Filme/The Movie \udc96 Part 2"
    slug_parts = ["Filme", "The_Movie__Part_2"]
    media_root = "/media/data"

    context = prepare_path_context(real_path, slug_parts, media_root)

    # The display name must not contain surrogates (would crash template rendering)
    assert "\udc96" not in context["current_name"]
    assert "\ufffd" in context["current_name"]


# --- .nfo metadata reader tests ---

EPISODE_NFO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<!--created by tinyMediaManager-->
<episodedetails>
  <title>Br\u00fcder</title>
  <originaltitle/>
  <showtitle>4 Blocks</showtitle>
  <season>1</season>
  <episode>1</episode>
  <rating>0.0</rating>
  <votes>0</votes>
  <plot>Toni Hamady plant den Ausstieg.</plot>
</episodedetails>
"""

TVSHOW_NFO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<tvshow>
  <title>4 Blocks</title>
  <year>2017</year>
  <rating>8.1</rating>
  <plot>Eine Geschichte um Freundschaft und Familie.</plot>
</tvshow>
"""


def test_read_nfo_metadata_episode(tmp_path) -> None:
    """Episode .nfo yields title and plot; placeholder rating 0.0 is dropped."""
    media = tmp_path / "4.blocks.s01e01.mkv"
    media.write_bytes(b"x")
    (tmp_path / "4.blocks.s01e01.nfo").write_text(EPISODE_NFO, encoding="utf-8")

    meta = read_nfo_metadata(str(media))
    assert meta["title"] == "Br\u00fcder"
    assert meta["plot"].startswith("Toni Hamady")
    assert meta["episode_marker"] == "S01E01"
    assert "rating" not in meta  # 0.0 dropped
    assert "year" not in meta


def test_read_nfo_metadata_no_marker_without_season(tmp_path) -> None:
    """A movie .nfo (no season/episode tags) has no episode marker."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    (tmp_path / "movie.nfo").write_text(
        "<movie><title>Der Pate</title><year>1972</year></movie>", encoding="utf-8"
    )
    meta = read_nfo_metadata(str(media))
    assert meta["title"] == "Der Pate"
    assert "episode_marker" not in meta


def test_read_nfo_metadata_nested_movie_rating(tmp_path) -> None:
    """Movie .nfo with a nested <ratings> block yields the default rating value."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    (tmp_path / "movie.nfo").write_text(
        "<movie><title>Der Pate</title>"
        '<ratings><rating default="true" max="10" name="imdb">'
        "<value>7.3</value><votes>397384</votes></rating></ratings>"
        "</movie>",
        encoding="utf-8",
    )
    meta = read_nfo_metadata(str(media))
    assert meta["rating"] == "7.3"


def test_read_nfo_metadata_nested_rating_prefers_default(tmp_path) -> None:
    """When multiple nested ratings exist, the one marked default wins."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    (tmp_path / "movie.nfo").write_text(
        "<movie><title>X</title><ratings>"
        '<rating name="themoviedb"><value>6.1</value></rating>'
        '<rating default="true" name="imdb"><value>7.3</value></rating>'
        "</ratings></movie>",
        encoding="utf-8",
    )
    assert read_nfo_metadata(str(media))["rating"] == "7.3"


def test_read_nfo_metadata_ignores_negative_season(tmp_path) -> None:
    """Placeholder -1 season/episode does not produce a marker."""
    media = tmp_path / "ep.mkv"
    media.write_bytes(b"x")
    (tmp_path / "ep.nfo").write_text(
        "<episodedetails><title>X</title><season>-1</season><episode>-1</episode></episodedetails>",
        encoding="utf-8",
    )
    assert "episode_marker" not in read_nfo_metadata(str(media))


def test_read_nfo_metadata_missing(tmp_path) -> None:
    """No sibling .nfo returns an empty dict."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    assert read_nfo_metadata(str(media)) == {}


def test_read_nfo_metadata_malformed(tmp_path) -> None:
    """Malformed XML returns an empty dict rather than raising."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    (tmp_path / "movie.nfo").write_text("<tvshow><title>broken", encoding="utf-8")
    assert read_nfo_metadata(str(media)) == {}


def test_read_nfo_metadata_rejects_doctype(tmp_path) -> None:
    """A .nfo declaring a DOCTYPE/ENTITY (XML-bomb vector) is refused."""
    bomb = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">]>\n'
        "<tvshow><title>&lol;</title></tvshow>"
    )
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    (tmp_path / "movie.nfo").write_text(bomb, encoding="utf-8")
    assert read_nfo_metadata(str(media)) == {}


def test_read_nfo_metadata_oversized(tmp_path) -> None:
    """A .nfo larger than the size cap is not parsed."""
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"x")
    big = "<tvshow><title>x</title></tvshow>" + ("<!-- pad -->" * 100000)
    (tmp_path / "movie.nfo").write_text(big, encoding="utf-8")
    assert read_nfo_metadata(str(media)) == {}


def test_read_tvshow_metadata(tmp_path) -> None:
    """tvshow.nfo yields title, year, rating and plot."""
    (tmp_path / "tvshow.nfo").write_text(TVSHOW_NFO, encoding="utf-8")
    meta = read_tvshow_metadata(str(tmp_path))
    assert meta["title"] == "4 Blocks"
    assert meta["year"] == "2017"
    assert meta["rating"] == "8.1"
    assert meta["plot"].startswith("Eine Geschichte")


def test_read_tvshow_metadata_missing(tmp_path) -> None:
    """Folder without tvshow.nfo returns an empty dict."""
    assert read_tvshow_metadata(str(tmp_path)) == {}


# --- audio metadata reader tests ---


def test_format_duration() -> None:
    """Durations format as m:ss, and h:mm:ss when at least one hour."""
    assert _format_duration(0) == "0:00"
    assert _format_duration(5) == "0:05"
    assert _format_duration(355) == "5:55"
    assert _format_duration(3661) == "1:01:01"
    assert _format_duration(59.6) == "1:00"  # rounds up


def _write_tagged_mp3(path) -> None:
    """Write a small real MP3 (silent frames) carrying EasyID3 tags for testing."""
    from mutagen.easyid3 import EasyID3

    # Eight valid silent MPEG-1 Layer III frames (44.1 kHz, 128 kbps) so mutagen's
    # format sniffer recognizes the file as MP3.
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    path.write_bytes(frame * 8)
    tags = EasyID3()
    tags["title"] = "Bohemian Rhapsody"
    tags["artist"] = "Queen"
    tags["album"] = "A Night at the Opera"
    tags["tracknumber"] = "11/12"
    tags.save(str(path))


def test_read_audio_metadata_tags(tmp_path) -> None:
    """Audio tags are read and normalized (track stripped of total, tagged audio)."""
    media = tmp_path / "song.mp3"
    _write_tagged_mp3(media)

    meta = read_audio_metadata(str(media))
    assert meta["kind"] == "audio"
    assert meta["title"] == "Bohemian Rhapsody"
    assert meta["artist"] == "Queen"
    assert meta["album"] == "A Night at the Opera"
    assert meta["track"] == "11"  # "11/12" -> "11"
    assert "duration" in meta  # silent frames still have a measurable length


def test_read_audio_metadata_untagged(tmp_path) -> None:
    """An audio file with no tags exposes no title/album/track."""
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    media = tmp_path / "untagged.mp3"
    media.write_bytes(frame * 8)
    meta = read_audio_metadata(str(media))
    assert "title" not in meta
    assert "album" not in meta
    assert "track" not in meta


def test_read_audio_metadata_not_audio(tmp_path) -> None:
    """A non-audio / unreadable file returns an empty dict rather than raising."""
    media = tmp_path / "notaudio.mp3"
    media.write_bytes(b"this is not audio")
    assert read_audio_metadata(str(media)) == {}
