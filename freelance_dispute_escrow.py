# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
FreelanceDisputeEscrow

Two-party escrow (client & freelancer) with LLM-based dispute resolution.
Funds are held on-chain until the freelancer marks the work done. If the
client disagrees, either party can open a dispute; validators then fetch
both pieces of evidence, read them, and produce a structured verdict that
is validated deterministically before it's written to state.
"""

from genlayer import *
import json


class EscrowStatus:
    FUNDED = "FUNDED"
    SUBMITTED = "SUBMITTED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"
    RELEASED = "RELEASED"


class FreelanceDisputeEscrow(gl.Contract):
    client: str
    freelancer: str
    amount: u256
    status: str
    work_description: str
    submission_evidence_url: str
    dispute_evidence_url: str
    verdict_reason: str
    client_payout_pct: u256
    deadline_ts: u256

    def __init__(
        self,
        client: str,
        freelancer: str,
        amount: int,
        work_description: str,
        deadline_ts: int,
    ):
        self.client = client
        self.freelancer = freelancer
        self.amount = amount
        self.status = EscrowStatus.FUNDED
        self.work_description = work_description
        self.submission_evidence_url = ""
        self.dispute_evidence_url = ""
        self.verdict_reason = ""
        self.client_payout_pct = 0
        self.deadline_ts = deadline_ts

    @gl.public.write
    def submit_work(self, evidence_url: str) -> None:
        assert self.status == EscrowStatus.FUNDED, "Status invalid untuk submit"
        self.submission_evidence_url = evidence_url
        self.status = EscrowStatus.SUBMITTED

    @gl.public.write
    def approve_work(self) -> None:
        assert self.status == EscrowStatus.SUBMITTED, "Belum ada submission"
        self.client_payout_pct = 0
        self.status = EscrowStatus.RELEASED

    @gl.public.write
    def open_dispute(self, dispute_evidence_url: str) -> None:
        assert self.status == EscrowStatus.SUBMITTED, "Hanya bisa dispute setelah submission"
        self.dispute_evidence_url = dispute_evidence_url
        self.status = EscrowStatus.DISPUTED

    @gl.public.write
    def resolve_dispute(self) -> None:
        assert self.status == EscrowStatus.DISPUTED, "Tidak ada sengketa aktif"

        work_desc = self.work_description
        submission_url = self.submission_evidence_url
        dispute_url = self.dispute_evidence_url

        def get_verdict() -> str:
            try:
                submission_content = gl.nondet.web.render(submission_url, mode="text")
            except Exception:
                submission_content = "(gagal mengambil konten - URL tidak dapat diakses)"

            try:
                dispute_content = gl.nondet.web.render(dispute_url, mode="text")
            except Exception:
                dispute_content = "(gagal mengambil konten - URL tidak dapat diakses)"

            submission_content = submission_content[:3000]
            dispute_content = dispute_content[:3000]

            prompt = f"""
Kamu adalah juri netral untuk sengketa kerja freelance.

Deskripsi pekerjaan yang disepakati:
{work_desc}

Isi bukti pengerjaan dari freelancer (diambil dari {submission_url}):
{submission_content}

Isi alasan keberatan dari client (diambil dari {dispute_url}):
{dispute_content}

Berdasarkan isi bukti di atas (bukan URL-nya), putuskan pembagian dana
escrow yang adil.

Balas HANYA dengan JSON valid, tanpa teks lain, dengan bentuk persis:
{{"client_payout_pct": <integer 0-100>, "reason": "<ringkasan singkat alasan>"}}
"""
            result = gl.nondet.exec_prompt(prompt)
            return result.strip()

        raw_verdict = gl.eq_principle.prompt_comparative(
            get_verdict,
            "Validator harus sepakat pada nilai client_payout_pct yang sama "
            "walau kalimat alasan (reason) boleh berbeda redaksinya.",
        )

        try:
            parsed = json.loads(raw_verdict)
            pct = int(parsed["client_payout_pct"])
            reason = str(parsed["reason"])[:280]
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pct = 50
            reason = "Verdict tidak valid/format rusak - default 50/50, perlu review manual."

        if pct < 0:
            pct = 0
        if pct > 100:
            pct = 100

        self.client_payout_pct = u256(pct)
        self.verdict_reason = reason
        self.status = EscrowStatus.RESOLVED

    @gl.public.write
    def auto_release_after_deadline(self, current_ts: int) -> None:
        assert self.status == EscrowStatus.SUBMITTED, "Hanya berlaku saat menunggu approval"
        assert current_ts >= self.deadline_ts, "Belum melewati deadline"
        self.client_payout_pct = 0
        self.status = EscrowStatus.RELEASED

    @gl.public.view
    def get_state(self) -> str:
        return json.dumps({
            "status": self.status,
            "amount": int(self.amount),
            "client_payout_pct": int(self.client_payout_pct),
            "verdict_reason": self.verdict_reason,
        })
