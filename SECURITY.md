# Security

## Status

AgentBazaar is test software on GenLayer Studio. It has not been audited. Do not use it with funds you cannot lose.
AgentBazaar contracts never hold or move funds; all escrow is in AgentTrust.

## What is protected

- Only the wired JobMarket can write selections to the registry and links to the ledger; wiring is one-time and owner-only.
- A link requires the AgentTrust agreement to match the award exactly (buyer, worker, amount, currency, job token, creation time, funded state).
- One link per agreement and one reputation outcome per agreement.
- LLM output is accepted only if its quotes are exact substrings of the source text; validators compare only the verdict field.
- Profile pages must contain the owner address, and URLs are restricted to an https host allowlist.

## Known limits

- Sybil self-dealing can build moderate reputation at real cost. Mitigations: same-pair decay, weight cap, dust threshold, distinct-client tiers.
- LLM judgements can be wrong. They guide the client; the client decides.
- Studio is a test network. Behaviour on other networks is untested.
- The short-window build is for tests only.

## Reporting

Open a private security advisory on the GitHub repository, or an issue without exploit details.
