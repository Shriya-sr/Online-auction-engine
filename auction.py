import threading
import time
import json
import os


class Auction:
    def __init__(
        self,
        item="Auction Item",
        duration_seconds=60,
        base_price=0.0,
        escalation_window_seconds=5,
        anti_sniping_window_seconds=5,
        anti_sniping_extension_seconds=5,
        state_file=None,
    ):
        self.item = item
        self.base_price = float(base_price)
        self.highest_bid = 0.0
        self.highest_bidder = None
        self.auction_active = False
        self.end_time = None
        self.lock = threading.Lock()

        self.escalation_window_seconds = escalation_window_seconds
        self.anti_sniping_window_seconds = anti_sniping_window_seconds
        self.anti_sniping_extension_seconds = anti_sniping_extension_seconds

        self.leading_bidders = set()
        self.escalation_active = False
        self.escalation_end_time = None
        self.escalation_blind_bids = {}

        self.bid_order = []
        self.first_valid_bid_time = {}
        self.reputation = {}

        self.default_duration_seconds = duration_seconds
        if state_file is None:
            state_file = os.path.join(os.path.dirname(__file__), "auction_state.json")
        self.state_file = state_file

        self._load_state()

    def _serialize_state(self):
        return {
            "item": self.item,
            "base_price": self.base_price,
            "highest_bid": self.highest_bid,
            "highest_bidder": self.highest_bidder,
            "auction_active": self.auction_active,
            "end_time": self.end_time,
            "escalation_active": self.escalation_active,
            "escalation_end_time": self.escalation_end_time,
            "escalation_blind_bids": {
                bidder: {"amount": amount, "ts": ts}
                for bidder, (amount, ts) in self.escalation_blind_bids.items()
            },
            "leading_bidders": sorted(list(self.leading_bidders)),
            "first_valid_bid_time": self.first_valid_bid_time,
            "reputation": self.reputation,
            "default_duration_seconds": self.default_duration_seconds,
            "escalation_window_seconds": self.escalation_window_seconds,
            "anti_sniping_window_seconds": self.anti_sniping_window_seconds,
            "anti_sniping_extension_seconds": self.anti_sniping_extension_seconds,
        }

    def _persist_state(self):
        payload = self._serialize_state()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _load_state(self):
        if not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.item = data.get("item", self.item)
            self.base_price = float(data.get("base_price", self.base_price))
            self.highest_bid = float(data.get("highest_bid", 0.0))
            self.highest_bidder = data.get("highest_bidder")
            self.auction_active = bool(data.get("auction_active", False))
            self.end_time = data.get("end_time")
            self.escalation_active = bool(data.get("escalation_active", False))
            self.escalation_end_time = data.get("escalation_end_time")
            self.escalation_blind_bids = {}
            for bidder, details in data.get("escalation_blind_bids", {}).items():
                self.escalation_blind_bids[bidder] = (
                    float(details.get("amount", 0.0)),
                    float(details.get("ts", 0.0)),
                )
            self.leading_bidders = set(data.get("leading_bidders", []))

            raw_first_times = data.get("first_valid_bid_time", {})
            self.first_valid_bid_time = {
                bidder: float(ts) for bidder, ts in raw_first_times.items()
            }

            self.reputation = {}
            for bidder, stats in data.get("reputation", {}).items():
                self.reputation[bidder] = {
                    "wins": int(stats.get("wins", 0)),
                    "valid_bids": int(stats.get("valid_bids", 0)),
                }

            self.default_duration_seconds = int(
                data.get("default_duration_seconds", self.default_duration_seconds)
            )
            self.escalation_window_seconds = int(
                data.get("escalation_window_seconds", self.escalation_window_seconds)
            )
        except Exception:
            # Start with in-memory defaults if persisted state is invalid.
            self.auction_active = False
            self.end_time = None
            self.escalation_active = False
            self.escalation_end_time = None
            self.escalation_blind_bids = {}
            self.leading_bidders = set()

    def start_auction(self, item=None, duration_seconds=None, base_price=None, escalation_window_seconds=None):
        with self.lock:
            if item:
                self.item = item

            if base_price is not None:
                self.base_price = float(base_price)

            if escalation_window_seconds is not None:
                self.escalation_window_seconds = int(escalation_window_seconds)

            duration = duration_seconds if duration_seconds is not None else self.default_duration_seconds
            self.default_duration_seconds = duration

            self.highest_bid = 0.0
            self.highest_bidder = None
            self.auction_active = True
            self.end_time = time.time() + duration
            self.escalation_active = False
            self.escalation_end_time = None
            self.escalation_blind_bids = {}
            self.leading_bidders = set()
            self.bid_order = []
            self.first_valid_bid_time = {}

            self._persist_state()
            return {
                "item": self.item,
                "duration_seconds": duration,
                "base_price": self.base_price,
                "escalation_window_seconds": self.escalation_window_seconds,
                "end_time": self.end_time,
            }

    def _ensure_bidder(self, bidder):
        if bidder not in self.reputation:
            self.reputation[bidder] = {"wins": 0, "valid_bids": 0}

    def _reputation_score(self, bidder):
        stats = self.reputation.get(bidder, {"wins": 0, "valid_bids": 0})
        # Weighted score: wins capture reliability, valid bids capture participation.
        return (2.0 * stats["wins"]) + (0.1 * stats["valid_bids"])

    def _maybe_extend_timer(self, now):
        time_left = self.end_time - now
        if time_left <= self.anti_sniping_window_seconds:
            self.end_time += self.anti_sniping_extension_seconds
            return True
        return False

    def _start_escalation(self, now):
        if not self.escalation_active:
            self.escalation_active = True
            self.escalation_end_time = now + self.escalation_window_seconds
        # Ensure escalation can complete even if auction was about to end.
        if self.end_time < self.escalation_end_time:
            self.end_time = self.escalation_end_time

    def _resolve_tie(self, candidates=None):
        if candidates is None:
            candidates = list(self.leading_bidders)
        else:
            candidates = list(candidates)

        if not candidates:
            return None, "No tied bidders available for resolution"

        scores = {bidder: self._reputation_score(bidder) for bidder in candidates}
        best_score = max(scores.values())
        best_bidders = [b for b in candidates if scores[b] == best_score]

        if len(best_bidders) == 1:
            winner = best_bidders[0]
            return winner, f"Tie resolved by reputation score ({best_score:.2f})"

        winner = min(
            best_bidders,
            key=lambda b: self.first_valid_bid_time.get(b, float("inf")),
        )
        return winner, "Tie resolved by FCFS among equal-reputation bidders"

    def _finalize_escalation_locked(self, now, force=False):
        if not self.escalation_active:
            return None

        if not force and now < self.escalation_end_time:
            return None

        self.escalation_active = False
        self.escalation_end_time = None

        winner = None
        reason = ""

        if self.escalation_blind_bids:
            highest_blind = max(amount for amount, _ in self.escalation_blind_bids.values())
            finalists = [
                bidder
                for bidder, (amount, _) in self.escalation_blind_bids.items()
                if amount == highest_blind
            ]
            self.highest_bid = max(self.highest_bid, highest_blind)

            if len(finalists) == 1:
                winner = finalists[0]
                reason = "Escalation resolved by highest blind bid"
            else:
                winner, tie_reason = self._resolve_tie(finalists)
                reason = f"Tie after escalation; {tie_reason}"
        else:
            winner, reason = self._resolve_tie(self.leading_bidders)

        self.highest_bidder = winner
        self.leading_bidders = {winner} if winner else set()
        self.escalation_blind_bids = {}
        self._persist_state()

        return {
            "winner": winner,
            "highest_bid": self.highest_bid,
            "reason": reason,
        }

    def place_bid(self, amount, bidder):
        with self.lock:
            if not self.auction_active:
                return {
                    "accepted": False,
                    "reason": "Auction not active. Wait for admin to start.",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": self.escalation_active,
                    "timer_extended": False,
                }

            now = time.time()
            self._ensure_bidder(bidder)

            if self.escalation_active:
                if amount <= self.highest_bid:
                    return {
                        "accepted": False,
                        "reason": "Escalation round requires a bid higher than current highest",
                        "highest_bid": self.highest_bid,
                        "highest_bidder": self.highest_bidder,
                        "tie": True,
                        "timer_extended": False,
                    }

                previous = self.escalation_blind_bids.get(bidder)
                if previous is not None and amount == previous[0]:
                    return {
                        "accepted": False,
                        "reason": "Duplicate escalation bid amount from same bidder",
                        "highest_bid": self.highest_bid,
                        "highest_bidder": self.highest_bidder,
                        "tie": True,
                        "timer_extended": False,
                    }

                self.reputation[bidder]["valid_bids"] += 1
                if bidder not in self.first_valid_bid_time:
                    self.first_valid_bid_time[bidder] = now
                self.bid_order.append((now, bidder, amount))

                if (
                    previous is None
                    or amount > previous[0]
                    or (amount == previous[0] and now < previous[1])
                ):
                    self.escalation_blind_bids[bidder] = (amount, now)

                self._persist_state()
                return {
                    "accepted": True,
                    "reason": "Blind escalation bid accepted",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": True,
                    "blind": True,
                    "escalation_end_time": self.escalation_end_time,
                    "timer_extended": False,
                }

            if self.highest_bid == 0.0 and amount < self.base_price:
                return {
                    "accepted": False,
                    "reason": f"Bid below base price ${self.base_price:.2f}",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": False,
                    "timer_extended": False,
                }

            if amount < self.highest_bid:
                return {
                    "accepted": False,
                    "reason": "Bid lower than current highest",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": self.escalation_active,
                    "timer_extended": False,
                }

            if amount == self.highest_bid and bidder == self.highest_bidder:
                return {
                    "accepted": False,
                    "reason": "Duplicate bid amount from same bidder",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": self.escalation_active,
                    "timer_extended": False,
                }

            self.reputation[bidder]["valid_bids"] += 1
            if bidder not in self.first_valid_bid_time:
                self.first_valid_bid_time[bidder] = now
            self.bid_order.append((now, bidder, amount))

            timer_extended = self._maybe_extend_timer(now)

            if amount > self.highest_bid:
                self.highest_bid = amount
                self.highest_bidder = bidder
                self.leading_bidders = {bidder}
                self._persist_state()

                return {
                    "accepted": True,
                    "reason": "New highest bid",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": False,
                    "timer_extended": timer_extended,
                }

            escalation_started = not self.escalation_active
            if self.highest_bidder:
                self.leading_bidders.add(self.highest_bidder)
            self.leading_bidders.add(bidder)
            self._start_escalation(now)
            self._persist_state()

            return {
                "accepted": True,
                "reason": "Tie detected at highest bid; escalation round started",
                "highest_bid": self.highest_bid,
                "highest_bidder": self.highest_bidder,
                "tie": True,
                "escalation_started": escalation_started,
                "escalation_end_time": self.escalation_end_time,
                "timer_extended": timer_extended,
            }

    def finalize_escalation_if_due(self):
        with self.lock:
            if not self.auction_active or not self.escalation_active:
                return None

            now = time.time()
            return self._finalize_escalation_locked(now, force=False)

    def get_state(self):
        with self.lock:
            return {
                "highest_bid": self.highest_bid,
                "highest_bidder": self.highest_bidder,
                "auction_active": self.auction_active,
                "tie_active": self.escalation_active,
                "escalation_end_time": self.escalation_end_time,
                "end_time": self.end_time,
                "item": self.item,
                "base_price": self.base_price,
                "escalation_window_seconds": self.escalation_window_seconds,
            }

    def get_reputation_snapshot(self):
        with self.lock:
            snapshot = {}
            for bidder, stats in self.reputation.items():
                snapshot[bidder] = {
                    "wins": stats["wins"],
                    "valid_bids": stats["valid_bids"],
                    "score": self._reputation_score(bidder),
                }
            return snapshot

    def end_auction(self):
        with self.lock:
            if self.escalation_active:
                self._finalize_escalation_locked(time.time(), force=True)

            self.auction_active = False
            self.end_time = None
            if self.highest_bidder:
                self._ensure_bidder(self.highest_bidder)
                self.reputation[self.highest_bidder]["wins"] += 1
            self._persist_state()
            return self.highest_bid, self.highest_bidder

    def is_active(self):
        with self.lock:
            return self.auction_active