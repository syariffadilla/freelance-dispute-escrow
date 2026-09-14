# FreelanceDisputeEscrow

A GenLayer Intelligent Contract primitive: a two-party escrow (client & freelancer) with LLM-based dispute resolution.

## Why this is a primitive, not a one-off demo

- **Explicit state design**: a status enum (`FUNDED` → `SUBMITTED` → `DISPUTED`/`RELEASED` → `RESOLVED`), escrow balance, evidence URLs, and a deadline.
- **Real consensus logic**: `resolve_dispute()` uses `gl.eq_principle.prompt_comparative` — validators may phrase their reasoning (`reason`) differently, but must still agree on the same structured decision (`client_payout_pct`).
- **Deterministic guard**: the LLM output is validated against a JSON schema and a range check in Python before it's written to state, so decision integrity lives in the contract logic — not blind trust in the model's raw output.
- **Reusable**: this pattern can be used by any freelance platform that needs two-party escrow with dispute resolution, not a single-use use case.

## Deployment

Deployed on GenLayer Studio (StudioNet):

- Contract address: `0xe2eD731A52bE0c5488F40ffdaDB00e2aCb20FEcA`
- Runner: `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (pinned, required for Full Consensus mode)

## End-to-end flow tested

1. **Deploy** — constructor takes `client`, `freelancer`, `amount`, `work_description`, `deadline_ts`. ✅ FINALIZED
2. **submit_work(evidence_url)** — freelancer submits proof of work. ✅ FINALIZED, approved by 4+ validators running different LLM providers (GPT-5.4, Minimax, Gemini-3-flash, GLM).
3. **open_dispute(dispute_evidence_url)** — client opens a dispute with evidence of their objection. ✅ FINALIZED
4. **resolve_dispute()** — validators read both pieces of evidence and reach consensus via `prompt_comparative`. ✅ FINALIZED, output:
   ```json
   {"client_payout_pct": 30, "reason": "Freelancer telah menyelesaikan landing page ..."}
   ```
   The process went through 2 leader rotations before being ACCEPTED — demonstrating GenLayer's Optimistic Democracy mechanism working as designed.
5. **get_state()** — view method to read status, balance, and the final verdict.

## Files

- `freelance_dispute_escrow.py` — full contract source.

## Notes

Because the `client_payout_pct` decision is inherently subjective, validators can occasionally fail to reach consensus (`UNDETERMINED`) if the underlying LLMs disagree sharply. GenLayer's protocol provides an **Appeal** mechanism for this case. A natural next iteration would constrain the output to a small set of discrete tiers (e.g. 0/25/50/75/100) to reduce the chance of this divergence.
