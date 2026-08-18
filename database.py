import os
import sqlite3
from pathlib import Path


# ==================================================
# DATABASE LOCATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("RADHE_DATABASE_PATH", str(BASE_DIR / "database.db")))


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_connection():
    """
    Create and return a SQLite database connection.
    """

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ==================================================
# CREATE DATABASE TABLES
# ==================================================

def init_db():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------
    # CUSTOMERS
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            first_name TEXT NOT NULL,

            last_name TEXT NOT NULL,

            email TEXT NOT NULL,

            phone TEXT NOT NULL,

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------
    # MENU
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            menu_date TEXT NOT NULL,

            day_name TEXT NOT NULL,

            day_name_german TEXT NOT NULL,

            meal_name TEXT NOT NULL,

            price REAL NOT NULL,

            is_active INTEGER
                DEFAULT 1,

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------
    # MENU ITEMS
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            menu_id INTEGER NOT NULL,

            item_name TEXT NOT NULL,

            item_name_german TEXT,

            FOREIGN KEY (menu_id)
                REFERENCES menu(id)
                ON DELETE CASCADE
        )
    """)

    # --------------------------------------------------
    # PICKUP SLOTS
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pickup_slots (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            pickup_date TEXT NOT NULL,

            location TEXT NOT NULL,

            start_time TEXT NOT NULL,

            end_time TEXT NOT NULL,

            maximum_orders INTEGER
                DEFAULT 5,

            current_orders INTEGER
                DEFAULT 0,

            is_active INTEGER
                DEFAULT 1
        )
    """)

    # --------------------------------------------------
    # ORDERS
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_number TEXT UNIQUE NOT NULL,

            customer_id INTEGER NOT NULL,

            menu_id INTEGER NOT NULL,

            pickup_slot_id INTEGER,

            quantity INTEGER NOT NULL,

            pickup_location TEXT NOT NULL,

            pickup_date TEXT NOT NULL,

            pickup_time TEXT NOT NULL,

            total_amount REAL NOT NULL,

            status TEXT
                DEFAULT 'pending',

            payment_status TEXT
                DEFAULT 'unpaid',

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (customer_id)
                REFERENCES customers(id),

            FOREIGN KEY (menu_id)
                REFERENCES menu(id),

            FOREIGN KEY (pickup_slot_id)
                REFERENCES pickup_slots(id)
        )
    """)

    # --------------------------------------------------
    # ORDER ITEMS
    # --------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_id INTEGER NOT NULL,

            item_name TEXT NOT NULL,

            FOREIGN KEY (order_id)
                REFERENCES orders(id)
                ON DELETE CASCADE
        )
    """)

    # --------------------------------------------------
    # PRODUCTION / PAYMENT FIELDS
    # --------------------------------------------------
    cursor.execute("PRAGMA table_info(orders)")
    order_columns = {row["name"] for row in cursor.fetchall()}

    if "payment_method" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash'")

    if "payment_reference" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN payment_reference TEXT")

    if "package_id" not in order_columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN package_id INTEGER")

    # --------------------------------------------------
    # WEEKLY TIFFIN PACKAGES
    # --------------------------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL,
            frequency INTEGER NOT NULL,
            weekly_price REAL NOT NULL,
            pickup_location TEXT NOT NULL,
            pickup_time TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'cash',
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            payment_reference TEXT,
            status TEXT NOT NULL DEFAULT 'confirmed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS package_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id INTEGER NOT NULL,
            order_id INTEGER,
            menu_date TEXT NOT NULL,
            day_name TEXT NOT NULL,
            pickup_slot_id INTEGER,
            FOREIGN KEY (package_id) REFERENCES weekly_packages(id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
            FOREIGN KEY (pickup_slot_id) REFERENCES pickup_slots(id)
        )
    ''')

    # --------------------------------------------------
    # OFFICE / MEETING / EVENT CATERING REQUESTS
    # --------------------------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS catering_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL,
            package_type TEXT NOT NULL,
            people_count INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            location TEXT NOT NULL,
            service_notes TEXT,
            estimated_amount REAL NOT NULL,
            payment_method TEXT,
            payment_status TEXT NOT NULL DEFAULT 'quote_pending',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    ''')

    connection.commit()
    connection.close()


# ==================================================
# SEED / UPDATE WEEKLY MENU
# ==================================================

def seed_sample_menu():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------
    # Weekly menu
    #
    # These are currently sample dishes.
    # You can change these names later.
    # --------------------------------------------------

    weekly_menu = [

        {
            "date": "2026-08-17",
            "day": "Monday",
            "german_day": "Montag",
            "name": "Aloo Matar Tiffin",
            "price": 12.00,
            "items": [
                "2 Rotis",
                "Aloo Matar Sabji",
                "Dal",
                "Rice",
                "Fresh Salad"
            ]
        },

        {
            "date": "2026-08-18",
            "day": "Tuesday",
            "german_day": "Dienstag",
            "name": "Rajma Tiffin",
            "price": 12.00,
            "items": [
                "2 Rotis",
                "Rajma Masala",
                "Dal",
                "Rice",
                "Fresh Salad"
            ]
        },

        {
            "date": "2026-08-19",
            "day": "Wednesday",
            "german_day": "Mittwoch",
            "name": "Chole Tiffin",
            "price": 12.00,
            "items": [
                "2 Rotis",
                "Chole Masala",
                "Dal",
                "Rice",
                "Fresh Salad"
            ]
        },

        {
            "date": "2026-08-20",
            "day": "Thursday",
            "german_day": "Donnerstag",
            "name": "Paneer Tiffin",
            "price": 12.00,
            "items": [
                "2 Rotis",
                "Paneer Curry",
                "Dal",
                "Rice",
                "Fresh Salad"
            ]
        },

        {
            "date": "2026-08-21",
            "day": "Friday",
            "german_day": "Freitag",
            "name": "Aloo Gobi Tiffin",
            "price": 12.00,
            "items": [
                "2 Rotis",
                "Aloo Gobi Sabji",
                "Dal",
                "Rice",
                "Fresh Salad"
            ]
        }

    ]

    # --------------------------------------------------
    # Insert/update each day
    # --------------------------------------------------

    for menu in weekly_menu:

        cursor.execute("""
            SELECT id
            FROM menu
            WHERE menu_date = ?
            AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """, (menu["date"],))

        existing = cursor.fetchone()

        if existing:

            menu_id = existing["id"]

            # Check whether this menu is already used by an order.
            cursor.execute("""
                SELECT COUNT(*) AS order_count
                FROM orders
                WHERE menu_id = ?
            """, (menu_id,))

            order_count = cursor.fetchone()["order_count"]

            # --------------------------------------------------
            # If old menu has orders, don't modify its history.
            # Create a new menu record instead.
            # --------------------------------------------------

            if order_count > 0:

                cursor.execute("""
                    UPDATE menu
                    SET is_active = 0
                    WHERE id = ?
                """, (menu_id,))

                cursor.execute("""
                    INSERT INTO menu (
                        menu_date,
                        day_name,
                        day_name_german,
                        meal_name,
                        price,
                        is_active
                    )
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (
                    menu["date"],
                    menu["day"],
                    menu["german_day"],
                    menu["name"],
                    menu["price"]
                ))

                menu_id = cursor.lastrowid

            else:

                cursor.execute("""
                    UPDATE menu
                    SET
                        day_name = ?,
                        day_name_german = ?,
                        meal_name = ?,
                        price = ?,
                        is_active = 1
                    WHERE id = ?
                """, (
                    menu["day"],
                    menu["german_day"],
                    menu["name"],
                    menu["price"],
                    menu_id
                ))

                # Remove old items.
                cursor.execute("""
                    DELETE FROM menu_items
                    WHERE menu_id = ?
                """, (menu_id,))

        else:

            cursor.execute("""
                INSERT INTO menu (
                    menu_date,
                    day_name,
                    day_name_german,
                    meal_name,
                    price,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                menu["date"],
                menu["day"],
                menu["german_day"],
                menu["name"],
                menu["price"]
            ))

            menu_id = cursor.lastrowid

        # --------------------------------------------------
        # Insert menu items
        # --------------------------------------------------

        for item in menu["items"]:

            cursor.execute("""
                INSERT INTO menu_items (
                    menu_id,
                    item_name
                )
                VALUES (?, ?)
            """, (
                menu_id,
                item
            ))

    connection.commit()
    connection.close()


# ==================================================
# CREATE PICKUP SLOTS
# ==================================================

def seed_pickup_slots():

    connection = get_connection()
    cursor = connection.cursor()

    locations = [
        "Ulm",
        "Neu-Ulm"
    ]

    time_slots = [

        ("12:00", "12:30"),
        ("12:30", "13:00"),
        ("13:00", "13:30"),
        ("13:30", "14:00"),
        ("14:00", "14:30"),
        ("14:30", "15:00")

    ]

    dates = [

        "2026-08-17",
        "2026-08-18",
        "2026-08-19",
        "2026-08-20",
        "2026-08-21"

    ]

    for pickup_date in dates:

        for location in locations:

            for start_time, end_time in time_slots:

                cursor.execute("""
                    SELECT id
                    FROM pickup_slots
                    WHERE pickup_date = ?
                    AND location = ?
                    AND start_time = ?
                    AND end_time = ?
                """, (
                    pickup_date,
                    location,
                    start_time,
                    end_time
                ))

                existing = cursor.fetchone()

                if existing:
                    continue

                cursor.execute("""
                    INSERT INTO pickup_slots (
                        pickup_date,
                        location,
                        start_time,
                        end_time,
                        maximum_orders,
                        current_orders,
                        is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pickup_date,
                    location,
                    start_time,
                    end_time,
                    5,
                    0,
                    1
                ))

    connection.commit()
    connection.close()


# ==================================================
# NORMALIZE PICKUP SLOTS
# ==================================================

STANDARD_PICKUP_SLOTS = (
    ("12:00", "12:30"),
    ("12:30", "13:00"),
    ("13:00", "13:30"),
    ("13:30", "14:00"),
    ("14:00", "14:30"),
    ("14:30", "15:00"),
)

PICKUP_LOCATIONS = ("Ulm", "Neu-Ulm")


def normalize_pickup_slots():
    """Clean invalid test slots without deleting booked order history."""
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT DISTINCT pickup_date FROM pickup_slots")
        dates = {row["pickup_date"] for row in cursor.fetchall()}

        cursor.execute("SELECT DISTINCT menu_date FROM menu WHERE is_active = 1")
        dates.update(row["menu_date"] for row in cursor.fetchall())

        cursor.execute("""
            SELECT id, location, start_time, end_time, current_orders
            FROM pickup_slots
        """)
        for row in cursor.fetchall():
            valid = (
                row["location"] in PICKUP_LOCATIONS
                and (row["start_time"], row["end_time"]) in STANDARD_PICKUP_SLOTS
            )

            if valid:
                continue

            cursor.execute("""
                SELECT COUNT(*) AS order_count
                FROM orders
                WHERE pickup_slot_id = ?
                  AND status != 'cancelled'
            """, (row["id"],))
            active_order_count = cursor.fetchone()["order_count"]

            has_history = (row["current_orders"] or 0) > 0 or active_order_count > 0

            if has_history:
                cursor.execute(
                    "UPDATE pickup_slots SET is_active = 0 WHERE id = ?",
                    (row["id"],),
                )
            else:
                cursor.execute(
                    "DELETE FROM pickup_slots WHERE id = ?",
                    (row["id"],),
                )

        for pickup_date in sorted(dates):
            for location in PICKUP_LOCATIONS:
                for start_time, end_time in STANDARD_PICKUP_SLOTS:
                    cursor.execute("""
                        SELECT id FROM pickup_slots
                        WHERE pickup_date = ? AND location = ?
                          AND start_time = ? AND end_time = ?
                        LIMIT 1
                    """, (pickup_date, location, start_time, end_time))

                    if cursor.fetchone():
                        continue

                    cursor.execute("""
                        INSERT INTO pickup_slots (
                            pickup_date, location, start_time, end_time,
                            maximum_orders, current_orders, is_active
                        )
                        VALUES (?, ?, ?, ?, 5, 0, 1)
                    """, (pickup_date, location, start_time, end_time))

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# ==================================================
# RUN DATABASE INITIALIZATION
# ==================================================

if __name__ == "__main__":

    init_db()

    seed_sample_menu()

    seed_pickup_slots()
    normalize_pickup_slots()

    print()
    print("======================================")
    print("Radhe Tiffin database initialized!")
    print("======================================")
    print()
    print("Database location:")
    print(DATABASE_PATH)
    print()