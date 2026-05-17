<img width="1890" height="930" alt="image" src="https://github.com/user-attachments/assets/3a94c2d6-ff50-4c74-a97a-74d6aebe0f1e" />
# Vendora AI Restaurant Auditor

An AI-powered restaurant operations intelligence platform that detects suspicious paidouts, inventory variance, and profit leakage using Gemini-powered analysis and MongoDB-backed operational data.

Built for the Google Cloud Rapid Agent Hackathon.

## Overview

Vendora AI Restaurant Auditor gives restaurant operators a structured audit layer over daily operating records. It analyzes paidouts, inventory levels, POS sales summaries, and close activity, then produces evidence-based risk findings and next actions.

The product is designed for operators, owners, and auditors who need fast answers to questions such as:

- Which paidouts require reconciliation?
- Which ingredients are creating inventory pressure?
- Are cash movements consistent with sales volume?
- Which recurring control gaps are affecting operating profit?

## Problem

Restaurant profit leakage is often hidden in small operational records: cash paidouts, emergency purchases, stock shortages, and inconsistent close procedures. Operators may have the data, but they rarely have time to investigate patterns across paidouts, sales, and inventory every day.

## Solution

Vendora turns operational records into a focused audit workflow:

1. Review store-level sales, paidouts, inventory value, low-stock exposure, and estimated operating profit.
2. Run an operational audit.
3. Gemini analyzes the operating context and returns a structured report.
4. Review executive summary, risk score, key findings, evidence, recommendations, and next actions.
5. Investigate recurring risk patterns across the prior seven-day window.

## Operational Audit Workflow

The primary workflow is intentionally narrow and business-focused:

- Fetch paidouts for the audit period.
- Fetch inventory and low-stock records.
- Fetch POS sales summaries and close activity.
- Calculate paidout-to-sales ratio and operating profit indicators.
- Identify suspicious transactions, inventory pressure, and control gaps.
- Send structured context to Gemini.
- Store generated reports locally and mirror them to MongoDB when configured.

## AI Audit Methodology

The AI auditor uses an operational audit prompt, not a chatbot prompt. Reports are expected to include:

- Executive summary
- Risk level and risk score
- Key findings
- Evidence list
- Explanation of operational impact
- Recommendations
- Next actions

The system favors evidence-based language around cash leakage, inventory variance, reconciliation, approval controls, and operating profit impact.

## Gemini Integration

Gemini requests are made only from the Django backend. The frontend never receives `GEMINI_API_KEY`.

Endpoint:

```http
POST /api/ai/analyze
```

Example request:

```json
{
  "storeId": "1",
  "dateRange": "yesterday",
  "question": "Run operational audit for the current audit period"
}
```

If Gemini is not configured or unavailable, Vendora returns a professional rule-based audit report so operators still receive a structured risk assessment.

## MongoDB Data Layer

MongoDB is used as the operational data and report layer when `MONGODB_URI` is configured.

Operational collections:

- `inventory`
- `paidouts`
- `salesReports`
- `aiReports`

Generated audit reports are mirrored to the `aiReports` collection with the operational context used for the analysis. This supports future MongoDB MCP workflows where the agent can query operational collections directly as tools/context.

## Architecture

- Django application server
- Server-rendered operational UI
- Backend-only Gemini integration
- MongoDB report mirroring
- SQLite local development database
- WhiteNoise static file serving
- Gunicorn production runtime
- Render deployment configuration

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_ai_auditor_demo
python manage.py runserver
```

Local analyst account created by the seed command:

```text
Username: ops_owner
Password: ops12345
```

Open:

```text
http://127.0.0.1:8000/ai/
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
DJANGO_SECRET_KEY=
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DEBUG=False
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
MONGODB_URI=
MONGODB_DB=vendora_ai
PORT=8000
```

## Deployment

The project is Render-ready with `render.yaml`, `Procfile`, WhiteNoise, and Gunicorn.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
python manage.py migrate && python manage.py collectstatic --noinput && gunicorn vendoraops.wsgi:application --bind 0.0.0.0:$PORT
```

Set production environment variables in Render:

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DEBUG=False`
- `GEMINI_API_KEY`
- `MONGODB_URI`
- `MONGODB_DB`

## Security Notes

- `GEMINI_API_KEY` is backend-only.
- `.env`, `.venv`, logs, bytecode, and local SQLite database files are ignored.
- AI report content is escaped in server-rendered templates.
- Dynamic report rendering uses text nodes instead of raw HTML injection.
- Production deployments should enable secure cookies, HTTPS redirect, and HSTS.

## License

MIT. See `LICENSE`.
