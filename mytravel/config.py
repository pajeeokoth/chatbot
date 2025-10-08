#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os

class DefaultConfig:
    """ Bot Configuration """

    PORT = 3978
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    # LUIS configuration - set these environment variables or replace with values
    LUIS_APP_ID = os.environ.get("LUIS_APP_ID", "")
    LUIS_PREDICTION_KEY = os.environ.get("LUIS_PREDICTION_KEY", "")
    # e.g. https://<your-resource-name>.cognitiveservices.azure.com/
    LUIS_ENDPOINT = os.environ.get("LUIS_ENDPOINT", "")
