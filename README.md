<!--
SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>

SPDX-License-Identifier: GPL-3.0-only
-->

# Home Stream

[![Test suites](https://github.com/mxmehl/home-stream/actions/workflows/test.yaml/badge.svg)](https://github.com/mxmehl/home-stream/actions/workflows/test.yaml)
[![REUSE status](https://api.reuse.software/badge/github.com/mxmehl/home-stream)](https://api.reuse.software/info/github.com/mxmehl/home-stream)
[![The latest version of this application can be found on PyPI.](https://img.shields.io/pypi/v/home-stream.svg)](https://pypi.org/project/home-stream/)
[![Information on what versions of Python this application supports can be found on PyPI.](https://img.shields.io/pypi/pyversions/home-stream.svg)](https://pypi.org/project/home-stream/)

A web-based browser and streaming interface for local media files. Supports in-browser playback, HTTP Basic Auth streaming (e.g. VLC), and user-based login with permanent stream URLs.

## Features

- Browse local folders and media files
- Show titles and metadata from Kodi-style `.nfo` files in the browse view (toggleable)
- Secure user login
- In-browser audio/video player (if supported by your browser)
- HTTP Basic Auth fallback for external players (VLC, mpv, etc.) using authenticated links
- Lightweight and dependency-minimal Python Flask app

### Use-Cases for home-stream

The application is mainly designed with the use-case of running it on a NAS or home server with direct media access to allow accessing your media files remotely.

For this, you may put this application behind a reverse proxy or make it accessible via a VPN connection.

Of course, you can also use it purely locally, although there are probably better tools to administrate your media files.

## Installation

Minimum Python version: 3.10

### Install and run via pipx (Recommended)

[pipx](https://pipx.pypa.io/) makes installing and running Python programs easier and avoids conflicts with other packages. Install it with

```sh
pip3 install pipx
```

The following one-liner both installs and runs this program from [PyPI](https://pypi.org/project/home-stream/):

```sh
pipx run home-stream
```

If you want to be able to use the application without prepending it with `pipx run` every time, install it globally like so:

```sh
pipx install home-stream
```

The application will then be available in `~/.local/bin`, which must be added to your `$PATH`. So make sure that `~/.local/bin` is in your `$PATH`. On Windows, the required path for your environment may look like `%USERPROFILE%\AppData\Roaming\Python\Python310\Scripts`, depending on the Python version you have installed. Recent pipx versions allow you to do this via `pipx ensurepath`.

To upgrade the application to the newest available version, run this command:

```sh
pipx upgrade home-stream
```

### Other installation methods

You may also use pure `pip` or `poetry` to install this package.

## Configuration

Create a `config.yaml` file in the project root. You can derive your configuration from [`config.sample.yaml`](./config.sample.yaml).

Passwords must be **bcrypt-hashed**. You can generate them using Python:

```python
import bcrypt
print(bcrypt.hashpw(b"your-password", bcrypt.gensalt()).decode())
```

or by using online tools like [bcrypt-generator.com](https://bcrypt-generator.com/), although not recommended for production passwords.

## Usage

Start the app (session login + streaming):

```bash
home-stream -c config.yaml  # uses Flask development server
```

Log in via browser, by default on [localhost:8000](http://localhost:8000). Browse and play media, or copy permanent stream URLs.

### Production Webserver

For productive use, you should use a proper WSGI server. uWSGI is officially supported and ships in the Docker image. With the default `download_method: direct`, large file transfers run through the WSGI worker, which can strain servers like gunicorn (worker blocking, timeouts) — uWSGI tolerates this better. If you enable download offloading (see below), large files are served by your webserver instead, so the WSGI server only handles short requests and this distinction no longer matters.

For a quick start, run `uv run uwsgi --ini uwsgi.ini`. Using the docker image [`ghcr.io/mxmehl/home-stream`](https://github.com/mxmehl/home-stream/pkgs/container/home-stream) you would have everything contained into one container, ready to be use locally or behind a reverse proxy. Note that depending on your use-cases, you may want to reconfigure some uwsgi settings. This currently would need to be done manually.

### Large file downloads (offloading)

By default (`download_method: direct`), the application serves file bytes itself through the Python/uWSGI worker. This works, but for large files (movies) it ties up a worker for the whole transfer, interacts poorly with proxy buffering, and can hit timeouts (e.g. uWSGI's `harakiri`). This is the classic reason large downloads drop while a plain nginx/sftp serve never does.

The robust solution is to keep **authentication and discovery in the app**, but let your **webserver push the bytes** using a zero-copy `sendfile()` path. The app authorizes the request exactly as before (your permanent per-user tokens are unchanged), then hands the file to the webserver via a response header. Choose the mechanism that matches your front-end webserver via `download_method` in `config.yaml`:

> **The one rule that matters:** whatever webserver serves the bytes must have **direct read access to the media files** at the same paths the app sees. This is the part that trips people up — see the note below.

#### Easiest robust option: an nginx sidecar container (recommended)

You do **not** need to bundle nginx into the app image, and you do **not** need your existing internet-facing reverse proxy to touch the media. The simplest robust setup is a dedicated nginx container that sits next to the app in the same `docker-compose.yaml`, shares the media volume, and does the offload. Your outer proxy (Caddy, Traefik, an existing nginx, …) just forwards HTTP to this sidecar and handles TLS as before.

Why a sidecar rather than your existing host/edge webserver? Because of the file-access rule above. The app container can already read the media (it runs as its own user). A *different* webserver — for example a host nginx running as `www-data`, or an edge proxy on another machine — usually **cannot** read your media (especially with read-only NFS mounts and restrictive ownership), so its offload attempts fail with 403/404 even though the app authorized them. A sidecar container avoids this entirely by mounting the same volume and running as the same user as the app.

Ready-to-use samples are provided: [`docker-compose.sample.yaml`](./docker-compose.sample.yaml) (app + nginx sidecar + valkey) and [`nginx.sample.conf`](./nginx.sample.conf) (the matching nginx config). Set `download_method: xaccel` in `config.yaml`, adjust the media path and port, and point your TLS-terminating reverse proxy at the sidecar.

The remaining subsections describe the underlying mechanisms if you prefer to use an existing nginx/Apache that *does* have media access instead of a sidecar.

#### nginx (`download_method: xaccel`)

The app emits an `X-Accel-Redirect` header pointing into an internal location that nginx maps to your media root. See [`nginx.sample.conf`](./nginx.sample.conf) for a ready-to-use example. The key points:

#### Apache / Lighttpd (`download_method: xsendfile`)

Requires [`mod_xsendfile`](https://github.com/nmaier/mod_xsendfile). The app emits an `X-Sendfile` header with the absolute file path, which Apache serves directly:

```apache
XSendFile On
# Scope strictly to the media root so only intended files can be served.
XSendFilePath /media/data
```

#### Notes

- **The offloading webserver must see the same media files** at the configured path. With the sidecar above, this is handled by mounting the same volume into the nginx container. If you instead reuse an existing host/edge webserver, it must have read access to the media itself — a separate user like `www-data` often does **not**, especially with read-only NFS mounts and restrictive ownership, which is exactly why the sidecar is recommended. Read-only access is sufficient.
- **Symlinks are resolved.** The app hands the webserver the symlink-resolved (real) path. If `media_root` is itself a symlink (or sits under one), point nginx's `alias` and Apache's `XSendFilePath` at the **real** target directory, not the symlink.
- **Security:** keep the nginx location `internal`, and scope `XSendFilePath` to exactly the media root. Authorization stays entirely in the app — the webserver only serves paths the app explicitly hands it.
- Folder downloads (generated M3U8 playlists) are always served directly by the app, since they are tiny.
- With offloading enabled, uWSGI's `harakiri`/keepalive settings no longer affect downloads.


## License

This project is licensed under the terms of the **GPL-3.0-only** license, but contains elements under different licenses.

The project is [REUSE compliant](https://reuse.software), so licensing and copyright information is available for every single file.
