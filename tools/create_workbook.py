"""Create an Azure Workbook with charts for MyTravel Bot (Intents + Errors).

This creates a workbook resource under the target resource group using the ARM REST API
and DefaultAzureCredential-based auth. The workbook contains two query parts:
- Intents over time (series by intent)
- Errors over time (error count)

Usage:
  python tools/create_workbook.py --env-file mytravel/.env \
    --subscription <sub> --resource-group <rg> --workbook-name MyTravelBotWorkbook --days 60

Permissions:
- Caller must have permission to create workbooks in the resource group.
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
import requests

INTENT_QUERY = """
traces
| where timestamp > ago({days}d)
| where message has "CLUResult |"
| parse message with * "intent=" intent " | confidence=" confidence " | entities=" entities
| summarize hits = count() by bin(timestamp, 1h), intent
| order by timestamp asc
"""

ERROR_QUERY = """
traces
| where timestamp > ago({days}d)
| where severityLevel >= 2
| summarize hits = count() by bin(timestamp, 1h)
| order by timestamp asc
"""

def load_env(path: str | None):
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f".env file not found: {p}")
        load_dotenv(p, override=False)
    else:
        repo_root = Path(__file__).resolve().parent.parent
        load_dotenv(repo_root / '.env', override=False)
        load_dotenv(repo_root / 'mytravel' / '.env', override=False)


def build_serialized_data(intents_kql: str, errors_kql: str, days: int) -> str:
    """Build the serializedData value for the workbook resource.
    We create a simple structure with two items of type "query" and visualization set to timechart.
    """
    # Basic workbook schema version and items
    data = {
        "version": "Notebook/1.0",
        "items": [
            {
                "type": 4,
                "content": {
                    "json": {
                        "query": intents_kql,
                        "timespan": f"P{days}D",
                        "visualization": {
                            "type": "TimeSeries",
                            "title": "Intents over time (by intent)",
                            "splitBy": "intent"
                        }
                    }
                }
            },
            {
                "type": 4,
                "content": {
                    "json": {
                        "query": errors_kql,
                        "timespan": f"P{days}D",
                        "visualization": {
                            "type": "TimeSeries",
                            "title": "Errors over time"
                        }
                    }
                }
            }
        ]
    }
    return json.dumps(data)


def create_workbook(subscription: str, rg: str, workbook_name: str, serialized_data: str, credential: DefaultAzureCredential, source_id: str | None = None):
    token = credential.get_token('https://management.azure.com/.default').token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # sanitize workbook resource name for ARM URL path
    def sanitize_resource_name(name: str) -> str:
        import re
        n = (name or '').strip()
        n = re.sub(r"\s+", '-', n)
        n = re.sub(r"[^A-Za-z0-9\-_.()]+", '', n)
        n = n.lower()
        if len(n) > 80:
            n = n[:80]
        if not n:
            n = 'workbook'
        if n[0] in '.-':
            n = 'w' + n[1:]
        return n

    # prefer explicit resource name if provided via CLI env (args not in scope here), or default to a safer variant
    explicit = os.environ.get('WORKBOOK_RESOURCE_NAME')
    if explicit:
        resource_name = sanitize_resource_name(explicit)
    else:
        # append a short suffix to avoid ending with 'workbook' which some tenants reject
        resource_name = sanitize_resource_name(workbook_name + '-wb')
    print(f"Using ARM resource name '{resource_name}' (displayName='{workbook_name}')")
    url = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{rg}/providers/microsoft.insights/workbooks/{resource_name}?api-version=2020-10-20"

    # location should be set by caller; default to eastus if not provided
    # determine kind and validate
    kind = os.environ.get('WORKBOOK_KIND', 'shared')
    kind_normalized = (kind or '').strip().lower()
    allowed = {'shared', 'personal'}
    if kind_normalized not in allowed:
        raise SystemExit(
            f"Invalid WORKBOOK_KIND='{kind}'. Allowed: {sorted(list(allowed))}. "
            "Set WORKBOOK_KIND=shared or WORKBOOK_KIND=personal in your .env or CLI env."
        )

    body = {
        "location": os.environ.get('WORKBOOK_REGION', 'eastus'),
        # 'kind' is required by the Workbooks ARM API (shared or personal)
        "kind": kind_normalized,
        "properties": {
            "displayName": workbook_name,
            "serializedData": serialized_data
        }
    }
    # attach source Application Insights resource if provided so the workbook is scoped
    if source_id:
        # some API versions expect a top-level sourceId in properties
        body['properties']['sourceId'] = source_id
    # debug/log the payload kind so user can see what's sent
    print(f"Creating workbook with kind='{kind_normalized}' in location='{body['location']}'")

    # Try the initial request
    resp = requests.put(url, headers=headers, json=body)
    if resp.ok:
        print(f"Workbook '{workbook_name}' created/updated in rg '{rg}' (subscription: {subscription}).")
        resjson = resp.json()
        return resjson.get('id')

    # If API complains about 'kind', attempt a few known alternatives
    text = resp.text or ''
    if resp.status_code == 400 and 'Parameter name: kind' in text:
        print(f"Initial attempt failed with kind='{body.get('kind')}'. Trying alternative kinds...")
        candidates = ['shared', 'personal', 'user', 'Shared', 'Personal', 'User']
        tried = {body.get('kind')}
        for k in candidates:
            if k in tried:
                continue
            body['kind'] = k
            print(f"Retrying with kind='{k}'...")
            resp2 = requests.put(url, headers=headers, json=body)
            if resp2.ok:
                print(f"Workbook created with kind='{k}'.")
                return resp2.json().get('id')
            print(f"Attempt with kind='{k}' failed: {resp2.status_code} {resp2.text}")

        # If the service reports the resource name is invalid, try simple fallback names
        if 'Invalid Workbook resource name' in (resp.text or ''):
            print('Service reported invalid resource name. Trying fallback resource name variants...')
            base = resource_name
            suffixes = ['-wb', '-workbook', '-1']
            for s in suffixes:
                alt_name = (base + s)[:80]
                alt_url = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{rg}/providers/microsoft.insights/workbooks/{alt_name}?api-version=2020-10-20"
                for k in candidates:
                    body['kind'] = k
                    print(f"Retrying with resource name='{alt_name}', kind='{k}'...")
                    resp3 = requests.put(alt_url, headers=headers, json=body)
                    if resp3.ok:
                        print(f"Workbook created with resource name='{alt_name}', kind='{k}'")
                        return resp3.json().get('id')
                    print(f"Attempt failed: {resp3.status_code} {resp3.text}")

        # As a last resort, try using a GUID resource name — some tenants require GUID-style ids
        import uuid
        guid_name = str(uuid.uuid4())
        guid_url = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{rg}/providers/microsoft.insights/workbooks/{guid_name}?api-version=2020-10-20"
        print(f"Trying last-resort GUID resource name '{guid_name}' with candidate kinds...")
        for k in candidates:
            body['kind'] = k
            print(f"Retrying with resource name='{guid_name}', kind='{k}'...")
            resp4 = requests.put(guid_url, headers=headers, json=body)
            if resp4.ok:
                print(f"Workbook created with resource name='{guid_name}', kind='{k}'")
                return resp4.json().get('id')
            print(f"Guid attempt failed: {resp4.status_code} {resp4.text}")

    # No successful attempt
    raise SystemExit(f"Failed to create workbook: {resp.status_code} {resp.text}")


def main():
    parser = argparse.ArgumentParser(description="Create Application Insights Workbook for MyTravel Bot")
    parser.add_argument('--env-file', help='Path to .env file (optional)')
    parser.add_argument('--subscription', required=True)
    parser.add_argument('--resource-group', required=True)
    parser.add_argument('--workbook-name', required=True)
    parser.add_argument('--resource-name', help='(Optional) explicit ARM resource name for the workbook')
    parser.add_argument('--location', help='Azure region to create the workbook in (overrides env WORKBOOK_REGION)')
    parser.add_argument('--days', type=int, default=60)
    args = parser.parse_args()

    load_env(args.env_file)
    resource_id = os.environ.get('AZURE_APP_INSIGHTS_RESOURCE_ID')
    if not resource_id:
        raise SystemExit('AZURE_APP_INSIGHTS_RESOURCE_ID not set in environment or .env')

    intents_kql = INTENT_QUERY.format(days=args.days)
    errors_kql = ERROR_QUERY.format(days=args.days)

    serialized = build_serialized_data(intents_kql, errors_kql, args.days)

    # allow overriding workbook region via CLI or env
    if args.location:
        os.environ['WORKBOOK_REGION'] = args.location
    # allow explicit ARM resource name via CLI
    if args.resource_name:
        os.environ['WORKBOOK_RESOURCE_NAME'] = args.resource_name

    credential = DefaultAzureCredential()
    wb_id = create_workbook(args.subscription, args.resource_group, args.workbook_name, serialized, credential, resource_id)

    print('Workbook resource id:', wb_id)
    print('Open it in the portal:')
    print(f'https://portal.azure.com/#@/resource{wb_id}')

if __name__ == '__main__':
    main()
