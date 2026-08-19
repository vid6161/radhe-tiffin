"""
One-time cleanup for the Radhe Tiffin pickup-slot database.

What it does:
- keeps the standard 30-minute slots from 12:00 to 15:00
- deletes old invalid slots that have no orders
- disables old invalid slots that are referenced by existing orders
- creates any missing standard slots for active menu dates
- creates a timestamped database backup before changing anything

Run from the project folder:
    python cleanup_pickup_slots.py
"""

from datetime import datetime
from pathlib import Path
import shutil

from database import (
    DATABASE_PATH,
    init_db,
    normalize_pickup_slots,
)


def main():
    if DATABASE_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = DATABASE_PATH.with_name(
            f"database_backup_before_slot_cleanup_{stamp}.db"
        )
        shutil.copy2(DATABASE_PATH, backup_path)
        print(f"Backup created: {backup_path}")
    else:
        print("No existing database.db found. A new database will be initialized.")

    init_db()
    normalize_pickup_slots()

    from database import get_connection

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM pickup_slots
        WHERE is_active = 1
    """)
    active_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM pickup_slots
        WHERE is_active = 1
          AND NOT (
              start_time = '12:00' AND end_time = '12:30'
              OR start_time = '12:30' AND end_time = '13:00'
              OR start_time = '13:00' AND end_time = '13:30'
              OR start_time = '13:30' AND end_time = '14:00'
              OR start_time = '14:00' AND end_time = '14:30'
              OR start_time = '14:30' AND end_time = '15:00'
          )
    """)
    invalid_active_count = cursor.fetchone()["count"]

    connection.close()

    print(f"Active pickup slots after cleanup: {active_count}")
    print(f"Active invalid pickup slots: {invalid_active_count}")
    print("Cleanup complete.")


if __name__ == "__main__":
    main()
