import queue
import socket
import ssl
import threading
import tkinter as tk
from tkinter import messagebox


class AuctionUIClient:
    def __init__(self, root): #The constructor initializes the AuctionUIClient class, which represents the client application for participating in the auction.
        self.root = root
        self.root.title("Auction Bidder")
        self.root.geometry("700x460")

        self.sock = None
        self.connected = False
        self.joined = False
        self.msg_queue = queue.Queue()

        self._build_ui()
        self.root.after(100, self._poll_messages)

    def _build_ui(self): #This constructs the GUI using Tkinter.
        top = tk.Frame(self.root, padx=10, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="localhost")
        tk.Entry(top, textvariable=self.host_var, width=20).grid(row=0, column=1, padx=4)

        tk.Label(top, text="Port").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value="5000")
        tk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=4)

        tk.Label(top, text="Username").grid(row=0, column=4, sticky="w")
        self.username_var = tk.StringVar(value="bidder1")
        tk.Entry(top, textvariable=self.username_var, width=16).grid(row=0, column=5, padx=4)

        self.connect_btn = tk.Button(top, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=6, padx=6)

        self.join_btn = tk.Button(top, text="Join Auction", command=self.join_auction, state=tk.DISABLED)
        self.join_btn.grid(row=0, column=7, padx=6)

        self.disconnect_btn = tk.Button(top, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=8)

        status = tk.Frame(self.root, padx=10, pady=4)
        status.pack(fill=tk.X)

        self.highest_var = tk.StringVar(value="Highest Bid: --")
        self.timer_var = tk.StringVar(value="Time Left: --")
        self.item_var = tk.StringVar(value="Item: --")
        self.base_price_var = tk.StringVar(value="Base Price: --")
        self.escalation_var = tk.StringVar(value="Escalation: --")
        self.anti_sniping_var = tk.StringVar(value="Anti-sniping: --")
        self.auction_state_var = tk.StringVar(value="Auction: --")
        self.participants_var = tk.StringVar(value="Participants: --")
        tk.Label(status, textvariable=self.highest_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(status, textvariable=self.timer_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.item_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.base_price_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.escalation_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.anti_sniping_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.participants_var, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(status, textvariable=self.auction_state_var, font=("Segoe UI", 10)).pack(anchor="w")

        bid = tk.Frame(self.root, padx=10, pady=8)
        bid.pack(fill=tk.X)

        tk.Label(bid, text="Bid Amount").grid(row=0, column=0)
        self.bid_var = tk.StringVar()
        tk.Entry(bid, textvariable=self.bid_var, width=16).grid(row=0, column=1, padx=5)
        self.bid_btn = tk.Button(bid, text="Place Bid", command=self.place_bid, state=tk.DISABLED)
        self.bid_btn.grid(row=0, column=2, padx=5)

        self.get_btn = tk.Button(bid, text="Get Status", command=lambda: self.send_line("GET"), state=tk.DISABLED)
        self.get_btn.grid(row=0, column=3, padx=5)

        self.rep_btn = tk.Button(bid, text="Reputation", command=lambda: self.send_line("REPUTATION"), state=tk.DISABLED)
        self.rep_btn.grid(row=0, column=4, padx=5)

        log_frame = tk.Frame(self.root, padx=10, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log = tk.Text(log_frame, height=16, wrap=tk.WORD)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.config(yscrollcommand=scrollbar.set)

    def connect(self): #It attempts to establish a secure SSL connection to the auction server using the host and port specified in the input fields. 
        #It also validates the input fields and handles any connection errors by displaying an error message in the log. 
        #If the connection is successful, it starts a separate thread to listen for incoming messages from the server and updates the GUI state accordingly.
        if self.connected:
            return

        host = self.host_var.get().strip()
        username = self.username_var.get().strip()

        if not host or not username: #Validate that the host and username fields are not empty. If either is empty, show an error message and return without attempting to connect.
            messagebox.showerror("Error", "Host and username are required")
            return

        try:
            port = int(self.port_var.get().strip()) #Validate that the port field contains a valid integer. If it cannot be converted to an integer, show an error message and return without attempting to connect.
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return

        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.load_verify_locations(cafile='server.crt')
            context.check_hostname = False

            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #Create a raw TCP socket using the AF_INET address family and SOCK_STREAM socket type, which is suitable for TCP connections.
            self.sock = context.wrap_socket(raw_sock, server_hostname=host)
            self.sock.connect((host, port))
            self.connected = True

            threading.Thread(target=self._receiver_loop, daemon=True).start() #Start a new thread to run the _receiver_loop method, which continuously listens for incoming messages from the server. The thread is marked as a daemon so that it will automatically exit when the main program exits.

            self.connect_btn.config(state=tk.DISABLED)
            self.join_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.NORMAL)
            self._append_log(f"Connected to {host}:{port}. Click Join Auction to enter.\n")
        except Exception as exc:
            self._append_log(f"Connection failed: {exc}\n")
            self.connected = False
            self.sock = None

    def join_auction(self):
        if not self.connected or not self.sock:
            return

        username = self.username_var.get().strip()
        if not username:
            messagebox.showerror("Error", "Username is required")
            return

        self.send_line(f"JOIN {username}") #Send a JOIN command to the server with the specified username to attempt to join the auction. 
        #The server will respond with a message indicating whether the join was successful or if there was an error. The client will then update its state and GUI based on the server's response, which is processed in the _receiver_loop method.

    def disconnect(self): #This method is responsible for disconnecting from the auction server. 
        #It sends an EXIT command to the server to gracefully close the connection, and then it updates the GUI state to reflect that the client is no longer connected.
        if self.connected and self.sock:
            try:
                self.send_line("EXIT") #Send an EXIT command to the server to inform it that the client is disconnecting.
                self.sock.close()
            except Exception:
                pass

        self.connected = False
        self.joined = False
        self.sock = None
        self.connect_btn.config(state=tk.NORMAL)
        self.join_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.bid_btn.config(state=tk.DISABLED)
        self.get_btn.config(state=tk.DISABLED)
        self.rep_btn.config(state=tk.DISABLED)
        self._append_log("Disconnected\n")

    def on_close(self): #It ensures that the client properly disconnects from the server before the application exits. It calls the disconnect method to cleanly close the connection and then destroys the main application window to exit the program.
        self.disconnect()
        self.root.destroy()

    def place_bid(self): #It retrieves the bid amount from the input field, validates that it is not empty, and then sends a BID command to the server with the specified amount.
        amount = self.bid_var.get().strip()
        if not amount:
            messagebox.showerror("Error", "Enter a bid amount")
            return
        self.send_line(f"BID {amount}")

    def send_line(self, text): #This method is a helper function to send a line of text to the server. 
        #It checks if the client is currently connected and if the socket exists.
        # If the client is connected, it attempts to send the specified text followed by a newline character to the server using the SSL socket. 
        #If an error occurs during sending (e.g., if the connection is lost), it logs the error message and calls the disconnect method to update the client's state accordingly.
        if not self.connected or not self.sock:
            return
        try:
            self.sock.sendall((text + "\n").encode("utf-8"))
        except Exception as exc:
            self._append_log(f"Send error: {exc}\n")
            self.disconnect()

    def _receiver_loop(self):
        while self.connected and self.sock:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                self.msg_queue.put(data.decode("utf-8", errors="replace"))
            except Exception:
                break

        if self.connected:
            self.msg_queue.put("\nConnection closed by server\n")
        self.connected = False

    def _append_log(self, text):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _set_auction_fields(self, payload): #Just a helper method to update the auction status fields in the GUI.
        item = payload.get("item") #Looks for the item in the payload (like laptop) and then update the UI label.
        if item:
            self.item_var.set(f"Item: {item}")

        base_price = payload.get("base_price") #Gets the base price of the item.
        if base_price is not None:
            self.base_price_var.set(f"Base Price: ${float(base_price):.2f}")

        escalation = payload.get("escalation") or payload.get("escalation_left") or payload.get("escalation_window_seconds")
        if escalation is not None:
            self.escalation_var.set(f"Escalation: {escalation}s")

        active = payload.get("active") #Show if the auction is active or not based on the "active" field in the payload.
        if active is not None:
            self.auction_state_var.set("Auction: Active" if str(active).lower() in ("1", "true", "yes") else "Auction: Inactive")

        highest = payload.get("highest") or payload.get("bid") #Get the highest bid amount from the payload.
        leader = payload.get("leader") or payload.get("bidder") #Get the current highest bidder's username from the payload.
        if highest is not None: #If there is a highest bid amount, update the highest bid label in the GUI. If there is also a leader (highest bidder), include their name in the label. Otherwise, just show the highest bid amount without a bidder name.
            if leader and leader != "None":
                self.highest_var.set(f"Highest Bid: ${float(highest):.2f} by {leader}")
            else:
                self.highest_var.set(f"Highest Bid: ${float(highest):.2f}")

        time_left = payload.get("time_left") #Get the time left for the auction from the payload.
        if time_left is not None:
            self.timer_var.set(f"Time Left: {time_left}s")

        participants = payload.get("participants") #Get the number of participants in the auction from the payload.
        users = payload.get("users") #Get the list of users in the auction from the payload.
        if participants is not None: 
            if users:
                self.participants_var.set(f"Participants ({participants}): {users}")
            else:
                self.participants_var.set(f"Participants: {participants}")

#I am doing this to translate raw server messages into user-friendly updates in the GUI. 
# The server sends messages in a key-value format and this formats it properly.
    def _parse_key_values(self, line): #This method takes a line of text and parses it into an event type and a dictionary of key-value pairs.
        parts = line.strip().split("|")
        event = parts[0].strip()
        payload = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                payload[key.strip()] = value.strip()
        return event, payload

#This function is the decision-maker of my client.
# It reads messages coming from the server, figures out what type of event happened
#And then it updates the GUI and logs accordingly.
    def _parse_status(self, message):
        event, payload = self._parse_key_values(message)

        if event == "Enter command: JOIN <username>":
            self.auction_state_var.set("Auction: Connect to join")
            return

        if event == "PREJOIN":
            self._set_auction_fields(payload)
            self.auction_state_var.set("Auction: Preview (join to participate)")
            return

        if event == "JOINED":
            self.joined = True
            self.join_btn.config(state=tk.DISABLED)
            self.bid_btn.config(state=tk.NORMAL)
            self.get_btn.config(state=tk.NORMAL)
            self.rep_btn.config(state=tk.NORMAL)
            self._set_auction_fields(payload)
            self._append_log(f"Joined auction as {payload.get('username', self.username_var.get().strip())}\n")
            return

        if event in {"AUCTION STARTED", "OK STARTED"}:
            self._set_auction_fields(payload)
            self.auction_state_var.set("Auction: Active")
            if self.joined:
                self.bid_btn.config(state=tk.NORMAL)
                self.get_btn.config(state=tk.NORMAL)
                self.rep_btn.config(state=tk.NORMAL)
            return

        if event == "BID UPDATE":
            self._set_auction_fields(payload)
            status = payload.get("status", "unknown")
            bidder = payload.get("bidder", "unknown")
            amount = payload.get("amount", "--")
            if payload.get("anti_sniping_extended") == "1":
                self.anti_sniping_var.set("Anti-sniping: Extended by 5s")
                self._append_log("Anti-sniping triggered: auction timer extended\n")
            if status == "accepted":
                self._append_log(f"Accepted bid from {bidder}: ${amount}\n")
            elif status == "rejected":
                reason = payload.get("reason", "rejected")
                self._append_log(f"Rejected bid from {bidder}: ${amount} ({reason})\n")
            elif status == "tie":
                self._append_log(f"Tie bid from {bidder}: ${amount}\n")
            elif status == "escalation_blind":
                self._append_log(f"Blind escalation bid from {bidder}: {amount}\n")
            return

        if event == "ESCALATION STARTED":
            esc_left = payload.get("escalation_left", "--")
            note = payload.get("note", "Escalation round started")
            self._append_log(f"Escalation started ({esc_left}s): {note}\n")
            return

        if event == "ESCALATION RESOLVED":
            winner = payload.get("winner", "unknown")
            highest_bid = payload.get("highest_bid", "--")
            reason = payload.get("reason", "")
            self._append_log(f"Escalation resolved: winner={winner}, highest=${highest_bid}. {reason}\n")
            return

        if event == "STATUS":
            self._set_auction_fields(payload)
            return

        if event == "AUCTION ENDED":
            result = payload.get("result")
            if result == "unsold":
                self.highest_var.set("Highest Bid: UNSOLD")
                self.auction_state_var.set("Auction: Ended")
                reason = payload.get("reason")
                if reason:
                    self._append_log(f"AUCTION ENDED | UNSOLD ({reason})\n")
            else:
                winner = payload.get("winner", "unknown")
                bid = payload.get("bid", "--")
                self.highest_var.set(f"Highest Bid: ${bid} by {winner}")
                self.auction_state_var.set("Auction: Ended")
            self.bid_btn.config(state=tk.DISABLED)
            self.get_btn.config(state=tk.NORMAL if self.joined else tk.DISABLED)
            self.rep_btn.config(state=tk.NORMAL if self.joined else tk.DISABLED)
            self.anti_sniping_var.set("Anti-sniping: --")
            return

        if event == "REPUTATION":
            self._append_log(message + "\n")
            return

        if "UNSOLD" in message:
            self.highest_var.set("Highest Bid: UNSOLD")
            self.auction_state_var.set("Auction: Ended")

#This function checks if any new messages came from the server and processes them one by one.
    def _poll_messages(self):
        while not self.msg_queue.empty():
            message = self.msg_queue.get_nowait()
            for line in message.splitlines():
                if not line.strip():
                    continue
                self._append_log(line + "\n")
                self._parse_status(line)

        # If connection died from receiver thread, keep controls in sync.
        if not self.connected and self.sock is not None:
            self.disconnect()

        self.root.after(100, self._poll_messages)


def main():
    root = tk.Tk()
    app = AuctionUIClient(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
