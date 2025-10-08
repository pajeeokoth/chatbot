#!/usr/bin/env python3
"""Upload a LUIS app JSON to the LUIS Authoring REST API, train and publish.

Usage:
  python scripts/upload_luis.py --file data/frames_dataset/luis_import.json --authoring-key <KEY> --region <region>

Environment variables supported (fallbacks):
  LUIS_AUTHORING_KEY, LUIS_AUTHORING_REGION

Notes:
- This script uses the Authoring endpoints (region-specific). For example, if your region is "westus2",
  the base URL is https://westus2.api.cognitive.microsoft.com/luis/authoring/v3.0.
- The script imports the app, waits for the operation to complete, optionally trains and publishes
  to the production slot. It prints the created appId on success.
"""

import argparse
import json
import os
import time
from urllib.parse import urljoin

import requests


def import_app(file_path: str, authoring_key: str, region: str) -> str:
    """Import a LUIS app JSON and return the created app id."""
    base = f"https://{region}.api.cognitive.microsoft.com/luis/authoring/v3.0/"
    url = urljoin(base, "apps/import")
    headers = {
        "Ocp-Apim-Subscription-Key": authoring_key,
        "Content-Type": "application/json",
    }

    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    app_id = data.get("id")
    if not app_id:
        raise RuntimeError(f"Import succeeded but no app id returned: {data}")
    return app_id


def train_app(app_id: str, authoring_key: str, region: str):
    base = f"https://{region}.api.cognitive.microsoft.com/luis/authoring/v3.0/"
    train_url = urljoin(base, f"apps/{app_id}/versions/0.1/train")
    headers = {"Ocp-Apim-Subscription-Key": authoring_key}

    resp = requests.post(train_url, headers=headers, timeout=10)
    resp.raise_for_status()

    # Poll training status
    status_url = urljoin(base, f"apps/{app_id}/versions/0.1/train")
    for _ in range(30):
        r = requests.get(status_url, headers=headers, timeout=10)
        r.raise_for_status()
        results = r.json()
        # results is a dict of modelId -> status
        if all(s.get("details", {}).get("status") == "Success" for s in results.values()):
            return True
        if any(s.get("details", {}).get("status") == "Fail" for s in results.values()):
            raise RuntimeError("Training failed: {}".format(results))
        time.sleep(1)
    raise RuntimeError("Training timed out")


def publish_app(app_id: str, authoring_key: str, region: str, endpoint_region: str = None):
    base = f"https://{region}.api.cognitive.microsoft.com/luis/authoring/v3.0/"
    publish_url = urljoin(base, f"apps/{app_id}/publish")
    headers = {"Ocp-Apim-Subscription-Key": authoring_key, "Content-Type": "application/json"}

    body = {"versionId": "0.1", "isStaging": False}
    if endpoint_region:
        body["endpointRegion"] = endpoint_region

    resp = requests.post(publish_url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Path to LUIS JSON to import")
    p.add_argument("--authoring-key", help="LUIS authoring key (falls back to LUIS_AUTHORING_KEY env var)")
    p.add_argument("--region", help="Authoring region (e.g. westus2) (falls back to LUIS_AUTHORING_REGION env var)")
    p.add_argument("--endpoint-region", help="Optional endpoint region for publish (e.g. westus2)")
    p.add_argument("--no-train", action="store_true", help="Skip training/publishing step")
    args = p.parse_args()

    authoring_key = args.authoring_key or os.environ.get("LUIS_AUTHORING_KEY")
    region = args.region or os.environ.get("LUIS_AUTHORING_REGION")
    if not (authoring_key and region):
        p.error("Authoring key and region required (via args or env vars LUIS_AUTHORING_KEY and LUIS_AUTHORING_REGION)")

    print("Importing app from", args.file)
    app_id = import_app(args.file, authoring_key, region)
    print("Imported app id:", app_id)

    if args.no_train:
        print("Skipping train/publish as requested")
        return

    print("Training app...")
    train_app(app_id, authoring_key, region)
    print("Training succeeded")

    print("Publishing app to production slot...")
    resp = publish_app(app_id, authoring_key, region, endpoint_region=args.endpoint_region)
    print("Publish response:", resp)
    print("Done. Your app is published and you can find the app id above.")


if __name__ == '__main__':
    main()
