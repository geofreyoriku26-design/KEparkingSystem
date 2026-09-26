"""
SmartPark - Modern Parking Management System
==============================================
Multimedia University of Kenya - Data Structures & Algorithms

CLI / in-memory prototype implementing the 8 modules identified in the
Task 1 design document:
    1. Slot Management        -> hash map + min-heap
    2. Entry / Registration   -> hash map (plate -> session)
    3. Duration & Fee Calc    -> sorted array + binary search
    4. Payment Processing     -> FIFO queue + hash map of completed txns
    5. Barrier Control        -> state flag, event-driven
    6. Rate Configuration     -> editable sorted array (no code change)
    7. Reporting & Audit      -> append-only log
    8. Display                -> reads live counts from Slot Management

This version simulates hardware (barrier, sensors, display board) and
payment gateways (M-Pesa/card) with console output, so the algorithms
and data structures can be demonstrated end-to-end without external
infrastructure. Swapping the simulated I/O for real APIs/hardware does
not require changing the module structure.
"""

import heapq
import bisect
from collections import deque
from datetime import datetime, timedelta


# ---------------------------------------------------------------------
# Module 6: Rate Configuration
# ---------------------------------------------------------------------
class RateConfig:
    """
    Holds parking fee tiers as editable DATA (not hardcoded logic), so
    management can change pricing at any time without a software change.

    Data structure: sorted list of (max_minutes, fee) tuples, kept
    sorted by max_minutes so Fee Calculation can binary-search it.
    """

    def __init__(self):
        # Default tiers from the client's terms of reference.
        # (max_minutes_inclusive, fee_in_kshs)
        self.tiers = [
            (30, 0),
            (120, 50),
            (240, 100),
            (360, 300),
            (float("inf"), 500),
        ]

    def add_or_update_tier(self, max_minutes, fee):
        """Admin operation: insert or replace a tier, keep list sorted."""
        self.tiers = [t for t in self.tiers if t[0] != max_minutes]
        bisect.insort(self.tiers, (max_minutes, fee))
        print(f"[RateConfig] Tier updated: up to {max_minutes} min -> Kshs {fee}")

    def get_fee(self, duration_minutes):
        """
        Binary search for the first tier whose max_minutes >= duration.
        O(log n) instead of a linear if/elif chain, and correct even if
        management adds more tiers later.
        """
        thresholds = [t[0] for t in self.tiers]
        index = bisect.bisect_left(thresholds, duration_minutes)
        if index == len(self.tiers):
            index = len(self.tiers) - 1
        return self.tiers[index][1]

    def display(self):
        print("\nCurrent Rate Tiers:")
        prev = 0
        for max_minutes, fee in self.tiers:
            label = "∞" if max_minutes == float("inf") else str(int(max_minutes))
            print(f"  up to {label} min : Kshs {fee}")
            prev = max_minutes


# ---------------------------------------------------------------------
# Module 1: Slot Management
# ---------------------------------------------------------------------
class SlotManager:
    """
    Data structures:
      - status_map : hash map {bay_id: 'FREE' | 'OCCUPIED'}  -> O(1) status
      - free_heap  : min-heap of free bay_ids                -> O(log n) allocate
    """

    def __init__(self, total_bays):
        self.status_map = {bay_id: "FREE" for bay_id in range(1, total_bays + 1)}
        self.free_heap = list(self.status_map.keys())
        heapq.heapify(self.free_heap)

    def allocate_bay(self):
        if not self.free_heap:
            return None  # FULL
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


# ---------------------------------------------------------------------
# Module 8: Display
# ---------------------------------------------------------------------
class DisplayBoard:
    """Reads live counts from SlotManager - no separate data structure."""

    def __init__(self, slot_manager: SlotManager):
        self.slot_manager = slot_manager

    def show(self):
        free = self.slot_manager.free_count()
        total = self.slot_manager.total_bays()
        print(f"\n=== ENTRANCE DISPLAY BOARD ===")
        print(f"  Available Slots: {free} / {total}")
        print(f"===============================")


# ---------------------------------------------------------------------
# Module 7: Reporting & Audit
# ---------------------------------------------------------------------
class AuditLog:
    """Append-only log of confirmed transactions for VAT reconciliation."""

    VAT_RATE = 0.16  # 16% VAT (Kenya standard rate)

    def __init__(self):
        self.records = []  # append-only list

    def record(self, plate, entry_time, exit_time, fee, method):
        vat = round(fee * self.VAT_RATE / (1 + self.VAT_RATE), 2)
        entry = {
            "plate": plate,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "fee": fee,
            "vat": vat,
            "method": method,
            "timestamp": datetime.now(),
        }
        self.records.append(entry)  # never edited afterwards -> auditable

    def reconciliation_report(self):
        total_fee = sum(r["fee"] for r in self.records)
        total_vat = sum(r["vat"] for r in self.records)
        print("\n=== RECONCILIATION REPORT ===")
        for r in self.records:
            print(f"  {r['plate']:<10} Kshs {r['fee']:<6} (VAT {r['vat']}) via {r['method']}")
        print(f"  ------------------------------")
        print(f"  TOTAL COLLECTED : Kshs {total_fee}")
        print(f"  TOTAL VAT       : Kshs {round(total_vat, 2)}")
        print("==============================")


# ---------------------------------------------------------------------
# Module 5: Barrier Control
# ---------------------------------------------------------------------
class Barrier:
    """Simple event-driven state flag - opens only on confirmed payment."""

    def __init__(self):
        self.state = "CLOSED"

    def open_barrier(self):
        self.state = "OPEN"
        print("[Barrier] Payment confirmed -> Barrier OPEN. Vehicle may exit.")

    def close_barrier(self):
        self.state = "CLOSED"
        print("[Barrier] Vehicle cleared -> Barrier CLOSED.")


# ---------------------------------------------------------------------
# Module 4: Payment Processing
# ---------------------------------------------------------------------
class PaymentProcessor:
    """
    Data structures:
      - pending_queue   : FIFO queue (deque) - exit lane is first-come-first-served
      - completed_txns  : hash map {txn_id: transaction} for O(1) audit lookup
    """

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
        """Simulates confirming payment for the vehicle at the front of the queue."""
        if not self.pending_queue:
            print("[Payment] No pending transactions.")
            return
        txn = self.pending_queue.popleft()
        confirmed = self._confirm_payment(txn["method"], txn["fee"])
        if confirmed:
            self.completed_txns[txn["txn_id"]] = txn
            session = txn["session"]
            self.audit_log.record(
                session["plate"], session["entry_time"], session["exit_time"],
                txn["fee"], txn["method"]
            )
            self.barrier.open_barrier()
            self.slot_manager.release_bay(session["bay_id"])
        else:
            print("[Payment] Payment FAILED - vehicle remains at barrier.")
            self.pending_queue.appendleft(txn)  # retry later

    def _confirm_payment(self, method, fee):
        # Simulated gateway confirmation (would call real M-Pesa/card API)
        print(f"[Payment] Processing Kshs {fee} via {method}...")
        return True


# ---------------------------------------------------------------------
# Module 2 & 3: Entry / Registration + Duration & Fee Calculation
# ---------------------------------------------------------------------
class ParkingSystem:
    """Ties all modules together - the main orchestrator."""

    def __init__(self, total_bays):
        self.slot_manager = SlotManager(total_bays)
        self.rate_config = RateConfig()
        self.audit_log = AuditLog()
        self.barrier = Barrier()
        self.payment_processor = PaymentProcessor(self.audit_log, self.barrier, self.slot_manager)
        self.display = DisplayBoard(self.slot_manager)
        self.active_sessions = {}  # plate -> {entry_time, bay_id}

    def register_entry(self, plate):
        bay_id = self.slot_manager.allocate_bay()
        if bay_id is None:
            print(f"[Entry] REJECTED - Parking FULL. Vehicle {plate} cannot enter.")
            return
        entry_time = datetime.now()
        self.active_sessions[plate] = {"entry_time": entry_time, "bay_id": bay_id}
        print(f"[Entry] {plate} allocated Bay {bay_id} at {entry_time.strftime('%H:%M:%S')}")

    def process_exit(self, plate, method="MPESA", simulated_minutes=None):
        session = self.active_sessions.get(plate)
        if not session:
            print(f"[Exit] No active session found for {plate}.")
            return

        exit_time = datetime.now()
        if simulated_minutes is not None:
            # Allows demoing longer stays without waiting in real time
            exit_time = session["entry_time"] + timedelta(minutes=simulated_minutes)

        duration = (exit_time - session["entry_time"]).total_seconds() / 60
        fee = self.rate_config.get_fee(duration)

        session["exit_time"] = exit_time
        session["plate"] = plate
        print(f"[Exit] {plate} duration={round(duration,1)} min -> Fee = Kshs {fee}")

        self.payment_processor.enqueue_transaction(session, fee, method)
        self.payment_processor.process_next()

        del self.active_sessions[plate]


# ---------------------------------------------------------------------
# CLI Demo
# ---------------------------------------------------------------------
def main():
    system = ParkingSystem(total_bays=5)

    menu = """
--- SmartPark Menu ---
1. View slot display
2. Register vehicle entry
3. Process vehicle exit + payment
4. View / update rate tiers
5. View reconciliation report
6. Exit program
"""
    while True:
        print(menu)
        choice = input("Choose an option: ").strip()

        if choice == "1":
            system.display.show()
        elif choice == "2":
            plate = input("Enter vehicle plate number: ").strip().upper()
            system.register_entry(plate)
        elif choice == "3":
            plate = input("Enter vehicle plate number: ").strip().upper()
            method = input("Payment method (MPESA/CARD/CASH): ").strip().upper()
            sim = input("Simulate stay duration in minutes (blank = real time): ").strip()
            sim_minutes = float(sim) if sim else None
            system.process_exit(plate, method or "MPESA", sim_minutes)
        elif choice == "4":
            system.rate_config.display()
            update = input("Add/update a tier? (y/n): ").strip().lower()
            if update == "y":
                max_min = float(input("  Max minutes for this tier: "))
                fee = float(input("  Fee (Kshs): "))
                system.rate_config.add_or_update_tier(max_min, fee)
        elif choice == "5":
            system.audit_log.reconciliation_report()
        elif choice == "6":
            print("Goodbye.")
            break
        else:
            print("Invalid option, try again.")


if __name__ == "__main__":
    main()
