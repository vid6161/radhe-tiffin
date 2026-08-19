import os
import secrets
import io
import zipfile

try:
    import stripe
except ImportError:
    stripe = None

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    flash,
)
from database import (
    init_db,
    seed_sample_menu,
    seed_pickup_slots,
    get_connection,
)
from datetime import datetime, date
from urllib.parse import urlparse
from excel_reports import generate_excel_workbook, EXCEL_PATH


# ==================================================
# PICKUP SLOT RULES
# ==================================================
# Fixed customer-facing schedule: six 30-minute slots from 12:00 to 15:00.
PICKUP_LOCATIONS = ("Ulm", "Neu-Ulm")
STANDARD_PICKUP_SLOTS = (
    ("12:00", "12:30"),
    ("12:30", "13:00"),
    ("13:00", "13:30"),
    ("13:30", "14:00"),
    ("14:00", "14:30"),
    ("14:30", "15:00"),
)

app = Flask(__name__)

# ==================================================
# ADMIN AUTHENTICATION CONFIGURATION
# ==================================================
# You can override these with environment variables:
# RADHE_SECRET_KEY
# RADHE_ADMIN_USERNAME
# RADHE_ADMIN_PASSWORD

# Local defaults are provided so the app can be started directly with
# `python app.py` without re-entering PowerShell environment variables on
# every run. Render/production environment variables still take precedence.
LOCAL_SECRET_KEY = "RadheTiffin-Local-Secret-Change-Before-Production-2026"
LOCAL_ADMIN_USERNAME = "admin"
LOCAL_ADMIN_PASSWORD = "RadheTiffin@2026#Admin"

app.secret_key = os.environ.get("RADHE_SECRET_KEY", LOCAL_SECRET_KEY).strip()

ADMIN_USERNAME = os.environ.get(
    "RADHE_ADMIN_USERNAME",
    LOCAL_ADMIN_USERNAME,
).strip() or LOCAL_ADMIN_USERNAME

ADMIN_PASSWORD = os.environ.get(
    "RADHE_ADMIN_PASSWORD",
    LOCAL_ADMIN_PASSWORD,
).strip() or LOCAL_ADMIN_PASSWORD

# IMPORTANT: For Render/production, set RADHE_SECRET_KEY and
# RADHE_ADMIN_PASSWORD in the service environment and use strong, unique
# production values. The built-in values above are only a convenience for
# local development so `python app.py` works immediately.

# ==================================================
# PAYMENT CONFIGURATION
# ==================================================
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "http://127.0.0.1:5000",
).rstrip("/")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

# Harden browser sessions automatically on HTTPS production deployments.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PUBLIC_BASE_URL.startswith("https://"),
)

BANK_ACCOUNT_HOLDER = os.environ.get(
    "RADHE_BANK_ACCOUNT_HOLDER",
    "Viraj Desai",
)
BANK_IBAN = os.environ.get(
    "RADHE_BANK_IBAN",
    "DE98721500000054409073",
)
BANK_BIC = os.environ.get(
    "RADHE_BANK_BIC",
    "BYLADEM1ING",
)

if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

PAYMENT_METHODS = {
    "cash": {
        "label": "Cash on pickup",
        "description": "Pay when you collect your tiffin.",
    },
    "bank_transfer": {
        "label": "Bank transfer",
        "description": "Transfer the amount before pickup using the bank details shown after ordering.",
    },
}
if stripe and STRIPE_SECRET_KEY:
    PAYMENT_METHODS["stripe"] = {
        "label": "Card / online payment",
        "description": "Secure checkout powered by Stripe.",
    }

# Weekly package prices are the total price for one tiffin on each
# selected day. The 5-day package is €55 instead of €60.
WEEKLY_PACKAGE_PRICES = {
    1: 12.00,
    2: 23.00,
    3: 34.00,
    4: 45.00,
    5: 55.00,
}

CATERING_PACKAGES = {
    "office": {
        "label": "Office Package",
        "min_people": 20,
        "max_people": 49,
        "price_per_person": 10.50,
    },
    "meeting": {
        "label": "Meeting Package",
        "min_people": 50,
        "max_people": 79,
        "price_per_person": 10.00,
    },
    "event": {
        "label": "Event Package",
        "min_people": 80,
        "max_people": 100,
        "price_per_person": 9.50,
    },
}

# ==================================================
# PROTECT ALL ADMIN ROUTES
# ==================================================

@app.before_request
def require_admin_login():
    """Require authentication for every /admin route except login/logout."""

    if not request.path.startswith("/admin"):
        return None

    if request.endpoint in {
        "admin_login",
        "admin_logout",
    }:
        return None

    if session.get("admin_logged_in"):
        return None

    next_url = request.full_path

    if next_url.endswith("?"):
        next_url = next_url[:-1]

    return redirect(
        url_for(
            "admin_login",
            next=next_url
        )
    )


# ==================================================
# ADMIN LOGIN
# ==================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    error = None

    next_url = request.args.get(
        "next",
        request.form.get("next", "/admin")
    )

    # Only allow local application paths.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/admin"

    if request.method == "POST":
        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        username_ok = secrets.compare_digest(
            username,
            ADMIN_USERNAME
        )

        password_ok = secrets.compare_digest(
            password,
            ADMIN_PASSWORD
        )

        if username_ok and password_ok:
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username
            session.permanent = True

            return redirect(next_url)

        error = "Incorrect username or password."

    return render_template(
        "admin_login.html",
        error=error,
        next_url=next_url
    )


# ==================================================
# ADMIN LOGOUT
# ==================================================

@app.route("/admin/logout", methods=["POST"])
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ==================================================
# INITIALIZE DATABASE
# ==================================================
init_db()
seed_sample_menu()
seed_pickup_slots()


# ==================================================
# HELPERS
# ==================================================

def safe_next_url(value):
    """Allow only local relative redirects."""
    if not value:
        return None

    parsed = urlparse(value)

    if parsed.scheme or parsed.netloc:
        return None

    if not value.startswith("/"):
        return None

    return value


def get_menu():
    """
    Load active menus from the database.

    Each menu contains:
        id, date, day, german_day, name, price, items
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            menu_date,
            day_name,
            day_name_german,
            meal_name,
            price
        FROM menu
        WHERE is_active = 1
        ORDER BY menu_date ASC
    """)

    menu_rows = cursor.fetchall()
    menu = {}

    for row in menu_rows:
        cursor.execute("""
            SELECT id, item_name, item_name_german
            FROM menu_items
            WHERE menu_id = ?
            ORDER BY id ASC
        """, (row["id"],))

        item_rows = cursor.fetchall()
        items = [item["item_name"] for item in item_rows]
        items_with_allergens = []
        for item in item_rows:
            allergen_rows = cursor.execute("SELECT allergen_code FROM menu_item_allergens WHERE menu_item_id=? ORDER BY allergen_code", (item["id"],)).fetchall()
            items_with_allergens.append({
                "name": item["item_name"],
                "allergens": [r["allergen_code"] for r in allergen_rows],
            })

        day_key = row["day_name"].lower()

        menu[day_key] = {
            "id": row["id"],
            "date": row["menu_date"],
            "day": row["day_name"],
            "german_day": row["day_name_german"],
            "name": row["meal_name"],
            "price": row["price"],
            "items": items,
            "items_with_allergens": items_with_allergens,
        }

    connection.close()
    return menu


def get_pickup_slots(pickup_date, active_only=True):
    connection = get_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            id,
            pickup_date,
            location,
            start_time,
            end_time,
            maximum_orders,
            current_orders,
            is_active
        FROM pickup_slots
        WHERE pickup_date = ?
    """

    params = [pickup_date]

    if active_only:
        query += " AND is_active = 1 "

    query += """
        ORDER BY
            location ASC,
            start_time ASC
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    connection.close()
    return rows


def get_all_pickup_slots():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            pickup_date,
            location,
            start_time,
            end_time,
            maximum_orders,
            current_orders,
            is_active
        FROM pickup_slots
        ORDER BY
            pickup_date ASC,
            location ASC,
            start_time ASC
    """)

    rows = cursor.fetchall()
    connection.close()
    return rows


def parse_pickup_time(value):
    """
    Accept:
        12:30–13:00 Uhr
        12:30-13:00
        12:30 – 13:00
    """
    if not value:
        return None, None

    normalized = (
        value.replace(" Uhr", "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    if "-" not in normalized:
        return None, None

    start_time, end_time = [
        part.strip()
        for part in normalized.split("-", 1)
    ]

    if not start_time or not end_time:
        return None, None

    return start_time, end_time


def normalize_pickup_date(value):
    """
    Normalize pickup dates to the database format YYYY-MM-DD.

    Accepts:
        YYYY-MM-DD
        DD/MM/YYYY
        DD.MM.YYYY
    """
    value = (value or "").strip()

    if not value:
        return ""

    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(
                value,
                date_format,
            ).date().isoformat()
        except ValueError:
            continue

    return value


def validate_slot_values(pickup_date, location, start_time, end_time, maximum_orders):
    if not pickup_date:
        return "Pickup date is required."

    if location not in PICKUP_LOCATIONS:
        return "Invalid pickup location."

    if (start_time, end_time) not in STANDARD_PICKUP_SLOTS:
        return (
            "Invalid pickup time. Choose one of the standard 30-minute "
            "pickup slots between 12:00 and 15:00."
        )

    try:
        maximum_orders = int(maximum_orders)
    except (TypeError, ValueError):
        return "Maximum capacity must be a whole number."

    if maximum_orders < 1 or maximum_orders > 500:
        return "Maximum capacity must be between 1 and 500."

    return None


def normalize_pickup_slots():
    """Clean old invalid/test slots while preserving booked order history."""
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


# Normalize/repair existing pickup slots once the helper is defined.
normalize_pickup_slots()

# Create the business workbook on startup. The workbook is an automatically
# regenerated Excel-compatible snapshot of the website database.
try:
    generate_excel_workbook()
except Exception as error:
    print("EXCEL WORKBOOK INITIALIZATION WARNING:", error)


# ==================================================
# AUTOMATIC EXCEL REFRESH
# ==================================================

@app.after_request
def refresh_business_workbook(response):
    # Any POST can change business data (orders, catering, admin changes,
    # finance entries, etc.). Refresh the workbook after successful requests.
    if request.method == "POST" and response.status_code < 400:
        try:
            generate_excel_workbook()
        except Exception as error:
            print("EXCEL WORKBOOK REFRESH WARNING:", error)
    return response


# ==================================================
# HOME PAGE
# ==================================================

@app.route("/")
def home():
    menu = get_menu()

    return render_template(
        "index.html",
        menu=menu,
    )


# ==================================================
# ORDER PAGE
# ==================================================

@app.route("/order/<day>")
def order(day):
    menu = get_menu()

    if day not in menu:
        return "Menu item not found", 404

    selected_menu = menu[day]
    pickup_slots = get_pickup_slots(selected_menu["date"], active_only=True)
    pickup_locations = sorted({slot["location"] for slot in pickup_slots})

    return render_template(
        "order.html",
        item=selected_menu,
        day_key=day,
        pickup_slots=pickup_slots,
        pickup_locations=pickup_locations,
        payment_methods=PAYMENT_METHODS,
        customer_allergens=ALLERGENS,
    )

# ==================================================
# ORDER SUMMARY
# ==================================================

@app.route(
    "/order/<day>/summary",
    methods=["POST"],
)
def order_summary(day):
    menu = get_menu()

    if day not in menu:
        return "Menu item not found", 404

    selected_menu = menu[day]

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    payment_method = request.form.get("payment_method", "cash").strip().lower()
    privacy_consent = request.form.get("privacy_consent") == "1"
    terms_accepted = request.form.get("terms_accepted") == "1"
    marketing_consent = request.form.get("marketing_consent") == "1"
    customer_allergens = [
        code for code in request.form.getlist("customer_allergens")
        if code in ALLERGENS
    ]

    if not privacy_consent or not terms_accepted:
        return "Please accept the Privacy Policy and Terms & Conditions before continuing.", 400

    if payment_method not in PAYMENT_METHODS:
        return "Invalid payment method.", 400

    try:
        quantity = int(request.form.get("quantity", 1))
        pickup_slot_id = int(request.form.get("pickup_slot_id", ""))
    except (TypeError, ValueError):
        return "Invalid order details", 400

    if not first_name or not last_name or not email or not phone:
        return "All customer details are required.", 400

    if quantity < 1 or quantity > 20:
        return "Invalid quantity", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT id, pickup_date, location, start_time, end_time,
                   maximum_orders, current_orders, is_active
            FROM pickup_slots
            WHERE id = ?
              AND pickup_date = ?
              AND is_active = 1
            LIMIT 1
        """, (pickup_slot_id, selected_menu["date"]))
        slot = cursor.fetchone()

        if slot is None:
            return "The selected pickup slot is no longer available.", 400

        remaining = slot["maximum_orders"] - slot["current_orders"]
        if quantity > remaining:
            return "The selected pickup slot does not have enough remaining capacity.", 400

        pickup_time = f'{slot["start_time"]}–{slot["end_time"]} Uhr'
        total = quantity * selected_menu["price"]
        allergen_items, allergen_summary = get_menu_allergen_summary(selected_menu)

        return render_template(
            "order_summary.html",
            item=selected_menu,
            quantity=quantity,
            location=slot["location"],
            pickup_time=pickup_time,
            pickup_date=selected_menu["date"],
            pickup_slot_id=slot["id"],
            total=total,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            payment_method=payment_method,
            payment_method_label=PAYMENT_METHODS[payment_method]["label"],
            privacy_consent=privacy_consent,
            terms_accepted=terms_accepted,
            marketing_consent=marketing_consent,
            bank_account_holder=BANK_ACCOUNT_HOLDER,
            bank_iban=BANK_IBAN,
            bank_bic=BANK_BIC,
            day_key=day,
            allergen_items=allergen_items,
            allergen_summary=allergen_summary,
            customer_allergens=customer_allergens,
            customer_allergen_labels=[ALLERGENS[c] for c in customer_allergens],
        )
    finally:
        connection.close()

# ==================================================
# PLACE ORDER
# ==================================================

@app.route(
    "/order/<day>/place-order",
    methods=["POST"],
)
def place_order(day):
    menu = get_menu()

    if day not in menu:
        return "Menu item not found", 404

    selected_menu = menu[day]

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    payment_method = request.form.get("payment_method", "cash").strip().lower()
    privacy_consent = request.form.get("privacy_consent") == "1"
    terms_accepted = request.form.get("terms_accepted") == "1"
    marketing_consent = request.form.get("marketing_consent") == "1"
    customer_allergens = [
        code for code in request.form.getlist("customer_allergens")
        if code in ALLERGENS
    ]

    if not privacy_consent or not terms_accepted:
        return "Please accept the Privacy Policy and Terms & Conditions before placing the order.", 400

    if payment_method not in PAYMENT_METHODS:
        return "Invalid payment method.", 400

    try:
        quantity = int(request.form.get("quantity", 1))
        pickup_slot_id = int(request.form.get("pickup_slot_id", ""))
    except (TypeError, ValueError):
        return "Invalid order details", 400

    if not first_name or not last_name or not email or not phone:
        return "All customer details are required.", 400

    if quantity < 1 or quantity > 20:
        return "Invalid quantity", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT id, pickup_date, location, start_time, end_time,
                   maximum_orders, current_orders, is_active
            FROM pickup_slots
            WHERE id = ?
              AND pickup_date = ?
              AND is_active = 1
            LIMIT 1
        """, (pickup_slot_id, selected_menu["date"]))
        pickup_slot = cursor.fetchone()

        if pickup_slot is None:
            connection.rollback()
            return "The selected pickup slot is no longer available.", 400

        # Reserve capacity atomically. Quantity is the number of tiffins.
        cursor.execute("""
            UPDATE pickup_slots
            SET current_orders = current_orders + ?
            WHERE id = ?
              AND is_active = 1
              AND current_orders + ? <= maximum_orders
        """, (quantity, pickup_slot_id, quantity))

        if cursor.rowcount != 1:
            connection.rollback()
            return "Sorry, this pickup slot does not have enough remaining capacity.", 400

        location = pickup_slot["location"]
        pickup_date = pickup_slot["pickup_date"]
        pickup_time = f'{pickup_slot["start_time"]}–{pickup_slot["end_time"]} Uhr'
        total = quantity * selected_menu["price"]

        cursor.execute("""
            INSERT INTO customers (first_name, last_name, email, phone, privacy_consent_at, terms_accepted_at, marketing_consent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (first_name, last_name, email, phone, datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds"), int(marketing_consent)))
        customer_id = cursor.lastrowid

        order_number = (
            "RT-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(customer_id)
        )

        cursor.execute("""
            INSERT INTO orders (
                order_number, customer_id, menu_id, pickup_slot_id, quantity,
                pickup_location, pickup_date, pickup_time, total_amount,
                status, payment_status, payment_method
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_number, customer_id, selected_menu["id"], pickup_slot_id, quantity,
            location, pickup_date, pickup_time, total, "confirmed", "unpaid",
            payment_method
        ))

        order_id = cursor.lastrowid

        for allergen_code in customer_allergens:
            cursor.execute("""
                INSERT INTO order_allergen_requests (order_id, allergen_code)
                VALUES (?, ?)
            """, (order_id, allergen_code))

        for food in selected_menu["items"]:
            cursor.execute("""
                INSERT INTO order_items (order_id, item_name)
                VALUES (?, ?)
            """, (order_id, food))

        connection.commit()

    except Exception as error:
        connection.rollback()
        print("ORDER DATABASE ERROR:", error)
        return "There was a problem saving your order. Please try again.", 500
    finally:
        connection.close()

    payment_url = None
    if payment_method == "stripe":
        try:
            checkout = stripe.checkout.Session.create(
                mode="payment",
                automatic_payment_methods={"enabled": True},
                customer_email=email,
                line_items=[{
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"{selected_menu['name']} — Radhe Tiffin",
                        },
                        "unit_amount": int(round(total * 100)),
                    },
                    "quantity": 1,
                }],
                metadata={"order_number": order_number},
                success_url=f"{PUBLIC_BASE_URL}/payment/success?order_number={order_number}&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{PUBLIC_BASE_URL}/payment/cancel?order_number={order_number}",
            )
            payment_url = checkout.url

            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE orders SET payment_status='pending', payment_reference=? WHERE order_number=?",
                (checkout.id, order_number),
            )
            connection.commit()
            connection.close()

        except Exception as error:
            print("STRIPE CHECKOUT ERROR:", error)
            payment_url = None

    allergen_items, allergen_summary = get_menu_allergen_summary(selected_menu)

    return render_template(
        "order_confirmation.html",
        order_number=order_number,
        item=selected_menu,
        quantity=quantity,
        location=location,
        pickup_time=pickup_time,
        pickup_date=pickup_date,
        total=total,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        payment_method=payment_method,
        payment_method_label=PAYMENT_METHODS[payment_method]["label"],
        payment_status="pending" if payment_method == "stripe" and payment_url else "unpaid",
        payment_url=payment_url,
        bank_account_holder=BANK_ACCOUNT_HOLDER,
        bank_iban=BANK_IBAN,
        bank_bic=BANK_BIC,
        allergen_items=allergen_items,
        allergen_summary=allergen_summary,
        customer_allergen_labels=[ALLERGENS[c] for c in customer_allergens],
    )


# ==================================================
# WEEKLY TIFFIN PACKAGES
# ==================================================

@app.route("/packages")
def packages():
    # Use the same de-duplicated weekly menu source as the home page.
    # This prevents old/duplicate active database rows from rendering the
    # same weekday multiple times on the package page.
    weekly_menu = get_menu()
    weekday_order = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    menus = [weekly_menu[day] for day in weekday_order if day in weekly_menu]
    package_allergens = []
    for menu_data in menus:
        _, labels = get_menu_allergen_summary(menu_data)
        package_allergens.extend(labels)
    package_allergens = list(dict.fromkeys(package_allergens))

    return render_template(
        "packages.html",
        menus=menus,
        package_prices=WEEKLY_PACKAGE_PRICES,
        payment_methods=PAYMENT_METHODS,
        package_allergens=package_allergens,
    )


@app.route("/packages/summary", methods=["POST"])
def package_summary():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    location = request.form.get("location", "").strip()
    pickup_time = request.form.get("pickup_time", "").strip()
    requested_days = {day.strip().lower() for day in request.form.getlist("days") if day.strip()}
    weekday_order = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    selected_days = [day.capitalize() for day in weekday_order if day in requested_days]
    customer_allergens = [code for code in request.form.getlist("customer_allergens") if code in ALLERGENS]

    try:
        frequency = int(request.form.get("frequency", "0"))
    except ValueError:
        return "Invalid package frequency.", 400

    if frequency not in WEEKLY_PACKAGE_PRICES:
        return "Please choose a package from 1 to 5 days per week.", 400

    if len(selected_days) != frequency:
        return f"Please select exactly {frequency} day(s) per week.", 400

    privacy_consent = request.form.get("privacy_consent") == "1"
    terms_accepted = request.form.get("terms_accepted") == "1"
    marketing_consent = request.form.get("marketing_consent") == "1"
    if not privacy_consent or not terms_accepted:
        return "Please accept the Privacy Policy and Terms & Conditions before continuing.", 400

    if not first_name or not last_name or not email or not phone:
        return "All customer details are required.", 400

    if location not in PICKUP_LOCATIONS:
        return "Invalid pickup location.", 400

    start_time, end_time = parse_pickup_time(pickup_time)
    if (start_time, end_time) not in STANDARD_PICKUP_SLOTS:
        return "Please select a valid pickup time.", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        menus = []
        weekly_menu = get_menu()
        for day in selected_days:
            menu_data = weekly_menu.get(day.lower())
            if menu_data is None:
                return f"No active menu is available for {day}.", 400

            cursor.execute("""
                SELECT id, pickup_date, location, start_time, end_time,
                       maximum_orders, current_orders
                FROM pickup_slots
                WHERE pickup_date = ?
                  AND location = ?
                  AND start_time = ?
                  AND end_time = ?
                  AND is_active = 1
                LIMIT 1
            """, (menu_data["date"], location, start_time, end_time))
            slot = cursor.fetchone()
            if slot is None:
                return f"The selected pickup time is unavailable for {menu_data['day']}.", 400

            remaining = slot["maximum_orders"] - slot["current_orders"]
            if remaining < 1:
                return f"The selected pickup time is full for {menu_data['day']}.", 400

            menus.append({
                "id": menu_data["id"],
                "date": menu_data["date"],
                "day": menu_data["day"],
                "name": menu_data["name"],
                "slot_id": slot["id"],
                "remaining": remaining,
            })

        weekly_price = WEEKLY_PACKAGE_PRICES[frequency]
        savings = (frequency * 12.00) - weekly_price
        package_allergens = []
        package_allergen_summary = []
        for menu_entry in menus:
            menu_data = weekly_menu.get(menu_entry["day"].lower())
            if menu_data:
                item_summary, labels = get_menu_allergen_summary(menu_data)
                package_allergen_summary.append({
                    "day": menu_data["day"],
                    "date": menu_data["date"],
                    "name": menu_data["name"],
                    "items": item_summary,
                    "allergens": labels,
                })
                package_allergens.extend(labels)
        package_allergens = list(dict.fromkeys(package_allergens))

        return render_template(
            "package_summary.html",
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            location=location,
            pickup_time=f"{start_time}–{end_time} Uhr",
            pickup_start=start_time,
            pickup_end=end_time,
            selected_days=selected_days,
            frequency=frequency,
            weekly_price=weekly_price,
            savings=savings,
            menus=menus,
            payment_methods=PAYMENT_METHODS,
            bank_account_holder=BANK_ACCOUNT_HOLDER,
            bank_iban=BANK_IBAN,
            bank_bic=BANK_BIC,
            privacy_consent=privacy_consent,
            terms_accepted=terms_accepted,
            marketing_consent=marketing_consent,
            package_allergen_summary=package_allergen_summary,
            package_allergens=package_allergens,
            customer_allergens=customer_allergens,
            customer_allergen_labels=[ALLERGENS[c] for c in customer_allergens],
        )
    finally:
        connection.close()


@app.route("/packages/place-order", methods=["POST"])
def package_place_order():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    location = request.form.get("location", "").strip()
    pickup_start = request.form.get("pickup_start", "").strip()
    pickup_end = request.form.get("pickup_end", "").strip()
    payment_method = request.form.get("payment_method", "cash").strip().lower()
    requested_days = {day.strip().lower() for day in request.form.getlist("days") if day.strip()}
    weekday_order = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    selected_days = [day.capitalize() for day in weekday_order if day in requested_days]
    customer_allergens = [code for code in request.form.getlist("customer_allergens") if code in ALLERGENS]

    try:
        frequency = int(request.form.get("frequency", "0"))
    except ValueError:
        return "Invalid package frequency.", 400

    if payment_method not in PAYMENT_METHODS:
        return "Invalid payment method.", 400

    if frequency not in WEEKLY_PACKAGE_PRICES or len(selected_days) != frequency:
        return "Invalid package day selection.", 400

    privacy_consent = request.form.get("privacy_consent") == "1"
    terms_accepted = request.form.get("terms_accepted") == "1"
    marketing_consent = request.form.get("marketing_consent") == "1"
    if not privacy_consent or not terms_accepted:
        return "Please accept the Privacy Policy and Terms & Conditions before placing the package.", 400

    if not first_name or not last_name or not email or not phone:
        return "All customer details are required.", 400

    if location not in PICKUP_LOCATIONS:
        return "Invalid pickup location.", 400

    if (pickup_start, pickup_end) not in STANDARD_PICKUP_SLOTS:
        return "Invalid pickup time.", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        selected_menus = []
        weekly_menu = get_menu()
        for day in selected_days:
            menu_data = weekly_menu.get(day.lower())
            if menu_data is None:
                connection.rollback()
                return f"No active menu is available for {day}.", 400

            cursor.execute("""
                SELECT id, pickup_date, location, start_time, end_time,
                       maximum_orders, current_orders
                FROM pickup_slots
                WHERE id IN (
                    SELECT id FROM pickup_slots
                    WHERE pickup_date = ?
                      AND location = ?
                      AND start_time = ?
                      AND end_time = ?
                      AND is_active = 1
                    LIMIT 1
                )
                LIMIT 1
            """, (menu_data["date"], location, pickup_start, pickup_end))
            slot = cursor.fetchone()

            if slot is None:
                connection.rollback()
                return f"The selected pickup time is unavailable for {menu_data['day']}.", 400

            cursor.execute("""
                UPDATE pickup_slots
                SET current_orders = current_orders + 1
                WHERE id = ?
                  AND is_active = 1
                  AND current_orders + 1 <= maximum_orders
            """, (slot["id"],))
            if cursor.rowcount != 1:
                connection.rollback()
                return f"The selected pickup time became full for {menu_data['day']}.", 400

            selected_menus.append({
                "menu": menu_data,
                "slot": slot,
            })

        cursor.execute("""
            INSERT INTO customers (first_name, last_name, email, phone, privacy_consent_at, terms_accepted_at, marketing_consent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (first_name, last_name, email, phone, datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds"), int(marketing_consent)))
        customer_id = cursor.lastrowid

        package_number = (
            "RTP-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-" + str(customer_id)
        )
        weekly_price = WEEKLY_PACKAGE_PRICES[frequency]

        cursor.execute("""
            INSERT INTO weekly_packages (
                package_number, customer_id, frequency, weekly_price,
                pickup_location, pickup_time, total_amount,
                payment_method, payment_status, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            package_number, customer_id, frequency, weekly_price,
            location, f"{pickup_start}–{pickup_end} Uhr", weekly_price,
            payment_method, "unpaid", "confirmed"
        ))
        package_id = cursor.lastrowid

        per_day_amount = round(weekly_price / frequency, 2)

        for item in selected_menus:
            menu = item["menu"]
            slot = item["slot"]
            order_number = (
                f"{package_number}-{menu['date'].replace('-', '')}"
            )

            cursor.execute("""
                INSERT INTO orders (
                    order_number, customer_id, menu_id, pickup_slot_id, quantity,
                    pickup_location, pickup_date, pickup_time, total_amount,
                    status, payment_status, payment_method, package_id
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_number, customer_id, menu["id"], slot["id"], location,
                menu["date"], f"{pickup_start}–{pickup_end} Uhr",
                per_day_amount, "confirmed", "unpaid", payment_method, package_id
            ))
            order_id = cursor.lastrowid

            for food in menu["items"]:
                cursor.execute(
                    "INSERT INTO order_items (order_id, item_name) VALUES (?, ?)",
                    (order_id, food),
                )

            for allergen_code in customer_allergens:
                cursor.execute(
                    "INSERT OR IGNORE INTO order_allergen_requests (order_id, allergen_code) VALUES (?, ?)",
                    (order_id, allergen_code),
                )

            cursor.execute("""
                INSERT INTO package_days (
                    package_id, order_id, menu_date, day_name, pickup_slot_id
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                package_id, order_id, menu["date"],
                menu["day"], slot["id"]
            ))

        connection.commit()

    except Exception as error:
        connection.rollback()
        print("PACKAGE DATABASE ERROR:", error)
        return "There was a problem saving your package. Please try again.", 500
    finally:
        connection.close()

    payment_url = None
    if payment_method == "stripe":
        try:
            checkout = stripe.checkout.Session.create(
                mode="payment",
                automatic_payment_methods={"enabled": True},
                customer_email=email,
                line_items=[{
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Radhe Tiffin {frequency}-day weekly package",
                        },
                        "unit_amount": int(round(weekly_price * 100)),
                    },
                    "quantity": 1,
                }],
                metadata={"package_number": package_number},
                success_url=f"{PUBLIC_BASE_URL}/package-payment/success?package_number={package_number}&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{PUBLIC_BASE_URL}/package-payment/cancel?package_number={package_number}",
            )
            payment_url = checkout.url

            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE weekly_packages SET payment_status='pending', payment_reference=? WHERE package_number=?",
                (checkout.id, package_number),
            )
            cursor.execute(
                "UPDATE orders SET payment_status='pending', payment_reference=? WHERE package_id=(SELECT id FROM weekly_packages WHERE package_number=?)",
                (checkout.id, package_number),
            )
            connection.commit()
            connection.close()
        except Exception as error:
            print("PACKAGE STRIPE CHECKOUT ERROR:", error)

    package_allergen_summary = []
    package_allergens = []
    weekly_menu_for_confirmation = get_menu()
    for day in selected_days:
        menu_data = weekly_menu_for_confirmation.get(day.lower())
        if menu_data:
            item_summary, labels = get_menu_allergen_summary(menu_data)
            package_allergen_summary.append({
                "day": menu_data["day"],
                "date": menu_data["date"],
                "name": menu_data["name"],
                "items": item_summary,
                "allergens": labels,
            })
            package_allergens.extend(labels)
    package_allergens = list(dict.fromkeys(package_allergens))

    return render_template(
        "package_confirmation.html",
        package_number=package_number,
        frequency=frequency,
        weekly_price=weekly_price,
        savings=(frequency * 12.00) - weekly_price,
        location=location,
        pickup_time=f"{pickup_start}–{pickup_end} Uhr",
        selected_days=selected_days,
        payment_method=payment_method,
        payment_method_label=PAYMENT_METHODS[payment_method]["label"],
        payment_status="pending" if payment_method == "stripe" and payment_url else "unpaid",
        payment_url=payment_url,
        bank_account_holder=BANK_ACCOUNT_HOLDER,
        bank_iban=BANK_IBAN,
        bank_bic=BANK_BIC,
        package_allergen_summary=package_allergen_summary,
        package_allergens=package_allergens,
        customer_allergens=customer_allergens,
        customer_allergen_labels=[ALLERGENS[c] for c in customer_allergens],
    )


# ==================================================
# OFFICE / MEETING / EVENT CATERING
# ==================================================

@app.route("/catering")
def catering():
    return render_template(
        "catering.html",
        catering_packages=CATERING_PACKAGES,
        payment_methods=PAYMENT_METHODS,
    )


@app.route("/catering/request", methods=["POST"])
def catering_request():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    package_type = request.form.get("package_type", "").strip().lower()
    event_date = request.form.get("event_date", "").strip()
    location = request.form.get("location", "").strip()
    service_notes = request.form.get("service_notes", "").strip()
    payment_method = request.form.get("payment_method", "bank_transfer").strip().lower()
    customer_allergens = [code for code in request.form.getlist("customer_allergens") if code in ALLERGENS]

    try:
        people_count = int(request.form.get("people_count", "0"))
    except ValueError:
        return "Invalid number of people.", 400

    package = CATERING_PACKAGES.get(package_type)
    if not package:
        return "Invalid catering package.", 400

    if people_count < package["min_people"] or people_count > package["max_people"]:
        return (
            f"{package['label']} is available for "
            f"{package['min_people']}–{package['max_people']} people."
        ), 400

    privacy_consent = request.form.get("privacy_consent") == "1"
    terms_accepted = request.form.get("terms_accepted") == "1"
    marketing_consent = request.form.get("marketing_consent") == "1"
    if not privacy_consent or not terms_accepted:
        return "Please accept the Privacy Policy and Terms & Conditions before submitting the catering request.", 400

    if not first_name or not last_name or not email or not phone or not event_date or not location:
        return "Please complete all required catering details.", 400

    if payment_method not in PAYMENT_METHODS:
        payment_method = "bank_transfer"

    estimated_amount = round(people_count * package["price_per_person"], 2)

    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            INSERT INTO customers (first_name, last_name, email, phone, privacy_consent_at, terms_accepted_at, marketing_consent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (first_name, last_name, email, phone, datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds"), int(marketing_consent)))
        customer_id = cursor.lastrowid

        request_number = (
            "RTC-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-" + str(customer_id)
        )

        cursor.execute("""
            INSERT INTO catering_requests (
                request_number, customer_id, package_type, people_count,
                event_date, location, service_notes, estimated_amount,
                payment_method, payment_status, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'quote_pending', 'new')
        """, (
            request_number, customer_id, package_type, people_count,
            event_date, location, service_notes, estimated_amount,
            payment_method
        ))
        catering_request_id = cursor.lastrowid
        for allergen_code in customer_allergens:
            cursor.execute(
                "INSERT OR IGNORE INTO catering_allergen_requests (catering_request_id, allergen_code) VALUES (?, ?)",
                (catering_request_id, allergen_code),
            )
        connection.commit()
    except Exception as error:
        connection.rollback()
        print("CATERING REQUEST ERROR:", error)
        return "We could not save your catering request.", 500
    finally:
        connection.close()

    return render_template(
        "catering_confirmation.html",
        request_number=request_number,
        package=package,
        people_count=people_count,
        estimated_amount=estimated_amount,
        event_date=event_date,
        location=location,
        payment_method_label=PAYMENT_METHODS[payment_method]["label"],
        customer_allergen_labels=[ALLERGENS[c] for c in customer_allergens],
    )



@app.route("/package-payment/success")
def package_payment_success():
    package_number = request.args.get("package_number", "").strip()
    session_id = request.args.get("session_id", "").strip()

    if not package_number or not session_id or not stripe or not STRIPE_SECRET_KEY:
        return "Invalid package payment confirmation.", 400

    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
        if checkout.payment_status == "paid" and checkout.metadata.get("package_number") == package_number:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE weekly_packages SET payment_status='paid', payment_reference=? WHERE package_number=?",
                (session_id, package_number),
            )
            cursor.execute(
                "UPDATE orders SET payment_status='paid', payment_reference=? WHERE package_id=(SELECT id FROM weekly_packages WHERE package_number=?)",
                (session_id, package_number),
            )
            connection.commit()
            connection.close()
            return redirect(url_for("package_payment_complete", package_number=package_number))
    except Exception as error:
        print("STRIPE PACKAGE PAYMENT VERIFICATION ERROR:", error)

    return "Package payment could not be verified.", 400


@app.route("/package-payment/complete")
def package_payment_complete():
    package_number = request.args.get("package_number", "").strip()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT package_number, frequency, total_amount, pickup_location, pickup_time,
               payment_status
        FROM weekly_packages
        WHERE package_number = ?
        LIMIT 1
    """, (package_number,))
    package = cursor.fetchone()
    connection.close()

    if not package:
        return "Package not found.", 404

    return render_template("package_payment_complete.html", package=package)


@app.route("/package-payment/cancel")
def package_payment_cancel():
    package_number = request.args.get("package_number", "").strip()
    return render_template("package_payment_cancel.html", package_number=package_number)


# ==================================================
# STRIPE WEBHOOK
# ==================================================

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Authoritative Stripe payment confirmation endpoint.

    The customer success page is only a browser redirect. Stripe's webhook is
    what marks an order/package as paid even if the customer closes the
    browser before returning to Radhe Tiffin.
    """
    if not stripe or not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        return "Stripe webhook is not configured.", 503

    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return "Invalid payload.", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature.", 400
    except Exception as error:
        print("STRIPE WEBHOOK ERROR:", error)
        return "Webhook verification failed.", 400

    event_type = event.get("type", "")
    if event_type not in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        return "", 200

    checkout = event["data"]["object"]
    if checkout.get("payment_status") != "paid":
        return "", 200

    metadata = checkout.get("metadata") or {}
    session_id = checkout.get("id", "")

    connection = get_connection()
    try:
        cursor = connection.cursor()

        order_number = (metadata.get("order_number") or "").strip()
        package_number = (metadata.get("package_number") or "").strip()

        if order_number:
            cursor.execute(
                "UPDATE orders SET payment_status='paid', payment_reference=? "
                "WHERE order_number=?",
                (session_id, order_number),
            )

        if package_number:
            cursor.execute(
                "UPDATE weekly_packages SET payment_status='paid', payment_reference=? "
                "WHERE package_number=?",
                (session_id, package_number),
            )
            cursor.execute(
                "UPDATE orders SET payment_status='paid', payment_reference=? "
                "WHERE package_id=(SELECT id FROM weekly_packages WHERE package_number=?)",
                (session_id, package_number),
            )

        connection.commit()
    except Exception as error:
        connection.rollback()
        print("STRIPE WEBHOOK DATABASE ERROR:", error)
        return "Webhook database update failed.", 500
    finally:
        connection.close()

    return "", 200


# ==================================================
# PAYMENT CALLBACKS
# ==================================================

@app.route("/payment/success")
def payment_success():
    order_number = request.args.get("order_number", "").strip()
    session_id = request.args.get("session_id", "").strip()

    if not order_number or not session_id or not stripe or not STRIPE_SECRET_KEY:
        return "Invalid payment confirmation.", 400

    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
        if checkout.payment_status == "paid" and checkout.metadata.get("order_number") == order_number:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE orders SET payment_status='paid', payment_reference=? WHERE order_number=?",
                (session_id, order_number),
            )
            connection.commit()
            connection.close()
            return redirect(url_for("payment_complete", order_number=order_number))
    except Exception as error:
        print("STRIPE PAYMENT VERIFICATION ERROR:", error)

    return "Payment could not be verified. Please contact Radhe Tiffin.", 400


@app.route("/payment/complete")
def payment_complete():
    order_number = request.args.get("order_number", "").strip()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT orders.order_number, orders.total_amount, orders.payment_status,
               orders.payment_method, menu.meal_name, orders.pickup_date,
               orders.pickup_location, orders.pickup_time
        FROM orders
        INNER JOIN menu ON orders.menu_id = menu.id
        WHERE orders.order_number = ?
        LIMIT 1
    """, (order_number,))
    order_record = cursor.fetchone()
    connection.close()
    if not order_record:
        return "Order not found.", 404
    return render_template("payment_complete.html", order=order_record)


@app.route("/payment/cancel")
def payment_cancel():
    order_number = request.args.get("order_number", "").strip()
    return render_template("payment_cancel.html", order_number=order_number)

# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin")
def admin_dashboard():
    selected_date = request.args.get(
        "date",
        date.today().isoformat(),
    )

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------
    # Available dates
    # --------------------------------------------------
    cursor.execute("""
        SELECT DISTINCT
            pickup_date AS date,
            strftime('%w', pickup_date) AS weekday
        FROM pickup_slots

        UNION

        SELECT DISTINCT
            menu_date AS date,
            strftime('%w', menu_date) AS weekday
        FROM menu

        ORDER BY date ASC
    """)

    date_rows = cursor.fetchall()

    weekday_names = {
        "0": "Sunday",
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday",
    }

    available_dates = [
        {
            "date": row["date"],
            "day": weekday_names.get(
                row["weekday"],
                "",
            ),
        }
        for row in date_rows
    ]

    if not available_dates:
        available_dates = [
            {
                "date": selected_date,
                "day": "",
            }
        ]

    valid_dates = {
        item["date"]
        for item in available_dates
    }

    if selected_date not in valid_dates:
        selected_date = available_dates[0]["date"]

    # --------------------------------------------------
    # Selected day
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            day_name,
            day_name_german
        FROM menu
        WHERE menu_date = ?
        AND is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """, (
        selected_date,
    ))

    selected_menu_day = cursor.fetchone()

    if selected_menu_day:
        selected_day = selected_menu_day["day_name"]
    else:
        selected_day = selected_date

    # --------------------------------------------------
    # Statistics
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            COUNT(*) AS total_orders,
            COALESCE(
                SUM(quantity),
                0
            ) AS total_tiffins,
            COALESCE(
                SUM(total_amount),
                0
            ) AS total_revenue
        FROM orders
        WHERE pickup_date = ?
    """, (
        selected_date,
    ))

    stats = cursor.fetchone()

    # --------------------------------------------------
    # Unpaid
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            COUNT(*) AS unpaid_orders
        FROM orders
        WHERE pickup_date = ?
        AND payment_status = 'unpaid'
    """, (
        selected_date,
    ))

    unpaid = cursor.fetchone()

    # --------------------------------------------------
    # Orders
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            orders.id,
            orders.order_number,
            orders.menu_id,
            orders.quantity,
            orders.pickup_location,
            orders.pickup_date,
            orders.pickup_time,
            orders.total_amount,
            orders.status,
            orders.payment_status,
            orders.payment_method,
            orders.package_id,
            orders.created_at,
            weekly_packages.package_number,
            weekly_packages.frequency,

            customers.first_name,
            customers.last_name,
            customers.email,
            customers.phone,

            menu.meal_name,
            menu.day_name,
            menu.day_name_german,

            pickup_slots.start_time,
            pickup_slots.end_time,
            pickup_slots.maximum_orders,
            pickup_slots.current_orders

        FROM orders

        INNER JOIN customers
            ON orders.customer_id = customers.id

        INNER JOIN menu
            ON orders.menu_id = menu.id

        LEFT JOIN pickup_slots
            ON orders.pickup_slot_id = pickup_slots.id

        LEFT JOIN weekly_packages
            ON orders.package_id = weekly_packages.id

        WHERE orders.pickup_date = ?

        ORDER BY
            orders.pickup_time ASC,
            orders.created_at ASC
    """, (
        selected_date,
    ))

    orders = cursor.fetchall()

    # Attach verified allergen information to every order so staff see an
    # immediate food-safety warning without opening another page.
    order_list = []
    for order in orders:
        order_data = dict(order)
        menu_item_rows = cursor.execute("""
            SELECT mi.item_name, mia.allergen_code
            FROM menu_items mi
            LEFT JOIN menu_item_allergens mia ON mia.menu_item_id = mi.id
            WHERE mi.menu_id = ?
            ORDER BY mi.id, mia.allergen_code
        """, (order["menu_id"],)).fetchall()
        grouped = {}
        for row in menu_item_rows:
            grouped.setdefault(row["item_name"], [])
            if row["allergen_code"]:
                grouped[row["item_name"]].append(row["allergen_code"])

        requested_rows = cursor.execute("""
            SELECT allergen_code FROM order_allergen_requests
            WHERE order_id = ? ORDER BY id
        """, (order["id"],)).fetchall()
        customer_allergen_codes = [row["allergen_code"] for row in requested_rows]
        order_data["customer_allergen_requests"] = [
            ALLERGENS.get(code, code) for code in customer_allergen_codes
        ]

        # Keep menu allergens recipe/dish-specific, but cross-check them against
        # the customer's overall allergy request for this order.
        order_data["allergen_items"] = []
        for name, codes in grouped.items():
            labels = [ALLERGENS.get(code, code) for code in codes]
            matched_codes = [code for code in codes if code in customer_allergen_codes]
            matched_labels = [ALLERGENS.get(code, code) for code in matched_codes]
            if labels:
                order_data["allergen_items"].append({
                    "name": name,
                    "allergens": labels,
                    "customer_matches": matched_labels,
                })

        order_data["allergens"] = list(dict.fromkeys(
            label for item in order_data["allergen_items"] for label in item["allergens"]
        ))
        order_data["allergen_matches"] = [
            {"name": item["name"], "allergens": item["customer_matches"]}
            for item in order_data["allergen_items"]
            if item["customer_matches"]
        ]
        order_list.append(order_data)
    orders = order_list

    # --------------------------------------------------
    # Pickup slots
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            id,
            pickup_date,
            location,
            start_time,
            end_time,
            maximum_orders,
            current_orders,
            is_active
        FROM pickup_slots
        WHERE pickup_date = ?
        AND is_active = 1
        ORDER BY
            location ASC,
            start_time ASC
    """, (
        selected_date,
    ))

    pickup_slots = cursor.fetchall()

    connection.close()

    return render_template(
        "admin.html",
        today=date.today().isoformat(),
        selected_date=selected_date,
        selected_day=selected_day,
        available_dates=available_dates,
        stats=stats,
        unpaid=unpaid,
        orders=orders,
        pickup_slots=pickup_slots,
    )


# ==================================================
# ADMIN ORDER STATUS
# ==================================================

@app.route(
    "/admin/order/<int:order_id>/status",
    methods=["POST"],
)
def admin_order_status(order_id):
    new_status = request.form.get(
        "status",
        "",
    ).strip().lower()

    allowed_statuses = {
        "confirmed",
        "ready",
        "completed",
        "cancelled",
    }

    if new_status not in allowed_statuses:
        return "Invalid order status", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                id,
                status,
                quantity,
                pickup_slot_id
            FROM orders
            WHERE id = ?
        """, (
            order_id,
        ))

        order_record = cursor.fetchone()

        if order_record is None:
            connection.rollback()
            return "Order not found", 404

        old_status = order_record["status"]

        # --------------------------------------------------
        # Release capacity when an active order is cancelled.
        # --------------------------------------------------
        if (
            new_status == "cancelled"
            and old_status != "cancelled"
            and order_record["pickup_slot_id"] is not None
        ):
            cursor.execute("""
                UPDATE pickup_slots
                SET current_orders =
                    MAX(
                        0,
                        current_orders - ?
                    )
                WHERE id = ?
            """, (
                order_record["quantity"],
                order_record["pickup_slot_id"],
            ))

        # --------------------------------------------------
        # If a cancelled order is restored, consume capacity
        # again only if enough capacity exists.
        # --------------------------------------------------
        if (
            old_status == "cancelled"
            and new_status != "cancelled"
            and order_record["pickup_slot_id"] is not None
        ):
            cursor.execute("""
                SELECT
                    maximum_orders,
                    current_orders,
                    is_active
                FROM pickup_slots
                WHERE id = ?
            """, (
                order_record["pickup_slot_id"],
            ))

            slot = cursor.fetchone()

            if slot is None or not slot["is_active"]:
                connection.rollback()
                return (
                    "The original pickup slot is no longer available."
                ), 400

            available = (
                slot["maximum_orders"]
                - slot["current_orders"]
            )

            if order_record["quantity"] > available:
                connection.rollback()
                return (
                    "The pickup slot does not have enough "
                    "remaining capacity to restore this order."
                ), 400

            cursor.execute("""
                UPDATE pickup_slots
                SET current_orders =
                    current_orders + ?
                WHERE id = ?
            """, (
                order_record["quantity"],
                order_record["pickup_slot_id"],
            ))

        cursor.execute("""
            UPDATE orders
            SET status = ?
            WHERE id = ?
        """, (
            new_status,
            order_id,
        ))

        connection.commit()

    except Exception as error:
        connection.rollback()
        print(
            "ADMIN STATUS ERROR:",
            error,
        )
        return "Could not update order status.", 500

    finally:
        connection.close()

    next_url = safe_next_url(
        request.form.get("next")
    )

    return redirect(
        next_url or url_for("admin_dashboard")
    )


# ==================================================
# ADMIN PAYMENT STATUS
# ==================================================

@app.route(
    "/admin/order/<int:order_id>/payment",
    methods=["POST"],
)
def admin_order_payment(order_id):
    payment_status = request.form.get(
        "payment_status",
        "",
    ).strip().lower()

    if payment_status not in {
        "paid",
        "unpaid",
    }:
        return "Invalid payment status", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE orders
            SET payment_status = ?
            WHERE id = ?
        """, (
            payment_status,
            order_id,
        ))

        if cursor.rowcount == 0:
            connection.rollback()
            return "Order not found", 404

        connection.commit()

    except Exception as error:
        connection.rollback()
        print(
            "ADMIN PAYMENT ERROR:",
            error,
        )
        return "Could not update payment status.", 500

    finally:
        connection.close()

    next_url = safe_next_url(
        request.form.get("next")
    )

    return redirect(
        next_url or url_for("admin_dashboard")
    )



# ==================================================
# ADMIN CATERING REQUESTS
# ==================================================

@app.route("/admin/catering")
def admin_catering():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            catering_requests.*,
            customers.first_name,
            customers.last_name,
            customers.email,
            customers.phone
        FROM catering_requests
        INNER JOIN customers
            ON catering_requests.customer_id = customers.id
        ORDER BY catering_requests.created_at DESC
    """)
    requests = cursor.fetchall()
    request_list = []
    for row in requests:
        data = dict(row)
        allergy_rows = cursor.execute("""
            SELECT allergen_code FROM catering_allergen_requests
            WHERE catering_request_id = ? ORDER BY id
        """, (row["id"],)).fetchall()
        data["customer_allergen_labels"] = [ALLERGENS.get(r["allergen_code"], r["allergen_code"]) for r in allergy_rows]
        request_list.append(data)
    connection.close()

    return render_template("admin_catering.html", requests=request_list)

# ==================================================
# ADMIN MENU MANAGEMENT
# ==================================================

@app.route("/admin/menu")
def admin_menu():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            menu_date,
            day_name,
            day_name_german,
            meal_name,
            price
        FROM menu
        WHERE is_active = 1
        ORDER BY menu_date ASC
    """)

    menu_rows = cursor.fetchall()
    menus = []

    for row in menu_rows:
        cursor.execute("""
            SELECT
                item_name,
                item_name_german
            FROM menu_items
            WHERE menu_id = ?
            ORDER BY id ASC
        """, (
            row["id"],
        ))

        item_rows = cursor.fetchall()

        menus.append({
            "id": row["id"],
            "date": row["menu_date"],
            "day": row["day_name"],
            "german_day": row["day_name_german"],
            "name": row["meal_name"],
            "price": row["price"],
            "items": [
                {
                    "name": item["item_name"],
                    "german_name": item["item_name_german"] or "",
                }
                for item in item_rows
            ],
        })

    connection.close()

    return render_template(
        "menu_admin.html",
        menus=menus,
    )


@app.route(
    "/admin/menu/save",
    methods=["POST"],
)
def admin_menu_save():
    menu_id = request.form.get(
        "menu_id",
        "",
    ).strip()

    menu_date = request.form.get(
        "menu_date",
        "",
    ).strip()

    meal_name = request.form.get(
        "meal_name",
        "",
    ).strip()

    day_name = request.form.get(
        "day_name",
        "",
    ).strip()

    german_day_name = request.form.get(
        "day_name_german",
        "",
    ).strip()

    try:
        price = float(
            request.form.get(
                "price",
                0,
            )
        )
    except ValueError:
        return "Invalid price", 400

    item_names = request.form.getlist(
        "item_name[]"
    )

    item_german_names = request.form.getlist(
        "item_name_german[]"
    )

    item_pairs = []

    for index, item_name in enumerate(item_names):
        item_name = item_name.strip()

        if not item_name:
            continue

        german_name = ""

        if index < len(item_german_names):
            german_name = (
                item_german_names[index].strip()
            )

        item_pairs.append(
            (
                item_name,
                german_name,
            )
        )

    if not menu_date:
        return "Menu date is required", 400

    if not meal_name:
        return "Meal name is required", 400

    if not day_name:
        return "Day name is required", 400

    if price <= 0:
        return "Price must be greater than zero", 400

    if not item_pairs:
        return "At least one menu item is required", 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # --------------------------------------------------
        # Editing existing menu
        # --------------------------------------------------
        if menu_id:
            try:
                menu_id_int = int(menu_id)
            except ValueError:
                connection.rollback()
                return "Invalid menu ID", 400

            cursor.execute("""
                SELECT COUNT(*) AS order_count
                FROM orders
                WHERE menu_id = ?
            """, (
                menu_id_int,
            ))

            order_count = cursor.fetchone()["order_count"]

            if order_count > 0:
                connection.rollback()
                return (
                    "This menu already has orders and cannot "
                    "be edited. Create a new menu instead."
                ), 400

            cursor.execute("""
                UPDATE menu
                SET
                    menu_date = ?,
                    day_name = ?,
                    day_name_german = ?,
                    meal_name = ?,
                    price = ?,
                    is_active = 1
                WHERE id = ?
            """, (
                menu_date,
                day_name,
                german_day_name,
                meal_name,
                price,
                menu_id_int,
            ))

            cursor.execute("""
                DELETE FROM menu_items
                WHERE menu_id = ?
            """, (
                menu_id_int,
            ))

            target_menu_id = menu_id_int

        # --------------------------------------------------
        # Creating new menu
        # --------------------------------------------------
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
                menu_date,
                day_name,
                german_day_name,
                meal_name,
                price,
            ))

            target_menu_id = cursor.lastrowid

        for item_name, german_name in item_pairs:
            cursor.execute("""
                INSERT INTO menu_items (
                    menu_id,
                    item_name,
                    item_name_german
                )
                VALUES (?, ?, ?)
            """, (
                target_menu_id,
                item_name,
                german_name,
            ))

        connection.commit()

    except Exception as error:
        connection.rollback()
        print(
            "ADMIN MENU SAVE ERROR:",
            error,
        )
        return "Could not save menu.", 500

    finally:
        connection.close()

    return redirect(
        url_for("admin_menu")
    )


@app.route(
    "/admin/menu/<int:menu_id>/delete",
    methods=["POST"],
)
def admin_menu_delete(menu_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT COUNT(*) AS order_count
            FROM orders
            WHERE menu_id = ?
        """, (
            menu_id,
        ))

        order_count = cursor.fetchone()["order_count"]

        if order_count > 0:
            connection.rollback()
            return (
                "This menu has orders and cannot be removed."
            ), 400

        cursor.execute("""
            UPDATE menu
            SET is_active = 0
            WHERE id = ?
        """, (
            menu_id,
        ))

        if cursor.rowcount == 0:
            connection.rollback()
            return "Menu not found", 404

        connection.commit()

    except Exception as error:
        connection.rollback()
        print(
            "ADMIN MENU DELETE ERROR:",
            error,
        )
        return "Could not remove menu.", 500

    finally:
        connection.close()

    return redirect(
        url_for("admin_menu")
    )


# ==================================================
# ADMIN PICKUP SLOT MANAGEMENT
# ==================================================

@app.route("/admin/pickup-slots")
def admin_pickup_slots():
    selected_date = normalize_pickup_date(
        request.args.get(
            "date",
            "",
        )
    )

    location_filter = request.args.get(
        "location",
        "",
    ).strip()

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------
    # Available dates
    # --------------------------------------------------
    cursor.execute("""
        SELECT DISTINCT pickup_date AS date
        FROM pickup_slots
        ORDER BY pickup_date ASC
    """)

    available_dates = [
        row["date"]
        for row in cursor.fetchall()
    ]

    if not selected_date and available_dates:
        selected_date = available_dates[0]

    # --------------------------------------------------
    # Slots
    # --------------------------------------------------
    query = """
        SELECT
            id,
            pickup_date,
            location,
            start_time,
            end_time,
            maximum_orders,
            current_orders,
            is_active
        FROM pickup_slots
        WHERE 1 = 1
    """

    params = []

    if selected_date:
        query += " AND pickup_date = ? "
        params.append(selected_date)

    if location_filter in ("Ulm", "Neu-Ulm"):
        query += " AND location = ? "
        params.append(location_filter)

    query += """
        ORDER BY
            pickup_date ASC,
            location ASC,
            start_time ASC
    """

    cursor.execute(
        query,
        params,
    )

    slots = cursor.fetchall()

    # --------------------------------------------------
    # Dates for new-slot form
    # Use menu dates as well, so a new slot can be
    # created for any existing menu date.
    # --------------------------------------------------
    cursor.execute("""
        SELECT DISTINCT menu_date AS date
        FROM menu
        WHERE is_active = 1
        ORDER BY menu_date ASC
    """)

    menu_dates = [
        row["date"]
        for row in cursor.fetchall()
    ]

    for menu_date in menu_dates:
        if menu_date not in available_dates:
            available_dates.append(menu_date)

    available_dates.sort()

    connection.close()

    return render_template(
        "pickup_slots_admin.html",
        slots=slots,
        pickup_slots=slots,
        selected_date=selected_date,
        location_filter=location_filter,
        available_dates=available_dates,
    )


@app.route(
    "/admin/pickup-slots/save",
    methods=["POST"],
)
def admin_pickup_slot_save():
    slot_id = request.form.get("slot_id", "").strip()
    pickup_date = normalize_pickup_date(request.form.get("pickup_date", ""))
    location = request.form.get("location", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    maximum_orders = request.form.get("maximum_orders", "").strip()

    error_message = validate_slot_values(
        pickup_date, location, start_time, end_time, maximum_orders
    )

    if error_message:
        flash(error_message, "error")
        return redirect(url_for(
            "admin_pickup_slots",
            date=pickup_date or None,
            location=location or None,
        ))

    maximum_orders = int(maximum_orders)
    connection = get_connection()
    cursor = connection.cursor()

    try:
        slot_id_int = int(slot_id) if slot_id else None

        if slot_id_int is not None:
            cursor.execute("""
                SELECT current_orders
                FROM pickup_slots
                WHERE id = ?
            """, (slot_id_int,))
            existing = cursor.fetchone()

            if existing is None:
                connection.rollback()
                flash("Pickup slot not found.", "error")
                return redirect(url_for("admin_pickup_slots"))

            if maximum_orders < existing["current_orders"]:
                connection.rollback()
                flash(
                    "Maximum capacity cannot be lower than the number of already booked tiffins.",
                    "error",
                )
                return redirect(url_for(
                    "admin_pickup_slots", date=pickup_date, location=location
                ))

            cursor.execute("""
                SELECT id
                FROM pickup_slots
                WHERE pickup_date = ? AND location = ?
                  AND start_time = ? AND end_time = ?
                  AND is_active = 1 AND id != ?
                LIMIT 1
            """, (pickup_date, location, start_time, end_time, slot_id_int))

            if cursor.fetchone():
                connection.rollback()
                flash(
                    "An active pickup slot with the same date, location and time already exists.",
                    "error",
                )
                return redirect(url_for(
                    "admin_pickup_slots", date=pickup_date, location=location
                ))

            cursor.execute("""
                UPDATE pickup_slots
                SET pickup_date = ?, location = ?, start_time = ?,
                    end_time = ?, maximum_orders = ?
                WHERE id = ?
            """, (
                pickup_date, location, start_time, end_time,
                maximum_orders, slot_id_int
            ))
            flash("Pickup slot updated successfully.", "success")

        else:
            cursor.execute("""
                SELECT id
                FROM pickup_slots
                WHERE pickup_date = ? AND location = ?
                  AND start_time = ? AND end_time = ?
                  AND is_active = 1
                LIMIT 1
            """, (pickup_date, location, start_time, end_time))

            if cursor.fetchone():
                connection.rollback()
                flash(
                    "An active pickup slot with the same date, location and time already exists.",
                    "error",
                )
                return redirect(url_for(
                    "admin_pickup_slots", date=pickup_date, location=location
                ))

            cursor.execute("""
                INSERT INTO pickup_slots (
                    pickup_date, location, start_time, end_time,
                    maximum_orders, current_orders, is_active
                )
                VALUES (?, ?, ?, ?, ?, 0, 1)
            """, (pickup_date, location, start_time, end_time, maximum_orders))
            flash("Pickup slot added successfully.", "success")

        connection.commit()

    except Exception as error:
        connection.rollback()
        print("ADMIN PICKUP SLOT SAVE ERROR:", error)
        flash("Could not save pickup slot.", "error")
    finally:
        connection.close()

    return redirect(url_for(
        "admin_pickup_slots", date=pickup_date, location=location
    ))

@app.route(
    "/admin/pickup-slots/<int:slot_id>/toggle",
    methods=["POST"],
)
def admin_pickup_slot_toggle(slot_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT id, pickup_date, location, start_time, end_time, is_active
            FROM pickup_slots
            WHERE id = ?
        """, (slot_id,))
        slot = cursor.fetchone()

        if slot is None:
            connection.rollback()
            flash("Pickup slot not found.", "error")
            return redirect(url_for("admin_pickup_slots"))

        new_status = 0 if slot["is_active"] else 1

        if new_status == 1:
            if (
                slot["location"] not in PICKUP_LOCATIONS
                or (slot["start_time"], slot["end_time"]) not in STANDARD_PICKUP_SLOTS
            ):
                connection.rollback()
                flash(
                    "This old slot uses a non-standard time and cannot be enabled. "
                    "Use one of the standard 30-minute slots between 12:00 and 15:00.",
                    "error",
                )
                return redirect(url_for(
                    "admin_pickup_slots",
                    date=slot["pickup_date"],
                    location=slot["location"],
                ))

            cursor.execute("""
                SELECT start_time, end_time
                FROM pickup_slots
                WHERE pickup_date = ? AND location = ?
                  AND is_active = 1 AND id != ?
                  AND start_time < ? AND end_time > ?
                LIMIT 1
            """, (
                slot["pickup_date"], slot["location"], slot_id,
                slot["end_time"], slot["start_time"]
            ))
            overlap = cursor.fetchone()
            if overlap:
                connection.rollback()
                flash(
                    f"Cannot enable this slot because it overlaps with the active "
                    f"{overlap['start_time']}–{overlap['end_time']} slot at {slot['location']}.",
                    "error",
                )
                return redirect(url_for(
                    "admin_pickup_slots",
                    date=slot["pickup_date"],
                    location=slot["location"],
                ))

        cursor.execute("""
            UPDATE pickup_slots
            SET is_active = ?
            WHERE id = ?
        """, (new_status, slot_id))

        connection.commit()
        flash(
            "Pickup slot enabled successfully." if new_status
            else "Pickup slot disabled successfully.",
            "success",
        )

    except Exception as error:
        connection.rollback()
        print("ADMIN PICKUP SLOT TOGGLE ERROR:", error)
        flash("Could not change pickup slot status.", "error")
    finally:
        connection.close()

    next_url = safe_next_url(request.form.get("next"))
    return redirect(next_url or url_for("admin_pickup_slots"))

@app.route(
    "/admin/pickup-slots/<int:slot_id>/delete",
    methods=["POST"],
)
def admin_pickup_slot_delete(slot_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                pickup_date,
                location,
                current_orders
            FROM pickup_slots
            WHERE id = ?
        """, (
            slot_id,
        ))

        slot = cursor.fetchone()

        if slot is None:
            connection.rollback()
            flash("Pickup slot not found.", "error")
            return redirect(
                url_for("admin_pickup_slots")
            )

        if slot["current_orders"] > 0:
            connection.rollback()
            flash(
                "This pickup slot already has booked tiffins and cannot be deleted. Disable it instead.",
                "error",
            )
            return redirect(
                url_for(
                    "admin_pickup_slots",
                    date=slot["pickup_date"],
                    location=slot["location"],
                )
            )

        cursor.execute("""
            DELETE FROM pickup_slots
            WHERE id = ?
        """, (
            slot_id,
        ))

        connection.commit()
        flash("Pickup slot deleted successfully.", "success")

    except Exception as error:
        connection.rollback()
        print(
            "ADMIN PICKUP SLOT DELETE ERROR:",
            error,
        )
        flash("Could not delete pickup slot.", "error")

    finally:
        connection.close()

    next_url = safe_next_url(
        request.form.get("next")
    )

    return redirect(
        next_url or url_for(
            "admin_pickup_slots"
        )
    )


# ==================================================
# PICKUP SLOT TEMPLATE ENDPOINT COMPATIBILITY
# ==================================================
# The existing pickup_slots_admin.html template uses these endpoint
# names. Keep aliases so the template works without any HTML changes.

app.add_url_rule(
    "/admin/pickup-slots/save",
    endpoint="add_pickup_slot",
    view_func=admin_pickup_slot_save,
    methods=["POST"],
)

app.add_url_rule(
    "/admin/pickup-slots/save",
    endpoint="edit_pickup_slot",
    view_func=admin_pickup_slot_save,
    methods=["POST"],
)

app.add_url_rule(
    "/admin/pickup-slots/<int:slot_id>/toggle",
    endpoint="toggle_pickup_slot",
    view_func=admin_pickup_slot_toggle,
    methods=["POST"],
)

app.add_url_rule(
    "/admin/pickup-slots/<int:slot_id>/delete",
    endpoint="delete_pickup_slot",
    view_func=admin_pickup_slot_delete,
    methods=["POST"],
)


# ==================================================
# BUSINESS SETTINGS / OPERATIONS HELPERS
# ==================================================

ALLERGENS = {
    "gluten": "Gluten-containing cereals",
    "milk": "Milk",
    "peanuts": "Peanuts",
    "nuts": "Nuts",
    "soy": "Soybeans",
    "sesame": "Sesame",
    "mustard": "Mustard",
    "celery": "Celery",
    "egg": "Eggs",
    "fish": "Fish",
    "crustaceans": "Crustaceans",
    "molluscs": "Molluscs",
    "lupin": "Lupin",
    "sulphites": "Sulphites",
}

def get_menu_allergen_summary(menu_item):
    """Return verified allergen labels grouped by menu item for customer/admin display."""
    summary = []
    all_codes = []
    for item in menu_item.get("items_with_allergens", []):
        labels = [ALLERGENS.get(code, code) for code in item.get("allergens", [])]
        if labels:
            summary.append({"name": item.get("name", ""), "allergens": labels})
            all_codes.extend(labels)
    unique_allergens = list(dict.fromkeys(all_codes))
    return summary, unique_allergens

def get_business_settings():
    connection = get_connection()
    try:
        row = connection.execute("SELECT * FROM business_settings WHERE id=1").fetchone()
        return dict(row) if row else {}
    finally:
        connection.close()

@app.context_processor
def inject_business_settings():
    return {"business": get_business_settings()}


# ==================================================
# FINANCE / BUSINESS MANAGEMENT
# ==================================================

EXPENSE_CATEGORIES = (
    "Ingredients",
    "Packaging",
    "Utilities",
    "Rent",
    "Transport",
    "Marketing",
    "Equipment",
    "Cleaning",
    "Insurance",
    "Software",
    "Other",
)

INVENTORY_TYPES = ("purchase", "usage", "waste", "adjustment")


@app.route("/admin/finance")
def admin_finance():
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_amount ELSE 0 END), 0) AS sales,
                COALESCE(SUM(CASE WHEN status != 'cancelled' AND payment_status = 'paid' THEN total_amount ELSE 0 END), 0) AS collected,
                COALESCE(SUM(CASE WHEN status != 'cancelled' AND payment_status != 'paid' THEN total_amount ELSE 0 END), 0) AS outstanding
            FROM orders
        """)
        sales = cursor.fetchone()

        cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expenses")
        other_expenses = cursor.fetchone()["total"]
        cursor.execute("SELECT COALESCE(SUM(gross_amount), 0) AS total FROM salaries")
        salaries_total = cursor.fetchone()["total"]
        cursor.execute("""
            SELECT COALESCE(SUM(total_cost), 0) AS total
            FROM inventory_transactions
            WHERE LOWER(transaction_type) IN ('usage', 'waste')
        """)
        usage_total = cursor.fetchone()["total"]

        cursor.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 12")
        recent_expenses = cursor.fetchall()
        cursor.execute("SELECT * FROM salaries ORDER BY pay_date DESC, id DESC LIMIT 12")
        recent_salaries = cursor.fetchall()
        cursor.execute("SELECT * FROM inventory_transactions ORDER BY transaction_date DESC, id DESC LIMIT 12")
        recent_inventory = cursor.fetchall()
    finally:
        connection.close()

    operational_profit = float(sales["sales"] or 0) - float(usage_total or 0) - float(other_expenses or 0) - float(salaries_total or 0)
    try:
        generate_excel_workbook()
    except Exception as error:
        print("FINANCE EXCEL REFRESH WARNING:", error)

    return render_template(
        "finance.html",
        sales=sales,
        usage_total=usage_total,
        other_expenses=other_expenses,
        salaries_total=salaries_total,
        operational_profit=operational_profit,
        recent_expenses=recent_expenses,
        recent_salaries=recent_salaries,
        recent_inventory=recent_inventory,
        expense_categories=EXPENSE_CATEGORIES,
        inventory_types=INVENTORY_TYPES,
        excel_filename=EXCEL_PATH.name,
        today=date.today().isoformat(),
    )


@app.route("/admin/finance/expense", methods=["POST"])
def admin_add_expense():
    expense_date = request.form.get("expense_date", "").strip() or date.today().isoformat()
    category = request.form.get("category", "Other").strip() or "Other"
    description = request.form.get("description", "").strip()
    vendor = request.form.get("vendor", "").strip()
    notes = request.form.get("notes", "").strip()
    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        amount = -1
    if not description or amount < 0:
        flash("Please enter a valid expense description and amount.", "error")
        return redirect(url_for("admin_finance"))
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO expenses (expense_date, category, description, vendor, amount, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (expense_date, category, description, vendor, amount, notes))
        connection.commit()
        flash("Expense added and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("EXPENSE SAVE ERROR:", error)
        flash("Could not save the expense.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/salary", methods=["POST"])
def admin_add_salary():
    pay_date = request.form.get("pay_date", "").strip() or date.today().isoformat()
    employee_name = request.form.get("employee_name", "").strip()
    role = request.form.get("role", "").strip()
    notes = request.form.get("notes", "").strip()
    try:
        hours = float(request.form.get("hours", "0") or 0)
        hourly_rate = float(request.form.get("hourly_rate", "0") or 0)
        gross_amount_input = request.form.get("gross_amount", "").strip()
        gross_amount = float(gross_amount_input) if gross_amount_input else round(hours * hourly_rate, 2)
    except ValueError:
        hours = hourly_rate = gross_amount = -1
    if not employee_name or hours < 0 or hourly_rate < 0 or gross_amount < 0:
        flash("Please enter valid staff/salary details.", "error")
        return redirect(url_for("admin_finance"))
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO salaries (pay_date, employee_name, role, hours, hourly_rate, gross_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pay_date, employee_name, role, hours, hourly_rate, gross_amount, notes))
        connection.commit()
        flash("Salary entry added and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("SALARY SAVE ERROR:", error)
        flash("Could not save the salary entry.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/inventory", methods=["POST"])
def admin_add_inventory_transaction():
    transaction_date = request.form.get("transaction_date", "").strip() or date.today().isoformat()
    item_name = request.form.get("item_name", "").strip()
    transaction_type = request.form.get("transaction_type", "usage").strip().lower()
    unit = request.form.get("unit", "kg").strip() or "unit"
    notes = request.form.get("notes", "").strip()
    try:
        quantity = float(request.form.get("quantity", "0"))
        unit_cost = float(request.form.get("unit_cost", "0") or 0)
    except ValueError:
        quantity = unit_cost = -1
    total_cost_raw = request.form.get("total_cost", "").strip()
    try:
        total_cost = float(total_cost_raw) if total_cost_raw else round(quantity * unit_cost, 2)
    except ValueError:
        total_cost = -1
    if not item_name or transaction_type not in INVENTORY_TYPES or quantity < 0 or unit_cost < 0 or total_cost < 0:
        flash("Please enter valid inventory/usage details.", "error")
        return redirect(url_for("admin_finance"))
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO inventory_transactions
                (transaction_date, item_name, transaction_type, quantity, unit, unit_cost, total_cost, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (transaction_date, item_name, transaction_type, quantity, unit, unit_cost, total_cost, notes))
        connection.commit()
        flash("Inventory/usage entry added and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("INVENTORY SAVE ERROR:", error)
        flash("Could not save the inventory entry.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/expense/<int:expense_id>/delete", methods=["POST"])
def admin_delete_expense(expense_id):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )
        if cursor.rowcount == 0:
            connection.rollback()
            flash("Expense entry not found.", "error")
            return redirect(url_for("admin_finance"))
        connection.commit()
        try:
            generate_excel_workbook()
        except Exception as error:
            print("EXPENSE DELETE EXCEL REFRESH WARNING:", error)
        flash("Expense deleted and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("EXPENSE DELETE ERROR:", error)
        flash("Could not delete the expense entry.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/salary/<int:salary_id>/delete", methods=["POST"])
def admin_delete_salary(salary_id):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM salaries WHERE id = ?",
            (salary_id,)
        )
        if cursor.rowcount == 0:
            connection.rollback()
            flash("Salary entry not found.", "error")
            return redirect(url_for("admin_finance"))
        connection.commit()
        try:
            generate_excel_workbook()
        except Exception as error:
            print("SALARY DELETE EXCEL REFRESH WARNING:", error)
        flash("Salary entry deleted and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("SALARY DELETE ERROR:", error)
        flash("Could not delete the salary entry.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/inventory/<int:transaction_id>/delete", methods=["POST"])
def admin_delete_inventory_transaction(transaction_id):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM inventory_transactions WHERE id = ?",
            (transaction_id,)
        )
        if cursor.rowcount == 0:
            connection.rollback()
            flash("Inventory/usage entry not found.", "error")
            return redirect(url_for("admin_finance"))
        connection.commit()
        try:
            generate_excel_workbook()
        except Exception as error:
            print("INVENTORY DELETE EXCEL REFRESH WARNING:", error)
        flash("Inventory/usage entry deleted and Excel report refreshed.", "success")
    except Exception as error:
        connection.rollback()
        print("INVENTORY DELETE ERROR:", error)
        flash("Could not delete the inventory/usage entry.", "error")
    finally:
        connection.close()
    return redirect(url_for("admin_finance"))


@app.route("/admin/excel/download")
def admin_excel_download():
    from flask import send_file
    try:
        generate_excel_workbook()
    except Exception as error:
        print("EXCEL DOWNLOAD REFRESH ERROR:", error)
        flash("Could not refresh the Excel workbook.", "error")
        return redirect(url_for("admin_finance"))
    return send_file(
        EXCEL_PATH,
        as_attachment=True,
        download_name="RadheTiffin_Business.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==================================================
# ADMIN BUSINESS SETTINGS
# ==================================================

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "POST":
        fields = [
            "business_name", "legal_name", "owner_name", "address", "city",
            "postal_code", "country", "email", "phone", "vat_id", "tax_number",
            "website", "pickup_policy", "cancellation_policy", "allergy_notice",
        ]
        values = {key: request.form.get(key, "").strip() for key in fields}
        if not values["business_name"]:
            flash("Business name is required.", "error")
            return redirect(url_for("admin_settings"))
        connection = get_connection()
        try:
            connection.execute("""
                UPDATE business_settings SET
                    business_name=?, legal_name=?, owner_name=?, address=?, city=?,
                    postal_code=?, country=?, email=?, phone=?, vat_id=?, tax_number=?,
                    website=?, pickup_policy=?, cancellation_policy=?, allergy_notice=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=1
            """, tuple(values[k] for k in fields))
            connection.commit()
            flash("Business settings saved.", "success")
        except Exception as error:
            connection.rollback(); print("SETTINGS SAVE ERROR:", error)
            flash("Could not save business settings.", "error")
        finally:
            connection.close()
        return redirect(url_for("admin_settings"))
    return render_template("settings.html", settings=get_business_settings())


# ==================================================
# ADMIN CUSTOMER MANAGEMENT
# ==================================================

@app.route("/admin/customers")
def admin_customers():
    connection = get_connection()
    try:
        customers = connection.execute("""
            SELECT c.*,
                   COUNT(DISTINCT o.id) AS order_count,
                   COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount ELSE 0 END),0) AS lifetime_value,
                   COALESCE(SUM(CASE WHEN o.status != 'cancelled' AND o.payment_status != 'paid' THEN o.total_amount ELSE 0 END),0) AS outstanding
            FROM customers c
            LEFT JOIN orders o ON o.customer_id=c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """).fetchall()
    finally:
        connection.close()
    return render_template("customers_admin.html", customers=customers)


# ==================================================
# ADMIN ALLERGEN MANAGEMENT
# ==================================================

@app.route("/admin/allergens", methods=["GET", "POST"])
def admin_allergens():
    connection = get_connection()
    try:
        if request.method == "POST":
            item_id = int(request.form.get("menu_item_id", "0"))
            selected = {x for x in request.form.getlist("allergens") if x in ALLERGENS}
            connection.execute("DELETE FROM menu_item_allergens WHERE menu_item_id=?", (item_id,))
            for code in selected:
                connection.execute("INSERT INTO menu_item_allergens (menu_item_id, allergen_code) VALUES (?,?)", (item_id, code))
            connection.commit()
            flash("Allergen information updated.", "success")
        items = connection.execute("""
            SELECT mi.id, mi.item_name, mi.item_name_german, m.meal_name, m.menu_date
            FROM menu_items mi JOIN menu m ON m.id=mi.menu_id
            WHERE m.is_active=1 ORDER BY m.menu_date, mi.id
        """).fetchall()
        allergen_rows = connection.execute("SELECT menu_item_id, allergen_code FROM menu_item_allergens").fetchall()
        selected = {}
        for row in allergen_rows:
            selected.setdefault(row["menu_item_id"], set()).add(row["allergen_code"])
    finally:
        connection.close()
    return render_template("allergens_admin.html", items=items, allergens=ALLERGENS, selected=selected)


# ==================================================
# ADMIN BACKUP
# ==================================================

@app.route("/admin/backup")
def admin_backup():
    from flask import send_file
    generate_excel_workbook()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(str(__import__('database').DATABASE_PATH), arcname="database.db")
        zf.write(str(EXCEL_PATH), arcname="RadheTiffin_Business.xlsx")
    memory.seek(0)
    filename = f"RadheTiffin_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(memory, as_attachment=True, download_name=filename, mimetype="application/zip")


# ==================================================
# PRODUCTION READINESS CHECK
# ==================================================

@app.route("/admin/production-readiness")
def admin_production_readiness():
    """Admin-only pre-launch checklist. Does not expose secret values."""
    checks = []

    def add_check(name, ok, detail, severity="required"):
        checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
            "severity": severity,
        })

    # Environment / security
    secret_from_env = bool(app.secret_key.strip())
    admin_password_from_env = bool(ADMIN_PASSWORD.strip())
    add_check(
        "Production secret key",
        secret_from_env,
        "RADHE_SECRET_KEY is configured." if secret_from_env else "Set RADHE_SECRET_KEY before production.",
    )
    add_check(
        "Admin password",
        admin_password_from_env,
        "RADHE_ADMIN_PASSWORD is configured." if admin_password_from_env else "Set a strong RADHE_ADMIN_PASSWORD before production.",
    )
    add_check(
        "HTTPS public URL",
        PUBLIC_BASE_URL.startswith("https://"),
        f"PUBLIC_BASE_URL = {PUBLIC_BASE_URL}" if PUBLIC_BASE_URL.startswith("https://") else "Set PUBLIC_BASE_URL to the final HTTPS production URL.",
    )

    # Business configuration
    settings = get_business_settings()
    required_business = {
        "Business name": settings.get("business_name"),
        "Legal name": settings.get("legal_name"),
        "Owner name": settings.get("owner_name"),
        "Business address": settings.get("address"),
        "City": settings.get("city"),
        "Postal code": settings.get("postal_code"),
        "Business email": settings.get("email"),
        "Business phone": settings.get("phone"),
    }
    missing_business = [name for name, value in required_business.items() if not str(value or "").strip()]
    add_check(
        "Business identity",
        not missing_business,
        "Business identity is complete." if not missing_business else "Missing: " + ", ".join(missing_business),
    )

    bank_ok = (
        BANK_ACCOUNT_HOLDER.strip()
        and BANK_IBAN.strip()
        and BANK_BIC.strip()
        and "ADD-YOUR" not in BANK_IBAN.upper()
        and "ADD-YOUR" not in BANK_BIC.upper()
    )
    add_check(
        "Bank transfer details",
        bank_ok,
        "Bank transfer details are configured." if bank_ok else "Replace placeholder bank holder/IBAN/BIC values before accepting bank transfers.",
    )

    # Data/configuration checks
    connection = get_connection()
    try:
        active_menu_count = connection.execute("SELECT COUNT(*) AS c FROM menu WHERE is_active=1").fetchone()["c"]
        active_slot_count = connection.execute("SELECT COUNT(*) AS c FROM pickup_slots WHERE is_active=1").fetchone()["c"]
        order_count = connection.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
        customer_count = connection.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
        allergen_count = connection.execute("SELECT COUNT(*) AS c FROM menu_item_allergens").fetchone()["c"]
    finally:
        connection.close()

    add_check(
        "Active menu",
        active_menu_count > 0,
        f"{active_menu_count} active menu day(s) configured." if active_menu_count else "Add and verify the final active weekly menu before launch.",
    )
    add_check(
        "Pickup capacity",
        active_slot_count > 0,
        f"{active_slot_count} active pickup slot(s) configured." if active_slot_count else "Configure and verify pickup slots/capacity before launch.",
    )
    add_check(
        "Allergen data review",
        allergen_count > 0,
        f"{allergen_count} dish-level allergen assignment(s) exist; manually verify every active dish before launch." if allergen_count else "No verified dish-level allergens are recorded; complete the allergen review before launch.",
        "review",
    )
    add_check(
        "Test/sample data review",
        order_count == 0,
        f"{order_count} order(s) currently exist. Review/delete test orders before going live." if order_count else "No orders currently exist.",
        "review",
    )

    # Storage / Excel
    from database import DATABASE_PATH
    db_ok = os.path.exists(DATABASE_PATH) and os.access(DATABASE_PATH, os.W_OK)
    add_check(
        "Database storage",
        db_ok,
        "Database exists and is writable." if db_ok else "Database path is missing or not writable.",
    )
    excel_ok = os.path.exists(EXCEL_PATH) and os.access(EXCEL_PATH, os.W_OK)
    add_check(
        "Excel report storage",
        excel_ok,
        "Excel workbook exists and is writable." if excel_ok else "Excel workbook is missing or not writable; it will be regenerated when possible.",
        "review",
    )

    # Stripe is optional until online card payments are enabled.
    stripe_ok = bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)
    add_check(
        "Stripe configuration",
        stripe_ok,
        "Stripe secret and webhook secret are configured." if stripe_ok else "Stripe is not fully configured. This is OK while card payments are intentionally disabled; configure test keys before enabling Stripe.",
        "optional",
    )

    required = [c for c in checks if c["severity"] == "required"]
    passed_required = sum(c["ok"] for c in required)
    review_items = [c for c in checks if c["severity"] == "review" and not c["ok"]]
    required_ready = passed_required == len(required)
    overall_ready = required_ready and not review_items

    return render_template(
        "production_readiness.html",
        checks=checks,
        required_ready=required_ready,
        overall_ready=overall_ready,
        passed_required=passed_required,
        required_total=len(required),
        order_count=order_count,
        customer_count=customer_count,
        stripe_configured=stripe_ok,
    )


# ==================================================
# LEGAL / CUSTOMER INFORMATION PAGES
# ==================================================

@app.route("/impressum")
def impressum():
    return render_template("impressum.html")


@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")


@app.route("/agb")
def agb():
    return render_template("agb.html")


@app.route("/allergene")
def allergene():
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT m.menu_date, m.day_name, m.meal_name, mi.item_name, mia.allergen_code
            FROM menu m
            JOIN menu_items mi ON mi.menu_id=m.id
            LEFT JOIN menu_item_allergens mia ON mia.menu_item_id=mi.id
            WHERE m.is_active=1
            ORDER BY m.menu_date, mi.id, mia.allergen_code
        """).fetchall()
    finally:
        connection.close()
    grouped = {}
    for row in rows:
        key=(row["menu_date"],row["day_name"],row["meal_name"],row["item_name"])
        grouped.setdefault(key,[]);
        if row["allergen_code"]: grouped[key].append(ALLERGENS.get(row["allergen_code"],row["allergen_code"]))
    return render_template("allergene.html", grouped=grouped, allergens=ALLERGENS)


@app.route("/kontakt")
def kontakt():
    return render_template("kontakt.html")


# ==================================================
# HEALTH CHECK
# ==================================================

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# ==================================================
# START APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )