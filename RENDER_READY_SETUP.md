# Radhe Foods — Render Ready Setup

## Business identity
- Business / legal name: Radhe Foods
- Owners: Viraj Desai & Saptamita Paul Choudhury
- Neu-Ulm: Petrusplatz 3, 89231 Neu-Ulm
- Ulm: Bahnhofstraße 1, 89073 Ulm
- Phone: +4917634660247

## Bank transfer
- Account holder: Viraj Desai
- IBAN: DE98721500000054409073
- BIC: BYLADEM1ING

## Allergy coverage
- Normal tiffin: overall customer allergy selection is stored on the order and cross-checked against verified dish allergens in Admin.
- Weekly package: overall customer allergy selection is copied to every daily order, so Admin can identify affected dishes for each selected day.
- Catering: overall customer allergy selection is stored on the catering request and shown to Admin. It is request-level only because the final catering menu is confirmed later.

## Render variables
Set in Render:
- RADHE_SECRET_KEY: new long random secret
- RADHE_ADMIN_USERNAME: admin username
- RADHE_ADMIN_PASSWORD: new strong admin password
- PUBLIC_BASE_URL: final HTTPS Render URL
- RADHE_DATABASE_PATH: /var/data/database.db
- RADHE_EXCEL_PATH: /var/data/RadheTiffin_Business.xlsx
- RADHE_BANK_ACCOUNT_HOLDER: Viraj Desai
- RADHE_BANK_IBAN: DE98721500000054409073
- RADHE_BANK_BIC: BYLADEM1ING

Leave Stripe variables unset until card payments are intentionally enabled.

## Final launch sequence
1. Deploy to Render with the included render.yaml.
2. Add the environment variables above.
3. Confirm the persistent disk is mounted at /var/data.
4. Open /health and confirm status=ok.
5. Open Admin → Production Readiness.
6. Business email is configured as radhefoods123@gmail.com. Add any VAT/tax information if applicable.
7. Verify every active dish allergen against the real recipe.
8. Run the final acceptance test.
9. Only then switch the final domain/public URL and announce ordering.

## Local startup without repeated PowerShell environment commands
The application now has stable local-development defaults for the admin username/password and Flask secret. You can start it directly with:

```powershell
.\\venv\\Scripts\\python.exe app.py
```

You no longer need to set `RADHE_ADMIN_USERNAME`, `RADHE_ADMIN_PASSWORD`, or `RADHE_SECRET_KEY` in PowerShell for every local run. Environment variables still override the local defaults when supplied, and Render should use its own production environment variables.

The admin login page remains enabled for security. Because the local Flask secret is now stable, the permanent admin session can survive application restarts in the same browser unless the browser cookies are cleared or the session expires.
