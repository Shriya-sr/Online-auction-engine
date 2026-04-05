# Test Plan and Edge Cases

This file supports rubric component: Optimization and Fixes.

## Functional Tests
1. Admin `START` begins auction and bidders receive active state.
2. Valid bid above current highest is accepted and broadcast.
3. Bid below base price (when no prior highest) is rejected.
4. Lower bid than current highest is rejected.
5. `GET` returns current state.
6. `REPUTATION` returns active-user ranking when available.
7. `STOP` ends auction and announces winner/unsold.

## Concurrency Tests
1. Two or more bidders submit bids near-simultaneously.
2. Verify no race conditions in highest bid updates.
3. Verify disconnected clients are removed from active lists.

## Tie and Escalation Tests
1. Two bidders place identical highest bids.
2. Verify escalation round starts.
3. Submit blind escalation bids.
4. Verify escalation resolves with highest blind bid.
5. If blind tie remains, verify reputation then FCFS resolution.

## Security Tests (TLS)
1. Normal TLS connection from bidder/admin clients.
2. Connection attempt with invalid trust/certificate.
3. Verify server logs TLS handshake failures without crashing.

## Fault and Validation Tests
1. Invalid commands.
2. Non-numeric bid amounts.
3. Empty username on join.
4. Abrupt client process termination during active auction.

## Persistence Tests
1. Start auction and place bids.
2. Stop and restart server.
3. Verify `auction_state.json` restores expected fields.

## Evidence to Attach in GitHub
- Screenshots/log snippets for each test category.
- Notes on bugs found and fixes applied.
- Before/after behavior for critical fixes.
