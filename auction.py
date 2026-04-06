import threading  # For thread safety (locks)
import time       # For timing and timestamps
import json       # For state persistence
import os         # For file path handling

class Auction:
    def __init__(
        self,
        item="Auction Item",  # Item name
        duration_seconds=60,  # Default auction duration
        base_price=0.0,  # Starting price
        escalation_window_seconds=5,  # Escalation round duration
        anti_sniping_window_seconds=5,  # Anti-sniping window
        anti_sniping_extension_seconds=5,  # Extension per snipe
        anti_sniping_max_total_extension_seconds=30,  # Max total extension
        state_file=None,  # State file path
    ):
        self.item = item  # Auction item
        self.base_price = float(base_price)  # Starting price
        self.highest_bid = 0.0  # Highest bid so far
        self.highest_bidder = None  # Highest bidder
        self.auction_active = False  # Is auction running?
        self.end_time = None  # Auction end timestamp
        self.lock = threading.Lock()  # Lock for thread safety

        self.escalation_window_seconds = escalation_window_seconds  # Escalation window
        self.anti_sniping_window_seconds = anti_sniping_window_seconds  # Anti-sniping window
        self.anti_sniping_extension_seconds = anti_sniping_extension_seconds  # Extension per snipe
        self.anti_sniping_max_total_extension_seconds = anti_sniping_max_total_extension_seconds  # Max extension
        self.original_end_time = None  # Original end time

        self.leading_bidders = set()  # Bidders tied for highest
        self.escalation_active = False  # Is escalation active?
        self.escalation_end_time = None  # Escalation end timestamp
        self.escalation_blind_bids = {}  # Blind bids in escalation

        self.bid_order = []  # List of (time, bidder, amount)
        self.first_valid_bid_time = {}  # First valid bid time per bidder
        self.reputation = {}  # Reputation stats

        self.default_duration_seconds = duration_seconds  # Default duration
        if state_file is None:
            state_file = os.path.join(os.path.dirname(__file__), "auction_state.json")  # Default state file
        self.state_file = state_file  # State file path

        self._load_state()  # Load state from file

    def _serialize_state(self):
        # Serialize auction state for saving
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
            "anti_sniping_max_total_extension_seconds": self.anti_sniping_max_total_extension_seconds,
            "original_end_time": self.original_end_time,
        }

    def _persist_state(self):
        # Save auction state to file
        payload = self._serialize_state() # saves auction state to file
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _load_state(self):
        # Load auction state from file if it exists
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
            self.original_end_time = data.get("original_end_time", self.end_time)
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
            self.anti_sniping_window_seconds = int(
                data.get("anti_sniping_window_seconds", self.anti_sniping_window_seconds)
            )
            self.anti_sniping_extension_seconds = int(
                data.get("anti_sniping_extension_seconds", self.anti_sniping_extension_seconds)
            )
            self.anti_sniping_max_total_extension_seconds = int(
                data.get(
                    "anti_sniping_max_total_extension_seconds",
                    self.anti_sniping_max_total_extension_seconds,
                )
            )
        except Exception:
            # Start with in-memory defaults if persisted state is invalid.
            self.auction_active = False
            self.end_time = None
            self.original_end_time = None
            self.escalation_active = False
            self.escalation_end_time = None
            self.escalation_blind_bids = {}
            self.leading_bidders = set()

    def start_auction(self, item=None, duration_seconds=None, base_price=None, escalation_window_seconds=None):
        # Start a new auction
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
            self.original_end_time = time.time() + duration
            self.end_time = self.original_end_time
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
        # Ensure bidder has a reputation entry
        if bidder not in self.reputation:
            self.reputation[bidder] = {"wins": 0, "valid_bids": 0}

    def _reputation_score(self, bidder):
        # Calculate reputation score (weighted)
        stats = self.reputation.get(bidder, {"wins": 0, "valid_bids": 0})
        # Weighted: wins = reliability, valid_bids = participation
        return (2.0 * stats["wins"]) + (0.1 * stats["valid_bids"])

    def _maybe_extend_timer(self, now):
        # Extend auction timer if bid is in anti-sniping window
        if self.end_time is None or self.original_end_time is None:
            return False   # if not valid end time, return false

        time_left = self.end_time - now  #calculate how much time left
        if time_left > self.anti_sniping_window_seconds:  # if more time than anti_sniping window do nothing
            return False

        max_end_time = self.original_end_time + self.anti_sniping_max_total_extension_seconds  # calculate max allowed extension (og end time + max allowed extension)
        if self.end_time >= max_end_time:  #( if we have already crossed the limit, return false)
            return False

        remaining_extension = max_end_time - self.end_time #how much more the auction can be extended
        applied_extension = min(self.anti_sniping_extension_seconds, remaining_extension)
        if applied_extension <= 0:  # if invalid extension do nothing 
            return False

        self.end_time += applied_extension  # else, extend auction
        return True

    def _start_escalation(self, now):
        # Start escalation round if not already active
        if not self.escalation_active:
            self.escalation_active = True
            self.escalation_end_time = now + self.escalation_window_seconds
        # Ensure auction end is after escalation end
        if self.end_time < self.escalation_end_time:
            self.end_time = self.escalation_end_time

    def _resolve_tie(self, candidates=None):
        # Resolve a tie among candidates
        if candidates is None:
            candidates = list(self.leading_bidders)
        else:
            candidates = list(candidates)

        if not candidates:
            return None, "No tied bidders available for resolution"

        scores = {bidder: self._reputation_score(bidder) for bidder in candidates} #get the reputation score of each 
        best_score = max(scores.values()) #get best rep score
        best_bidders = [b for b in candidates if scores[b] == best_score] # best bidder

        if len(best_bidders) == 1:
            winner = best_bidders[0] #if there only one => declare him winner
            return winner, f"Tie resolved by reputation score ({best_score:.2f})"

        winner = min(
            best_bidders,  # if tie, see the time 
            key=lambda b: self.first_valid_bid_time.get(b, float("inf")),
        )
        return winner, "Tie resolved by FCFS among equal-reputation bidders"

    def _finalize_escalation_locked(self, now, force=False):
        # Finalize escalation round if due
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

    def _normalize_phase_locked(self, now):
        # Normalize auction phase (handle escalation timing)
        if not self.auction_active:
            return

        if self.escalation_active:
            # Finalize escalation if window ended
            self._finalize_escalation_locked(now, force=False)

        if self.escalation_active and self.escalation_end_time and self.end_time:
            # Align auction end with escalation end
            if self.end_time < self.escalation_end_time:
                self.end_time = self.escalation_end_time
                self._persist_state()

    def _end_auction_locked(self):
        # End the auction and update winner's reputation
        if self.escalation_active:
            self._finalize_escalation_locked(time.time(), force=True)

        self.auction_active = False
        self.end_time = None
        self.original_end_time = None
        if self.highest_bidder:
            self._ensure_bidder(self.highest_bidder)
            self.reputation[self.highest_bidder]["wins"] += 1
        self._persist_state()
        return self.highest_bid, self.highest_bidder

    def place_bid(self, amount, bidder):
        # Place a bid for a bidder
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
            self._normalize_phase_locked(now)

            # chcek if auction has ended already 
            if self.end_time and now >= self.end_time:
                self._end_auction_locked()
                return {
                    "accepted": False,
                    "reason": "Auction ended before bid could be processed",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": False,
                    "timer_extended": False,
                }

            self._ensure_bidder(bidder)  # give the bidder reputation (since he is not already there)

            # Escalation round logic
            if self.escalation_active:
                if amount <= self.highest_bid:
                    return {
                        # case where bid is lesser than highest_bid
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
                        "accepted": False,          #if bidder bids same amount, reject it
                        "reason": "Duplicate escalation bid amount from same bidder",
                        "highest_bid": self.highest_bid,
                        "highest_bidder": self.highest_bidder,
                        "tie": True,
                        "timer_extended": False,
                    }

                self.reputation[bidder]["valid_bids"] += 1  # increasing count in valid bids
                if bidder not in self.first_valid_bid_time:
                    self.first_valid_bid_time[bidder] = now   # record first valid bid 
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

            # Normal bid logic


            if self.highest_bid == 0.0 and amount < self.base_price:  #handle 0 bid and less than base price case
                return {
                    "accepted": False,
                    "reason": f"Bid below base price ${self.base_price:.2f}",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": False,
                    "timer_extended": False,
                }

            if amount < self.highest_bid:   # amount less than highest bid case
                return {
                    "accepted": False,
                    "reason": "Bid lower than current highest",
                    "highest_bid": self.highest_bid,
                    "highest_bidder": self.highest_bidder,
                    "tie": self.escalation_active,
                    "timer_extended": False,
                }

            if amount == self.highest_bid and bidder == self.highest_bidder:   #duplicate bid from same bidder 
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

            if amount > self.highest_bid:  # update highest bidder and bid amount if amount is greater
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

            # Tie at highest bid, start escalation
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
        # Finalize escalation if its window has ended
        with self.lock:
            if not self.auction_active or not self.escalation_active:
                return None

            now = time.time()
            return self._finalize_escalation_locked(now, force=False)

    def get_state(self):
        # Get current auction state (for server/client)
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
        # Get a snapshot of all bidders' reputations
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
        # End the auction (public method)
        with self.lock:
            return self._end_auction_locked()

    def end_auction_if_due(self, now=None):
        # End the auction only if the timer is still due at the moment of the check.
        with self.lock:
            if not self.auction_active:
                return None

            current_time = time.time() if now is None else now
            self._normalize_phase_locked(current_time)

            if self.end_time and current_time >= self.end_time:
                return self._end_auction_locked()

            return None

    def is_active(self):
        # Check if auction is active
        with self.lock:
            return self.auction_active
