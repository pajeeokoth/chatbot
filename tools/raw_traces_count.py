"""Run a simple traces count query against Application Insights.

Usage:
  python tools/raw_traces_count.py --env-file mytravel/.env --days 90
"""
import argparse
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient

QUERY = '''
traces
| where timestamp > ago({days}d)
| summarize count = count()
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', help='Path to .env file')
    parser.add_argument('--resource-id', help='App Insights resource id')
    parser.add_argument('--days', type=int, default=90)
    args = parser.parse_args()

    load_env(args.env_file)
    resource_id = args.resource_id or os.environ.get('AZURE_APP_INSIGHTS_RESOURCE_ID')
    if not resource_id:
        raise SystemExit('AZURE_APP_INSIGHTS_RESOURCE_ID not set')

    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)
    timespan = timedelta(days=args.days)
    q = QUERY.format(days=args.days)
    print('Running query:')
    print(q)
    res = client.query_resource(resource_id, q, timespan=timespan)
    if res.status != 'Success':
        print('Query failed:', res.error)
        return
    for table in res.tables:
        for row in table.rows:
            print('Traces count:', row[0])

if __name__ == '__main__':
    main()
