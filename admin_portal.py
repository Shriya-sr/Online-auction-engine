import queue
import socket
import ssl
import threading
import tkinter as tk
from tkinter import messagebox


class AdminPortal:
    def __init__(self, root):
        self.root = root
        self.root.title("Auction Admin Portal")
        self.root.geometry("760x520")

        self.sock = None
        self.connected = False
        self.msg_queue = queue.Queue()

        self._build_ui()
        self.root.after(100, self._poll_messages)

    def _build_ui(self):
        top = tk.Frame(self.root, padx=10, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="localhost")
        tk.Entry(top, textvariable=self.host_var, width=18).grid(row=0, column=1, padx=4)

        tk.Label(top, text="Admin Port").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value="5001")
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
        if self.connected:
            return

        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Admin port must be a number")
            return

        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.load_verify_locations(cafile='server.crt')
            context.check_hostname = False

            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock = context.wrap_socket(raw_sock, server_hostname=host)
            self.sock.connect((host, port))
            self.connected = True

            threading.Thread(target=self._receiver_loop, daemon=True).start()
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_btn.config(state=tk.NORMAL)
            self.status_var.set(f"Connected to admin port {host}:{port}")
            self._append_log(f"Connected to admin port {host}:{port}\n")
        except Exception as exc:
            self._append_log(f"Connection failed: {exc}\n")
            self.connected = False
            self.sock = None

    def disconnect(self):
        if self.connected and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

        self.connected = False
        self.sock = None
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_btn.config(state=tk.DISABLED)
        self.status_var.set("Disconnected")
        self._append_log("Disconnected\n")

    def on_close(self):
        self.disconnect()
        self.root.destroy()

    def send_command(self, command):
        if not self.connected or not self.sock:
            return
        try:
            self.sock.sendall((command + "\n").encode("utf-8"))
        except Exception as exc:
            self._append_log(f"Send error: {exc}\n")
            self.disconnect()

    def start_auction(self):
        item = self.item_var.get().strip()
        duration = self.duration_var.get().strip()
        base_price = self.base_price_var.get().strip()

        if not duration or not base_price:
            messagebox.showerror("Error", "Duration and base price are required")
            return

        escalation = self.escalation_var.get().strip()
        if not escalation:
            messagebox.showerror("Error", "Escalation time is required")
            return

        command = f"START {duration} {base_price} {escalation} {item}".strip()
        self.send_command(command)

    def stop_auction(self):
        self.send_command("STOP")

    def status(self):
        self.send_command("STATUS")

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

    def _poll_messages(self):
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
