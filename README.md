# ArriveAssist 

A Streamlit chat interface for an n8n-powered newcomer settlement assistant covering Canadian citizenship, OHIP, and Social Insurance Numbers.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:N8N_WEBHOOK_URL = "https://your-n8n-host/webhook/your-path"
streamlit run app.py
```

The webhook URL can also be entered under **Webhook settings** in the app sidebar. Conversations are stored in Streamlit session state and last only for the current browser session.

The app sends:

```json
{"chatInput": "the user's message", "sessionId": "the n8n session ID, when available"}
```

It accepts the first response field found in this order: `output`, `text`, `response`, `message`.

