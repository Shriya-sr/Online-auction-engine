

import socket
import threading
import time
import os

HOST = "127.0.0.1"
PORT = 5000
LOG_FILE = os.path.join(os.path.dirname(__file__), "simulated_clients_log.txt")

def log_event(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

def simulate_bidder(username, bid_sequence):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
        s.sendall(f"JOIN {username}\n".encode())
        log_event(f"{username} joined the auction.")
        print(f"[JOIN] {username}")
        time.sleep(1)
        for idx, bid in enumerate(bid_sequence):
            s.sendall(f"BID {bid}\n".encode())
            log_event(f"{username} placed bid {bid} (round={idx})")
            s.settimeout(0.5)
            try:
                resp = s.recv(1024).decode()
                if resp:
                    resp_lines = resp.strip().split('\n')
                    for line in resp_lines:
                        if line:
                            log_event(f"{username} received: {line}")
                            print(f"[{username}] {line}")
                            if "TIE DETECTED" in line:
                                print(f"\n{'*'*60}")
                                print(f"*** TIE DETECTED - ESCALATION STARTED ***")
                                print(f"*** {line} ***")
                                print(f"{'*'*60}\n")
                            if "ESCALATION RESOLVED" in line or "ESCALATION" in line:
                                print(f"\n{'#'*60}")
                                print(f"### {line}")
                                print(f"{'#'*60}\n")
                            if "AUCTION ENDED" in line:
                                print(f"\n{'█'*60}")
                                print(f"█ {username}: {line}")
                                print(f"{'█'*60}\n")
                                return
            except Exception:
                pass
            time.sleep(1)
        s.close()
        log_event(f"{username} left the auction.")
    except Exception as e:
        log_event(f"{username} error: {e}")

def main():
    print("\n" + "="*60)
    print("=== SIMULATED CLIENTS - AUCTION TESTING ===")
    print("="*60)
    print(f"Launching deterministic test scenarios")
    print("="*60 + "\n")
    threads = []
    # Scenario 1: Basic correctness
    threads.append(threading.Thread(target=simulate_bidder, args=("A", [100])))
    threads.append(threading.Thread(target=simulate_bidder, args=("B", [90, 150])))
    # Scenario 2: Tie case
    threads.append(threading.Thread(target=simulate_bidder, args=("C", [200])))
    threads.append(threading.Thread(target=simulate_bidder, args=("D", [200])))
    # Scenario 3: Late bid rejection
    threads.append(threading.Thread(target=simulate_bidder, args=("E", [250])))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("\n=== ALL CLIENTS FINISHED ===\n")
if __name__ == "__main__":
    # Clear log file
    with open(LOG_FILE, "w") as f:
        f.write("")
    main()
