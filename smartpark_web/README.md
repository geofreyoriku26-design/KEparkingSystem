# SmartPark - Modern Parking System

A web-based parking management system built for Multimedia University of
Kenya's Data Structures & Algorithms Task 1/2 assignment.

## What it does

- Live slot availability board (entrance display + web view)
- Vehicle entry logging (plate, time, allocated bay)
- Automatic duration + fee calculation on exit (tiered rates)
- Simulated M-Pesa / card / cash payment, barrier opens on confirmation
- Admin page to change rate tiers at any time (no code change)
- Append-only audit log with VAT breakdown for reconciliation

## Project structure

```
smartpark_web/
├── app.py                  # Flask routes (the "web" layer)
├── core/
│   └── parking_system.py   # All 8 modules: slots, fees, payment, audit...
├── templates/
│   ├── base.html
│   ├── index.html           # Gate dashboard
│   └── admin.html           # Rate config + audit report
├── static/
│   └── style.css
├── parking_system_cli.py    # Standalone CLI version (same core logic)
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py


## Design notes

See `TASK1_Parking_System_Design.md` (in the repo root) for the module
breakdown, algorithms, data structure justifications, and the dynamic
database schema this prototype is modeled on.

This version keeps state in memory for a single process, which is enough
to demonstrate every module end-to-end. Swapping `core/parking_system.py`'s
in-memory dictionaries/queues for the SQL tables in the design document
(Bay, ParkingSession, RateTier, Payment, AuditRecord) is the next step for
a production deployment.
