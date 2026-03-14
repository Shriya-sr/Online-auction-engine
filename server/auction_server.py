import socket
import threading

HOST = "127.0.0.1"
PORT = 5000

clients = []
client_usernames = {}


def broadcast(message, sender=None):
    """
    Send message to all connected clients except the sender
    """
    for client in clients:
        if client != sender:
            try:
                client.send(message.encode())
            except:
                remove_client(client)


def remove_client(client):
    """
    Remove client if connection is lost
    """
    if client in clients:
        username = client_usernames.get(client, "Unknown")
        print(f"{username} disconnected")

        clients.remove(client)
        client.close()

        if client in client_usernames:
            del client_usernames[client]


def handle_client(conn, addr):
    """
    Handles communication with one client
    """
    print(f"Connected: {addr}")

    clients.append(conn)

    while True:
        try:
            message = conn.recv(1024).decode()

            if not message:
                break

            print(f"Received: {message}")

            parts = message.split()

            if parts[0] == "JOIN":
                username = parts[1]
                client_usernames[conn] = username

                welcome = f"SERVER: {username} joined the auction"
                broadcast(welcome)

            elif parts[0] == "BID":
                amount = parts[1]
                bidder = client_usernames.get(conn, "Unknown")

                update = f"BID_UPDATE {amount} {bidder}"
                broadcast(update)

        except:
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
        thread.start()


if __name__ == "__main__":
    start_server()