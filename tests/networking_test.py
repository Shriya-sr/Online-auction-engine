
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import socket
import threading
import time
import unittest

from server import auction_server
from protocol.message_protocol import create_bid_message, create_join_message

HOST = "127.0.0.1"


def get_free_port():
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp_socket.bind((HOST, 0))
    port = temp_socket.getsockname()[1]
    temp_socket.close()
    return port


class TestClient:
    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(0.3)
        self.socket.connect((host, port))
        self._stop_event = threading.Event()
        self._messages = []
        self._lock = threading.Lock()
        self._buffer = ""

        self._receiver = threading.Thread(target=self._receive_loop, daemon=True)
        self._receiver.start()

    def _receive_loop(self):
        while not self._stop_event.is_set():
            try:
                packet = self.socket.recv(1024).decode()
                if not packet:
                    return

                self._buffer += packet
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    message = line.strip()
                    if message:
                        with self._lock:
                            self._messages.append(message)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return

    def send(self, message):
        self.socket.sendall(f"{message}\n".encode())

    def join(self, username):
        self.send(create_join_message(username))

    def bid(self, amount):
        self.send(create_bid_message(amount))

    def snapshot_messages(self):
        with self._lock:
            return list(self._messages)

    def close(self):
        self._stop_event.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()


class NetworkingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = get_free_port()

        auction_server.HOST = HOST
        auction_server.PORT = cls.port
        cls.server_thread = threading.Thread(target=auction_server.start_server, daemon=True)
        cls.server_thread.start()

        # Give the server a moment to bind/listen before clients connect.
        time.sleep(0.4)

    def setUp(self):
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()

        # Small pause so server handler threads can observe socket closure.
        time.sleep(0.1)

    def add_client(self):
        client = TestClient(HOST, self.port)
        self.clients.append(client)
        return client

    def assert_eventually_contains(self, client, expected_substring, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            messages = client.snapshot_messages()
            if any(expected_substring in item for item in messages):
                return
            time.sleep(0.05)

        self.fail(f"Did not receive expected message: {expected_substring}. Seen: {client.snapshot_messages()}")

    def test_multiple_clients_can_connect_and_join(self):
        client_a = self.add_client()
        client_b = self.add_client()

        client_a.join("userA")
        client_b.join("userB")

        self.assert_eventually_contains(client_a, "userA joined the auction")
        self.assert_eventually_contains(client_b, "userA joined the auction")
        self.assert_eventually_contains(client_a, "userB joined the auction")
        self.assert_eventually_contains(client_b, "userB joined the auction")

    def test_bid_update_is_broadcast_to_all_clients(self):
        client_a = self.add_client()
        client_b = self.add_client()
        client_c = self.add_client()

        client_a.join("alice")
        client_b.join("bob")
        client_c.join("carol")

        client_b.bid(150)

        self.assert_eventually_contains(client_a, "BID_UPDATE 150 bob")
        self.assert_eventually_contains(client_b, "BID_UPDATE 150 bob")
        self.assert_eventually_contains(client_c, "BID_UPDATE 150 bob")

    def test_equal_bid_triggers_tie_escalation(self):
        client_a = self.add_client()
        client_b = self.add_client()

        client_a.join("a")
        client_b.join("b")

        client_a.bid(200)
        self.assert_eventually_contains(client_a, "BID_UPDATE 200 a")

        client_b.bid(200)
        self.assert_eventually_contains(client_a, "TIE DETECTED")
        self.assert_eventually_contains(client_b, "TIE DETECTED")

if __name__ == "__main__":
    unittest.main(verbosity=2)