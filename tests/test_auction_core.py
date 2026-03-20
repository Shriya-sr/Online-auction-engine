import time
import unittest
from server.auction_core import AuctionStateManager, BidManager, AntiSnipingTimer, AuctionLifecycle

class TestAuctionCore(unittest.TestCase):
    def setUp(self):
        self.state = AuctionStateManager()
        self.state.add_participant('alice')
        self.state.add_participant('bob')
        self.bid_manager = BidManager(self.state)
        self.timer = AntiSnipingTimer(self.state)
        self.lifecycle = AuctionLifecycle(self.state, self.bid_manager, self.timer)

    def test_correct_bid_ordering(self):
        self.lifecycle.start_auction()
        self.lifecycle.update_bid('alice', 100)
        self.lifecycle.update_bid('bob', 150)
        self.assertEqual(self.state.current_highest_bid, 150)
        self.assertEqual(self.state.highest_bidder, 'bob')

    def test_invalid_bid(self):
        self.lifecycle.start_auction()
        result = self.lifecycle.update_bid('alice', -10)
        self.assertFalse(result)
        result = self.lifecycle.update_bid('charlie', 50)  # Not a participant
        self.assertFalse(result)

    def test_auction_timer_behavior(self):
        self.lifecycle.start_auction()
        # Simulate bid in last 5 seconds
        self.state.auction_end_time = time.time() + 5
        before = self.state.auction_end_time
        self.lifecycle.update_bid('alice', 200)
        after = self.state.auction_end_time
        self.assertGreater(after, before)

    def test_auction_closure(self):
        self.lifecycle.start_auction()
        self.lifecycle.update_bid('alice', 100)
        self.lifecycle.close_auction()
        self.assertFalse(self.state.auction_active)

if __name__ == '__main__':
    unittest.main()
