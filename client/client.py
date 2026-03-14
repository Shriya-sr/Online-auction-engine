import socket
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.message_protocol import create_bid_message, create_join_message, parse_message

HOST = "127.0.0.1"
PORT = 5000


def send_wire_message(client_socket, message):
    """
    Sends a single newline-delimited message to the server.
    """
    client_socket.sendall(f"{message}\n".encode())


def run_countdown(seconds):
    """
    Displays a simple local countdown for tie/escalation windows.
    """
    for remaining in range(seconds, 0, -1):
        print(f"Auction event ends in {remaining:2d}s", end="\r")
        time.sleep(1)
    print(" " * 40, end="\r")


def render_server_message(message):
    """
    Renders protocol messages in a user-friendly format.
    """
    parsed = parse_message(message)
    if not parsed:
        return

    message_type = parsed.get("type")

    if message_type == "BID_UPDATE":
        print(f"\nCurrent bid: {parsed['amount']} | Bidder: {parsed['bidder']}")
        return

    if message_type == "TIE_START":
        duration = parsed["duration"]
        print(f"\nTie round started ({duration}s)")
        countdown_thread = threading.Thread(target=run_countdown, args=(duration,), daemon=True)
        countdown_thread.start()
        return

    if message_type == "TIE_END":
        print("\nTie round ended")
        return

    if message_type == "AUCTION_END":
        print(f"\nAuction ended: winner={parsed['winner']} amount={parsed['amount']}")
        return

    if message_type == "ERROR":
        print(f"\nServer error: {parsed['message']}")
        return

    print(f"\n{message}")


def receive_messages(client_socket):
    """
    Continuously receive messages from server
    """
    buffer = ""
    while True:
        try:
            packet = client_socket.recv(1024).decode()
            if not packet:
                print("Disconnected from server.")
                client_socket.close()
                break

            buffer += packet
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                message = line.strip()
                if message:
                    render_server_message(message)

        except Exception:
            print("Disconnected from server.")
            client_socket.close()
            break


def send_messages(client_socket):
    """
    Send user input to server
    """
    while True:
        raw_input_message = input().strip()
        if not raw_input_message:
            continue

        if raw_input_message.upper() == "QUIT":
            client_socket.close()
            break

        if raw_input_message.isdigit():
            wire_message = create_bid_message(int(raw_input_message))
            send_wire_message(client_socket, wire_message)
            continue

        parsed = parse_message(raw_input_message)
        if parsed and parsed.get("type") == "BID":
            wire_message = create_bid_message(parsed["amount"])
            send_wire_message(client_socket, wire_message)
            continue

        print("Use BID <amount>, just <amount>, or QUIT")


def start_client():
    """
    Connect client to auction server
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((HOST, PORT))
        print("Connected to auction server.")
    except:
        print("Unable to connect to server.")
        return

    username = input("Enter your username: ")

    # send JOIN message
    join_message = create_join_message(username)
    send_wire_message(client_socket, join_message)

    # start receiving thread
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    receive_thread.daemon = True
    receive_thread.start()

    print("You can now place bids using: BID <amount> or just <amount>")
    print("Type QUIT to disconnect.\n")

    send_messages(client_socket)


if __name__ == "__main__":
    start_client()