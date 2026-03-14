import socket
import threading

HOST = "127.0.0.1"
PORT = 5000


def receive_messages(client_socket):
    """
    Continuously receive messages from server
    """
    while True:
        try:
            message = client_socket.recv(1024).decode()
            if message:
                print("\n" + message)
        except:
            print("Disconnected from server.")
            client_socket.close()
            break


def send_messages(client_socket):
    """
    Send user input to server
    """
    while True:
        message = input()
        client_socket.send(message.encode())


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
    join_message = f"JOIN {username}"
    client_socket.send(join_message.encode())

    # start receiving thread
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    receive_thread.daemon = True
    receive_thread.start()

    print("You can now place bids using: BID <amount>")
    print("Example: BID 100\n")

    send_messages(client_socket)


if __name__ == "__main__":
    start_client()