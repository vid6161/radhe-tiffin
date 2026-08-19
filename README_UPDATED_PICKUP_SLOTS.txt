RADHE TIFFIN - GROUPED PICKUP SLOT UPDATE

This update adds the final customer pickup-page UX improvement:

1. When Pickup Location = All locations:
   - Neu-Ulm slots are grouped under a Neu-Ulm heading.
   - Ulm slots are grouped under an Ulm heading.
   - Each location shows its six standard 30-minute slots.

2. When Pickup Location = Neu-Ulm or Ulm:
   - Only that location's six slots are shown.
   - The location filter and slot count continue to work.

3. Selected slot clarity:
   - The selected slot displays a SELECTED badge.
   - The selection note shows location + exact pickup time + remaining capacity.

4. The existing fixed pickup-slot rules and capacity/order validation remain unchanged.

FILES INCLUDED:
- app.py
- database.py
- cleanup_pickup_slots.py
- templates/order.html
- templates/order_summary.html
- templates/order_confirmation.html
- templates/pickup_slots_admin.html

INSTALLATION:
1. Stop Flask with Ctrl+C.
2. Back up your current project/database.
3. Replace the corresponding files with these files.
4. Do NOT run cleanup_pickup_slots.py again if you already completed the cleanup.
5. Start the application:
   .\\venv\\Scripts\\python.exe app.py
6. Open:
   http://127.0.0.1:5000

TEST:
- Open a menu item for a date with pickup slots.
- Select All locations: expect Neu-Ulm group followed by Ulm group, 12 slots total.
- Select Neu-Ulm: expect 6 Neu-Ulm slots.
- Select Ulm: expect 6 Ulm slots.
- Select a slot: it should show SELECTED and the exact location/time in the note.
