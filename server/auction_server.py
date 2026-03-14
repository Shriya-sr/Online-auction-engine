import socket
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.message_protocol import create_bid_update, parse_message

HOST = "127.0.0.1"
PORT = 5000

clients = []
client_usernames = {}
clients_lock = threading.Lock()
state_lock = threading.Lock()

highest_bid = 0
highest_bidder = None


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
    global highest_bid
    global highest_bidder

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

        welcome = f"SERVER: {username} joined the auction"
        broadcast(welcome, include_sender=True)
        return

    if message_type == "BID":
        bidder = client_usernames.get(conn)
        if not bidder:
            send_wire_message(conn, "ERROR Join first using: JOIN <username>")
            return

        amount = parsed["amount"]
        with state_lock:
            if amount <= highest_bid:
                send_wire_message(conn, f"ERROR Bid must be greater than current highest bid ({highest_bid})")
                return

            highest_bid = amount
            highest_bidder = bidder

        update = create_bid_update(amount, highest_bidder)
        broadcast(update, include_sender=True)
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
    start_server()