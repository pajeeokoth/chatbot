#!/usr/bin/env python3
"""Upload a LUIS app JSON using the Azure LUIS Authoring SDK if available, else fall back to REST.

This script attempts to use the official (older) Python SDK `azure-cognitiveservices-language-luis`
to import a LUIS app programmatically. If the SDK is not installed or the SDK client
doesn't expose an import method, the script falls back to the REST-based uploader
(`scripts/upload_luis.py`) which performs the same import via REST.

Install SDK (optional):
  pip install azure-cognitiveservices-language-luis msrest

Usage:
  python scripts/upload_luis_sdk.py --file data/frames_dataset/luis_import.json --authoring-key <KEY> --region <region>

Note: region should be the authoring region for your LUIS resource (e.g. westus2).
"""

import argparse
import importlib
import json
import os
import sys
from pathlib import Path


def sdk_import(file_path, authoring_key, region):
    """Attempt import using azure-cognitiveservices-language-luis SDK.

    Returns app_id on success, raises if SDK not available or import fails.
    """
    try:
        # Import SDK classes
        mod = importlib.import_module('azure.cognitiveservices.language.luis.authoring')
        LUISAuthoringClient = getattr(mod, 'LUISAuthoringClient')
        # msrest auth
        creds_mod = importlib.import_module('msrest.authentication')
        CognitiveServicesCredentials = getattr(creds_mod, 'CognitiveServicesCredentials')
    except Exception as e:
        raise RuntimeError('Azure LUIS Authoring SDK not available: {}'.format(e))

    # Build authoring endpoint
    authoring_endpoint = f'https://{region}.api.cognitive.microsoft.com'

    client = LUISAuthoringClient(authoring_endpoint, CognitiveServicesCredentials(authoring_key))

    # Load payload
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    # Try several likely method names on client.apps
    apps = getattr(client, 'apps', None) or getattr(client, 'applications', None)
    if not apps:
        raise RuntimeError('LUIS SDK client has no `apps` property to import an app')

    candidate_methods = [
        'import_application',
        'import_application_async',
        'import',
        'create',
        'import_app',
        'import_app_with_http_info',
    ]

    for name in candidate_methods:
        if hasattr(apps, name):
            method = getattr(apps, name)
            try:
                # SDKs may accept either a JSON string or the deserialized object
                try:
                    res = method(payload)
                except TypeError:
                    # maybe expects a JSON string
                    res = method(json.dumps(payload))
                # result may be a dict-like object or a response with id
                # try to extract an id
                if isinstance(res, dict) and 'id' in res:
                    return res['id']
                # Some SDK returns an object with an 'id' attribute
                app_id = getattr(res, 'id', None)
                if app_id:
                    return app_id
                # If res is a string id
                if isinstance(res, str):
                    return res
                # otherwise, try to read a location header or similar
                # fallthrough to error
                raise RuntimeError(f'Import returned unexpected result: {res}')
            except Exception as e:
                raise RuntimeError(f'SDK import method `{name}` failed: {e}')

    raise RuntimeError('No supported import method found on SDK client.apps; falling back to REST')


def rest_fallback(file_path, authoring_key, region):
    """Call the REST uploader script implemented in this repo as fallback."""
    # Import the earlier REST uploader if available
    repo_script = Path(__file__).resolve().parents[1] / 'scripts' / 'upload_luis.py'
    if repo_script.exists():
        # Add repo scripts to sys.path and import
        scripts_dir = str(repo_script.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import upload_luis as rest_uploader
            # Call its main functions programmatically
            authoring_key_arg = authoring_key
            region_arg = region
            app_id = rest_uploader.import_app(file_path, authoring_key_arg, region_arg)
            return app_id
        except Exception as e:
            raise RuntimeError(f'REST fallback failed: {e}')
    else:
        raise RuntimeError('No REST uploader found for fallback')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--file', required=True, help='LUIS JSON file to import')
    p.add_argument('--authoring-key', help='Authoring key (env LUIS_AUTHORING_KEY)')
    p.add_argument('--region', help='Authoring region (env LUIS_AUTHORING_REGION)')
    p.add_argument('--no-train', action='store_true', help='Skip training/publishing steps (if using REST fallback)')
    args = p.parse_args()

    authoring_key = args.authoring_key or os.environ.get('LUIS_AUTHORING_KEY')
    region = args.region or os.environ.get('LUIS_AUTHORING_REGION')

    if not (authoring_key and region):
        p.error('Authoring key and region required (via args or env vars LUIS_AUTHORING_KEY and LUIS_AUTHORING_REGION)')

    file_path = args.file
    if not Path(file_path).exists():
        p.error(f'File not found: {file_path}')

    print('Attempting SDK-based import...')
    try:
        app_id = sdk_import(file_path, authoring_key, region)
        print('Imported app via SDK, app id:', app_id)
        # Note: older SDK may not include train/publish wrappers; recommend using REST uploader for training/publishing
        if not args.no_train:
            print('Note: training/publishing via SDK may not be supported by this script; use the REST uploader if you need automatic train/publish.')
        return
    except Exception as e:
        print('SDK import failed:', e)
        print('Falling back to REST uploader...')

    try:
        app_id = rest_fallback(file_path, authoring_key, region)
        print('Imported app via REST fallback, app id:', app_id)
    except Exception as e:
        print('Upload failed:', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
