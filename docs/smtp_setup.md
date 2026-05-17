# VendoraOps SMTP Setup

VendoraOps uses Django's free built-in password reset flow.

Local development defaults to console email, so reset emails print in the terminal and the reset page shows a development link.

Settings are loaded with `django-environ`, so production values can live in `.env`, Render/host environment variables, or Windows environment variables.

For production SMTP, set these environment variables:

```powershell
$env:EMAIL_HOST="smtp.your-provider.com"
$env:EMAIL_PORT="587"
$env:EMAIL_HOST_USER="your-smtp-user"
$env:EMAIL_HOST_PASSWORD="your-smtp-password"
$env:EMAIL_USE_TLS="True"
$env:EMAIL_USE_SSL="False"
$env:DJANGO_DEFAULT_FROM_EMAIL="VendoraOps <no-reply@yourdomain.com>"
```

If your SMTP provider needs SSL on port 465:

```powershell
$env:EMAIL_PORT="465"
$env:EMAIL_USE_TLS="False"
$env:EMAIL_USE_SSL="True"
```

When `EMAIL_HOST` is set, VendoraOps automatically uses Django's SMTP email backend unless `DJANGO_EMAIL_BACKEND` overrides it.

VendoraOps sends automatic daily-close emails to active client owners. Weekly and month-end reports can be sent with:

```powershell
.\.venv\Scripts\python.exe manage.py send_scheduled_reports --period weekly
.\.venv\Scripts\python.exe manage.py send_scheduled_reports --period monthly
```

Use `--dry-run` first to confirm the report window and recipient groups.

For Super Admin platform-safe reports, set:

```powershell
$env:PLATFORM_NOTIFICATION_EMAILS="admin@yourdomain.com"
```

You need these SMTP values to send real email: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` or `EMAIL_USE_SSL`, `DJANGO_DEFAULT_FROM_EMAIL`, and recipient emails on the user accounts.

For provider APIs, the project also includes the open-source `django-anymail` bridge. Example Mailgun configuration:

```powershell
$env:DJANGO_EMAIL_BACKEND="anymail.backends.mailgun.EmailBackend"
$env:ANYMAIL_MAILGUN_API_KEY="key-your-mailgun-key"
$env:ANYMAIL_MAILGUN_SENDER_DOMAIN="mg.yourdomain.com"
$env:DJANGO_DEFAULT_FROM_EMAIL="VendoraOps <no-reply@yourdomain.com>"
```
