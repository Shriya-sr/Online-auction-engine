# Performance Evaluation

This document is intended for rubric component: Performance Evaluation (response time, throughput, latency, scalability).

## Test Environment
- OS: Windows
- Python version: 3.13
- Machine specs (CPU/RAM): Local developer machine (single-host test run)
- Network setup (localhost/LAN): localhost (single machine)

## Workload Scenarios
1. Baseline: 1 bidder, normal bidding.
2. Moderate load: 5 concurrent bidders.
3. High load: 10+ concurrent bidders.
4. Tie-heavy: equal bids to trigger escalation repeatedly.
5. Invalid-input stress: mixed valid/invalid bid commands.

## Metrics
- Response time (ms): client command to server acknowledgment.
- Throughput (ops/sec): accepted bids per second.
- Latency under contention (ms): when many clients bid simultaneously.
- Scalability trend: how performance changes with more bidders.

## Measurement Procedure
1. Start server.
2. Start admin portal and run `START`.
3. Launch N bidder clients.
4. Record timestamps for each bid request and corresponding `BID UPDATE` response.
5. Repeat each scenario 3 times.
6. Compute mean and standard deviation.

## Results Table Template
| Scenario | Clients | Avg Response Time (ms) | Throughput (bids/s) | Notes |
|---|---:|---:|---:|---|
| Baseline | 1 | 6.25 | 91.91 | Stable under single client load |
| Moderate | 5 | 15.74 | 206.23 | Latency rises under concurrent bidders |
| High | 10 | 36.19 | 187.06 | Contention and broadcast overhead are more visible |
| Tie-heavy | 5 | 6.45 | 511.72 | Fast reject/quick-path responses during escalation |
| Invalid-input stress | 5 | 2.38 | 412.77 | Invalid commands rejected quickly; valid bids still processed |

## Observations
- Response time increases from baseline to moderate and rises further at high load, consistent with shared-state contention and broadcast fan-out.
- Throughput improves from baseline to moderate, then decreases at high load due to synchronization and message fan-out overhead.
- Tie-heavy workload shows lower latency and higher throughput in this run because several requests are processed through fast escalation-reject paths.
- Invalid-input stress remains stable; invalid requests are rejected quickly and valid bids continue to be processed.
- Primary bottlenecks observed: broadcast overhead, lock contention around shared state updates, and GUI client processing under bursty updates.

## Optimization/Fixes Applied
- Locking and thread-safe send paths.
- Anti-sniping and escalation logic stabilization.
- TLS handshake error handling at accept points.
- Input validation for command parsing.

## Conclusion
The system meets mini-project performance expectations for secure multi-client auction behavior on localhost and remains stable under normal, concurrent, tie-heavy, and invalid-input workloads. Performance degrades predictably with contention, but no failure mode was observed in these scenarios. Further improvements can be achieved by optimizing broadcast paths, reducing lock scope where safe, and using lightweight load clients for higher-scale benchmarking.

Note: The above values are from the single localhost run captured in the latest `RAW_RESULTS_JSON` output. For final report rigor, repeat each scenario three times and report mean and standard deviation.
