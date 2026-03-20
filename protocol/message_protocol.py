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


def create_error_message(message):
    return f"ERROR {message}"


# ---- Message Parsing Function ----

def parse_message(message):
    """
    Parses incoming messages into structured components.
    """
    # incoming message is parsed
    parts = message.strip().split()

    if not parts:
        return None

    command = parts[0]

    # A dictionary of sorts created, based on keyword by user
    if command == "JOIN":
        if len(parts) != 2:
            return {"type": "INVALID", "error": "JOIN requires exactly one username", "raw": message}
        return {"type": "JOIN", "user_id": parts[1]}

    elif command == "BID":
        if len(parts) != 2:
            return {"type": "INVALID", "error": "BID requires exactly one amount", "raw": message}
        try:
            amount = int(parts[1])
        except ValueError:
            return {"type": "INVALID", "error": "BID amount must be an integer", "raw": message}

        return {"type": "BID", "amount": amount}

# if existing bidder is updating his bid amount
    elif command == "BID_UPDATE":
        if len(parts) != 3:
            return {"type": "INVALID", "error": "BID_UPDATE requires amount and bidder", "raw": message}
        try:
            amount = int(parts[1])
        except ValueError:
            return {"type": "INVALID", "error": "BID_UPDATE amount must be an integer", "raw": message}

        return {
            "type": "BID_UPDATE",
            "amount": amount,
            "bidder": parts[2]
        }

    elif command == "TIE_START":
        if len(parts) != 2:
            return {"type": "INVALID", "error": "TIE_START requires duration", "raw": message}
        try:
            duration = int(parts[1])
        except ValueError:
            return {"type": "INVALID", "error": "TIE_START duration must be an integer", "raw": message}
        return {"type": "TIE_START", "duration": duration}

    elif command == "TIE_END":
        if len(parts) != 1:
            return {"type": "INVALID", "error": "TIE_END takes no arguments", "raw": message}
        return {"type": "TIE_END"}

    elif command == "AUCTION_END":
        if len(parts) != 3:
            return {"type": "INVALID", "error": "AUCTION_END requires winner and amount", "raw": message}
        try:
            amount = int(parts[2])
        except ValueError:
            return {"type": "INVALID", "error": "AUCTION_END amount must be an integer", "raw": message}

        return {
            "type": "AUCTION_END",
            "winner": parts[1],
            "amount": amount
        }

    elif command == "ERROR":
        if len(parts) < 2:
            return {"type": "INVALID", "error": "ERROR requires a message", "raw": message}
        return {"type": "ERROR", "message": " ".join(parts[1:])}

    else:
        return {"type": "UNKNOWN", "raw": message}
    
    # tie start and toe end to be implpemented such that it calls Ahana's function