"""
================================================================================
AUCTION SERVER - Main Application Server
================================================================================
PURPOSE:
  - Central server managing the entire online auction system
  - Accepts connections from multiple bidder clients (on port 5000)
  - Accepts connection from admin portal (on port 5001)
  - Routes all bids to the Auction logic engine
  - Broadcasts auction updates to all connected clients
  - Enforces SSL/TLS encryption for all communications

KEY RESPONSIBILITIES:
  1. Connection Management: Accept and track bidder connections
  2. Message Broadcasting: Send updates to all/specific clients
  3. Client Handling: Process BID, GET, REPUTATION, JOIN, EXIT commands
  4. Admin Portal: Process START, STOP, STATUS commands
  5. Timer Management: Monitor auction countdown and escalation window
  6. Timeout Enforcement: Disconnect idle clients

PROTOCOL:
  - Uses TCP sockets with SSL/TLS encryption
  - Messages are line-delimited (newline-terminated)
  - Format: MESSAGE_TYPE|key=value|key=value\n
  Examples:
    JOINED|username=bidder1|item=Laptop|highest=500.0|leader=bidder2
    BID UPDATE|status=accepted|bidder=bidder1|amount=550.0|highest=550.0
    STATUS|item=Laptop|time_left=45|active=true|highest=550.0

SECURITY:
  - Requires server.crt and server.key for SSL/TLS
  - Bidders connect on secure port 5000
  - Admin connects on separate secure port 5001

EXAMPLE USAGE:
  if __name__ == "__main__":
      server = AuctionServer(host='0.0.0.0', port=5000, use_ssl=True)
      server.start()
================================================================================
"""
import socket      # For network communication
import ssl         # For SSL/TLS encryption
import threading   # For handling multiple clients concurrently
import time        # For timing and delays
from auction import Auction  # Auction logic engine

#normal tcp server created and then upgraded to tls (i.e secure tcp)

class AuctionServer:
    def __init__(self, host='localhost', port=5000, use_ssl=True, admin_port=5001):
        self.host = host  # Server hostname or IP
        self.port = port  # Port for bidder clients
        self.admin_port = admin_port  # Port for admin portal
        self.auction = Auction()  # Auction logic instance
        self.clients = []  # List of connected clients
        self.clients_lock = threading.Lock()  # Lock for client list
        self.usernames = set()  # Set of active usernames
        self.usernames_lock = threading.Lock()  # Lock for usernames
        self.recv_timeout_seconds = 5.0  # Socket receive timeout
        self.client_idle_timeout_seconds = 180.0  # Idle timeout for clients
        self.admin_idle_timeout_seconds = 300.0  # Idle timeout for admin
        self.max_line_bytes = 16384  # Max allowed message size

        # Create SSL context and wrap socket if SSL is enabled
        if use_ssl:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)  # TLS server context
            context.load_cert_chain(certfile='server.crt', keyfile='server.key')  # Load server certificate and key

            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP socket for clients
            self.server_socket = context.wrap_socket(server_socket, server_side=True)  # Wrap with SSL/TLS

            # All data sent/received is encrypted/decrypted automatically

            admin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP socket for admin
            self.admin_server_socket = context.wrap_socket(admin_socket, server_side=True)  # Wrap with SSL/TLS
        else:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Plain TCP socket for clients
            self.admin_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Plain TCP socket for admin

    def start(self):
        """Start the server and listen for incoming connections."""
        self.server_socket.bind((self.host, self.port))  # Bind client socket to host/port
        self.server_socket.listen(5)  # Listen for up to 5 queued connections
        self.admin_server_socket.bind((self.host, self.admin_port))  # Bind admin socket
        self.admin_server_socket.listen(2)  # Listen for up to 2 admin connections
        print(f"Server started on {self.host}:{self.port}")  # Log server start
        print(f"Admin portal listening on {self.host}:{self.admin_port}")  # Log admin start

        # Start timer thread for auction timing
        timer = threading.Thread(target=self.timer_thread)
        timer.daemon = True  # Daemon thread exits with main program
        timer.start()

        # Start admin listener thread for admin portal
        admin_listener = threading.Thread(target=self.admin_listener_thread)
        admin_listener.daemon = True
        admin_listener.start()

        try:
            while True:
                client_socket, client_address = self.server_socket.accept()  # Accept new client connection
                print(f"New connection from {client_address}")  # Log connection

                # Handle client in a new thread
                client_thread = threading.Thread(
                    target=self.handle_client,  # Target function
                    args=(client_socket, client_address)  # Arguments
                )
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\nServer shutting down...")  # Graceful shutdown
        finally:
            self.server_socket.close()  # Close server socket

    def timer_thread(self):
        """Monitor auction timer and end auction when time expires."""
        while True:
            escalation_result = self.auction.finalize_escalation_if_due()  # Check escalation window
            if escalation_result:
                msg = (
                    f"ESCALATION RESOLVED|winner={escalation_result['winner']}|"
                    f"highest_bid={escalation_result['highest_bid']:.2f}|"
                    f"reason={escalation_result['reason']}\n"
                )  # Escalation finished
                self.broadcast(msg)  # Notify all clients

            # Check if auction time has expired
            state = self.auction.get_state()  # Get auction state
            now = time.time()  # Current time
            if (
                state['auction_active']
                and state['tie_active']
                and state['escalation_end_time']
                and now < state['escalation_end_time']
            ):
                time.sleep(0.1)  # Wait if escalation is happening
                continue

            if state['auction_active'] and state['end_time'] and now >= state['end_time']:
                # End the auction
                final_bid, final_bidder = self.auction.end_auction()  # End auction

                # Broadcast result
                if final_bidder:
                    msg = f"AUCTION ENDED|winner={final_bidder}|bid={final_bid:.2f}|result=won\n"  # Final winner
                else:
                    msg = "AUCTION ENDED|result=unsold|reason=No valid bids\n"  # No valid bids

                self.broadcast(msg)  # Notify all clients
                print("Auction ended by timer")  # Log
                continue

            time.sleep(0.1)  # Check every 100ms to avoid busy waiting

    def _send_client(self, client_entry, message):
        try:
            with client_entry['send_lock']:  # Acquire lock for thread safety
                client_entry['socket'].sendall(message.encode('utf-8'))  # Send encoded message
        except Exception:
            return False  # Sending failed
        return True  # Sending succeeded

    def _recv_line(self, sock, recv_buffer):
        """Read one newline-delimited message with buffering for TCP framing."""
        while b'\n' not in recv_buffer:
            chunk = sock.recv(4096)  # Read up to 4096 bytes
            if not chunk:  # Client disconnected
                return None, recv_buffer
            recv_buffer += chunk  # Append to buffer
            if len(recv_buffer) > self.max_line_bytes:
                raise ValueError("Incoming message too large")  # Prevent DoS

        raw_line, recv_buffer = recv_buffer.split(b'\n', 1)  # Split at newline
        line = raw_line.decode('utf-8', errors='replace').strip()  # Decode and strip
        return line, recv_buffer  # Return line and remaining buffer

    def _active_usernames(self):  # List of active connected users
        with self.usernames_lock:
            return sorted(list(self.usernames))  # Return sorted usernames

    def admin_listener_thread(self):
        """Accept admin portal connections and process commands over TCP."""
        while True:
            try:
                admin_socket, admin_address = self.admin_server_socket.accept()  # Accept admin connection
                print(f"Admin portal connected from {admin_address}")  # Log
                threading.Thread(
                    target=self.handle_admin_client,  # Handle admin
                    args=(admin_socket, admin_address),
                    daemon=True,  # Daemon thread
                ).start()
            except Exception as exc:
                print(f"Admin listener error: {exc}")  # Log error

    def handle_admin_client(self, admin_socket, admin_address):
        try:
            admin_socket.settimeout(self.recv_timeout_seconds)  # Set timeout
            last_activity = time.time()  # Track last activity
            recv_buffer = b""  # Buffer for incoming data

            def send_admin(message):
                admin_socket.sendall(message.encode('utf-8'))  # Send message to admin

            send_admin("CONNECTED TO ADMIN PORTAL\n")  # Initial greeting

            while True:
                try:
                    raw, recv_buffer = self._recv_line(admin_socket, recv_buffer)  # Receive command
                except socket.timeout:
                    if time.time() - last_activity >= self.admin_idle_timeout_seconds:
                        print(f"Admin portal idle timeout {admin_address}")  # Idle timeout
                        break
                    continue
                except ValueError as exc:
                    print(f"Admin portal protocol error {admin_address}: {exc}")  # Protocol error
                    break

                if raw is None:
                    break  # Disconnected

                last_activity = time.time()  # Update activity
                if not raw:
                    continue  # Ignore empty

                parts = raw.split()  # Split command
                command = parts[0].upper()  # Command keyword

                if command == 'START':
                    if len(parts) < 4:
                        response = "ERROR START requires duration and base_price\n"
                    else:
                        try:
                            duration = int(parts[1])  # Auction duration
                            base_price = float(parts[2])  # Starting price
                            escalation_window = int(parts[3])  # Escalation window
                            item = " ".join(parts[4:]).strip() if len(parts) > 4 else None  # Item name
                            start_result = self.auction.start_auction(
                                item=item,
                                duration_seconds=duration,
                                base_price=base_price,
                                escalation_window_seconds=escalation_window,
                            )
                            response = (
                                f"OK STARTED|item={start_result['item']}|duration={duration}|"
                                f"base_price={base_price:.2f}|escalation={escalation_window}\n"
                            )
                            self.broadcast(response)  # Notify all clients
                        except ValueError:
                            response = "ERROR START requires numeric duration, base_price, and escalation_seconds\n"

                elif command == 'STOP':
                    final_bid, final_bidder = self.auction.end_auction()  # End auction
                    if final_bidder:
                        response = f"OK STOPPED | Winner: {final_bidder} | Bid: ${final_bid:.2f}\n"
                    else:
                        response = "OK STOPPED | UNSOLD\n"
                    self.broadcast(response)  # Notify all clients

                elif command == 'STATUS':
                    state = self.auction.get_state()  # Get auction state
                    if state['auction_active'] and state['end_time']:
                        time_left = max(0, int(state['end_time'] - time.time()))  # Time left
                    else:
                        time_left = 0
                    response = (
                        f"STATUS|active={state['auction_active']}|item={state['item']}|"
                        f"base_price={state['base_price']:.2f}|escalation={state['escalation_window_seconds']}|"
                        f"highest={state['highest_bid']:.2f}|bidder={state['highest_bidder']}|time_left={time_left}\n"
                    )

                else:
                    response = "ERROR Unknown command. Supported: START, STOP, STATUS\n"

                send_admin(response)  # Send response
        except Exception as exc:
            print(f"Admin portal error {admin_address}: {exc}")  # Log error
        finally:
            try:
                admin_socket.close()  # Close socket
            except Exception:
                pass

    def handle_client(self, client_socket, client_address):
        """Handle communication with a single client."""
        username = None  # Username for this client
        try:
            client_socket.settimeout(self.recv_timeout_seconds)  # Set socket timeout
            last_activity = time.time()  # Track last activity
            recv_buffer = b""  # Buffer for incoming data

            # Request username with JOIN command
            client_entry = None
            initial_entry = {'socket': client_socket, 'send_lock': threading.Lock()}  # For pre-join

            state = self.auction.get_state()  # Get auction state
            if state['auction_active'] and state['end_time']:
                time_left = max(0, int(state['end_time'] - time.time()))  # Time left
            else:
                time_left = 0
            esc_left = 0
            if state['tie_active'] and state['escalation_end_time']:
                esc_left = max(0, int(state['escalation_end_time'] - time.time()))  # Escalation left
            participants = self._active_usernames()  # Current users

            prejoin_msg = (
                f"PREJOIN|item={state['item']}|base_price={state['base_price']:.2f}|"
                f"highest={state['highest_bid']:.2f}|leader={state['highest_bidder']}|"
                f"active={state['auction_active']}|time_left={time_left}|"
                f"escalation_left={esc_left}|participants={len(participants)}|"
                f"users={','.join(participants)}\n"
            )
            self._send_client(initial_entry, prejoin_msg)  # Send auction info
            self._send_client(initial_entry, "Enter command: JOIN <username>\n")  # Prompt for username

            # Keep asking for valid username until successful
            while not username:
                try:
                    data, recv_buffer = self._recv_line(client_socket, recv_buffer)  # Receive input
                except socket.timeout:
                    if time.time() - last_activity >= self.client_idle_timeout_seconds:
                        self._send_client(initial_entry, "ERROR Connection closed due to inactivity\n")  # Idle timeout
                        return
                    continue
                except ValueError:
                    self._send_client(initial_entry, "ERROR Incoming message too large\n")  # Too large
                    return

                last_activity = time.time()  # Update activity

                if data is None:
                    self._send_client(initial_entry, "Invalid input. Disconnecting.\n")  # Disconnected
                    return

                if not data:
                    continue  # Ignore empty

                command = data.split(maxsplit=1)  # Split command

                if command[0].upper() == 'JOIN' and len(command) > 1:
                    potential_username = command[1].strip()  # Extract username

                    if not potential_username:
                        self._send_client(initial_entry, "ERROR Username cannot be empty\n")
                        self._send_client(initial_entry, "Enter command: JOIN <username>\n")
                        continue

                    # Check if username already taken
                    with self.usernames_lock:
                        if potential_username in self.usernames:
                            self._send_client(initial_entry, "ERROR Username already taken\n")
                            self._send_client(initial_entry, "Enter command: JOIN <username>\n")
                            continue

                        # Add username to the set
                        self.usernames.add(potential_username)
                        username = potential_username
                else:
                    self._send_client(initial_entry, "Invalid command. Use: JOIN <username>\n")

            # Register client
            client_entry = {
                'socket': client_socket,
                'send_lock': threading.Lock(),
                'username': username,
                'address': client_address,
            }

            with self.clients_lock:
                self.clients.append(client_entry)  # Add to client list

            # Calculate time left
            state = self.auction.get_state()
            if state['auction_active'] and state['end_time']:
                time_left = max(0, int(state['end_time'] - time.time()))
            else:
                time_left = 0

            # Send welcome info with item and timer
            participants = self._active_usernames()
            welcome_msg = (
                f"JOINED|username={username}|item={self.auction.item}|base_price={self.auction.base_price:.2f}|"
                f"duration={self.auction.default_duration_seconds}|escalation={self.auction.escalation_window_seconds}|"
                f"time_left={time_left}|active={state['auction_active']}|highest={state['highest_bid']:.2f}|"
                f"leader={state['highest_bidder']}|participants={len(participants)}|"
                f"users={','.join(participants)}\n"
            )
            self._send_client(client_entry, welcome_msg)  # Send welcome

            # Handle client commands
            while True:
                try:
                    data, recv_buffer = self._recv_line(client_socket, recv_buffer)  # Receive command
                except socket.timeout:
                    if time.time() - last_activity >= self.client_idle_timeout_seconds:
                        self._send_client(client_entry, "ERROR Connection closed due to inactivity\n")  # Idle timeout
                        break
                    continue
                except ValueError:
                    self._send_client(client_entry, "ERROR Incoming message too large\n")  # Too large
                    break

                last_activity = time.time()  # Update activity

                if data is None:
                    break  # Disconnected

                if not data:
                    continue  # Ignore empty

                command = data.split()  # Split command
                if not command:
                    continue

                if command[0].upper() == 'EXIT':
                    self._send_client(client_entry, "Goodbye!\n")  # Exit
                    break

                elif command[0].upper() == 'BID':
                    if len(command) < 2:
                        self._send_client(client_entry, "Invalid command. Use: BID <amount>\n")
                        continue

                    try:
                        amount = float(command[1])  # Parse bid amount
                        result = self.auction.place_bid(amount, username)  # Place bid
                        state = self.auction.get_state()
                        time_left = 0
                        if state['auction_active'] and state['end_time']:
                            time_left = max(0, int(state['end_time'] - time.time()))

                        if result['accepted']:
                            bidder = result['highest_bidder']
                            current_bid = result['highest_bid']

                            if result.get('blind'):
                                esc_end = int(result['escalation_end_time'] - time.time())
                                sender_msg = (
                                    f"BID UPDATE|status=escalation_blind|bidder={username}|amount={amount:.2f}|"
                                    f"highest={current_bid:.2f}|leader={bidder}|time_left={time_left}|"
                                    f"escalation_left={max(0, esc_end)}\n"
                                )
                                others_msg = (
                                    f"BID UPDATE|status=escalation_blind|bidder={username}|amount=HIDDEN|"
                                    f"highest={current_bid:.2f}|leader={bidder}|time_left={time_left}|"
                                    f"escalation_left={max(0, esc_end)}\n"
                                )
                                self._send_client(client_entry, sender_msg)  # Notify bidder
                                self.broadcast(others_msg, exclude_socket=client_socket)  # Notify others

                            elif result.get('tie'):
                                esc_end = int(result['escalation_end_time'] - time.time())
                                msg = f"BID UPDATE|status=tie|bidder={username}|amount={amount:.2f}|highest={current_bid:.2f}|leader={bidder}|time_left={time_left}|escalation_left={max(0, esc_end)}\n"

                                if result.get('escalation_started'):
                                    escalation_msg = (
                                        f"ESCALATION STARTED|highest={current_bid:.2f}|"
                                        f"escalation_left={max(0, esc_end)}|"
                                        f"note=Blind round active. Submit a higher bid to win.\n"
                                    )
                                    self.broadcast(escalation_msg)  # Notify all

                                if result.get('timer_extended'):
                                    msg = msg.strip() + f"|anti_sniping_extended=1\n"

                                self._send_client(client_entry, msg)  # Notify bidder
                                self.broadcast(msg, exclude_socket=client_socket)  # Notify others

                            else:
                                msg = f"BID UPDATE|status=accepted|bidder={username}|amount={amount:.2f}|highest={current_bid:.2f}|leader={bidder}|time_left={time_left}\n"

                                if result.get('timer_extended'):
                                    msg = msg.strip() + f"|anti_sniping_extended=1\n"

                                self._send_client(client_entry, msg)  # Notify bidder
                                self.broadcast(msg, exclude_socket=client_socket)  # Notify others
                        else:
                            current_bid = result['highest_bid']
                            bidder = result['highest_bidder']
                            bidder_text = bidder if bidder else "None"
                            msg = f"BID UPDATE|status=rejected|bidder={username}|amount={amount:.2f}|reason={result['reason']}|highest={current_bid:.2f}|leader={bidder_text}|time_left={time_left}\n"
                            self._send_client(client_entry, msg)  # Notify bidder
                            self.broadcast(msg)  # Notify all
                    except ValueError:
                        with client_entry['send_lock']:
                            client_socket.sendall(b"Invalid amount. Please enter a number.\n")  # Invalid input

                elif command[0].upper() == 'GET':
                    state = self.auction.get_state()  # Get state
                    bid = state['highest_bid']
                    bidder = state['highest_bidder']
                    participants = self._active_usernames()
                    if state['auction_active'] and state['end_time']:
                        time_left = max(0, int(state['end_time'] - time.time()))
                    else:
                        time_left = 0
                    esc_left = 0
                    if state['tie_active'] and state['escalation_end_time']:
                        esc_left = max(0, int(state['escalation_end_time'] - time.time()))
                    msg = (
                        f"STATUS|item={state['item']}|base_price={state['base_price']:.2f}|"
                        f"highest={bid:.2f}|leader={bidder}|time_left={time_left}|"
                        f"active={state['auction_active']}|escalation_left={esc_left}|"
                        f"participants={len(participants)}|users={','.join(participants)}\n"
                    )
                    self._send_client(client_entry, msg)  # Send status

                elif command[0].upper() == 'REPUTATION':
                    snapshot = self.auction.get_reputation_snapshot()  # Get reputation
                    participants = self._active_usernames()
                    active_snapshot = {u: snapshot[u] for u in participants if u in snapshot}

                    if not active_snapshot:
                        with client_entry['send_lock']:
                            client_socket.sendall(b"No reputation data for active users yet.\n")  # No data
                        continue

                    rows = []
                    for bidder, stats in sorted(active_snapshot.items(), key=lambda x: x[1]['score'], reverse=True):
                        rows.append(
                            f"{bidder}={stats['score']:.2f}(wins={stats['wins']},valid={stats['valid_bids']})"
                        )
                    self._send_client(
                        client_entry,
                        "REPUTATION|scope=active|participants="
                        + str(len(participants))
                        + "|users="
                        + ",".join(participants)
                        + "|"
                        + "|".join(rows)
                        + "\n",
                    )  # Send reputation

                else:
                    with client_entry['send_lock']:
                        client_socket.sendall(b"Unknown command. Use: BID <amount>, GET, REPUTATION, or EXIT\n")  # Unknown command

        except Exception as e:
            print(f"Error handling client {client_address}: {e}")  # Log error

        finally:
            # Remove username from set safely
            if username:
                with self.usernames_lock:
                    self.usernames.discard(username)  # Remove username

            # Remove client from list
            with self.clients_lock:
                self.clients = [c for c in self.clients if c['socket'] != client_socket]  # Remove client

            client_socket.close()  # Close socket
            print(f"Client {username or client_address} disconnected")  # Log disconnect

    def broadcast(self, message, exclude_socket=None):
        """Send message to all connected clients except the sender."""
        print(message.strip())  # Log broadcast
        with self.clients_lock:
            for client in self.clients:
                if exclude_socket and client['socket'] == exclude_socket:
                    continue  # Skip excluded socket
                self._send_client(client, message)  # Send message


if __name__ == '__main__':
    server = AuctionServer(host='localhost', port=5000)  # Create server instance
    server.start()  # Start server
