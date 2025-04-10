# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: GPL-3.0-only

"""Forms handler for the media browser"""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    """
    LoginForm is a form class used for user authentication.

    Attributes:
        username (StringField): A field for entering the username. It is required.
        password (PasswordField): A field for entering the password. It is required.
    """

    username = StringField(label="Username", validators=[DataRequired()])
    password = PasswordField(label="Password", validators=[DataRequired()])
