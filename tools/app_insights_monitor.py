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
traces
| where timestamp > ago({days}d)
| where message has "CLUResult |"
| parse message with * "intent=" intent " | confidence=" confidence " | entities=" entities
| summarize hits = count() by bin(timestamp, 1h), intent
| order by timestamp asc, intent asc
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

        headers = [col.name for col in table.columns]
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
    parser.add_argument("query", choices=["intents", "errors", "error-breakdown"], nargs="?", default="intents")

    args = parser.parse_args()

    load_env(args.env_file)

    resource_id = get_resource_id(args.resource_id)
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)

    if args.query == "intents":
        print("Intents over time (per hour):")
        run_query(client, resource_id, INTENT_QUERY, args.days)
    elif args.query == "errors":
        print("Errors over time (per hour):")
        run_query(client, resource_id, ERROR_QUERY, args.days)
    else:
        print(f"Top {args.top} errors over {args.days} days:")
        run_query(client, resource_id, ERROR_BREAKDOWN_QUERY, args.days, top=args.top)


if __name__ == "__main__":
    main()







# """Simple CLI helper to run App Insights log queries for the chatbot."""

# import argparse
# import os
# from datetime import timedelta
# from pathlib import Path

# from dotenv import load_dotenv
# from azure.identity import DefaultAzureCredential
# from azure.monitor.query import LogsQueryClient

# # ----------------------------------------------------------------------------------------------------
# # Load environment variables from a `.env` file if it exists in the repository root or `mytravel` subdirectory.
# # Use telemetry-specific environment variables if set, otherwise fall back to the default credentials.
# # If the SDK is not installed, log a warning and skip telemetry.
# # ----------------------------------------------------------------------------------------------------
# import os, logging
# try:
#     from applicationinsights import TelemetryClient
# except Exception:
#     TelemetryClient = None  # type: ignore

# def _get_tc():
#     ikey = os.getenv("APPINSIGHTS_INSTRUMENTATION_KEY") or os.getenv("APPLICATIONINSIGHTS_INSTRUMENTATION_KEY")
#     if not ikey:
#         logging.info("AppInsights: no instrumentation key found")
#         return None
#     if TelemetryClient is None:
#         logging.info("AppInsights: SDK not installed, skipping telemetry")
#         return None
#     try:
#         return TelemetryClient(ikey)
#     except Exception as exc:
#         logging.warning("AppInsights: TelemetryClient create failed: %s", exc)
#         return None

# def track_event(name: str, properties: dict | None = None, measurements: dict | None = None) -> bool:
#     tc = _get_tc()
#     if not tc:
#         logging.info("AppInsights: skipping track_event(%s) — no client", name)
#         return False
#     try:
#         tc.track_event(name, properties or {}, measurements or {})
#         tc.flush()
#         logging.info("AppInsights: track_event(%s) sent; props=%s", name, properties or {})
#         return True
#     except Exception as exc:
#         logging.warning("AppInsights: track_event(%s) failed: %s", name, exc)
#         return False


# # --------------------------------------------------------------------------------------------------
# # Query templates: these are parameterized with `{days}` to allow specifying the timespan.
# # The `traces` table is used for most telemetry, but some may be mapped into the `dependencies` table
# # and have different columns (e.g., `name`, `data`, `properties`).
# # Traces-specific queries: these are designed to work with the `traces` table.
# # --------------------------------------------------------------------------------------------------
# INTENT_QUERY = '''
# traces
# | where timestamp > ago({days}d)
# | where message has "CLUResult |"
# | parse message with * "intent=" intent " | confidence=" confidence " | entities=" entities
# | summarize hits = count() by bin(timestamp, 1h), intent
# | order by timestamp asc, intent asc
# '''

# ERROR_QUERY = '''
# traces
# | where timestamp > ago({days}d)
# | where severityLevel >= 2
# | summarize hits = count() by bin(timestamp, 1h)
# | order by timestamp asc
# '''

# ERROR_BREAKDOWN_QUERY = '''
# traces
# | where timestamp > ago({days}d)
# | where severityLevel >= 2
# | summarize hits = count() by message
# | top {top} by hits
# '''

# # Dependency-specific queries: some telemetry may be mapped into `dependencies` table
# # and has different columns (e.g., `name`, `data`, `properties`). These queries
# # attempt to detect CLU-related messages by searching common fields for the
# # CLUResult marker and then summarize similarly to the traces queries.
# DEP_INTENT_QUERY = '''
# dependencies
# | where timestamp > ago({days}d)
# | search "CLUResult"
# | summarize hits = count() by bin(timestamp, 1h), name
# | order by timestamp asc, name asc
# '''

# DEP_ERROR_QUERY = '''
# dependencies
# | where timestamp > ago({days}d)
# | search "exception" or "error" or "fail"
# | summarize hits = count() by bin(timestamp, 1h)
# | order by timestamp asc
# '''

# DEP_ERROR_BREAKDOWN_QUERY = '''
# dependencies
# | where timestamp > ago({days}d)
# | search "exception" or "error" or "fail"
# | summarize hits = count() by name
# | top {top} by hits
# '''


# def run_query(client: LogsQueryClient, resource_id: str, query_template: str, days: int, tables: list[str] | None = None, table_overrides: dict | None = None, **extra) -> None:
#     """Run the provided query template against one or more tables.

#     The query_template is expected to start with the table name `traces` which
#     will be replaced for each requested table (e.g. `dependencies`). This keeps
#     the same logical query but runs it against both `traces` and `dependencies`.
#     """
#     if tables is None:
#         tables = ["traces"]

#     timespan = timedelta(days=days)

#     for table_name in tables:
#         # If querying the dependencies table, always use a dependency-safe
#         # template. This avoids sending traces-specific queries that reference
#         # columns like `message` or `severityLevel` which don't exist on
#         # `dependencies` (causing semantic errors).
#         if table_name == "dependencies":
#             # Prefer an explicit override if provided
#             if table_overrides and table_name in table_overrides:
#                 formatted = table_overrides[table_name].format(days=days, **extra)
#             else:
#                 # Map the generic template to the matching dependency template
#                 if query_template is INTENT_QUERY or "CLUResult" in query_template or "intent=" in query_template:
#                     formatted = DEP_INTENT_QUERY.format(days=days, **extra)
#                 elif query_template is ERROR_BREAKDOWN_QUERY or "severityLevel" in query_template or "by message" in query_template:
#                     formatted = DEP_ERROR_BREAKDOWN_QUERY.format(days=days, **extra)
#                 else:
#                     # Default to the error-time series template
#                     formatted = DEP_ERROR_QUERY.format(days=days, **extra)
#         else:
#             # Non-dependencies: replace only the first occurrence of 'traces'
#             # so other occurrences (if any) in the query text aren't accidentally changed.
#             formatted = query_template.replace("traces", table_name, 1).format(days=days, **extra)
#         print(f"=== Results from table: {table_name} ===")
#         try:
#             result = client.query_resource(resource_id, formatted, timespan=timespan)
#         except Exception as e:
#             # Print a concise error and continue to the next table
#             print("Query failed for table", table_name, "->", repr(e))
#             continue

#         if result.status != "Success":
#             print("Query failed:", result.error)
#             continue

#         any_rows = False
#         for table in result.tables:
#             if not table.rows:
#                 print("No rows returned for table", table.name)
#                 continue

#             any_rows = True
#             headers = [col.name for col in table.columns]
#             print(" | ".join(headers))
#             print("-" * 60)
#             for row in table.rows:
#                 print(" | ".join(str(value) for value in row))
#             print()

#         if not any_rows:
#             print("(no results)")
#         print()


# def get_resource_id(cli_resource: str) -> str:
#     resource_id = cli_resource or os.environ.get("AZURE_APP_INSIGHTS_RESOURCE_ID")
#     if not resource_id:
#         raise SystemExit("Set AZURE_APP_INSIGHTS_RESOURCE_ID to the App Insights resource ID.")
#     return resource_id


# def load_env(path: str | None) -> None:
#     if path:
#         env_path = Path(path)
#         if not env_path.exists():
#             raise SystemExit(f"Unable to read .env file at {env_path}")
#         load_dotenv(env_path, override=False)
#         return

#     repo_root = Path(__file__).resolve().parent.parent
#     load_dotenv(repo_root / ".env", override=False)
#     load_dotenv(repo_root / "mytravel" / ".env", override=False)


# def main() -> None:
#     parser = argparse.ArgumentParser(description="Run canned App Insights queries for MyTravel Bot.")
#     parser.add_argument("--env-file", help="Path to a .env file to load before running queries.")
#     parser.add_argument("--resource-id", help="Azure resource ID for the Application Insights resource.")
#     parser.add_argument("--days", type=int, default=7, help="Timespan in days to query (default 7).")
#     parser.add_argument("--top", type=int, default=10, help="Limit for error breakdown query.")
#     parser.add_argument("query", choices=["intents", "errors", "error-breakdown"], nargs="?", default="intents")

#     args = parser.parse_args()

#     load_env(args.env_file)

#     resource_id = get_resource_id(args.resource_id)
#     credential = DefaultAzureCredential()
#     client = LogsQueryClient(credential)

#     if args.query == "intents":
#         print("Intents over time (per hour):")
#         # Run against both traces and dependencies to capture spans mapped to dependencies
#         run_query(
#             client,
#             resource_id,
#             INTENT_QUERY,
#             args.days,
#             tables=["traces", "dependencies"],
#             table_overrides={"dependencies": DEP_INTENT_QUERY},
#         )
#     elif args.query == "errors":
#         print("Errors over time (per hour):")
#         run_query(
#             client,
#             resource_id,
#             ERROR_QUERY,
#             args.days,
#             tables=["traces", "dependencies"],
#             table_overrides={"dependencies": DEP_ERROR_QUERY},
#         )
#     else:
#         print(f"Top {args.top} errors over {args.days} days:")
#         run_query(
#             client,
#             resource_id,
#             ERROR_BREAKDOWN_QUERY,
#             args.days,
#             tables=["traces", "dependencies"],
#             table_overrides={"dependencies": DEP_ERROR_BREAKDOWN_QUERY},
#             top=args.top,
#         )


# if __name__ == "__main__":
#     main()
