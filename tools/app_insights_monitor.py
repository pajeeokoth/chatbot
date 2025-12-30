"""Simple CLI helper to run App Insights log queries for the chatbot."""

import argparse
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient

import os, logging
try:
    from applicationinsights import TelemetryClient
except Exception:
    TelemetryClient = None  # type: ignore

def _get_tc():
    ikey = os.getenv("APPINSIGHTS_INSTRUMENTATION_KEY") or os.getenv("APPLICATIONINSIGHTS_INSTRUMENTATION_KEY")
    if not ikey:
        logging.info("AppInsights: no instrumentation key found")
        return None
    if TelemetryClient is None:
        logging.info("AppInsights: SDK not installed, skipping telemetry")
        return None
    try:
        return TelemetryClient(ikey)
    except Exception as exc:
        logging.warning("AppInsights: TelemetryClient create failed: %s", exc)
        return None

def track_event(name: str, properties: dict | None = None, measurements: dict | None = None) -> bool:
    tc = _get_tc()
    if not tc:
        logging.info("AppInsights: skipping track_event(%s) — no client", name)
        return False
    try:
        tc.track_event(name, properties or {}, measurements or {})
        tc.flush()
        logging.info("AppInsights: track_event(%s) sent; props=%s", name, properties or {})
        return True
    except Exception as exc:
        logging.warning("AppInsights: track_event(%s) failed: %s", name, exc)
        return False

INTENT_QUERY = '''
customEvents
| where name == "bot.response"
| where tostring(customDimensions.type) == "clu"
| extend confidence = todouble(customDimensions.confidence)
| where isnotnull(confidence)
| summarize AvgConfidence = avg(confidence) by bin(timestamp, 15m)
| render timechart
'''

WEEKLY_ALERTS_QUERY = '''
customEvents
| where timestamp > ago({days}d)
| where name == "bot.response"
| where tostring(customDimensions.type) == "clu"
| extend confidence = todouble(customDimensions.confidence)
| where isnotnull(confidence) and confidence < 0.8
| summarize alerts = count() by week = bin(timestamp, 7d)
| order by week asc
'''

ERROR_QUERY = '''
traces
| where timestamp > ago({days}d)
| where severityLevel >= 2
| summarize hits = count() by bin(timestamp, 1h)
| order by timestamp asc
'''

ERROR_BREAKDOWN_QUERY = '''
traces
| where timestamp > ago({days}d)
| where severityLevel >= 2
| summarize hits = count() by message
| top {top} by hits
'''


def run_query(client: LogsQueryClient, resource_id: str, query_template: str, days: int, **extra) -> None:
    timespan = timedelta(days=days)
    formatted = query_template.format(days=days, **extra)
    result = client.query_resource(resource_id, formatted, timespan=timespan)


    if result.status != "Success":
        print("Query failed:", result.error)
        return

    for table in result.tables:
        if not table.rows:
            print("No rows returned for table", table.name)
            continue
        print(table.columns)

        headers = [col for col in table.columns]

        print(" | ".join(headers))
        print("-" * 60)
        for row in table.rows:
            print(" | ".join(str(value) for value in row))
        print()


def get_resource_id(cli_resource: str) -> str:
    resource_id = cli_resource or os.environ.get("AZURE_APP_INSIGHTS_RESOURCE_ID")
    if not resource_id:
        raise SystemExit("Set AZURE_APP_INSIGHTS_RESOURCE_ID to the App Insights resource ID.")
    return resource_id


def load_env(path: str | None) -> None:
    if path:
        env_path = Path(path)
        if not env_path.exists():
            raise SystemExit(f"Unable to read .env file at {env_path}")
        load_dotenv(env_path, override=False)
        return

    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(repo_root / "mytravel" / ".env", override=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canned App Insights queries for MyTravel Bot.")
    parser.add_argument("--env-file", help="Path to a .env file to load before running queries.")
    parser.add_argument("--resource-id", help="Azure resource ID for the Application Insights resource.")
    parser.add_argument("--days", type=int, default=7, help="Timespan in days to query (default 7).")
    parser.add_argument("--top", type=int, default=10, help="Limit for error breakdown query.")
    parser.add_argument("query", choices=["intents", "alerts", "errors", "error-breakdown"], nargs="?", default="intents")

    args = parser.parse_args()

    load_env(args.env_file)

    resource_id = get_resource_id(args.resource_id)
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)

    if args.query == "intents":
        print("Intents over time (per hour):")
        run_query(client, resource_id, INTENT_QUERY, args.days)
    elif args.query == "alerts":
        print(f"Weekly low-confidence alerts over {args.days} days:")
        run_query(client, resource_id, WEEKLY_ALERTS_QUERY, args.days)
    elif args.query == "errors":
        print("Errors over time (per hour):")
        run_query(client, resource_id, ERROR_QUERY, args.days)
    else:
        print(f"Top {args.top} errors over {args.days} days:")
        run_query(client, resource_id, ERROR_BREAKDOWN_QUERY, args.days, top=args.top)


if __name__ == "__main__":
    main()
