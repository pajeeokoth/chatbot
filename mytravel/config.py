#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os

# Try to load a .env file if python-dotenv is installed. This is optional and
# allows local development to pick up values written by the uploader script.
try:
    from dotenv import load_dotenv
    # Look for a .env file at the repository root (one level above this package)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dotenv_path = os.path.join(repo_root, '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except Exception:
    # dotenv not available or failed; continue using environment variables
    pass


class DefaultConfig:
    """ Bot Configuration """

    PORT = 3978
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    # LUIS configuration - read from environment (or .env if present)
    LUIS_APP_ID = os.environ.get("LUIS_APP_ID", "")
    LUIS_PREDICTION_KEY = os.environ.get("LUIS_PREDICTION_KEY", "")
    # e.g. https://<your-resource-name>.cognitiveservices.azure.com/
    LUIS_ENDPOINT = os.environ.get("LUIS_ENDPOINT", "")
