# Live test report

Network: GenLayer Studio (studionet). Run date: 7 October 2026. Followed `docs/LIVE_CAMPAIGN.md` with five wallets.

Offline results (this repository): 171 tests passing, 61 of 61 mutants killed, Studio lint clean on all contracts and the short-window build.

## Deployed contracts

| Contract | Address |
|---|---|
| AgentRegistry | `0x72E1e42ccD9136619B4387C5685eA73da0a4D072` |
| ReputationLedger | `0xE7612D58a0B4954BC69a4434eB68304617406315` |
| JobMarket (short-window build) | `0x5510acf80558a8b32FCFE23e75E9bd191300fF54` |
| AgentTrust (unchanged, existing deployment) | `0x9d04ea1E3C0BBA11c85e7325C87D2E009AcF3ccc` |

Explorer: https://explorer-studio.genlayer.com

## Setup results

- All three contracts deployed, wired once, and the wiring locks were confirmed (a second wiring attempt is rejected as already wired).
- Three agents registered. The profile pages were published on GitHub and `verify_claims` returned CLAIMS_SUPPORTED for Alpha Agent (AG-2) and Beta Agent (AG-3).
- Negative test: AG-1 was registered by the client wallet, whose address is not on the profile page it points to. `verify_claims` returned CLAIMS_UNSUPPORTED with detail ADDRESS_NOT_FOUND, so proof-of-control works.

## Job lifecycle (JB-1, agreement AT-6)

| Step | Result | Transaction | Notes |
|---|---|---|---|
| post_job | Returned JB-1 | [0x17afd81f...a69a4d](https://explorer-studio.genlayer.com/tx/0x17afd81f8c91eaf21f220a077830e25f1bb2ff2f187734616f4c77f95ba69a4d) | Client Wallet 1 |
| submit_bid (Alpha Agent) | Returned BD-1 | [0x6392f807...0e4759](https://explorer-studio.genlayer.com/tx/0x6392f8075305e18d10307912475b582476ebf3c13557d7cddbcf945be20e4759) | Registered, claims supported |
| submit_bid (Beta Agent) | Returned BD-2 | [0xc4426b14...92d212](https://explorer-studio.genlayer.com/tx/0xc4426b14f7cb8c65b28bba3a5f1ba918fb4fff7e9a01f1464328cf666692d212) |  |
| assess_bid BD-1 | STRONG_FIT with exact quotes from pitch and spec | [0x8d70cf12...21c1b0](https://explorer-studio.genlayer.com/tx/0x8d70cf12a8164fddc7cc847b5f316ac7b25446be6f12cdb69b0d6d19ff21c1b0) | prompt_comparative consensus worked live |
| assess_bid BD-2 | POOR_FIT, empty quotes | [0x383e64e9...3dd485](https://explorer-studio.genlayer.com/tx/0x383e64e905e24e6d8d5bbed68917d2e1c5dfb795d58d0448dae4db32113dd485) | Generic pitch correctly rejected |
| select_bid BD-2 (negative test) | Rejected: only bids assessed as STRONG_FIT or PARTIAL_FIT can be selected | [0xd05db357...05ba96](https://explorer-studio.genlayer.com/tx/0xd05db3577f927a649367ce6f26d684c215a3dd2c756e36bd181234ae6a05ba96) | Expected failure |
| note_selection (market to registry emit) | RECORDED | [0xa2c321a3...77e552](https://explorer-studio.genlayer.com/tx/0xa2c321a36b979b58a854c5c260de512dbdd29e222ae7e263ba0397a58677e552) | Cross-contract emit on accepted worked live |
| AgentTrust create_agreement | Returned AT-6 | [0x73358a18...88d04a](https://explorer-studio.genlayer.com/tx/0x73358a18a63488533e23d835b83dc90500aa35e4eb590ae52856f8663388d04a) | Title carries [JB-1] |
| AgentTrust accept | Accepted | [0x3ce4cb52...98d78f](https://explorer-studio.genlayer.com/tx/0x3ce4cb5287ed60e4a641688320780a29ca1b16ce7c8713d26be792ee2598d78f) | Worker Wallet 2 |
| AgentTrust start_work | IN_PROGRESS | [0xfd1fd90e...463b97](https://explorer-studio.genlayer.com/tx/0xfd1fd90e4ecff465eb81e6d9b5e0347794192fc2f144b9caeba3ebb72b463b97) |  |
| AgentTrust submit_deliverable | Delivered | [0x344880b5...a943cc](https://explorer-studio.genlayer.com/tx/0x344880b5f45e5fbf501356ecbdc0531b8530a34c85dcf12893b511a85da943cc) | github_file evidence at a fixed commit |
| AgentTrust freeze_evidence | Evidence frozen | [0x70cd5dd2...748568](https://explorer-studio.genlayer.com/tx/0x70cd5dd2b1615a0320272caff027f72a7ce4a3bf38730abe6ab5f638d7748568) |  |
| AgentTrust verify_requirement REQ-001 | PASS with an exact quote of record_outcome | [0x90f021d8...620de5](https://explorer-studio.genlayer.com/tx/0x90f021d896d9de5483119ba6e6c5421d5ba3c2b1634126fb6f04b8faa3620de5) |  |
| AgentTrust aggregate | PASS | [0xacbc30ee...e82c6d](https://explorer-studio.genlayer.com/tx/0xacbc30eee82f725e2f928278c1d2905026406dd2aab433081a29ac1ea4e82c6d) |  |
| sync_agreement (before settlement) | LINKED | [0x6f64c086...25bd5e](https://explorer-studio.genlayer.com/tx/0x6f64c086d5043f4cd8504c81768ca2bcc8a7f2c877ac6a3fba1f2d946425bd5e) | Not final yet, as expected |
| AgentTrust settle | SETTLED | [0x2b1360b3...5c9cea](https://explorer-studio.genlayer.com/tx/0x2b1360b3d70d8b241057cd9a9fa0ee3157f496a4e0549341d89b9ec9ce5c9cea) | After the challenge window |
| sync_agreement (after settlement) | CLOSED | [0x60687a7b...3703cc](https://explorer-studio.genlayer.com/tx/0x60687a7bd2818f142f94142c3c90c35a4b31cb7abd5938ff4ff92efbef3703cc) |  |
| record_outcome AT-6 | COMPLETED | [0x859d028d...1b49e8](https://explorer-studio.genlayer.com/tx/0x859d028d8ee675e1c4fd5f79e7e127997d45c9ad64cb70f82dc62b2d7d1b49e8) |  |
| record_outcome AT-6 again (negative test) | Rejected: outcome already recorded for AT-6 | [0xab912e0f...ec5c2b](https://explorer-studio.genlayer.com/tx/0xab912e0faa49923bed8b0affa87f0b079711f8ad7b3d44009f1b821057ec5c2b) | Replay protection |

## Final reputation (get_profile for the worker wallet)

| Field | Value |
|---|---|
| completed | 1 |
| qualified_completed | 1 |
| market_completed | 1 |
| distinct_clients | 1 |
| total_earned | 4000000000000000000 (4 GEN) |
| pos_points | 4000 |
| score | 666 |
| tier | ESTABLISHED |
| success_bps | 10000 |

The score matches the offline campaign replay exactly (4000 * 1000 / (4000 + 2000) = 666).

## What this proves live

- `prompt_comparative` equivalence on the fit verdict reaches consensus across five validators.
- Cross-contract writes with `.emit(on="accepted")` work in both directions (JobMarket to AgentRegistry and JobMarket to ReputationLedger).
- Cross-contract reads of AgentTrust from the ledger and the market work.
- The full path from job to bid to award to escrow to verified delivery to settlement to reputation completes on chain without the marketplace ever holding funds.

## Failures

No unexpected live failures in this run. Two earlier mistakes were instruction errors, not contract bugs: arguments typed with quotes (fixed in the campaign instructions) and a profile registered with the wrong wallet (kept as the negative test above).
