"""
SmartPark core logic
=====================
The same 8 modules and data structures from the Task 1 design document,
refactored as an importable package so both the CLI prototype and the
Flask web app share one implementation.

    1. Slot Management        -> hash map + min-heap        (SlotManager)
    2. Entry / Registration   -> hash map plate -> session   (ParkingSystem)
    3. Duration & Fee Calc    -> sorted array + binary search (RateConfig)
    4. Payment Processing     -> FIFO queue + txn hash map   (PaymentProcessor)
    5. Barrier Control        -> event-driven state flag     (Barrier)
    6. Rate Configuration     -> editable sorted array        (RateConfig)
    7. Reporting & Audit      -> append-only log              (AuditLog)
    8. Display                -> reads live counts             (SlotManager.free_count)
"""

import heapq
import bisect
from collections import deque
from datetime import datetime, timedelta


class RateConfig:
    """Fixed time bands with editable amounts only."""

    def __init__(self):
        # Time bands are fixed for the assignment and should remain constant.
        self.tiers = [
            (30, 0),
            (120, 50),
            (240, 100),
            (360, 300),
            (float("inf"), 500),
        ]

    def update_fee_for_tier(self, max_minutes, fee):
        """Update the fee for a fixed time band without changing the time threshold."""
        normalized = float("inf") if max_minutes == float("inf") or max_minutes == "inf" else float(max_minutes)
        for index, (current_max, _) in enumerate(self.tiers):
            if current_max == normalized:
                self.tiers[index] = (current_max, fee)
                return

    def get_fee(self, duration_minutes):
        """Binary search for the first tier whose max_minutes >= duration."""
        thresholds = [t[0] for t in self.tiers]
        index = bisect.bisect_left(thresholds, duration_minutes)
        if index == len(self.tiers):
            index = len(self.tiers) - 1
        return self.tiers[index][1]

    def as_list(self):
        """Human-readable view for the admin page."""
        return [
            {"max_minutes": ("∞" if m == float("inf") else int(m)), "fee": f}
            for m, f in self.tiers
        ]


class SlotManager:
    """hash map for O(1) status lookup + min-heap for O(log n) allocation."""

    def __init__(self, total_bays):
        self.status_map = {bay_id: "FREE" for bay_id in range(1, total_bays + 1)}
        self.free_heap = list(self.status_map.keys())
        heapq.heapify(self.free_heap)

    def allocate_bay(self):
        if not self.free_heap:
            return None
        bay_id = heapq.heappop(self.free_heap)
        self.status_map[bay_id] = "OCCUPIED"
        return bay_id

    def release_bay(self, bay_id):
        self.status_map[bay_id] = "FREE"
        heapq.heappush(self.free_heap, bay_id)

    def free_count(self):
        return len(self.free_heap)

    def total_bays(self):
        return len(self.status_map)

    def snapshot(self):
        """Full per-bay status, sorted by bay id, for the display board grid."""
        return [{"bay_id": b, "status": s} for b, s in sorted(self.status_map.items())]


class AuditLog:
    """Append-only transaction log for VAT reconciliation."""

    VAT_RATE = 0.16

    def __init__(self):
        self.records = []

    def record(self, plate, entry_time, exit_time, fee, method):
        vat = round(fee * self.VAT_RATE / (1 + self.VAT_RATE), 2)
        self.records.append({
            "plate": plate,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "duration_min": round((exit_time - entry_time).total_seconds() / 60, 1),
            "fee": fee,
            "vat": vat,
            "method": method,
            "timestamp": datetime.now(),
        })

    def totals(self):
        return {
            "total_fee": sum(r["fee"] for r in self.records),
            "total_vat": round(sum(r["vat"] for r in self.records), 2),
            "count": len(self.records),
        }


class Barrier:
    """Event-driven state flag - opens only on confirmed payment."""

    def __init__(self):
        self.state = "CLOSED"
        self.last_event = None

    def open_barrier(self, plate):
        self.state = "OPEN"
        self.last_event = f"Barrier opened for {plate}"

    def close_barrier(self):
        self.state = "CLOSED"


class PaymentProcessor:
    """FIFO queue for exit-lane order + hash map of completed transactions."""

    def __init__(self, audit_log: AuditLog, barrier: Barrier, slot_manager: SlotManager):
        self.pending_queue = deque()
        self.completed_txns = {}
        self.audit_log = audit_log
        self.barrier = barrier
        self.slot_manager = slot_manager
        self._next_id = 1

    def enqueue_transaction(self, session, fee, method):
        txn_id = self._next_id
        self._next_id += 1
        self.pending_queue.append({
            "txn_id": txn_id, "session": session, "fee": fee, "method": method
        })
        return txn_id

    def process_next(self):
        """Confirms payment for the transaction at the front of the queue."""
        if not self.pending_queue:
            return None
        txn = self.pending_queue.popleft()
        confirmed = self._confirm_payment(txn["method"], txn["fee"])
        if confirmed:
            self.completed_txns[txn["txn_id"]] = txn
            session = txn["session"]
            self.audit_log.record(
                session["plate"], session["entry_time"], session["exit_time"],
                txn["fee"], txn["method"]
            )
            self.barrier.open_barrier(session["plate"])
            self.slot_manager.release_bay(session["bay_id"])
            return txn
        else:
            self.pending_queue.appendleft(txn)
            return None

    def _confirm_payment(self, method, fee):
        # Simulated gateway confirmation - swap for the real M-Pesa/card API here.
        return True


class ParkingSystem:
    """Orchestrates all modules - one shared instance backs both CLI and web."""

    def __init__(self, total_bays=20):
        self.slot_manager = SlotManager(total_bays)
        self.rate_config = RateConfig()
        self.audit_log = AuditLog()
        self.barrier = Barrier()
        self.payment_processor = PaymentProcessor(self.audit_log, self.barrier, self.slot_manager)
        self.active_sessions = {}  # plate -> {entry_time, bay_id}

    def register_entry(self, plate):
        """Returns (success, bay_id_or_None, message)."""
        plate = plate.strip().upper()
        if not plate:
            return False, None, "Plate number is required."
        if plate in self.active_sessions:
            return False, None, f"{plate} already has an active session."
        bay_id = self.slot_manager.allocate_bay()
        if bay_id is None:
            return False, None, "Parking is full - no bays available."
        self.active_sessions[plate] = {"entry_time": datetime.now(), "bay_id": bay_id}
        return True, bay_id, f"{plate} allocated Bay {bay_id}."

    def process_exit(self, plate, method="MPESA", simulated_minutes=None):
        """Returns (success, fee_or_None, message)."""
        plate = plate.strip().upper()
        session = self.active_sessions.get(plate)
        if not session:
            return False, None, f"No active session found for {plate}."

        exit_time = datetime.now()
        if simulated_minutes:
            exit_time = session["entry_time"] + timedelta(minutes=float(simulated_minutes))

        duration = (exit_time - session["entry_time"]).total_seconds() / 60
        fee = self.rate_config.get_fee(duration)

        session["exit_time"] = exit_time
        session["plate"] = plate

        self.payment_processor.enqueue_transaction(session, fee, method)
        self.payment_processor.process_next()

        del self.active_sessions[plate]
        return True, fee, f"{plate} paid Kshs {fee} ({round(duration,1)} min) via {method}. Barrier open."
