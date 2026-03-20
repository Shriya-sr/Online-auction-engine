# tie_resolver.py
import time
import threading

class TieResolver:
    """
    Handles tie situations in the auction.
    When multiple bidders place the same bid amount, an escalation round begins.
    """
    
    def __init__(self, auction_state_manager):
        self.auction_state_manager = auction_state_manager
        self.escalation_active = False
        self.escalation_end_time = None
        self.tied_bidders = set()  # Bidders involved in the tie
        self.escalation_bids = {}  # {user_id: bid_amount}
        self.escalation_duration = 5  # seconds
        self.escalation_lock = threading.Lock()
    
    def detect_tie(self, user_id, bid_amount):
        """
        Detect if the current bid matches the highest bid.
        Returns True if tie is detected.
        """
        return bid_amount == self.auction_state_manager.current_highest_bid
    
    def start_escalation(self, user_id, bid_amount):
        """
        Start a tie escalation round.
        user_id: bidder who triggered the tie
        bid_amount: the tied amount
        """
        with self.escalation_lock:
            if self.escalation_active:
                return False  # Escalation already active
            
            self.escalation_active = True
            self.escalation_end_time = time.time() + self.escalation_duration
            self.tied_bidders = {self.auction_state_manager.highest_bidder, user_id}
            self.escalation_bids = {}
            
            print(f"[TIE RESOLVER] Escalation started | Tied bidders: {self.tied_bidders} | Bid: {bid_amount}")
            return True
    
    def is_escalation_active(self):
        """Check if escalation is currently active."""
        with self.escalation_lock:
            if not self.escalation_active:
                return False
            
            # Check if escalation time has expired
            if time.time() >= self.escalation_end_time:
                self.escalation_active = False
                return False
        
        return True
    
    def handle_escalation_bid(self, user_id, bid_amount):
        """
        Handle bids during escalation round.
        
        Rules:
        - Tied bidders MUST bid to stay in escalation
        - Others can bid higher amounts
        - Highest bid wins
        
        Returns:
        - "ESCALATION_ACCEPTED" if bid is valid
        - "ESCALATION_REJECTED" if bid is invalid
        - "ESCALATION_ENDED" if escalation time expired
        """
        with self.escalation_lock:
            # Check if escalation has ended
            if time.time() >= self.escalation_end_time:
                self.escalation_active = False
                return "ESCALATION_ENDED"
            
            # Must be higher than current tied amount
            tied_amount = self.auction_state_manager.current_highest_bid
            if bid_amount <= tied_amount:
                print(f"[TIE RESOLVER] Escalation bid rejected: {user_id} bid {bid_amount} <= {tied_amount}")
                return "ESCALATION_REJECTED"
            
            # Record the bid
            self.escalation_bids[user_id] = bid_amount
            print(f"[TIE RESOLVER] Escalation bid accepted: {user_id} bid {bid_amount}")
            return "ESCALATION_ACCEPTED"
    
    def resolve_escalation(self):
        """
        End escalation and determine winner.
        
        Returns:
        {
            "status": "RESOLVED",
            "winner": winning_user_id,
            "amount": winning_amount,
            "all_bids": {user_id: bid_amount, ...}
        }
        """
        with self.escalation_lock:
            if not self.escalation_bids:
                # No one bid during escalation, keep previous highest
                return {
                    "status": "RESOLVED",
                    "winner": self.auction_state_manager.highest_bidder,
                    "amount": self.auction_state_manager.current_highest_bid,
                    "all_bids": {}
                }
            
            # Find the highest bid during escalation
            winner = max(self.escalation_bids, key=self.escalation_bids.get)
            winning_amount = self.escalation_bids[winner]
            
            print(f"[TIE RESOLVER] Escalation resolved | Winner: {winner} | Amount: {winning_amount}")
            
            self.escalation_active = False
            return {
                "status": "RESOLVED",
                "winner": winner,
                "amount": winning_amount,
                "all_bids": dict(self.escalation_bids)
            }
    
    def get_remaining_escalation_time(self):
        """Get remaining time in escalation round."""
        with self.escalation_lock:
            if not self.escalation_active:
                return 0
            
            remaining = max(0, self.escalation_end_time - time.time())
            return remaining
    
    def cancel_escalation(self):
        """Cancel the ongoing escalation."""
        with self.escalation_lock:
            self.escalation_active = False
            print("[TIE RESOLVER] Escalation cancelled")
