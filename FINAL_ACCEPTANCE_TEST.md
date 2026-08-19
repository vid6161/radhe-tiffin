# Radhe Tiffin — Final Acceptance Test

The project includes an automated end-to-end acceptance test at:

`tests/final_acceptance_test.py`

## What it tests

1. Customer order page loads.
2. Customer allergy/intolerance section is present.
3. Dish-level verified allergens are configured for a test scenario.
4. Customer places a complete cash order with an overall Milk allergy request.
5. Customer confirmation contains the allergy request.
6. Order and allergy request are stored in SQLite.
7. Pickup-slot capacity increases after the order.
8. Admin login works.
9. Admin Order Dashboard shows the customer allergy and affected dishes.
10. Customer record is created.
11. Finance dashboard reflects the order.
12. Excel export contains the order.
13. Weekly package page exposes the customer allergy controls.
14. Weekly package selection automatically selects the required number of weekdays.
15. Weekly package allergy request is shown in the summary/confirmation and persisted to each generated package-day order.
16. Catering page exposes customer allergy controls.
17. Catering allergy requests are stored with the catering request.
18. Admin Catering shows the customer-reported allergy warning and requested allergens.
19. Admin can mark the individual order paid.
20. Admin can mark the order ready.
21. Cancelling the order releases pickup capacity.
22. `/health` returns a healthy response.

## Run it locally

From the `RadheTiffin` project directory:

```bash
python tests/final_acceptance_test.py
```

The test uses a temporary SQLite database, so it does **not** modify the real business database.

A successful run ends with:

```text
ACCEPTANCE TEST PASSED
Customer → Order → Allergy → Packages → Catering → Admin → Finance → Excel → Status → Capacity: OK
```

## Important production checks still required

The acceptance test validates application behavior. Before going live, still enter and verify the real business/legal information, final menu and recipes, allergen information, pickup capacities, bank details, legal pages, production secrets, persistent database/storage, and payment provider configuration.
