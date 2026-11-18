import os
import time
from datetime import datetime, date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling, Error

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "user": os.getenv("DB_USER", "campus"),
    "password": os.getenv("DB_PASSWORD", "campuspass"),
    "database": os.getenv("DB_NAME", "smart_campus"),
    "port": int(os.getenv("DB_PORT", "3306")),
}

pool = None


def get_pool():
    global pool
    if pool is None:
        for _ in range(30):
            try:
                pool = pooling.MySQLConnectionPool(
                    pool_name="campus_pool",
                    pool_size=10,
                    **DB_CONFIG
                )
                break
            except Error:
                time.sleep(2)
        if pool is None:
            raise RuntimeError("Database is unavailable. Check the db container.")
    return pool


def conn():
    return get_pool().get_connection()


def audit(c, actor, action, entity, entity_id, details=""):
    cur = c.cursor()
    cur.execute(
        """INSERT INTO audit_logs
           (actor, action, entity_type, entity_id, details)
           VALUES (%s, %s, %s, %s, %s)""",
        (actor, action, entity, entity_id, details)
    )
    cur.close()


def fail(message, status=400):
    return jsonify({"error": message}), status


def close_db(c=None, cur=None):
    if cur is not None:
        try:
            cur.close()
        except Exception:
            pass
    if c is not None:
        try:
            c.close()
        except Exception:
            pass


def iso_dates(data, fields):
    for item in data:
        for field in fields:
            value = item.get(field)
            if value is not None and hasattr(value, "isoformat"):
                item[field] = value.isoformat()
    return data


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    c = conn()
    c.close()
    return jsonify({"status": "ok", "service": "smart-campus-api"})


@app.get("/api/facilities")
def facilities():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM facilities ORDER BY name")
        return jsonify(cur.fetchall())
    finally:
        close_db(c, cur)


@app.get("/api/dashboard")
def dashboard():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        result = {}
        for table, key in [
            ("facilities", "facilities"),
            ("bookings", "bookings"),
            ("tickets", "tickets"),
            ("approvals", "pending_approvals"),
            ("equipment_loans", "equipment_loans"),
        ]:
            if table == "approvals":
                cur.execute("SELECT COUNT(*) AS n FROM approvals WHERE status='PENDING'")
            else:
                # Table names come only from the fixed list above.
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            result[key] = cur.fetchone()["n"]

        cur.execute("SELECT status, COUNT(*) AS count FROM tickets GROUP BY status")
        result["ticket_status"] = cur.fetchall()
        return jsonify(result)
    finally:
        close_db(c, cur)


@app.get("/api/bookings")
def list_bookings():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute(
            """SELECT b.*, f.name AS facility_name
               FROM bookings b
               JOIN facilities f ON f.id=b.facility_id
               ORDER BY b.start_time DESC LIMIT 100"""
        )
        data = cur.fetchall()
        iso_dates(data, ["start_time", "end_time", "created_at"])
        return jsonify(data)
    finally:
        close_db(c, cur)


@app.post("/api/bookings")
def create_booking():
    d = request.get_json(silent=True) or {}
    required = ["facility_id", "user_name", "start_time", "end_time", "purpose"]
    if any(not d.get(k) for k in required):
        return fail("All booking fields are required.")

    c = None
    cur = None
    try:
        start = datetime.fromisoformat(d["start_time"])
        end = datetime.fromisoformat(d["end_time"])
        if end <= start:
            return fail("End time must be after start time.")

        c = conn()
        c.start_transaction()
        cur = c.cursor(dictionary=True)

        # Lock the facility row so simultaneous bookings for the same facility serialize.
        cur.execute("SELECT id FROM facilities WHERE id=%s FOR UPDATE", (d["facility_id"],))
        if not cur.fetchone():
            c.rollback()
            return fail("Facility not found.", 404)

        cur.execute(
            """SELECT id FROM bookings
               WHERE facility_id=%s
                 AND status IN ('REQUESTED','APPROVED','CONFIRMED','IN_USE')
                 AND start_time < %s AND end_time > %s
               FOR UPDATE""",
            (d["facility_id"], end, start)
        )
        if cur.fetchone():
            c.rollback()
            return fail("This facility already has an overlapping booking.", 409)

        status = "REQUESTED" if d.get("restricted") else "CONFIRMED"
        cur.execute(
            """INSERT INTO bookings
               (facility_id,user_name,start_time,end_time,purpose,status)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (d["facility_id"], d["user_name"], start, end, d["purpose"], status)
        )
        booking_id = cur.lastrowid

        if d.get("restricted"):
            cur.execute(
                """INSERT INTO approvals
                   (request_type,request_id,requested_by,status)
                   VALUES ('BOOKING',%s,%s,'PENDING')""",
                (booking_id, d["user_name"])
            )

        audit(c, d["user_name"], "BOOKING_CREATED", "booking", booking_id, status)
        c.commit()
        return jsonify({"id": booking_id, "status": status}), 201

    except ValueError:
        if c:
            c.rollback()
        return fail("Use a valid date and time.")
    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Booking creation failed")
        return fail("Could not create booking. Check the server logs.", 500)
    finally:
        close_db(c, cur)


@app.get("/api/tickets")
def tickets():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 100")
        data = cur.fetchall()
        iso_dates(data, ["created_at"])
        return jsonify(data)
    finally:
        close_db(c, cur)


@app.post("/api/tickets")
def create_ticket():
    d = request.get_json(silent=True) or {}
    if not all(d.get(k) for k in ["title", "description", "reported_by"]):
        return fail("Title, description and reporter are required.")

    text = (d["title"] + " " + d["description"]).lower()
    category = (
        "ELECTRICAL"
        if any(w in text for w in ["power", "light", "electric", "socket"])
        else "PLUMBING"
        if any(w in text for w in ["water", "tap", "leak", "pipe"])
        else "GENERAL"
    )
    priority = (
        "HIGH"
        if any(w in text for w in ["urgent", "danger", "smoke", "flood"])
        else "MEDIUM"
    )
    event_id = d.get("event_id")

    c = None
    cur = None
    try:
        c = conn()
        c.start_transaction()
        cur = c.cursor(dictionary=True)

        # Unique source_event_id in MySQL is the final duplicate protection.
        if event_id:
            cur.execute("SELECT id FROM tickets WHERE source_event_id=%s FOR UPDATE", (event_id,))
            existing = cur.fetchone()
            if existing:
                c.commit()
                return jsonify({"id": existing["id"], "duplicate": True}), 200

        cur.execute(
            """INSERT INTO tickets
               (title,description,category,priority,status,reported_by,source_event_id)
               VALUES (%s,%s,%s,%s,'OPEN',%s,%s)""",
            (d["title"], d["description"], category, priority, d["reported_by"], event_id)
        )
        ticket_id = cur.lastrowid
        audit(c, d["reported_by"], "TICKET_CREATED", "ticket", ticket_id, f"{category}/{priority}")
        c.commit()
        return jsonify({
            "id": ticket_id,
            "category": category,
            "priority": priority,
            "status": "OPEN"
        }), 201

    except mysql.connector.IntegrityError:
        if c:
            c.rollback()
        # A concurrent retry may have inserted the same event ID.
        if event_id:
            lookup = conn()
            lookup_cur = lookup.cursor(dictionary=True)
            try:
                lookup_cur.execute("SELECT id FROM tickets WHERE source_event_id=%s", (event_id,))
                existing = lookup_cur.fetchone()
                if existing:
                    return jsonify({"id": existing["id"], "duplicate": True}), 200
            finally:
                close_db(lookup, lookup_cur)
        return fail("Could not save the ticket because of a duplicate or invalid value.", 409)
    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Ticket creation failed")
        return fail("Could not create ticket. Check the server logs.", 500)
    finally:
        close_db(c, cur)


@app.patch("/api/tickets/<int:tid>")
def update_ticket(tid):
    d = request.get_json(silent=True) or {}
    actor = d.get("actor", "technician")
    allowed = {
        "OPEN": ["ASSIGNED"],
        "ASSIGNED": ["INSPECTION"],
        "INSPECTION": ["PENDING_WORK", "RESOLVED"],
        "PENDING_WORK": ["INSPECTION", "RESOLVED"],
        "RESOLVED": ["CLOSED"],
    }

    c = None
    cur = None
    try:
        c = conn()
        c.start_transaction()
        cur = c.cursor(dictionary=True)
        cur.execute("SELECT * FROM tickets WHERE id=%s FOR UPDATE", (tid,))
        ticket = cur.fetchone()

        if not ticket:
            c.rollback()
            return fail("Ticket not found.", 404)

        new_status = d.get("status", ticket["status"])
        if new_status != ticket["status"] and new_status not in allowed.get(ticket["status"], []):
            c.rollback()
            return fail(
                f"Invalid transition: {ticket['status']} to {new_status}.",
                409
            )

        if new_status == "CLOSED" and d.get("role") not in ["ADMIN", "MANAGER"]:
            c.rollback()
            return fail("Only an administrator or manager can close a ticket.", 403)

        cur.execute(
            """UPDATE tickets
               SET status=%s,
                   assigned_to=COALESCE(%s,assigned_to),
                   inspection_notes=COALESCE(%s,inspection_notes),
                   resolution=COALESCE(%s,resolution),
                   version=version+1
               WHERE id=%s""",
            (
                new_status,
                d.get("assigned_to"),
                d.get("inspection_notes"),
                d.get("resolution"),
                tid,
            )
        )
        audit(c, actor, "TICKET_UPDATED", "ticket", tid, f"{ticket['status']} -> {new_status}")
        c.commit()
        return jsonify({"id": tid, "status": new_status})

    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Ticket update failed")
        return fail("Could not update ticket. Check the server logs.", 500)
    finally:
        close_db(c, cur)


@app.get("/api/approvals")
def approvals():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM approvals ORDER BY created_at DESC")
        data = cur.fetchall()
        iso_dates(data, ["created_at"])
        return jsonify(data)
    finally:
        close_db(c, cur)


@app.patch("/api/approvals/<int:aid>")
def decide_approval(aid):
    d = request.get_json(silent=True) or {}
    if d.get("role") not in ["ADMIN", "MANAGER", "APPROVER"]:
        return fail("Approver role required.", 403)

    decision = d.get("decision")
    if decision not in ["APPROVED", "REJECTED"]:
        return fail("Decision must be APPROVED or REJECTED.")

    c = None
    cur = None
    try:
        c = conn()
        c.start_transaction()
        cur = c.cursor(dictionary=True)
        cur.execute("SELECT * FROM approvals WHERE id=%s FOR UPDATE", (aid,))
        approval = cur.fetchone()

        if not approval:
            c.rollback()
            return fail("Approval not found.", 404)
        if approval["status"] != "PENDING":
            c.rollback()
            return fail("Approval already decided.", 409)

        cur.execute(
            """UPDATE approvals
               SET status=%s, decided_by=%s, comments=%s
               WHERE id=%s""",
            (decision, d.get("actor", "approver"), d.get("comments", ""), aid)
        )

        if approval["request_type"] == "BOOKING":
            cur.execute(
                "UPDATE bookings SET status=%s WHERE id=%s",
                ("APPROVED" if decision == "APPROVED" else "CANCELLED", approval["request_id"])
            )

        audit(
            c,
            d.get("actor", "approver"),
            "APPROVAL_" + decision,
            "approval",
            aid,
            d.get("comments", "")
        )
        c.commit()
        return jsonify({"id": aid, "status": decision})

    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Approval update failed")
        return fail("Could not update approval. Check the server logs.", 500)
    finally:
        close_db(c, cur)


@app.post("/api/sensor-events")
def sensor_event():
    d = request.get_json(silent=True) or {}
    if not d.get("event_id"):
        return fail("event_id is required for safe retries.")

    payload = {
        "title": d.get("title", "Sensor alert"),
        "description": d.get("description", "Threshold exceeded"),
        "reported_by": "SENSOR",
        "event_id": d["event_id"],
    }
    # Reuse the ticket creation logic with a controlled request context.
    with app.test_request_context(json=payload):
        return create_ticket()


@app.get("/api/equipment-loans")
def get_equipment_loans():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM equipment_loans ORDER BY created_at DESC LIMIT 200")
        data = cur.fetchall()
        iso_dates(data, ["checkout_date", "due_date", "return_date", "created_at"])
        return jsonify(data)
    finally:
        close_db(c, cur)


@app.post("/api/equipment-loans")
def create_equipment_loan():
    d = request.get_json(silent=True) or {}
    required = ["equipment_name", "borrower_name", "checkout_date", "due_date"]
    if any(not d.get(key) for key in required):
        return fail("Equipment, borrower, checkout date and due date are required.")

    try:
        checkout_date = date.fromisoformat(d["checkout_date"])
        due_date = date.fromisoformat(d["due_date"])
        quantity = int(d.get("quantity", 1))
    except (ValueError, TypeError):
        return fail("Enter valid dates and a whole-number quantity.")

    if due_date < checkout_date:
        return fail("Due date cannot be earlier than checkout date.")
    if quantity < 1:
        return fail("Quantity must be at least 1.")

    c = None
    cur = None
    try:
        c = conn()
        c.start_transaction()
        cur = c.cursor()
        cur.execute(
            """INSERT INTO equipment_loans
               (equipment_name, borrower_name, department, quantity,
                checkout_date, due_date, status)
               VALUES (%s,%s,%s,%s,%s,%s,'REQUESTED')""",
            (
                d["equipment_name"].strip(),
                d["borrower_name"].strip(),
                d.get("department") or None,
                quantity,
                checkout_date,
                due_date,
            )
        )
        loan_id = cur.lastrowid
        audit(
            c,
            d["borrower_name"].strip(),
            "LOAN_REQUESTED",
            "equipment_loan",
            loan_id,
            f"{d['equipment_name']} / quantity {quantity}"
        )
        c.commit()
        return jsonify({"id": loan_id, "status": "REQUESTED"}), 201

    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Equipment loan creation failed")
        return fail("Could not create equipment loan. Check the entered details.", 500)
    finally:
        close_db(c, cur)


@app.patch("/api/equipment-loans/<int:loan_id>")
def update_equipment_loan(loan_id):
    d = request.get_json(silent=True) or {}
    new_status = d.get("status")
    transitions = {
        "REQUESTED": ["APPROVED", "REJECTED"],
        "APPROVED": ["ISSUED", "REJECTED"],
        "ISSUED": ["RETURNED"],
        "RETURNED": [],
        "REJECTED": [],
    }
    if new_status not in ["APPROVED", "ISSUED", "RETURNED", "REJECTED"]:
        return fail("Status must be APPROVED, ISSUED, RETURNED or REJECTED.")

    c = None
    cur = None
    try:
        c = conn()
        c.start_transaction()
        cur = c.cursor(dictionary=True)
        cur.execute(
            "SELECT id, status FROM equipment_loans WHERE id=%s FOR UPDATE",
            (loan_id,)
        )
        loan = cur.fetchone()

        if not loan:
            c.rollback()
            return fail("Equipment loan not found.", 404)

        if new_status not in transitions.get(loan["status"], []):
            c.rollback()
            return fail(
                f"Invalid loan transition: {loan['status']} to {new_status}.",
                409
            )

        if new_status == "RETURNED":
            cur.execute(
                """UPDATE equipment_loans
                   SET status=%s, return_date=CURDATE()
                   WHERE id=%s""",
                (new_status, loan_id)
            )
        else:
            cur.execute(
                "UPDATE equipment_loans SET status=%s WHERE id=%s",
                (new_status, loan_id)
            )

        actor = d.get("actor", "MANAGER")
        audit(
            c,
            actor,
            "LOAN_STATUS_UPDATED",
            "equipment_loan",
            loan_id,
            f"{loan['status']} -> {new_status}"
        )
        c.commit()
        return jsonify({"id": loan_id, "status": new_status})

    except Exception:
        if c:
            c.rollback()
        app.logger.exception("Equipment loan status update failed")
        return fail("Could not update equipment loan. Check the server logs.", 500)
    finally:
        close_db(c, cur)


@app.get("/api/audit")
def audit_logs():
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100")
        data = cur.fetchall()
        iso_dates(data, ["created_at"])
        return jsonify(data)
    finally:
        close_db(c, cur)


@app.get("/api/devops")
def devops():
    return jsonify({
        "mode": "LOCAL_SIMULATION",
        "issue": "SC-001",
        "release": "v1.0.0",
        "status": "DEMO_READY",
        "note": "Local demonstration record; no external issue tracker is connected."
    })


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
