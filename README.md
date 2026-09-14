# FreelanceDisputeEscrow

A GenLayer Intelligent Contract primitive: two-party escrow (client & freelancer) with LLM-based dispute resolution.

## Why this is a primitive, not a one-off demo

- **Explicit state design**: status enum (`FUNDED` → `SUBMITTED` → `DISPUTED`/`RELEASED` → `RESOLVED`), escrow balance, evidence URLs, deadline.
- **Real consensus logic**: `resolve_dispute()` uses `gl.eq_principle.prompt_comparative` — validators can phrase their reasoning differently but must agree on the same `client_payout_pct`.
- **Validators judge actual evidence, not links**: before the verdict prompt runs, the contract fetches both evidence URLs with `gl.nondet.web.render(url, mode="text")` and hands the retrieved content to the LLM. Validators are reading and comparing the work itself, not guessing from a URL string.
- **Deterministic guard**: LLM output is validated against a JSON schema and range check in Python before it's written to state.
- **Reusable**: works for any two-party escrow flow that needs dispute resolution, not a single use case.

## Deployment

Deployed on GenLayer Studio (StudioNet):

- Contract address: `0x8f54c954c4B900e64Ed67CE56F657aEFfBfF3f00`
- Runner: `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (pinned, required for Full Consensus mode)

## End-to-end flow tested

1. **Deploy** — constructor takes `client`, `freelancer`, `amount`, `work_description`, `deadline_ts`. ✅ FINALIZED
2. **submit_work(evidence_url)** — freelancer submits proof of work. ✅ FINALIZED
3. **open_dispute(dispute_evidence_url)** — client opens a dispute with evidence of their objection. ✅ FINALIZED
4. **resolve_dispute()** — validators fetch both evidence URLs, read the actual content, and reach consensus via `prompt_comparative`. ✅ FINALIZED, output:

```json
{"client_payout_pct": 40, "reason": "Freelancer terbukti menyelesaikan landing page 5 section dan responsive, namun client menyatakan 2 dari 5 section belum sesuai brief/Figma. Karena mayoritas pekerjaan selesai tetapi ada ketidaksesuaian parsial, pembagian adil adalah client menerima 40% escrow."}
```

The verdict reasoning reflects specifics from the evidence content itself (section counts, Figma mismatch) — confirming validators are reasoning over the retrieved evidence, not the URL text.

5. **get_state()** — view method to read status, balance, and the final verdict.

## Files

- `freelance_dispute_escrow.py` — full contract source.

## Notes

Because `client_payout_pct` is inherently subjective, validators can occasionally fail to reach consensus (`UNDETERMINED`) if the underlying LLMs disagree sharply. GenLayer's protocol provides an **Appeal** mechanism for this case. A natural next iteration would constrain the output to a small set of discrete tiers (e.g. 0/25/50/75/100) to reduce the chance of this divergence.
