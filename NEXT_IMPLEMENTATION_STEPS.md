# Radhe Tiffin — Next Implementation Steps

## Completed before payment
- [x] Individual tiffin ordering
- [x] Weekly packages with automatic weekday selection
- [x] Ulm and Neu-Ulm pickup locations
- [x] Six pickup slots from 12:00–15:00
- [x] Office / Meeting / Event catering for 20–100 people
- [x] Admin dashboard and order status controls
- [x] Finance & Excel business workbook
- [x] Revenue, expenses, salaries, usage/waste and monthly Profit & Loss sheets
- [x] Customer management with lifetime value and outstanding balance
- [x] Business settings for legal/contact/policy information
- [x] Allergen management for every active menu item
- [x] Customer-facing allergen information page
- [x] Privacy Policy / AGB / Impressum structure
- [x] Privacy + Terms acceptance recorded with customer orders
- [x] Optional marketing consent recorded separately
- [x] Admin backup download containing database + Excel workbook
- [x] Production health endpoint

## Required business data before launch
1. Enter the real business/legal details in **Admin → Settings**.
2. Enter and verify allergens against every recipe and supplier ingredient.
3. Complete the final Privacy Policy, Impressum and AGB with business-specific/legal-reviewed wording.
4. Enter the final weekly menu and prices.
5. Confirm pickup locations, capacities and times.
6. Enter real bank details in Render environment variables when bank transfer is enabled.
7. Test a complete customer order and verify the order appears in Admin and Excel.
8. Download and verify a backup before production.

## Payment / production stage — do only after the above
- Configure Stripe test mode and webhook.
- Verify cash, bank transfer and Stripe flows.
- Move Render from Free to a persistent production setup.
- Configure persistent storage / production database strategy.
- Add production environment secrets.
- Run final acceptance testing on the public HTTPS URL.

## Added in the latest build — Production Readiness
- Admin-only `/admin/production-readiness` checklist.
- Checks production secret/admin credentials, HTTPS URL, business identity, bank details, active menu, pickup capacity, database/Excel storage and optional Stripe configuration.
- Does not expose secret values.
- Added Production Readiness link to the Admin Dashboard.
- Existing acceptance-test workflow remains unchanged.
