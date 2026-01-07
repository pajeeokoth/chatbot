
# MyTravel Bot 
### (aiohttp + Conversational Language Understanding)

This bot runs on aiohttp, uses the Microsoft Bot Framework SDK for Python, and integrates with Azure AI Language — Conversational Language Understanding (CLU). It exposes the Bot Framework endpoint at `/api/messages`.

## Structure
- `extraction_script.py`
- `P10_jupyternotebook.ipynb`
- `mytravel/` — aiohttp bot exposing `/api/messages` (CLU-enabled)


The app runs on `http://localhost:3978` for local development.
# chatbot
chatbot to help users choose a travel offer
This project is to create a chatbot to help users choose a travel offer.
It is part of the OpenClassrooms "Build your own chatbot with Deep Learning" course.
The chatbot will be trained on a dataset of conversations between users and travel agents.
The dataset is in JSON format and contains information about the user's preferences, the travel offers, and the conversation history.
The chatbot will be implemented using Python and the Azure Services.
The project will be divided into the following steps:
1. Load and preprocess the dataset
2. Build and train the chatbot model
3. Evaluate the model
4. Deploy the chatbot
The dataset used in this project is the Frames dataset, which is available on GitHub:



## Prerequisites
- Python 3.9+
- Bot Framework Emulator (for local testing)
- An Azure AI Language resource with a CLU project and a deployed model

## Setup
1. Create a virtualenv and install dependencies:

```bash
python -m venv venv
source venv/Scripts/activate  # Windows Git-bash: source venv/Scripts/activate
python -m pip install -r mytravel/requirements.txt
```

2) Environment variables (create `mytravel/.env`)
Use uppercase names. For local Emulator, leave App ID/Password empty.
```bash
export MICROSOFT_APP_ID=""
export MICROSOFT_APP_PASSWORD=""

# CLU env vars 
CLU_PROJECT_NAME=""
CLU_DEPLOYMENT_NAME=""
CLU_API_KEY=""
CLU_ENDPOINT=""
```

```
# Bot Framework credentials (leave empty for local Emulator)
MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=

# Conversational Language Understanding (CLU)
CLU_PROJECT_NAME=
CLU_DEPLOYMENT_NAME=
CLU_API_KEY=
CLU_ENDPOINT=  # e.g., https://your-resource.cognitiveservices.azure.com
```

Notes:
- `CLU_ENDPOINT` must include `https://` and no trailing slash.
- If CLU variables are not set, the bot falls back to echo so you can keep developing.

## Run
```bash
python mytravel/app.py
```
The server listens on `http://localhost:3978`.

## Monitoring in production
Use the helper script `tools/app_insights_monitor.py` to run Kusto queries against your Application Insights resource and keep an eye on intent volume or server errors.

1. Create or export these environment variables before running the script:
	```bash
	export AZURE_APP_INSIGHTS_RESOURCE_ID="/subscriptions/.../resourceGroups/.../providers/microsoft.insights/components/YourAppInsights"
	export AZURE_CLIENT_ID=...
	export AZURE_TENANT_ID=...
	export AZURE_CLIENT_SECRET=...
	```

2. Run one of the canned queries:
	```bash
	python tools/app_insights_monitor.py intents --days 3
	python tools/app_insights_monitor.py errors --days 1
	python tools/app_insights_monitor.py error-breakdown --top 12
	```

The tool uses `azure.monitor.query.LogsQueryClient` with [`DefaultAzureCredential`](https://learn.microsoft.com/azure/developer/python/azure-sdk-authenticate?tabs=cmd) so it works with managed identities, VS Code/CLI sign-in, or service principals.

**Telemetry / OpenTelemetry**

- **Purpose:** Configure the app to send OpenTelemetry traces to Application Insights (traces) and fall back to a legacy log handler when logs exporter isn't available.
- **Enable:** Add an Application Insights connection string to `mytravel/.env` using one of these keys:
	- `APPLICATIONINSIGHTS_CONNECTION_STRING` or `APPINSIGHTS_CONNECTION_STRING`.
- **Install packages (local venv):**

	```bash
	python -m pip install opentelemetry-api opentelemetry-sdk azure-monitor-opentelemetry-exporter
	```

- **What the app does:** When a connection string is present, `mytravel/app.py` attempts to configure OpenTelemetry tracing (Azure Monitor exporter). It also tries to wire an OpenTelemetry logs exporter when the installed `opentelemetry-sdk` supports it; otherwise it attaches the legacy `opencensus.ext.azure.log_exporter.AzureLogHandler` as a best-effort fallback.
- **Quick test:** Start the app and call the test endpoint to emit a span and log:

	```bash
	python mytravel/app.py
	curl http://localhost:3978/telemetry-test
	```

- **Verify ingestion (KQL):** Use `tools/app_insights_monitor.py` or the LogsQueryClient snippet to check counts. Common queries:

	- Traces:
		```kusto
		traces | where timestamp > ago(1d) | summarize c = count()
		```
	- Requests:
		```kusto
		requests | where timestamp > ago(1d) | summarize c = count()
		```
	- Dependencies:
		```kusto
		dependencies | where timestamp > ago(1d) | summarize c = count()
		```

- **Note on tables:** Depending on exporter mapping and SDK versions, spans may appear under `dependencies` or `traces`. If you see zero `traces` but non-zero `dependencies`, include both in your dashboards/alerts.
- **Troubleshooting import errors:** If you see errors like `ImportError: cannot import name 'set_logger_provider'`, the README's wiring is designed to tolerate different `opentelemetry-sdk` versions. To help diagnose your environment, run:

	```bash
	python -m pip show opentelemetry-sdk azure-monitor-opentelemetry-exporter opentelemetry-api

	# Optional diagnostic script
	python - <<'PY'
	import importlib
	mods = ['opentelemetry', 'opentelemetry.sdk', 'opentelemetry.sdk._logs', 'azure.monitor.opentelemetry.exporter']
	for m in mods:
			try:
					mod = importlib.import_module(m)
					print(m, '->', getattr(mod, '__version__', 'no __version__'))
			except Exception as e:
					print(m, 'import failed:', e)
	PY
	```

	If the logs exporter is not available for your SDK version, the app will fall back to `AzureLogHandler` for logs and continue sending traces.

- **Permissions for querying:** `tools/app_insights_monitor.py` uses `DefaultAzureCredential`. Ensure one of these is available:
	- `az login` (CLI) for developer scenarios
	- Service principal credentials in `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`

Add or update these values in `mytravel/.env` as needed before running the monitor tools.

### Open workbook & pin visuals to dashboard

After you create a Workbook with `tools/create_workbook.py` the workbook appears as an ARM resource. To open it and pin visuals to a portal dashboard:

- Open the workbook resource in the Azure Portal using the resource id printed by the script (or the URL shown after creation). Example:

```text
https://portal.azure.com/#@/resource/subscriptions/<sub>/resourcegroups/<rg>/providers/microsoft.insights/workbooks/<workbook-id>
```

- Open the workbook and click `Edit` (top menu) to enable editing mode.

- For each visual or query tile you want on a dashboard:
	- Hover the tile and click the small pin icon (Pin to dashboard) or use the tile's menu (•••) → `Pin to dashboard`.
	- Choose an existing dashboard or create a new one, then select the tile size/position options the portal shows.

- After pinning the desired visuals, open the Dashboard (via the portal left-nav or the link the pin dialog provided) and rearrange tiles if needed.

- Save the dashboard (top-right `Save`) so the pinned tiles remain available for your team.

Notes and alternatives:
- You can also pin Logs results directly from the Logs (Analytics) blade: run a query → `Pin to dashboard` → choose dashboard and tile layout.
- If pinning programmatically is required, consider generating dashboard ARM JSON parts that reference workbook/query deep-links — this is more involved and fragile across portal versions; the helper `tools/pin_dashboard.py` creates markdown-link tiles as a stable alternative.


## Alerts (Action Group + Scheduled Query Rules)

Added an ARM template that creates an Action Group that can attach to alert rules. The template is at `azure/action_group_template.json`.

To create alerts (scheduled log alerts) in the Portal:

1. Create an Action Group (quick):
	 ```bash
	 az deployment group create \
		 --resource-group <your-rg> \
		 --template-file azure/action_group_template.json \
		 --parameters actionGroupName=MyTravelAlerts emailAddress=ops@example.com
	 ```

2. In the Portal: Application Insights → Logs, paste one of the queries from `tools/app_insights_monitor.py`, run it to confirm results, then click `New alert rule` → `Create` → choose `Custom log search` and point it to the same App Insights resource. For the action, select the Action Group you created.

Suggested alert rules to create (KQL):

- Errors over time (fire when any error in 5m window):

```kusto
traces
| where timestamp > ago(5m)
| where severityLevel >= 2
| summarize hits = count()
| where hits > 0
```

- CLU failures (fire when CLU errors appear):

```kusto
traces
| where message has "CLU error (fallback to echo)"
| where timestamp > ago(10m)
| summarize count() by bin(timestamp, 5m)
| where count_ > 0
```



## Test with Emulator
- Endpoint URL: `http://localhost:3978/api/messages`
- Microsoft App ID: leave empty for local
- Microsoft App Password: leave empty for local

Auth rules:
- For local Emulator, leave BOTH MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD empty in `.env` and in the Emulator.
- For channels or authenticated Emulator connections, set BOTH values and enter the same pair in the Emulator. If only one is set, the app falls back to unauthenticated mode for local development.

## CLU behavior
- With CLU configured, the bot calls CLU and returns a compact JSON summary: top intent, confidence, and entities.
- Without CLU, the bot echoes the user message.
# MyTravel Bot (aiohttp + CLU)

This is a minimal messaging web application using aiohttp and the Microsoft Bot Builder SDK (Python).

Files:
- `app.py` - aiohttp app exposing `/api/messages` for Bot Framework requests.
- `bot.py` - `TravelBot` implementing `ActivityHandler` with optional LUIS integration.
- `requirements.txt` - Python dependencies.

LUIS integration:

- `LUIS_APP_ID` - your LUIS application ID
- `LUIS_API_KEY` - your LUIS prediction key
- `LUIS_API_HOST_NAME` - the host name for the LUIS prediction endpoint, e.g. `your-resource-name.cognitiveservices.azure.com` or `<region>.api.cognitive.microsoft.com`

If these environment variables are set, the bot will call LUIS for each incoming message and return a JSON response containing the top intent and detected entities. If they are not set the bot falls back to a simple echo behavior.

Notes:
- This is a minimal example. For production, use proper error handling, HTTPS, and configure channels in Azure Bot Service.
