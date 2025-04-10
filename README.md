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
- Secure user login
- In-browser audio/video player (if supported by your browser)
- HTTP Basic Auth fallback for external players (VLC, mpv, etc.) using authenticated links
- Lightweight and dependency-minimal Python Flask app

## Installation

Minimum Python version: 3.10

### Install and run via pipx (Recommended)

[pipx](hhttps://pipx.pypa.io/) makes installing and running Python programs easier and avoids conflicts with other packages. Install it with

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

For productive use, you should use a proper webserver. Streaming many and large chunks of files may trigger issues with apps like gunicorn, so uWSGI is officially supported.

For a quick start, run `poetry run uwsgi --ini uwsgi.ini`. Using the docker image [`ghcr.io/mxmehl/home-stream`](https://github.com/mxmehl/home-stream/pkgs/container/home-stream) you would have everything contained into one container, ready to be use locally or behind a reverse proxy. Note that depending on your use-cases, you may want to reconfigure some uwsgi settings. This currently would need to be done manually.

### Usage Scenarios

The application is mainly designed with the use-case of running it on a NAS or home server with direct media access to allow accessing your media files remotely.

For this, you may put this application behind a reverse proxy or make it accessible via a VPN connection.

Of course, you can also use it purely locally, although there are probably better tools to administrate your media files.

## License

This project is licensed under the terms of the **GPL-3.0-only** license, but contains elements under different licenses.

The project is [REUSE compliant](https://reuse.software), so licensing and copyright information is available for every single file.
