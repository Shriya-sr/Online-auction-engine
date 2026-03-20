
import socket
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.message_protocol import create_bid_update, parse_message
from server.auction_core import AuctionStateManager, BidManager, AntiSnipingTimer, AuctionLifecycle
from server.tie_resolver import TieResolver

HOST = "127.0.0.1"
PORT = 5000

clients = []
client_usernames = {}
clients_lock = threading.Lock()

# Initialize core auction logic (single source of truth)


import time
import threading
import os

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "auction_log.txt")
def log_event(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

auction_state = AuctionStateManager(item="Rare Painting", base_price=100)
bid_manager = BidManager(auction_state)
anti_sniping_timer = AntiSnipingTimer(auction_state)
tie_resolver = TieResolver(auction_state)
lifecycle = AuctionLifecycle(auction_state, bid_manager, anti_sniping_timer)

# Timer loop handler
def handle_auction_end(result):
    if result["status"] == "ENDED":
        # Resolve any ongoing escalation before ending auction
        if tie_resolver.is_escalation_active():
            resolution = tie_resolver.resolve_escalation()
            auction_state.current_highest_bid = resolution["amount"]
            auction_state.highest_bidder = resolution["winner"]
            log_event(f"FINAL ESCALATION RESOLUTION: {resolution['winner']} wins with bid {resolution['amount']}")
        
        summary = f"AUCTION ENDED | Winner: {result['winner']} | Bid: {result['amount']} | Item: {auction_state.item} | Participants: {', '.join(auction_state.participants)}"
        print("\n=== AUCTION END SUMMARY ===")
        print(summary)
        print("BID HISTORY:")
        print("| Time | User | Bid Amount | Result |")
        for entry in auction_state.bid_history:
            t, user, amount, res = entry
            print(f"| {t} | {user} | {amount} | {res} |")
        print("===========================\n")
        # Broadcast to all clients individually
        print(f"Broadcasting to {len(clients)} clients...")
        with clients_lock:
            current_clients = list(clients)
        for client in current_clients:
            try:
                send_wire_message(client, summary)
                print(f"Sent auction end message to client")
            except Exception as e:
                print(f"Failed to send to client: {e}")
        log_event(summary)
        # Print bid history as a table
        log_event("BID HISTORY:")
        log_event("| Time | User | Bid Amount | Result |")
        for entry in auction_state.bid_history:
            t, user, amount, res = entry
            log_event(f"| {t} | {user} | {amount} | {res} |")

def start_timer_thread():
    from server.auction_core import run_timer_loop
    t = threading.Thread(target=run_timer_loop, args=(lifecycle, anti_sniping_timer, auction_state, handle_auction_end))
    t.daemon = True
    t.start()

lifecycle.start_auction()
start_timer_thread()


def send_wire_message(client, message):
    """
    Sends a single newline-delimited message to a client.
    """
    client.sendall(f"{message}\n".encode())


def broadcast(message, sender=None, include_sender=False):
    """
    Send message to all connected clients except the sender
    """
    with clients_lock:
        current_clients = list(clients)

    for client in current_clients:
        if include_sender or client != sender:
            try:
                send_wire_message(client, message)
            except Exception:
                remove_client(client)


def remove_client(client):
    """
    Remove client if connection is lost
    """
    with clients_lock:
        if client not in clients:
            return

        username = client_usernames.get(client, "Unknown")
        print(f"{username} disconnected")

        clients.remove(client)

        if client in client_usernames:
            del client_usernames[client]

    client.close()



def process_message(conn, raw_message):
    """
    Parses and processes one client message.
    """
    parsed = parse_message(raw_message)
    if not parsed:
        return

    message_type = parsed.get("type")

    if message_type == "INVALID":
        send_wire_message(conn, f"ERROR {parsed['error']}")
        return

    if message_type == "JOIN":
        username = parsed["user_id"]
        with clients_lock:
            client_usernames[conn] = username
        auction_state.add_participant(username)
        welcome = f"SERVER: {username} joined the auction. Total participants: {len(auction_state.participants)}"
        broadcast(welcome, include_sender=True)
        log_event(welcome)
        return

    if message_type == "BID":
        bidder = client_usernames.get(conn)
        if not bidder:
            send_wire_message(conn, "ERROR Join first using: JOIN <username>")
            return
        amount = parsed["amount"]
        now = time.strftime("%H:%M:%S", time.localtime())
        
        # Check if escalation is active
        if tie_resolver.is_escalation_active():
            esc_result = tie_resolver.handle_escalation_bid(bidder, amount)
            if esc_result == "ESCALATION_ACCEPTED":
                auction_state.current_highest_bid = amount
                auction_state.highest_bidder = bidder
                auction_state.bid_history.append((now, bidder, amount, "ESCALATION_BID"))
                log_event(f"ESCALATION BID: {bidder} bid {amount} ({esc_result})")
                broadcast(f"ESCALATION: {bidder} bid {amount}", include_sender=True)
            elif esc_result == "ESCALATION_REJECTED":
                auction_state.bid_history.append((now, bidder, amount, "ESCALATION_REJECTED"))
                log_event(f"ESCALATION BID REJECTED: {bidder} bid {amount}")
                send_wire_message(conn, f"ERROR Escalation bid must be > {auction_state.current_highest_bid}")
            elif esc_result == "ESCALATION_ENDED":
                # Escalation ended, resolve it
                resolution = tie_resolver.resolve_escalation()
                auction_state.current_highest_bid = resolution["amount"]
                auction_state.highest_bidder = resolution["winner"]
                log_event(f"ESCALATION RESOLVED: Winner {resolution['winner']} with bid {resolution['amount']}")
                broadcast(f"ESCALATION RESOLVED: {resolution['winner']} wins with bid {resolution['amount']}", include_sender=True)
            return
        
        # Normal bid handling
        result = lifecycle.update_bid(bidder, amount)
        # Determine result string
        if result is True:
            res_str = "ACCEPTED"
        elif result is None:
            res_str = "TIE"
        else:
            res_str = "REJECTED"
        # Log bid
        auction_state.bid_history.append((now, bidder, amount, res_str))
        log_event(f"BID: {bidder} bid {amount} at {now} ({res_str})")
        state = auction_state.get_current_state()
        print(f"[STATE] highest={state['current_highest_bid']} | bidder={state['highest_bidder']}")
        if result is True:
            update = create_bid_update(state["current_highest_bid"], state["highest_bidder"])
            broadcast(update, include_sender=True)
        elif result is None:
            # Detect tie and start escalation
            if tie_resolver.start_escalation(bidder, amount):
                tie_msg = f"TIE DETECTED: {bidder} and {auction_state.highest_bidder} both bid {amount} | 5-SEC ESCALATION STARTED"
                broadcast(tie_msg, include_sender=True)
                log_event(tie_msg)
                print(tie_msg)
        else:
            send_wire_message(conn, f"ERROR Bid rejected")
        return

    send_wire_message(conn, f"ERROR Unknown command: {raw_message}")


def handle_client(conn, addr):
    """
    Handles communication with one client
    """
    print(f"Connected: {addr}")

    with clients_lock:
        clients.append(conn)

    buffer = ""

    while True:
        try:
            packet = conn.recv(1024).decode()

            if not packet:
                break

            buffer += packet
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                message = line.strip()
                if not message:
                    continue

                print(f"Received: {message}")
                process_message(conn, message)

        except Exception:
            break

    remove_client(conn)


def start_server():
    """
    Starts the auction server
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.bind((HOST, PORT))
    server.listen()

    print(f"Auction Server running on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()

        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.daemon = True
        thread.start()


if __name__ == "__main__":
    # Print auction metadata at start
    print(f"\n=== AUCTION START ===")
    print(f"Item: {auction_state.item}")
    print(f"Base Price: {auction_state.base_price}")
    print(f"====================\n")
    log_event(f"AUCTION START | Item: {auction_state.item} | Base Price: {auction_state.base_price}")
    start_server()