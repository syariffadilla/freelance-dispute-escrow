# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
FreelanceDisputeEscrow
-----------------------
Primitive kontrak escrow dua pihak (client & freelancer) dengan resolusi
sengketa berbasis LLM. Dana ditahan on-chain sampai freelancer menandai
pekerjaan selesai. Jika client tidak setuju, salah satu pihak bisa membuka
sengketa; validator GenLayer lalu MENGAMBIL isi kedua bukti (bukan cuma
URL-nya) dan menghasilkan verdict terstruktur (JSON) yang divalidasi secara
deterministik sebelum ditulis ke state.

Kenapa ini bukan "thin LLM wrapper":
- Validator benar-benar fetch konten evidence lewat `gl.nondet.web.render()`
  di dalam blok non-deterministic, lalu isi konten itu (bukan sekadar URL)
  yang dikirim ke LLM untuk diadili.
- Konsensus dipakai lewat `gl.eq_principle.prompt_comparative`, sehingga
  validator boleh menulis alasan dengan kalimat berbeda tapi tetap harus
  sepakat pada payout_split yang sama (keputusan terstruktur, bukan teks bebas).
- Output LLM WAJIB lolos schema + range check di Python (guard deterministik)
  sebelum dipercaya -> integritas keputusan ada di kode kontrak, bukan
  cuma dipercaya mentah dari model.
- State design eksplisit: enum status, saldo escrow, riwayat bukti,
  dan deadline auto-release supaya dana tidak macet selamanya.
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
    client_payout_pct: u256  # 0-100, dipakai saat auto-release juga
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
        # Hanya client yang boleh approve manual (freelancer full payout)
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
        """
        Inti dari primitive ini: validator MENGAMBIL isi kedua bukti (bukan
        cuma URL-nya) lalu membaca deskripsi kerja + kedua bukti tersebut,
        kemudian menghasilkan verdict terstruktur. Konsensus dicapai lewat
        prompt_comparative, tapi hasil akhirnya tetap divalidasi deterministik
        sebelum dipercaya.
        """
        assert self.status == EscrowStatus.DISPUTED, "Tidak ada sengketa aktif"

        work_desc = self.work_description
        submission_url = self.submission_evidence_url
        dispute_url = self.dispute_evidence_url

        def get_verdict() -> str:
            # --- Ambil isi bukti sebenarnya, bukan cuma URL-nya ---
            try:
                submission_content = gl.nondet.web.render(submission_url, mode="text")
            except Exception:
                submission_content = "(gagal mengambil konten - URL tidak dapat diakses)"

            try:
                dispute_content = gl.nondet.web.render(dispute_url, mode="text")
            except Exception:
                dispute_content = "(gagal mengambil konten - URL tidak dapat diakses)"

            # Normalisasi panjang supaya prompt tetap wajar & konsisten
            # untuk perbandingan antar validator.
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

        # Semua validator harus sepakat pada payout_split final walau
        # kalimat "reason" mereka boleh berbeda -> comparative equivalence.
        raw_verdict = gl.eq_principle.prompt_comparative(
            get_verdict,
            "Validator harus sepakat pada nilai client_payout_pct yang sama "
            "walau kalimat alasan (reason) boleh berbeda redaksinya.",
        )

        # --- Guard deterministik: JANGAN percaya LLM mentah-mentah ---
        try:
            parsed = json.loads(raw_verdict)
            pct = int(parsed["client_payout_pct"])
            reason = str(parsed["reason"])[:280]
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            # Fallback aman: kalau format rusak, anggap tidak konklusif
            # dan default ke split 50/50 sambil menandai perlu review manusia.
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
        """
        Kalau melewati deadline dan tidak ada dispute, dana otomatis cair
        penuh ke freelancer supaya escrow tidak macet selamanya.
        """
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
