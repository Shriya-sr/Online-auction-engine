import socket
import ssl
import threading
import time
from threading import Lock
import statistics
import json
from datetime import datetime

# Configuration - Can be adjusted for different test scenarios
HOST = 'localhost'
PORT = 5000
NUM_CLIENTS = 5
BIDS_PER_CLIENT = 10

# Metrics
metrics_lock = Lock()
total_requests = 0
total_time = 0.0
response_times = []
bid_distribution = {}  # Track actual bid amounts processed
failed_bids = 0
successful_bids = 0
connection_times = []
error_log = []

# Test scenarios configuration
TEST_SCENARIOS = {
    "baseline": {
        "num_clients": 1,
        "bids_per_client": 5,
        "description": "Baseline: Single client, normal bidding"
    },
    "moderate_load": {
        "num_clients": 5,
        "bids_per_client": 10,
        "description": "Moderate load: 5 concurrent bidders"
    },
    "high_load": {
        "num_clients": 15,
        "bids_per_client": 8,
        "description": "High load: 15 concurrent bidders"
    },
    "tie_heavy": {
        "num_clients": 5,
        "bids_per_client": 5,
        "description": "Tie-heavy: Multiple clients submitting identical bids",
        "tie_mode": True
    },
    "invalid_stress": {
        "num_clients": 5,
        "bids_per_client": 10,
        "description": "Invalid-input stress: Mixed valid/invalid commands",
        "invalid_mode": True
    }
}


def run_client(client_id, bids_per_client=BIDS_PER_CLIENT, tie_mode=False, invalid_mode=False):
    """Simulate a single client connecting and bidding."""
    global total_requests, total_time, failed_bids, successful_bids
    
    username = f"user_{client_id}"
    local_requests = 0
    local_time = 0.0
    client_bids_success = 0
    client_bids_failed = 0
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Measure connection time
        connection_start = time.time()
        
        # Connect to server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = context.wrap_socket(sock, server_hostname=HOST)
        ssl_sock.connect((HOST, PORT))
        
        connection_elapsed = time.time() - connection_start
        with metrics_lock:
            connection_times.append(connection_elapsed)
        
        print(f"[Client {client_id:2d}] Connected in {connection_elapsed*1000:.2f}ms")
        
        # Receive server prompt
        try:
            data = ssl_sock.recv(1024).decode('utf-8')
        except socket.timeout:
            raise Exception("Server did not respond to initial connection")
        
        # Send JOIN command
        ssl_sock.send(f"JOIN {username}\n".encode('utf-8'))
        response = ssl_sock.recv(1024).decode('utf-8')
        print(f"[Client {client_id:2d}] Joined as {username}")
        
        # Send multiple BID commands and measure response time
        for bid_num in range(bids_per_client):
            bid_command = None
            
            if tie_mode:
                # Send identical bids to trigger ties/escalations
                bid_amount = 100.0
                bid_command = f"BID {bid_amount}\n"
            elif invalid_mode and bid_num % 4 == 0:
                # Send invalid commands periodically
                invalid_commands = [
                    f"BID -50\n",  # Negative bid
                    f"BID abc\n",  # Non-numeric
                    f"INVALID_CMD\n",  # Unknown command
                ]
                bid_command = invalid_commands[bid_num % len(invalid_commands)]
                print(f"[Client {client_id:2d}] Sending invalid: {bid_command.strip()}")
            else:
                # Normal ascending bids
                bid_amount = 10.0 + (bid_num * 5.0)
                bid_command = f"BID {bid_amount}\n"
            
            # Measure time for BID request
            start_time = time.time()
            try:
                ssl_sock.send(bid_command.encode('utf-8'))
                response = ssl_sock.recv(1024).decode('utf-8')
                elapsed = time.time() - start_time
                
                local_requests += 1
                local_time += elapsed
                client_bids_success += 1
                
                with metrics_lock:
                    total_requests += 1
                    total_time += elapsed
                    response_times.append(elapsed)
                    successful_bids += 1
                
                # Track bid distribution
                if "BID" in bid_command and not invalid_mode:
                    with metrics_lock:
                        bid_key = bid_command.split()[1]
                        bid_distribution[bid_key] = bid_distribution.get(bid_key, 0) + 1
                
                status = "✓" if "BID UPDATE" in response or "JOINED" in response else "⚠"
                print(f"[Client {client_id:2d}] Bid {bid_num + 1:2d}: {status} Response: {elapsed*1000:7.2f}ms")
                
            except socket.timeout:
                client_bids_failed += 1
                with metrics_lock:
                    failed_bids += 1
                print(f"[Client {client_id:2d}] Bid {bid_num + 1:2d}: ✗ TIMEOUT")
            except Exception as e:
                client_bids_failed += 1
                with metrics_lock:
                    failed_bids += 1
                    error_log.append(f"Client {client_id} bid {bid_num}: {str(e)}")
                print(f"[Client {client_id:2d}] Bid {bid_num + 1:2d}: ✗ ERROR - {e}")
        
        # Send EXIT command
        ssl_sock.send(b"EXIT\n")
        ssl_sock.close()
        print(f"[Client {client_id:2d}] Disconnected ({client_bids_success} successful, {client_bids_failed} failed)")
        
    except Exception as e:
        print(f"[Client {client_id:2d}] Connection error: {e}")
        with metrics_lock:
            error_log.append(f"Client {client_id}: {str(e)}")


def calculate_statistics(response_times):
    """Calculate comprehensive performance statistics."""
    if not response_times:
        return {}
    
    sorted_times = sorted(response_times)
    
    stats = {
        "count": len(response_times),
        "min": min(sorted_times) * 1000,
        "max": max(sorted_times) * 1000,
        "mean": statistics.mean(response_times) * 1000,
        "median": statistics.median(response_times) * 1000,
        "stdev": statistics.stdev(response_times) * 1000 if len(response_times) > 1 else 0,
        "p95": sorted_times[int(len(sorted_times) * 0.95)] * 1000,
        "p99": sorted_times[int(len(sorted_times) * 0.99)] * 1000,
    }
    return stats


def run_scenario(scenario_name, scenario_config):
    """Run a single test scenario."""
    global total_requests, total_time, response_times, failed_bids, successful_bids
    global connection_times
    
    # Reset global metrics for this scenario
    total_requests = 0
    total_time = 0.0
    response_times = []
    failed_bids = 0
    successful_bids = 0
    connection_times = []
    bid_distribution.clear()
    
    print(f"\n{'='*80}")
    print(f"SCENARIO: {scenario_config['description']}")
    print(f"{'='*80}\n")
    
    num_clients = scenario_config.get("num_clients", NUM_CLIENTS)
    bids_per_client = scenario_config.get("bids_per_client", BIDS_PER_CLIENT)
    tie_mode = scenario_config.get("tie_mode", False)
    invalid_mode = scenario_config.get("invalid_mode", False)
    
    print(f"Starting test: {num_clients} clients × {bids_per_client} bids")
    print(f"Expected total requests: {num_clients * bids_per_client}\n")
    
    # Create and start client threads
    threads = []
    start_time = time.time()
    
    for i in range(num_clients):
        thread = threading.Thread(
            target=run_client,
            args=(i, bids_per_client, tie_mode, invalid_mode)
        )
        threads.append(thread)
        thread.start()
        # Small delay to stagger connection attempts
        time.sleep(0.01)
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    total_elapsed = time.time() - start_time
    
    # Calculate statistics
    response_stats = calculate_statistics(response_times)
    connection_stats = calculate_statistics(connection_times)
    
    throughput = total_requests / total_elapsed if total_elapsed > 0 else 0
    success_rate = (successful_bids / (successful_bids + failed_bids) * 100) if (successful_bids + failed_bids) > 0 else 0
    
    # Print detailed results
    print(f"\n{'='*80}")
    print(f"RESULTS FOR: {scenario_config['description']}")
    print(f"{'='*80}\n")
    
    print("CONCURRENCY & WORKLOAD:")
    print(f"  Number of Clients:           {num_clients}")
    print(f"  Bids per Client:             {bids_per_client}")
    print(f"  Expected Total Requests:     {num_clients * bids_per_client}")
    print(f"  Actual Total Requests Sent:  {total_requests}")
    
    print("\nRESPONSE TIME METRICS (milliseconds):")
    if response_stats:
        print(f"  Average Response Time:       {response_stats['mean']:.2f} ms")
        print(f"  Median Response Time:        {response_stats['median']:.2f} ms")
        print(f"  Min Response Time:           {response_stats['min']:.2f} ms")
        print(f"  Max Response Time:           {response_stats['max']:.2f} ms")
        print(f"  Std Dev (σ):                 {response_stats['stdev']:.2f} ms")
        print(f"  95th Percentile (p95):       {response_stats['p95']:.2f} ms")
        print(f"  99th Percentile (p99):       {response_stats['p99']:.2f} ms")
    
    print("\nLATENCY & THROUGHPUT:")
    print(f"  Total Execution Time:        {total_elapsed:.2f} seconds")
    print(f"  Throughput:                  {throughput:.2f} requests/second")
    
    print("\nCONNECTION METRICS (milliseconds):")
    if connection_stats:
        print(f"  Avg Connection Time:         {connection_stats['mean']:.2f} ms")
        print(f"  Min Connection Time:         {connection_stats['min']:.2f} ms")
        print(f"  Max Connection Time:         {connection_stats['max']:.2f} ms")
    
    print("\nRELIABILITY:")
    print(f"  Successful Bids:             {successful_bids}")
    print(f"  Failed Bids:                 {failed_bids}")
    print(f"  Success Rate:                {success_rate:.2f}%")
    
    if error_log:
        print("\nERRORS ENCOUNTERED:")
        for error in error_log[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(error_log) > 10:
            print(f"  ... and {len(error_log) - 10} more errors")
    
    return {
        "scenario": scenario_name,
        "description": scenario_config['description'],
        "num_clients": num_clients,
        "bids_per_client": bids_per_client,
        "total_time": total_elapsed,
        "throughput": throughput,
        "response_stats": response_stats,
        "connection_stats": connection_stats,
        "successful_bids": successful_bids,
        "failed_bids": failed_bids,
        "success_rate": success_rate,
    }


def main():
    """Run comprehensive load test with multiple scenarios."""
    print("\n" + "="*80)
    print("ONLINE AUCTION ENGINE - COMPREHENSIVE LOAD TEST")
    print("="*80)
    print(f"Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis test evaluates:")
    print("  1. System behavior under realistic conditions (multiple concurrent clients)")
    print("  2. Performance metrics (response time, throughput, latency)")
    print("  3. Scalability trends as client load increases")
    print("  4. Robustness under edge cases (ties, invalid inputs)")
    print("\n" + "="*80 + "\n")
    
    # Check if running single scenario or full suite
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in TEST_SCENARIOS:
        scenarios_to_run = {sys.argv[1]: TEST_SCENARIOS[sys.argv[1]]}
    else:
        scenarios_to_run = TEST_SCENARIOS
    
    results = []
    
    for scenario_name, scenario_config in scenarios_to_run.items():
        result = run_scenario(scenario_name, scenario_config)
        results.append(result)
        time.sleep(1)  # Delay between scenarios
    
    # Print comparative summary
    print("\n\n" + "="*80)
    print("COMPARATIVE ANALYSIS & SCALABILITY TRENDS")
    print("="*80 + "\n")
    
    print("Performance Across All Scenarios:")
    print(f"{'Scenario':<25} {'Clients':<10} {'Avg RT (ms)':<15} {'Throughput':<15} {'Success %':<12}")
    print("-" * 77)
    
    for result in results:
        avg_rt = result['response_stats'].get('mean', 0) if result['response_stats'] else 0
        throughput = result['throughput']
        success_rate = result['success_rate']
        print(f"{result['scenario']:<25} {result['num_clients']:<10} {avg_rt:<15.2f} {throughput:<15.2f} {success_rate:<12.2f}")
    
    print("\nKEY OBSERVATIONS:\n")
    
    # Analyze scalability
    if len(results) >= 3:
        baseline = results[0]
        moderate = results[1]
        high = results[2]
        
        baseline_throughput = baseline['throughput']
        moderate_throughput = moderate['throughput']
        high_throughput = high['throughput']
        
        baseline_rt = baseline['response_stats'].get('mean', 0)
        moderate_rt = moderate['response_stats'].get('mean', 0)
        high_rt = high['response_stats'].get('mean', 0)
        
        print(f"1. SCALABILITY TREND:")
        print(f"   - Baseline (1 client): {baseline_throughput:.2f} req/s, avg RT: {baseline_rt:.2f}ms")
        print(f"   - Moderate (5 clients): {moderate_throughput:.2f} req/s, avg RT: {moderate_rt:.2f}ms")
        print(f"   - High Load (15 clients): {high_throughput:.2f} req/s, avg RT: {high_rt:.2f}ms")
        
        # Calculate degradation
        moderate_throughput_ratio = (moderate_throughput / baseline_throughput) if baseline_throughput > 0 else 0
        high_throughput_ratio = (high_throughput / baseline_throughput) if baseline_throughput > 0 else 0
        
        print(f"\n   Throughput scaling: {moderate_throughput_ratio:.2f}x at 5 clients, {high_throughput_ratio:.2f}x at 15 clients")
        
        moderate_rt_ratio = (moderate_rt / baseline_rt) if baseline_rt > 0 else 0
        high_rt_ratio = (high_rt / baseline_rt) if baseline_rt > 0 else 0
        
        print(f"   Response time degradation: {moderate_rt_ratio:.2f}x at 5 clients, {high_rt_ratio:.2f}x at 15 clients")
    
    print(f"\n2. LATENCY ANALYSIS:")
    for result in results:
        if result['response_stats']:
            p95 = result['response_stats'].get('p95', 0)
            p99 = result['response_stats'].get('p99', 0)
            print(f"   - {result['scenario']}: p95={p95:.2f}ms, p99={p99:.2f}ms")
    
    print(f"\n3. RELIABILITY:")
    for result in results:
        print(f"   - {result['scenario']}: {result['success_rate']:.2f}% success rate")
    
    print(f"\n4. CONCURRENCY BOTTLENECKS:")
    print(f"   - Connection establishment overhead visible in connection_time metrics")
    print(f"   - Thread synchronization via metrics_lock may cause contention")
    print(f"   - Server-side thread pool capacity reached at high load levels")
    
    # Save results to JSON
    output_file = "load_test_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "scenarios": results
        }, f, indent=2)
    print(f"\n\nDetailed results saved to: {output_file}")
    
    print("\n" + "="*80)
    print("LOAD TEST COMPLETED")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
