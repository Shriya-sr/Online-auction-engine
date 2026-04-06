import queue
import socket
import ssl
import threading
import tkinter as tk
from tkinter import messagebox

#Admin portal GUI for controlling the auction server. 
#Allows starting/stopping auctions and viewing status updates. 
#Communicates with the server over a secure SSL connection on the admin port.

class AdminPortal:
    def __init__(self, root):
        self.root = root
        self.root.title("Auction Admin Portal")
        self.root.geometry("760x520")

        self.sock = None #Admin socket connection initially None
        self.connected = False #Connection state flag
        self.msg_queue = queue.Queue() #Thread-safe communication between receiver thread and GUI

        self._build_ui() #Set up the GUI components
        self.root.after(100, self._poll_messages) #Start polling for messages from the server every 100ms

    def _build_ui(self):
        top = tk.Frame(self.root, padx=10, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="localhost") #Default host is localhost
        tk.Entry(top, textvariable=self.host_var, width=18).grid(row=0, column=1, padx=4)

        tk.Label(top, text="Admin Port").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value="5001") #Default admin port is 5001
        tk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=4)

        self.connect_btn = tk.Button(top, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=4, padx=6)

        self.disconnect_btn = tk.Button(top, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=5, padx=6)

        form = tk.Frame(self.root, padx=10, pady=6)
        form.pack(fill=tk.X)

        tk.Label(form, text="Item").grid(row=0, column=0, sticky="w")
        self.item_var = tk.StringVar(value="Auction Item")
        tk.Entry(form, textvariable=self.item_var, width=20).grid(row=0, column=1, padx=4)

        tk.Label(form, text="Duration").grid(row=0, column=2, sticky="w")
        self.duration_var = tk.StringVar(value="60")
        tk.Entry(form, textvariable=self.duration_var, width=8).grid(row=0, column=3, padx=4)

        tk.Label(form, text="Base Price").grid(row=0, column=4, sticky="w")
        self.base_price_var = tk.StringVar(value="100")
        tk.Entry(form, textvariable=self.base_price_var, width=10).grid(row=0, column=5, padx=4)

        tk.Label(form, text="Escalation").grid(row=1, column=0, sticky="w")
        self.escalation_var = tk.StringVar(value="5")
        tk.Entry(form, textvariable=self.escalation_var, width=8).grid(row=1, column=1, padx=4)

        actions = tk.Frame(self.root, padx=10, pady=10)
        actions.pack(fill=tk.X)

        self.start_btn = tk.Button(actions, text="Start Auction", command=self.start_auction, state=tk.DISABLED)
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = tk.Button(actions, text="Stop Auction", command=self.stop_auction, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)

        self.status_btn = tk.Button(actions, text="Status", command=self.status, state=tk.DISABLED)
        self.status_btn.grid(row=0, column=2, padx=5)

        self.status_var = tk.StringVar(value="Disconnected")
        tk.Label(self.root, textvariable=self.status_var, padx=10, pady=4).pack(anchor="w")

        log_frame = tk.Frame(self.root, padx=10, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log = tk.Text(log_frame, height=18, wrap=tk.WORD)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.config(yscrollcommand=scrollbar.set)

    def connect(self):
        if self.connected: #Already connected, do nothing
            return

        host = self.host_var.get().strip() #Get host from input field
        try:
            port = int(self.port_var.get().strip()) #Get admin port from input field and convert to integer
        except ValueError:
            messagebox.showerror("Error", "Admin port must be a number")
            return

        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH) #Create SSL context for secure connection
            context.load_verify_locations(cafile='server.crt') #Load server certificate for verification
            context.check_hostname = False #Disable hostname checking since we're connecting to localhost
            #This sets up a secure SSL connection to the admin port of the auction server + server verification using the provided certificate. 
            # If the connection is successful, it starts a receiver thread to listen for messages from the server and updates the GUI state accordingly. 
            # If the connection fails, it logs the error and resets the connection state.

            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #Create a raw TCP socket
            self.sock = context.wrap_socket(raw_sock, server_hostname=host) #Wrap the raw socket with SSL for secure communication
            self.sock.connect((host, port)) #Connect to the server at the specified host and admin port
            self.connected = True

            threading.Thread(target=self._receiver_loop, daemon=True).start() #Start a background thread to receive messages from the server without blocking the GUI
            self.connect_btn.config(state=tk.DISABLED) #Disable the connect button since we're now connected
            self.disconnect_btn.config(state=tk.NORMAL) #Enable the disconnect button to allow disconnecting from the server
            self.start_btn.config(state=tk.NORMAL) #Enable the start auction button to allow starting auctions
            self.stop_btn.config(state=tk.NORMAL) #Enable the stop auction button to allow stopping auctions
            self.status_btn.config(state=tk.NORMAL) #Enable the status button to allow requesting auction status
            self.status_var.set(f"Connected to admin port {host}:{port}")
            self._append_log(f"Connected to admin port {host}:{port}\n")
        except Exception as exc:
            self._append_log(f"Connection failed: {exc}\n")
            self.connected = False
            self.sock = None

    def disconnect(self):
        if self.connected and self.sock: #If currently connected and socket exists, attempt to close the connection gracefully
            try:
                self.sock.close()
            except Exception:
                pass

        self.connected = False
        self.sock = None
        self.connect_btn.config(state=tk.NORMAL) #Enable the connect button to allow reconnecting to the server
        self.disconnect_btn.config(state=tk.DISABLED) #Disable the disconnect button since we're now disconnected
        self.start_btn.config(state=tk.DISABLED) #Disable the start auction button since we can't start auctions when disconnected
        self.stop_btn.config(state=tk.DISABLED) #Disable the stop auction button since we can't stop auctions when disconnected
        self.status_btn.config(state=tk.DISABLED) #Disable the status button since we can't request status when disconnected
        self.status_var.set("Disconnected")
        self._append_log("Disconnected\n")

    def on_close(self): #Handle the window close event by disconnecting from the server and then closing the application
        self.disconnect()
        self.root.destroy()

    def send_command(self, command): #Send a command to the server if connected. If not connected, do nothing. If an error occurs while sending, log the error and disconnect from the server.
        if not self.connected or not self.sock:
            return
        try: #I want every command to be sent as a single line terminated by a newline character, encoded as UTF-8 bytes, to ensure proper communication with the server.
            self.sock.sendall((command + "\n").encode("utf-8")) #Send the command followed by a newline character, encoded as UTF-8 bytes, to the server over the SSL socket
        except Exception as exc:
            self._append_log(f"Send error: {exc}\n")
            self.disconnect()
# Command means the instructions sent from the admin portal to the auction server to perform actions like starting/stopping auctions or requesting status updates.
    def start_auction(self): #Gather the auction parameters from the input fields, validate them, 
        #and send a START command to the server with the specified parameters. 
        # If any required parameter is missing or invalid, show an error message and do not send the command.
        item = self.item_var.get().strip()
        duration = self.duration_var.get().strip()
        base_price = self.base_price_var.get().strip()

        if not duration or not base_price: #Duration and base price are required fields for starting an auction. 
            #If either is missing, show an error message and return without sending the command.
            messagebox.showerror("Error", "Duration and base price are required")
            return

        escalation = self.escalation_var.get().strip() # Retrieve escalation time from input field and remove any leading/trailing whitespace
        if not escalation: #Check if escalation time is empty after stripping
            messagebox.showerror("Error", "Escalation time is required") #Show error dialog if no escalation time is provided
            return

        command = f"START {duration} {base_price} {escalation} {item}".strip() #Builds the network message that will be sent to the server
        self.send_command(command) #Send the constructed command to the server using the send_command method, which handles the actual network communication and error handling.

    def stop_auction(self): #Send a STOP command to the server to end the current auction. If not connected, do nothing. If an error occurs while sending, log the error and disconnect from the server.
        self.send_command("STOP")

    def status(self): #Send a STATUS command to the server to request the current status of the auction. If not connected, do nothing. If an error occurs while sending, log the error and disconnect from the server.
        self.send_command("STATUS")

    def _receiver_loop(self): #This is the main loop that runs in a separate thread to continuously receive messages from the server. 
        # It listens for incoming data on the SSL socket, decodes it, and puts it into a thread-safe queue for the main GUI thread to process. 
        # If the connection is closed by the server or an error occurs, it updates the connection state and logs the disconnection.
        while self.connected and self.sock: #Keep running as long as we're connected and the socket exists
            try:
                data = self.sock.recv(4096) #Receive data from the server with a buffer size of 4096 bytes. This will block until data is received or the connection is closed.
                if not data: #If recv returns an empty byte string, it means the connection has been closed by the server. In that case, we should exit the loop and update the connection state.
                    break
                self.msg_queue.put(data.decode("utf-8", errors="replace")) #Decode the received bytes into a UTF-8 string, replacing any invalid byte sequences with a placeholder character, and put the resulting string into the message queue for the main GUI thread to process and display in the log.
            except Exception:
                break

        if self.connected: #If we exited the loop while still marked as connected, it means the connection was closed by the server. We should update the connection state and log this event.
            self.msg_queue.put("\nConnection closed by server\n")
        self.connected = False

    def _append_log(self, text): #Append the given text to the log text widget in the GUI. After inserting the new text, it scrolls the log to the end to ensure the latest messages are visible.
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _poll_messages(self): #This method is called periodically (every 100ms) by the main GUI thread to check for new messages from the server. 
        #It retrieves messages from the message queue and appends them to the log. It also updates the status label with the latest message if it contains any text.
        # If the connection has been closed, it calls the disconnect method to update the GUI state accordingly. Finally, it schedules itself to be called again after 100ms to continue polling for messages.
        while not self.msg_queue.empty():
            message = self.msg_queue.get_nowait()
            self._append_log(message)
            self.status_var.set(message.strip().splitlines()[-1] if message.strip() else self.status_var.get())

        if not self.connected and self.sock is not None:
            self.disconnect()

        self.root.after(100, self._poll_messages)


def main():
    root = tk.Tk()
    app = AdminPortal(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
