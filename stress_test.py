import os, sys, ssl, socket, threading, time, statistics, json

root = r"D:\Desktop\PES\SEM4\CN\Lab project\auction_engine_done"
oa_dir = os.path.join(root, "OA")
sys.path.insert(0, oa_dir)

from server import AuctionServer

HOST = "localhost"
PORT = 5610
ADMIN_PORT = 5611
CERT = os.path.join(oa_dir, "server.crt")

def make_ctx():
    ctx = ssl.create_default_context(cafile=CERT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx

class Client:
    def __init__(self, name):
        self.name = name
        self.sock = None
        self.buf = ""

    def connect_and_join(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock = make_ctx().wrap_socket(raw, server_hostname=HOST)
        self.sock.settimeout(3.0)
        self.sock.connect((HOST, PORT))
        self._read_until_any(["Enter command: JOIN <username>", "JOINED|"])
        self.send(f"JOIN {self.name}")
        self._read_until_any(["JOINED|"])

    def send(self, line):
        self.sock.sendall((line + "\n").encode("utf-8"))

    def _readline(self, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                return line.strip()
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return ""
                self.buf += chunk.decode("utf-8", errors="replace")
            except socket.timeout:
                continue
        return ""

    def _read_until_any(self, needles, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            line = self._readline(timeout=0.5)
            if not line:
                continue
            if any(n in line for n in needles):
                return line
        return ""

    def bid_and_wait(self, amount):
        t0 = time.perf_counter()
        self.send(f"BID {amount}")
        end = time.time() + 5.0
        while time.time() < end:
            line = self._readline(timeout=0.5)
            if not line:
                continue
            if "BID UPDATE|" in line and f"bidder={self.name}" in line:
                return (time.perf_counter() - t0) * 1000.0
        return None

    def send_and_wait_any(self, cmd, tokens):
        t0 = time.perf_counter()
        self.send(cmd)
        end = time.time() + 5.0
        while time.time() < end:
            line = self._readline(timeout=0.5)
            if not line:
                continue
            if any(tok in line for tok in tokens):
                return (time.perf_counter() - t0) * 1000.0
        return None

    def close(self):
        try:
            self.send("EXIT")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

def admin_cmd(cmd, wait_tokens=("OK", "STATUS", "ERROR"), timeout=5.0):
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s = make_ctx().wrap_socket(raw, server_hostname=HOST)
    s.settimeout(3.0)
    s.connect((HOST, ADMIN_PORT))
    try:
        s.recv(4096)
    except Exception:
        pass
    s.sendall((cmd + "\n").encode("utf-8"))
    buf = ""
    end = time.time() + timeout
    while time.time() < end:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            for ln in buf.splitlines():
                if any(t in ln for t in wait_tokens):
                    s.close()
                    return ln
        except socket.timeout:
            continue
    s.close()
    return ""

def run_parallel_bids(clients, amounts):
    lats = []
    lock = threading.Lock()

    def worker(c, amt):
        lat = c.bid_and_wait(amt)
        with lock:
            if lat is not None:
                lats.append(round(lat, 4))

    t0 = time.perf_counter()
    threads = []
    for c, a in zip(clients, amounts):
        th = threading.Thread(target=worker, args=(c, a), daemon=True)
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    elapsed = time.perf_counter() - t0
    return lats, elapsed

def scenario(tag, nclients, mode):
    admin_cmd("START 40 100 5 PerfItem")
    clients = [Client(f"{tag}_{i}") for i in range(nclients)]
    for c in clients:
        c.connect_and_join()

    if mode == "normal":
        lats, elapsed = run_parallel_bids(clients, [101 + i for i in range(nclients)])
    elif mode == "tie":
        lats, elapsed = run_parallel_bids(clients, [150 for _ in range(nclients)])
    else:
        lats = []
        t0 = time.perf_counter()
        for i, c in enumerate(clients):
            for cmd, toks in [
                ("BID abc", ["Invalid amount", "BID UPDATE|status=rejected"]),
                ("PING", ["Unknown command"]),
            ]:
                lat = c.send_and_wait_any(cmd, toks)
                if lat is not None:
                    lats.append(round(lat, 4))
            lat = c.bid_and_wait(120 + i)
            if lat is not None:
                lats.append(round(lat, 4))
        elapsed = time.perf_counter() - t0

    admin_cmd("STOP")
    for c in clients:
        c.close()

    avg = round(statistics.mean(lats), 4) if lats else 0.0
    tp = round(len(lats)/elapsed, 4) if elapsed > 0 else 0.0
    return {
        "latencies_ms": lats,
        "count": len(lats),
        "elapsed_s": round(elapsed, 6),
        "avg_ms": avg,
        "throughput_ops_per_s": tp,
    }

server = AuctionServer(host=HOST, port=PORT, admin_port=ADMIN_PORT, use_ssl=True)
threading.Thread(target=server.start, daemon=True).start()
time.sleep(1.0)

results = {
    "Baseline": scenario("baseline", 1, "normal"),
    "Moderate": scenario("moderate", 5, "normal"),
    "High": scenario("high", 10, "normal"),
    "Tie-heavy": scenario("tie", 5, "tie"),
    "Invalid-input stress": scenario("invalid", 5, "invalid"),
}

print("RAW_RESULTS_JSON_START")
print(json.dumps(results, indent=2))
print("RAW_RESULTS_JSON_END")
