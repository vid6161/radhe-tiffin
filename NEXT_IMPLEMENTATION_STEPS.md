# Radhe Tiffin — Implementation Status & Final Launch Steps

## Completed in this build

### 1. Weekly package selection
- 1 day/week: €12
- 2 days/week: €23
- 3 days/week: €34
- 4 days/week: €45
- 5 days/week: €55
- Added a single **Choose your package** dropdown.
- Selecting a package automatically selects the matching number of weekdays: Monday → Friday.
- Package cards and dropdown stay synchronized.
- Customers can change the automatically selected weekdays while keeping the required package count.
- The server still validates the exact package frequency and selected weekdays.
- Pickup location and pickup time remain consistent across the package.

### 2. Payments
- Cash on pickup.
- Bank transfer with order/package reference instructions.
- Stripe card checkout when `STRIPE_SECRET_KEY` is configured.
- Payment status and payment reference are stored.
- Success and cancellation pages are included.
- Stripe secrets remain environment variables.

### 3. Group catering
- Office Package: 20–49 people, estimated €10.50/person.
- Meeting Package: 50–79 people, estimated €10.00/person.
- Event Package: 80–100 people, estimated €9.50/person.
- Catering request captures date, location, people count, notes and payment preference.
- Final catering price remains subject to confirmation.
- Protected admin catering view is included.

### 4. Admin
- Protected admin login/logout.
- Orders and payment status.
- Weekly package orders are linked to the normal order system.
- Catering requests have a dedicated admin page.
- Menu management.
- Pickup-slot management and capacity validation.
- Dashboard revenue/unpaid overview.

### 5. Production preparation
- Gunicorn configuration.
- Render deployment configuration.
- Persistent SQLite path through `RADHE_DATABASE_PATH`.
- Environment-variable configuration for admin credentials, secret key, bank details, Stripe and public URL.
- Production launch documentation.

## Final items before the public launch

The application code is now prepared for deployment. The remaining launch items below require the business owner's real production accounts/details and cannot be safely invented in code.

### A. Business configuration — required
1. Replace placeholder bank account holder/IBAN/BIC with the real business details.
2. Set a strong production `RADHE_ADMIN_PASSWORD`.
3. Generate a new production `RADHE_SECRET_KEY`.
4. Set the final `PUBLIC_BASE_URL`.
5. Confirm the final weekly menu and prices.
6. Remove any test/sample customer orders before going live.

### B. Stripe — required only for online card payment
1. Create/configure the Stripe account.
2. Test with Stripe test keys first.
3. Set `STRIPE_SECRET_KEY` in the deployment environment only.
4. Verify one individual tiffin payment and one weekly-package payment.
5. Switch to the live Stripe key only after successful testing.

### C. Deployment
1. Push this project to the production repository.
2. Create the Render web service using `render.yaml`.
3. Configure all required environment variables.
4. Verify the persistent database disk is mounted.
5. Deploy with Gunicorn.
6. Connect the final custom domain.
7. Verify HTTPS.

### D. Final acceptance test
- Individual tiffin order: complete end-to-end.
- Weekly packages: test 1, 2, 3, 4 and 5 days/week.
- Confirm package dropdown automatically selects the correct number of days.
- Test both Ulm and Neu-Ulm.
- Test every pickup time.
- Test full pickup-slot rejection.
- Test cash payment.
- Test bank transfer flow.
- Test Stripe success and cancellation when configured.
- Test catering at 20, 49, 50, 79, 80 and 100 people.
- Test admin login and dashboard.
- Test menu and pickup-slot administration.
- Test mobile, tablet and desktop layouts.

## Optional future feature

### Recurring automatic weekly subscription
Automatic weekly renewal should be enabled only after the business defines cancellation/pause rules and the Stripe subscription workflow. The current build intentionally keeps weekly packages as one-time package orders so customers are not charged automatically without those business rules being finalized.
