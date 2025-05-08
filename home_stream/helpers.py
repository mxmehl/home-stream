# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Helper functions for the media browser."""

import hashlib
import hmac
import os
import re
import subprocess
from urllib.parse import quote

import yaml
from bcrypt import checkpw
from flask import Flask, abort, current_app, request

from . import __version__

REQUIRED_CONFIG_KEYS = (
    "users",
    "video_extensions",
    "audio_extensions",
    "media_root",
    "secret_key",
    "protocol",
)


def load_config(app: Flask, filename: str) -> None:
    """Load configuration from a YAML file."""
    with open(filename, encoding="UTF-8") as f:
        config = yaml.safe_load(f)

    # Check whether mandatory keys are filled
    for required_key in REQUIRED_CONFIG_KEYS:
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

    # Error when using default secret key
    if app.secret_key == "CHANGE_ME_IN_FAVOUR_OF_A_LONG_PASSWORD":
        raise ValueError("You must change the default secret_key in the config file.")

    # Set defaults
    app.config["RATE_LIMIT_STORAGE_URI"] = app.config.get("RATE_LIMIT_STORAGE_URI", "memory://")

    # Print the loaded config in DEBUG mode
    app.logger.debug(app.config)


def secure_path(subpath: str) -> str:
    """Secure and resolve a path inside the media root, including mounts or symlinks."""
    media_root = os.path.abspath(current_app.config["MEDIA_ROOT"])
    real_media_root = os.path.realpath(media_root)

    unsafe_path = os.path.normpath(os.path.join(media_root, subpath))
    resolved_path = os.path.realpath(unsafe_path)

    allowed_roots = [media_root, real_media_root]

    if not any(
        resolved_path == root or resolved_path.startswith(root + os.sep) for root in allowed_roots
    ):
        current_app.logger.warning(
            f"Blocked path traversal or symlink escape: {subpath} → {resolved_path}"
        )
        abort(403)

    return resolved_path


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
    """Generate a permanent token for streaming based on username, password hash, and secret key"""
    secret = current_app.config["STREAM_SECRET"]
    users = current_app.config.get("USERS", {})

    password_hash = users.get(username)
    if not password_hash:
        raise ValueError(f"User '{username}' not found when generating stream token.")

    token_input = f"{username}:{password_hash}"
    return hmac.new(secret.encode(), token_input.encode(), hashlib.sha256).hexdigest()[:chars]


def compute_session_signature(username, password_hash, secret):
    """Compute a session signature based on username and password hash."""
    data = f"{username}:{password_hash}"
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


def truncate_secret(secret: str, chars: int = 8) -> str:
    """Truncate the secret key to a specified length"""
    if len(secret) > chars:
        return secret[:chars] + "*" * (len(secret) - chars)
    return secret


def get_version_info():
    """Get the version information of the application"""
    # Get short git commit hash if available
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:  # pylint: disable=broad-exception-caught
        current_app.logger.debug("Failed to get git commit hash.", exc_info=True)
        commit = "unknown commit"

    return f"{__version__} ({commit})"


def slugify(name: str) -> str:
    """Turn a filename into a URL-safe slug (preserving readability)"""
    name = name.strip()
    name = re.sub(r"[\s]+", "_", name)  # Replace spaces with underscores
    name = re.sub(r"[^a-zA-Z0-9_&\-\.]", "", name)  # Keep only safe characters
    return name


def deslugify(slug: str, directory: str) -> str:
    """Find real filename in a directory matching the slug"""
    for fname in os.listdir(directory):
        if slugify(fname) == slug:
            return fname
    raise FileNotFoundError(f"No match for slug '{slug}' in '{directory}'")


def resolve_real_path_from_slugs(slug_parts):
    """
    Resolve a slugified URL path into the real filesystem path.

    - Each part of the path (slug) is matched against actual filesystem entries.
    - All intermediate parts must resolve to directories.
    - The final part can resolve to either a file or a directory (depending on the route purpose).

    Args:
        slug_parts (list[str]): The slugified URL path segments
            (e.g. ["Shows", "Battlestar_Galactica", "Season_1"]).

    Returns:
        str: The full real filesystem path.

    Raises:
        404 error if any slug part does not match a real filesystem entry.
    """
    current_dir = secure_path("")  # Start from the media root
    real_parts = []

    for idx, slug in enumerate(slug_parts):
        entries = os.listdir(current_dir)
        is_last = idx == len(slug_parts) - 1  # Final path segment?

        for entry in entries:
            full_entry = os.path.join(current_dir, entry)

            if slugify(entry) == slug:
                # Intermediate parts must be directories
                # Last part can be either file or directory
                if is_last or os.path.isdir(full_entry):
                    real_parts.append(entry)
                    current_dir = full_entry
                    break
        else:
            # No match found for this slug part → abort
            abort(404)

    return os.path.join(secure_path(""), *real_parts)


def extract_path_components(subpath):
    """Extract path components from a slugified subpath.

    This function splits the subpath into its individual parts,
    resolves the real filesystem path, and prepares a context for rendering.

    Args:
        subpath (str): The slugified subpath to be processed.

    Returns:
        tuple: A tuple containing:
            - list of slug parts
            - real filesystem path
            - context dictionary for rendering
    """
    parts = [p for p in subpath.split("/") if p]
    real_path = resolve_real_path_from_slugs(parts)
    path_context = prepare_path_context(real_path, parts, current_app.config["MEDIA_ROOT"])
    return parts, real_path, path_context


def list_folder_entries_with_stream_urls(
    real_path: str, slug_parts: list[str], username: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """List directories and media files in a folder with slugified paths.

    This function scans the given directory, filters out hidden folders,
    and includes only files with allowed media extensions as defined in
    the Flask app's config. It returns both folders and files with their
    original names, corresponding slugified paths, and Stream URLs for files.

    Args:
        real_path (str): Absolute path to the folder to be listed.
        slug_parts (list[str]): List of slug parts to prefix to each entry's slug.
        username (str): Authenticated user.

    Returns:
        tuple: A tuple containing two lists of dictionaries:
            - list of dicts (name (folder), slug_path)
            - list of dicts (name (file), slug_path, stream_url)
    """
    folders: list[dict[str, str]] = []
    files: list[dict[str, str]] = []

    # Loop through all entries in the directory
    for dir_element in os.listdir(real_path):
        full = os.path.join(real_path, dir_element)
        entry_slug = slugify(dir_element)

        # Check if entry is a directory and not hidden
        if os.path.isdir(full) and not dir_element.startswith("."):
            folder_slug_path = "/".join(slug_parts + [entry_slug])
            folders.append({"name": dir_element, "slug_path": folder_slug_path})

        # Check if entry is a file with a valid media extension
        elif os.path.isfile(full):
            ext = os.path.splitext(dir_element)[1].lower().strip(".")
            if ext in current_app.config["MEDIA_EXTENSIONS"]:
                file_slug_path = "/".join(slug_parts + [entry_slug])
                stream_url = build_stream_url(username, get_stream_token(username), file_slug_path)
                files.append(
                    {"name": dir_element, "slug_path": file_slug_path, "stream_url": stream_url}
                )

    # Sort entries alphabetically by name (case-insensitive)
    folders.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())

    return folders, files


def prepare_path_context(real_path: str, slug_parts: list, media_root: str):
    """
    Construct context information for templates based on a resolved real path and its slug parts.

    This includes:
    - The current item's name (used as the headline)
    - A slugified path (used in URLs)
    - A relative display path from the media root
    - A breadcrumb trail leading up to the current item

    The breadcrumb list will always start with an "Overview" entry linking to the root.

    Args:
        real_path (str): The absolute filesystem path to the file or directory.
        slug_parts (list): List of URL slug parts (e.g., ['Shows', 'Battlestar_Galactica']).
        media_root (str): The absolute path to the media root directory.

    Returns:
        dict: {
            "slugified_path": str,         # e.g., "Shows/Battlestar_Galactica"
            "display_path": str,           # e.g., "Shows/Battlestar Galactica"
            "breadcrumb_parts": List[dict],# e.g., [{"name": "Overview", "slug": ""}, # {"name": "Shows", "slug": "Shows"}]
            "current_name": str            # e.g., "Battlestar Galactica"
        }
    """  # pylint: disable=line-too-long
    # Join slugified parts back into a path string
    slugified_path = "/".join(slug_parts) if slug_parts else ""

    # Convert real path to relative path from the media root
    display_path = os.path.relpath(real_path, media_root)

    # Special case: media root itself
    if display_path == ".":
        display_parts = []
    else:
        display_parts = [p for p in display_path.strip("/").split("/") if p]

    # Build breadcrumb from all parts except the last (shown as headline)
    breadcrumb_parts = [
        {"name": name, "slug": "/".join(slug_parts[: i + 1])}
        for i, name in enumerate(display_parts[:-1])
    ]

    # Always include the Overview/root link
    if breadcrumb_parts or display_parts:
        breadcrumb_parts.insert(0, {"name": "Overview", "slug": ""})

    # The last segment is shown as the <h1> headline
    current_name = display_parts[-1] if display_parts else "Overview"

    return {
        "slugified_path": slugified_path,
        "display_path": display_path,
        "breadcrumb_parts": breadcrumb_parts,
        "current_name": current_name,
    }


def build_stream_url(username: str, token: str, rel_path: str) -> str:
    """
    Build a full stream URL for a given user and relative file path.

    Args:
        username (str): Authenticated user
        token (str): Token generated via get_stream_token()
        rel_path (str): Slugified relative path (e.g. Music/HipHop/Track.mp3)

    Returns:
        str: Full stream URL
    """
    protocol = current_app.config["PROTOCOL"]
    host = request.host
    return f"{protocol}://{host}/dl-token/{quote(username)}/{token}/{quote(rel_path)}"


def build_playlist_content(playlist_name: str, files: list[dict[str, str]]) -> str:
    """Build a playlist content string for M3U8 format."""
    playlist_lines = ["#EXTM3U"]
    playlist_lines.append(f"#PLAYLIST: {playlist_name}")
    for file in files:
        playlist_lines.append(
            # TODO: Add duration of file
            f"#EXTINF:-1,{file.get('name', '')}"  # NOTE: -1 means unknown duration
        )
        playlist_lines.append(file.get("stream_url", ""))
    return "\n".join(playlist_lines)
