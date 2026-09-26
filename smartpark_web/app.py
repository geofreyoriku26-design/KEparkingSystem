"""
SmartPark Web - Flask front end for the Modern Parking System

Multimedia University of Kenya - Data Structures & Algorithms

Routes:
    GET  /                 -> dashboard: display board, entry form, exit form
    POST /entry             -> Module 2: register a vehicle on arrival
    POST /exit               -> Modules 3+4+5: fee calc, payment, barrier
    GET  /api/status         -> Module 8: JSON feed for the live display board
    GET  /admin               -> Module 6+7: rate configuration + audit report
    POST /admin/rate          -> Module 6: add/update a fee tier

Run with:  python app.py    (visit http://127.0.0.1:5000)

NOTE: this is a single-process, in-memory prototype (state lives in the
`system` object below). Task 1's database design shows how this maps onto
persistent tables (Bay, ParkingSession, RateTier, Payment, AuditRecord)
for production use.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from core.parking_system import ParkingSystem

app = Flask(__name__)
app.secret_key = "smartpark-dev-secret"  # replace with a real secret in production

# One shared in-memory system instance - the "database" for this prototype.
system = ParkingSystem(total_bays=20)


@app.route("/")
def dashboard():
    return render_template(
        "index.html",
        free_count=system.slot_manager.free_count(),
        total_bays=system.slot_manager.total_bays(),
        bays=system.slot_manager.snapshot(),
        active_sessions=system.active_sessions,
        barrier_state=system.barrier.state,
    )


@app.route("/entry", methods=["POST"])
def entry():
    plate = request.form.get("plate", "")
    success, bay_id, message = system.register_entry(plate)
    flash(message, "success" if success else "error")
    return redirect(url_for("dashboard"))


@app.route("/exit", methods=["POST"])
def exit_vehicle():
    plate = request.form.get("plate", "")
    method = request.form.get("method", "MPESA")
    simulated_minutes = request.form.get("simulated_minutes") or None
    success, fee, message = system.process_exit(plate, method, simulated_minutes)
    flash(message, "success" if success else "error")
    return redirect(url_for("dashboard"))


@app.route("/api/status")
def api_status():
    """Polled by the dashboard's JavaScript to refresh the live board."""
    return jsonify({
        "free": system.slot_manager.free_count(),
        "total": system.slot_manager.total_bays(),
        "barrier": system.barrier.state,
    })


@app.route("/admin")
def admin():
    return render_template(
        "admin.html",
        tiers=system.rate_config.as_list(),
        records=list(reversed(system.audit_log.records)),
        totals=system.audit_log.totals(),
    )


@app.route("/admin/rate", methods=["POST"])
def update_rate():
    try:
        max_minutes_raw = request.form.get("max_minutes", "").strip()
        fee = float(request.form.get("fee", "0"))
        if not max_minutes_raw:
            flash("Please choose a fixed time band before saving the fee.", "error")
            return redirect(url_for("admin"))

        max_minutes = float("inf") if max_minutes_raw == "inf" else float(max_minutes_raw)
        system.rate_config.update_fee_for_tier(max_minutes, fee)
        label = "∞" if max_minutes == float("inf") else str(int(max_minutes))
        flash(f"Fee updated: up to {label} min -> Kshs {fee}", "success")
    except ValueError:
        flash("Invalid fee value - please enter numbers only.", "error")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
