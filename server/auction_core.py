
# auction_core.py

class AuctionStateManager:
    def __init__(self, item="Mystery Box", base_price=100):
        # Initialize auction state variables
        self.item = item
        self.base_price = base_price
        self.current_highest_bid = base_price
        self.highest_bidder = None
        self.auction_active = False
        self.auction_end_time = None
        self.participants = set()
        self.bid_history = []  # List of (timestamp, user, amount, result)

    def add_participant(self, user_id):
        self.participants.add(user_id)

    def remove_participant(self, user_id):      # remove bidder and handle if not present
        try:
            self.participants.remove(user_id)
        except KeyError:
            print(f"{user_id} not found")

    def get_current_state(self):
        # Return the current auction state as a dictionary
        return {
            "item": self.item,
            "base_price": self.base_price,
            "current_highest_bid": self.current_highest_bid,
            "highest_bidder": self.highest_bidder,
            "auction_active": self.auction_active,
            "auction_end_time": self.auction_end_time,
            "participants": list(self.participants),
            "bid_history": self.bid_history
        }

# ...existing code...

class BidManager:
    def __init__(self, auction_state_manager):
        self.auction_state_manager = auction_state_manager

    def handle_bid(self, user_id, bid_amount):
        """Handle incoming bid, validate, update state, trigger broadcasts."""
        # Allow bid if escalation is active and bid is higher than tied amount
        if not self.validate_bid(user_id, bid_amount):
            return False  # Invalid bid
        if bid_amount > self.auction_state_manager.current_highest_bid:
            self.auction_state_manager.current_highest_bid = bid_amount
            self.auction_state_manager.highest_bidder = user_id
            self.broadcast_bid_update()
            return True
        elif bid_amount == self.auction_state_manager.current_highest_bid:
            self.trigger_tie_resolver(user_id, bid_amount)
            return None  # Tie
        else:
            return False  # Bid too low

    def validate_bid(self, user_id, bid_amount):
        """Validate bid according to auction rules."""
        # Auction must be active, user must be participant, bid must be positive
        if not self.auction_state_manager.auction_active:
            return False
        if user_id not in self.auction_state_manager.participants:
            return False
        if bid_amount <= 0:
            return False
        # Accept bid if escalation is active and bid is higher than tied amount
        # (Escalation logic handled in server)
        return True

    def trigger_tie_resolver(self, user_id, bid_amount):
        """Resolve tie bids using time factor."""
        # Placeholder: implement time-based tie resolution
        print(f"Tie detected for bid {bid_amount} by {user_id}")

    def broadcast_bid_update(self):
        return{
            "current_highest_bid": self.auction_state_manager.current_highest_bid,
            "highest_bidder": self.auction_state_manager.highest_bidder,
            "auction_active": self.auction_state_manager.auction_active,
            "auction_end_time": self.auction_state_manager.auction_end_time,
            "participants": list(self.auction_state_manager.participants)
        }
        

class AntiSnipingTimer:
    def __init__(self, auction_state_manager):
        self.auction_state_manager = auction_state_manager
        self.auction_duration = 60  # seconds
        self.extension_time = 5     # seconds

    def check_and_extend_timer(self, bid_time):
        """Extend timer if bid arrives in last 5 seconds."""
        if self.auction_state_manager.auction_end_time is None:
            return
        time_left = self.auction_state_manager.auction_end_time - bid_time
        if time_left <= 5:
            self.auction_state_manager.auction_end_time += self.extension_time
            print("Auction timer extended by 5 seconds due to last-second bid.")

    def get_remaining_time(self):
        """Return remaining auction time."""
        import time
        if self.auction_state_manager.auction_end_time is None:
            return 0
        return max(0, self.auction_state_manager.auction_end_time - time.time())
    def time_up(self):
        import time
        if self.auction_state_manager.auction_end_time is None:
            return False
        return time.time() >= self.auction_state_manager.auction_end_time

def run_timer_loop(lifecycle, timer, state, handle_auction_end):
    import time
    while state.auction_active:
        if timer.time_up():
            result = lifecycle.end_auction()
            handle_auction_end(result)
            break
        time.sleep(1)

class AuctionLifecycle:
    def __init__(self, auction_state_manager, bid_manager, anti_sniping_timer):
        self.auction_state_manager = auction_state_manager
        self.bid_manager = bid_manager
        self.anti_sniping_timer = anti_sniping_timer

    def start_auction(self):
        """Start the auction."""
        import time
        self.auction_state_manager.auction_active = True
        self.auction_state_manager.auction_end_time = time.time() + self.anti_sniping_timer.auction_duration
        print("Auction started.")

    def update_bid(self, user_id, bid_amount):
        """Update bid during auction."""
        import time
        print(f"[CORE] Incoming bid | bidder={user_id} | amount={bid_amount}")
        print(f"[CORE] Current highest | {self.auction_state_manager.current_highest_bid}")
        assert self.auction_state_manager.current_highest_bid >= 0
        result = self.bid_manager.handle_bid(user_id, bid_amount)
        self.anti_sniping_timer.check_and_extend_timer(time.time())
        print(f"[CORE] RESULT | highest={self.auction_state_manager.current_highest_bid} | winner={self.auction_state_manager.highest_bidder}")
        if self.auction_state_manager.current_highest_bid > 0:
            assert self.auction_state_manager.highest_bidder is not None
        return result

    def close_auction(self):
        """Close the auction."""
        self.auction_state_manager.auction_active = False
        print("Auction closed.")

    def announce_winner(self):
        """Announce the winner of the auction."""
        winner = self.auction_state_manager.highest_bidder
        amount = self.auction_state_manager.current_highest_bid
        print(f"Winner is {winner} with bid {amount}")

    def end_auction(self):
        """End the auction and return result."""
        self.auction_state_manager.auction_active = False
        return {
            "status": "ENDED",
            "winner": self.auction_state_manager.highest_bidder,
            "amount": self.auction_state_manager.current_highest_bid
        }
