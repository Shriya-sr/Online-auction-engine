# networking_test.py

import socket
import threading
import time
import random

HOST = "127.0.0.1"
PORT = 5000


def simulated_client(client_id):
    """
    Simulates a bidder connecting to the server and placing bids.
    """
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((HOST, PORT))

        username = f"user{client_id}"

        # send join message
        join_message = f"JOIN {username}"
        client.send(join_message.encode())

        time.sleep(random.uniform(1, 2))

        # place random bids
        for _ in range(3):
            bid_amount = random.randint(50, 200)
            bid_message = f"BID {bid_amount}"

            client.send(bid_message.encode())

            time.sleep(random.uniform(1, 3))

        client.close()

    except Exception as e:
        print(f"Client {client_id} error:", e)


def run_network_test(num_clients=5):
    """
    Launch multiple simulated clients to test server networking.
    """
    threads = []

    print(f"Starting networking test with {num_clients} simulated clients...\n")

    for i in range(num_clients):
        t = threading.Thread(target=simulated_client, args=(i + 1,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\nNetworking test completed.")


if __name__ == "__main__":
    run_network_test()