# Radhe Tiffin — Production Launch

## New customer features

### Weekly packages
- 1 day/week: €12
- 2 days/week: €23
- 3 days/week: €34
- 4 days/week: €45
- 5 days/week: €55

The 5-day package saves €5 compared with five €12 individual tiffins.

Customers select the exact weekdays, pickup location and one recurring pickup time. The system checks capacity for every selected day and reserves one tiffin on each day.

### Group catering
- Office Package: 20–49 people, estimated €10.50/person
- Meeting Package: 50–79 people, estimated €10.00/person
- Event Package: 80–100 people, estimated €9.50/person

Group catering is a quote workflow. The customer submits event details and the request appears in the protected admin catering page. The displayed price is an estimate; final logistics and pricing are confirmed before payment.

### Payments
- Cash on pickup
- Bank transfer
- Stripe card checkout when `STRIPE_SECRET_KEY` is configured

Stripe is optional. Never put a Stripe secret key in source code. Use the environment variable.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:RADHE_ADMIN_USERNAME="admin"
$env:RADHE_ADMIN_PASSWORD="choose-a-strong-password"
$env:RADHE_SECRET_KEY="choose-a-long-random-secret"
python app.py
```

Open `http://127.0.0.1:5000`.

## Render

The included `render.yaml` uses Gunicorn and a persistent disk for SQLite.

Set:
- `RADHE_ADMIN_USERNAME`
- `RADHE_ADMIN_PASSWORD`
- `PUBLIC_BASE_URL`
- `RADHE_BANK_ACCOUNT_HOLDER`
- `RADHE_BANK_IBAN`
- `RADHE_BANK_BIC`
- `STRIPE_SECRET_KEY` if online payments are required

For a custom domain, point the domain to the Render service and enable HTTPS.

## Important payment note

Do not use placeholder bank details in production. Replace them with the real business bank information.

For Stripe, use test keys first, complete a full test order, and only then switch to the live key.

## Database

The application automatically adds the payment/package/catering tables and columns when it starts. Keep a backup of `database.db` before the first production deployment.

## Existing features retained

The existing menu, pickup slots, capacity validation, customer ordering, admin dashboard, menu management and pickup-slot management remain part of the application.
