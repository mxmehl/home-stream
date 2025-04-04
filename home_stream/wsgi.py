# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""WSGI entry point for the Home Stream application."""

from home_stream.app import create_app

app = create_app("config.yaml")
