"""Create or update an Azure portal dashboard that pins links to App Insights queries.

This helper does not attempt to embed live query visuals (that requires complex portal part definitions).
Instead it creates a dashboard with Markdown tiles that contain:
 - the Kusto query (as code block)
 - a deep link to open the Logs blade for the specified resource with the query prefilled

Usage:
  python tools/pin_dashboard.py --env-file mytravel/.env \
      --subscription <sub-id> --resource-group <rg> --dashboard-name MyTravelDashboard

Permissions: the identity used by DefaultAzureCredential must have Contributor or Owner on the resource group
or at least permissions to create/update dashboard resources.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

# Simple KQL snippets (same as app_insights_monitor)
INTENT_QUERY = '''traces
| where timestamp > ago({days}d)
| where message has "CLUResult |"
| parse message with * "intent=" intent " | confidence=" confidence " | entities=" entities
| summarize hits = count() by bin(timestamp, 1h), intent
| order by timestamp asc, intent asc
'''

ERROR_QUERY = '''traces
| where timestamp > ago({days}d)
| where severityLevel >= 2
| summarize hits = count() by bin(timestamp, 1h)
| order by timestamp asc
'''


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


def build_logs_deeplink(resource_id: str, query: str, timespan='PT24H') -> str:
    """Construct a portal URL that opens Logs blade with the KQL prefilled.
    The portal deep link pattern encodes the query in the URL path.
    """
    # URL encode the query; portal expects certain encoding. Use quote_plus then replace '+' with '%20'
    encoded = quote_plus(query)
    # Replace plus with %20 for spaces
    encoded = encoded.replace('+', '%20')
    # Build the fragment for Logs blade
    fragment = (
        f"#blade/Microsoft_Azure_Monitoring_Logs/LogsBlade/resourceId/{quote_plus(resource_id)}/"
        f"source/LogsBlade.AnalyticsShareLinkToQuery/query/{encoded}/timespan/{timespan}"
    )
    return f"https://portal.azure.com/{fragment}"


def build_dashboard_body(dashboard_name: str, resource_id: str, days: int = 7, location: str = "eastus") -> dict:
    """Create a minimal dashboard JSON with markdown parts for intents and errors.
    Each part shows the query and a link to open the Logs blade.
    """
    intents = INTENT_QUERY.format(days=days)
    errors = ERROR_QUERY.format(days=days)

    intents_link = build_logs_deeplink(resource_id, intents)
    errors_link = build_logs_deeplink(resource_id, errors)

    # Basic dashboard structure - uses markdown parts
    body = {
        "location": location,
        "properties": {
            "lenses": {
                "0": {
                    "order": 0,
                    "parts": {
                        "intents": {
                            "position": {"x": 0, "y": 0, "rowSpan": 4, "colSpan": 6},
                            "metadata": {
                                "type": "MarkdownPart",
                                "inputs": [],
                                "settings": {
                                    "content": (
                                        "## Intents over time (last {days} days)\n\n"
                                        "[Open in Logs]({link})\n\n"
                                        "```kql\n{query}\n```"
                                    ).format(days=days, link=intents_link, query=intents)
                                }
                            }
                        },
                        "errors": {
                            "position": {"x": 6, "y": 0, "rowSpan": 4, "colSpan": 6},
                            "metadata": {
                                "type": "MarkdownPart",
                                "inputs": [],
                                "settings": {
                                    "content": (
                                        "## Errors over time (last {days} days)\n\n"
                                        "[Open in Logs]({link})\n\n"
                                        "```kql\n{query}\n```"
                                    ).format(days=days, link=errors_link, query=errors)
                                }
                            }
                        }
                    }
                }
            },
            "metadata": {"dashboardSchemaVersion": "1.0"}
        }
    }
    return body


def get_resource_group_location(subscription: str, rg: str, credential: DefaultAzureCredential) -> str:
    """Query the resource group's location using the ARM management API."""
    token = credential.get_token('https://management.azure.com/.default').token
    url = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{rg}?api-version=2021-04-01"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if not resp.ok:
        raise SystemExit(f"Failed to query resource group: {resp.status_code} {resp.text}")
    data = resp.json()
    loc = data.get('location')
    if not loc:
        raise SystemExit("Resource group location not found in API response")
    return loc


def put_dashboard(subscription: str, rg: str, name: str, body: dict, credential: DefaultAzureCredential):
    token = credential.get_token('https://management.azure.com/.default').token
    url = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Portal/dashboards/{name}?api-version=2019-01-01-preview"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.put(url, headers=headers, json=body)
    if not resp.ok:
        raise SystemExit(f"Failed to create dashboard: {resp.status_code} {resp.text}")
    print(f"Dashboard '{name}' created/updated in rg '{rg}' (subscription: {subscription}).")


def main():
    parser = argparse.ArgumentParser(description="Create a dashboard with links to App Insights queries")
    parser.add_argument("--env-file", help="Path to .env to load (optional)")
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--dashboard-name", required=True)
    parser.add_argument("--location", help="Override dashboard location/region (e.g. westus2)")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    load_env(args.env_file)
    resource_id = os.environ.get('AZURE_APP_INSIGHTS_RESOURCE_ID')
    if not resource_id:
        raise SystemExit('AZURE_APP_INSIGHTS_RESOURCE_ID not set in environment or .env')

    credential = DefaultAzureCredential()
    if args.location:
        loc = args.location
    else:
        # Try to detect resource group location; fall back to 'eastus' if detection fails
        try:
            loc = get_resource_group_location(args.subscription, args.resource_group, credential)
        except Exception:
            loc = 'eastus'

    body = build_dashboard_body(args.dashboard_name, resource_id, days=args.days, location=loc)
    put_dashboard(args.subscription, args.resource_group, args.dashboard_name, body, credential)


if __name__ == '__main__':
    main()
