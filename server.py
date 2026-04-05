import socket
import ssl
import threading
import time
from auction import Auction


class AuctionServer:
    def __init__(self, host='localhost', port=5000, use_ssl=True, admin_port=5001):
        self.host = host
        self.port = port
        self.admin_port = admin_port
        self.auction = Auction()
        self.clients = []
        self.clients_lock = threading.Lock()
        self.usernames = set()
        self.usernames_lock = threading.Lock()
        self.recv_timeout_seconds = 5.0
        self.client_idle_timeout_seconds = 180.0
        self.admin_idle_timeout_seconds = 300.0
        self.max_line_bytes = 16384
        
        # Create SSL context and wrap socket
        if use_ssl:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile='server.crt', keyfile='server.key')
            
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket = context.wrap_socket(server_socket, server_side=True)

            admin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.admin_server_socket = context.wrap_socket(admin_socket, server_side=True)
        else:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.admin_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
        """Start the server and listen for incoming connections."""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.admin_server_socket.bind((self.host, self.admin_port))
        self.admin_server_socket.listen(2)
        print(f"Server started on {self.host}:{self.port}")
        print(f"Admin portal listening on {self.host}:{self.admin_port}")
        
        # Start timer thread
        timer = threading.Thread(target=self.timer_thread)
        timer.daemon = True
        timer.start()

        # Start socket-based admin listener for the GUI portal
        admin_listener = threading.Thread(target=self.admin_listener_thread)
        admin_listener.daemon = True
        admin_listener.start()

        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                print(f"New connection from {client_address}")
                
                # Handle client in a new thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\nServer shutting down...")
        finally:
            self.server_socket.close()

    def timer_thread(self):
        """Monitor auction timer and end auction when time expires."""
        while True:
            escalation_result = self.auction.finalize_escalation_if_due()
            if escalation_result:
                msg = (
                    f"ESCALATION RESOLVED|winner={escalation_result['winner']}|"
                    f"highest_bid={escalation_result['highest_bid']:.2f}|"
                    f"reason={escalation_result['reason']}\n"
                )
                self.broadcast(msg)

            # Check if auction time has expired
            state = self.auction.get_state()
            now = time.time()
            if (
                state['auction_active']
                and state['tie_active']
                and state['escalation_end_time']
                and now < state['escalation_end_time']
            ):
                time.sleep(0.1)
                continue

            if state['auction_active'] and state['end_time'] and now >= state['end_time']:
                # End the auction
                final_bid, final_bidder = self.auction.end_auction()
                
                # Broadcast result
                if final_bidder:
                    msg = f"AUCTION ENDED|winner={final_bidder}|bid={final_bid:.2f}|result=won\n"
                else:
                    msg = "AUCTION ENDED|result=unsold|reason=No valid bids\n"
                
                self.broadcast(msg)
                print("Auction ended by timer")
                continue
            
            time.sleep(0.1)  # Check every 100ms to avoid busy waiting

    def _send_client(self, client_entry, message):
        try:
            with client_entry['send_lock']:
                client_entry['socket'].sendall(message.encode('utf-8'))
        except Exception:
            return False
        return True

    def _recv_line(self, sock, recv_buffer):
        """Read one newline-delimited message with buffering for TCP framing."""
        while b'\n' not in recv_buffer:
            chunk = sock.recv(4096)
            if not chunk:
                return None, recv_buffer
            recv_buffer += chunk
            if len(recv_buffer) > self.max_line_bytes:
                raise ValueError("Incoming message too large")

        raw_line, recv_buffer = recv_buffer.split(b'\n', 1)
        line = raw_line.decode('utf-8', errors='replace').strip()
        return line, recv_buffer

    def _active_usernames(self):
        with self.usernames_lock:
            return sorted(list(self.usernames))

    def admin_listener_thread(self):
        """Accept admin portal connections and process commands over TCP."""
        while True:
            try:
                admin_socket, admin_address = self.admin_server_socket.accept()
                print(f"Admin portal connected from {admin_address}")
                threading.Thread(
                    target=self.handle_admin_client,
                    args=(admin_socket, admin_address),
                    daemon=True,
                ).start()
            except Exception as exc:
                print(f"Admin listener error: {exc}")

    def handle_admin_client(self, admin_socket, admin_address):
        try:
            admin_socket.settimeout(self.recv_timeout_seconds)
            last_activity = time.time()
            recv_buffer = b""

            def send_admin(message):
                admin_socket.sendall(message.encode('utf-8'))

            send_admin("CONNECTED TO ADMIN PORTAL\n")

            while True:
                try:
                    raw, recv_buffer = self._recv_line(admin_socket, recv_buffer)
                except socket.timeout:
                    if time.time() - last_activity >= self.admin_idle_timeout_seconds:
                        print(f"Admin portal idle timeout {admin_address}")
                        break
                    continue
                except ValueError as exc:
                    print(f"Admin portal protocol error {admin_address}: {exc}")
                    break

                if raw is None:
                    break

                last_activity = time.time()
                if not raw:
                    continue

                parts = raw.split()
                command = parts[0].upper()

                if command == 'START':
                    if len(parts) < 4:
                        response = "ERROR START requires duration and base_price\n"
                    else:
                        try:
                            duration = int(parts[1])
                            base_price = float(parts[2])
                            escalation_window = int(parts[3])
                            item = " ".join(parts[4:]).strip() if len(parts) > 4 else None
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
                            self.broadcast(response)
                        except ValueError:
                            response = "ERROR START requires numeric duration, base_price, and escalation_seconds\n"

                elif command == 'STOP':
                    final_bid, final_bidder = self.auction.end_auction()
                    if final_bidder:
                        response = f"OK STOPPED | Winner: {final_bidder} | Bid: ${final_bid:.2f}\n"
                    else:
                        response = "OK STOPPED | UNSOLD\n"
                    self.broadcast(response)

                elif command == 'STATUS':
                    state = self.auction.get_state()
                    if state['auction_active'] and state['end_time']:
                        time_left = max(0, int(state['end_time'] - time.time()))
                    else:
                        time_left = 0
                    response = (
                        f"STATUS|active={state['auction_active']}|item={state['item']}|"
                        f"base_price={state['base_price']:.2f}|escalation={state['escalation_window_seconds']}|"
                        f"highest={state['highest_bid']:.2f}|bidder={state['highest_bidder']}|time_left={time_left}\n"
                    )

                else:
                    response = "ERROR Unknown command. Supported: START, STOP, STATUS\n"

                send_admin(response)
        except Exception as exc:
            print(f"Admin portal error {admin_address}: {exc}")
        finally:
            try:
                admin_socket.close()
            except Exception:
                pass

    def handle_client(self, client_socket, client_address):
        """Handle communication with a single client."""
        username = None
        try:
            client_socket.settimeout(self.recv_timeout_seconds)
            last_activity = time.time()
            recv_buffer = b""

            # Request username with JOIN command
            client_entry = None
            initial_entry = {'socket': client_socket, 'send_lock': threading.Lock()}

            state = self.auction.get_state()
            if state['auction_active'] and state['end_time']:
                time_left = max(0, int(state['end_time'] - time.time()))
            else:
                time_left = 0
            esc_left = 0
            if state['tie_active'] and state['escalation_end_time']:
                esc_left = max(0, int(state['escalation_end_time'] - time.time()))
            participants = self._active_usernames()

            prejoin_msg = (
                f"PREJOIN|item={state['item']}|base_price={state['base_price']:.2f}|"
                f"highest={state['highest_bid']:.2f}|leader={state['highest_bidder']}|"
                f"active={state['auction_active']}|time_left={time_left}|"
                f"escalation_left={esc_left}|participants={len(participants)}|"
                f"users={','.join(participants)}\n"
            )
            self._send_client(initial_entry, prejoin_msg)
            self._send_client(initial_entry, "Enter command: JOIN <username>\n")
            
            # Keep asking for valid username until successful
            while not username:
                try:
                    data, recv_buffer = self._recv_line(client_socket, recv_buffer)
                except socket.timeout:
                    if time.time() - last_activity >= self.client_idle_timeout_seconds:
                        self._send_client(initial_entry, "ERROR Connection closed due to inactivity\n")
                        return
                    continue
                except ValueError:
                    self._send_client(initial_entry, "ERROR Incoming message too large\n")
                    return

                last_activity = time.time()
                
                if data is None:
                    self._send_client(initial_entry, "Invalid input. Disconnecting.\n")
                    return

                if not data:
                    continue
                
                command = data.split(maxsplit=1)
                
                if command[0].upper() == 'JOIN' and len(command) > 1:
                    potential_username = command[1].strip()

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
                self.clients.append(client_entry)
            
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
            self._send_client(client_entry, welcome_msg)
            
            # Handle client commands
            while True:
                try:
                    data, recv_buffer = self._recv_line(client_socket, recv_buffer)
                except socket.timeout:
                    if time.time() - last_activity >= self.client_idle_timeout_seconds:
                        self._send_client(client_entry, "ERROR Connection closed due to inactivity\n")
                        break
                    continue
                except ValueError:
                    self._send_client(client_entry, "ERROR Incoming message too large\n")
                    break

                last_activity = time.time()
                
                if data is None:
                    break

                if not data:
                    continue
                
                command = data.split()
                if not command:
                    continue
                
                if command[0].upper() == 'EXIT':
                    self._send_client(client_entry, "Goodbye!\n")
                    break
                
                elif command[0].upper() == 'BID':
                    if len(command) < 2:
                        self._send_client(client_entry, "Invalid command. Use: BID <amount>\n")
                        continue
                    
                    try:
                        amount = float(command[1])
                        result = self.auction.place_bid(amount, username)
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
                                self._send_client(client_entry, sender_msg)
                                self.broadcast(others_msg, exclude_socket=client_socket)

                            elif result.get('tie'):
                                esc_end = int(result['escalation_end_time'] - time.time())
                                msg = f"BID UPDATE|status=tie|bidder={username}|amount={amount:.2f}|highest={current_bid:.2f}|leader={bidder}|time_left={time_left}|escalation_left={max(0, esc_end)}\n"

                                if result.get('escalation_started'):
                                    escalation_msg = (
                                        f"ESCALATION STARTED|highest={current_bid:.2f}|"
                                        f"escalation_left={max(0, esc_end)}|"
                                        f"note=Blind round active. Submit a higher bid to win.\n"
                                    )
                                    self.broadcast(escalation_msg)

                                if result.get('timer_extended'):
                                    msg = msg.strip() + f"|anti_sniping_extended=1\n"

                                self._send_client(client_entry, msg)
                                self.broadcast(msg, exclude_socket=client_socket)

                            else:
                                msg = f"BID UPDATE|status=accepted|bidder={username}|amount={amount:.2f}|highest={current_bid:.2f}|leader={bidder}|time_left={time_left}\n"

                                if result.get('timer_extended'):
                                    msg = msg.strip() + f"|anti_sniping_extended=1\n"

                                self._send_client(client_entry, msg)
                                self.broadcast(msg, exclude_socket=client_socket)
                        else:
                            current_bid = result['highest_bid']
                            bidder = result['highest_bidder']
                            bidder_text = bidder if bidder else "None"
                            msg = f"BID UPDATE|status=rejected|bidder={username}|amount={amount:.2f}|reason={result['reason']}|highest={current_bid:.2f}|leader={bidder_text}|time_left={time_left}\n"
                            self._send_client(client_entry, msg)
                            self.broadcast(msg)
                    except ValueError:
                        with client_entry['send_lock']:
                            client_socket.sendall(b"Invalid amount. Please enter a number.\n")
                
                elif command[0].upper() == 'GET':
                    state = self.auction.get_state()
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
                    self._send_client(client_entry, msg)

                elif command[0].upper() == 'REPUTATION':
                    snapshot = self.auction.get_reputation_snapshot()
                    participants = self._active_usernames()
                    active_snapshot = {u: snapshot[u] for u in participants if u in snapshot}

                    if not active_snapshot:
                        with client_entry['send_lock']:
                            client_socket.sendall(b"No reputation data for active users yet.\n")
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
                    )
                
                else:
                    with client_entry['send_lock']:
                        client_socket.sendall(b"Unknown command. Use: BID <amount>, GET, REPUTATION, or EXIT\n")
        
        except Exception as e:
            print(f"Error handling client {client_address}: {e}")
        
        finally:
            # Remove username from set safely
            if username:
                with self.usernames_lock:
                    self.usernames.discard(username)
            
            # Remove client from list
            with self.clients_lock:
                self.clients = [c for c in self.clients if c['socket'] != client_socket]
            
            client_socket.close()
            print(f"Client {username or client_address} disconnected")

    def broadcast(self, message, exclude_socket=None):
        """Send message to all connected clients except the sender."""
        print(message.strip())
        with self.clients_lock:
            for client in self.clients:
                if exclude_socket and client['socket'] == exclude_socket:
                    continue
                self._send_client(client, message)


if __name__ == '__main__':
    server = AuctionServer(host='localhost', port=5000)
    server.start()
