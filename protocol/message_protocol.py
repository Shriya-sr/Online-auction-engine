# message_protocol.py

"""
Defines message formats and helper functions for the auction system.
This module standardizes communication between clients and server.
"""


# ---- Message Creation Functions ----

def create_join_message(user_id):
    return f"JOIN {user_id}"


def create_bid_message(amount):
    return f"BID {amount}"


def create_bid_update(amount, bidder):
    return f"BID_UPDATE {amount} {bidder}"


def create_tie_start(duration):
    return f"TIE_START {duration}"


def create_tie_end():
    return "TIE_END"


def create_auction_end(winner, amount):
    return f"AUCTION_END {winner} {amount}"


# ---- Message Parsing Function ----

def parse_message(message):
    """
    Parses incoming messages into structured components.
    """
    parts = message.strip().split()

    if not parts:
        return None

    command = parts[0]

    if command == "JOIN":
        return {"type": "JOIN", "user_id": parts[1]}

    elif command == "BID":
        return {"type": "BID", "amount": int(parts[1])}

    elif command == "BID_UPDATE":
        return {
            "type": "BID_UPDATE",
            "amount": int(parts[1]),
            "bidder": parts[2]
        }

    elif command == "TIE_START":
        return {"type": "TIE_START", "duration": int(parts[1])}

    elif command == "TIE_END":
        return {"type": "TIE_END"}

    elif command == "AUCTION_END":
        return {
            "type": "AUCTION_END",
            "winner": parts[1],
            "amount": int(parts[2])
        }

    else:
        return {"type": "UNKNOWN", "raw": message}