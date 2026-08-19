# Radhe Tiffin — Production Launch Guide

## Before payment setup
Complete the following from the Admin area:

- **Business Settings:** legal name, owner, address, contact, VAT/tax information, pickup and cancellation policies.
- **Menu:** final dishes and prices.
- **Allergens:** verify allergens for every active menu item against the real recipe.
- **Customers:** review customer records and balances.
- **Finance & Excel:** enter expenses, salaries and ingredient usage/waste.
- **Backup:** download a database + Excel backup before production.

The generated Excel workbook contains:

- Dashboard
- Orders
- Revenue
- Expenses
- Salaries
- Usage
- Profit & Loss
- Catering
- Packages
- Customers
- Menu
- Pickup Slots
- Allergens
- Business Settings

## Customer safeguards
Orders and catering requests require acceptance of the Privacy Policy and Terms & Conditions. Optional marketing consent is stored separately.

## Important
The legal pages are templates and must be completed/reviewed for the actual business. Allergen data must be verified against the actual recipes and ingredients. The Excel workbook is an operational management report and is not a substitute for formal tax/accounting records.

## Payment stage
After all non-payment items are complete, configure Stripe test mode, webhook secrets and final payment settings. Then configure Render production persistence and run final acceptance tests.
