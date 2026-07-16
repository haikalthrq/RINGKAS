# RINGKAS_AGENTS.md

Status: Agent Execution Rules  
Project: RINGKAS — Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
Default agent setup: **1 Supervisor Agent + 1 Subagent Executor**  
Expandable setup: Supervisor may split work into multiple subagents when needed.

---

## 1. Purpose

Dokumen ini mengatur cara AI agents bekerja dalam proyek RINGKAS.

Tujuan utama:

1. Membatasi scope kerja agent agar tidak keluar dari Project Brief, PRD, SRD, Technical Spec, dan Tasks.
2. Menjaga implementasi tetap konsisten dengan arsitektur final.
3. Mencegah agent menambah fitur out-of-scope.
4. Menjaga traceability antara task, file yang diubah, acceptance criteria, dan laporan kerja.
5. Membuat workflow aman untuk default **1 supervisor + 1 subagent**, tetapi tetap fleksibel jika subagent ditambah.

---

## 2. Source of Truth Hierarchy

Agents wajib mengikuti dokumen berikut dalam urutan prioritas:

1. `RINGKAS_PROJECT_BRIEF.md`
2. `RINGKAS_PRD.md`
3. `RINGKAS_SRD.md`
4. `RINGKAS_TECHNICAL_SPEC.md`
5. `RINGKAS_TASKS.md`
6. `RINGKAS_AGENTS.md`

Jika terjadi konflik:

- Technical implementation detail mengikuti `RINGKAS_TECHNICAL_SPEC.md`.
- Product behavior mengikuti `RINGKAS_PRD.md`.
- System requirement mengikuti `RINGKAS_SRD.md`.
- Task execution mengikuti `RINGKAS_TASKS.md`.
- Scope besar mengikuti `RINGKAS_PROJECT_BRIEF.md`.
- Agent workflow mengikuti dokumen ini.

Jika agent menemukan konflik antar dokumen, agent **tidak boleh langsung mengambil keputusan besar**. Agent harus melaporkan konflik ke Supervisor Agent.

---

## 3. Default Agent Setup

Default setup proyek:

```text
1 Supervisor Agent
1 Subagent Executor
```

### 3.1 Supervisor Agent

Supervisor Agent bertugas:

1. Membaca semua dokumen proyek.
2. Memilih task dari `RINGKAS_TASKS.md`.
3. Menentukan scope kerja subagent.
4. Memberikan instruksi spesifik berbasis Task ID.
5. Mereview hasil subagent.
6. Memastikan perubahan tidak melanggar Technical Spec.
7. Memastikan acceptance criteria terpenuhi.
8. Menolak perubahan yang out-of-scope.
9. Menjaga task dikerjakan dalam urutan dependency yang benar.
10. Memutuskan kapan perlu menambah subagent tambahan.

Supervisor Agent sebaiknya memakai model paling kuat yang tersedia.

Rekomendasi model:

- GPT-5.5 Thinking atau model supervisor kuat.
- Reasoning mode medium/high untuk planning, decomposition, dan review.

---

### 3.2 Subagent Executor

Subagent Executor bertugas:

1. Mengerjakan task yang diberikan Supervisor.
2. Membaca dokumen yang relevan sebelum mengedit.
3. Mengubah file hanya sesuai assigned Task ID.
4. Menjalankan test/lint/build jika tersedia.
5. Melaporkan file yang diubah.
6. Melaporkan acceptance criteria yang terpenuhi.
7. Melaporkan blocker atau ambiguity.
8. Tidak mengambil keputusan arsitektur besar sendiri.

Subagent Executor boleh memakai model murah/cepat selama instruksi task sangat spesifik.

---

## 4. Expandable Agent Setup

Jika task mulai kompleks, Supervisor boleh menambah subagent dengan role berikut.

```text
Supervisor Agent
├── Backend/API Agent
├── Frontend Agent
├── RAG Worker Agent
├── Evaluation Agent
└── QA/Docs Agent
```

Penambahan subagent hanya boleh dilakukan jika:

1. Task paralel tidak saling mengganggu.
2. Boundary file jelas.
3. Dependency antar task sudah aman.
4. Supervisor mampu melakukan review hasil semua subagent.
5. Branch conflict bisa dikelola.

---

## 5. Optional Subagent Roles

### 5.1 Backend/API Agent

Scope:

- `apps/api`
- ASP.NET Core Web API
- Auth
- Role
- Chat API
- Document search API
- Admin ingestion API
- Rate limit
- Application logging
- EF Core migrations

Tidak boleh:

- Mengubah Python RAG Worker secara besar tanpa approval.
- Mengubah frontend routing tanpa approval.
- Mengganti ASP.NET dengan framework lain.
- Memindahkan auth ke frontend library tanpa approval.

---

### 5.2 Frontend Agent

Scope:

- Hanya `apps/web`
- Next.js + TypeScript
- App Router
- Frontend/web presentation layer
- API consumer terhadap ASP.NET Core Web API
- Auth pages
- Chat UI
- Document search UI
- Admin ingestion UI
- Citation/source display

Tidak boleh:

- Mengganti Next.js dengan Vite atau frontend framework lain.
- Memindahkan core backend logic, authentication, authorization, Chat/Q&A API, document search API, admin ingestion API, rate limiting, atau application logging ke Next.js.
- Mengakses PostgreSQL atau Qdrant secara langsung.
- Menggunakan sumber data backend selain ASP.NET Core Web API tanpa approval Supervisor.
- Menggunakan Next.js Route Handlers untuk selain kebutuhan frontend-specific yang sangat terbatas tanpa approval Supervisor.
- Meletakkan secrets backend di client bundle.
- Menambahkan dashboard analytics kompleks.
- Menambahkan fitur upload dokumen user.
- Menyembunyikan citation atau limitation warning dari user.

---

### 5.3 RAG Worker Agent

Scope:

- `services/rag-worker`
- BPS ingestion
- PDF download
- PyMuPDF parsing
- Cleaning
- Chunking
- Embedding
- Qdrant indexing
- Evaluation harness

Tidak boleh:

- Menambahkan OCR ke MVP.
- Menjadikan Docling parser production.
- Menggunakan embedding provider selain Cloudflare Workers AI atau menambahkan embedding fallback.
- Mengubah corpus scope tanpa approval.
- Membuat angka/statistik sendiri di output.

---

### 5.4 Evaluation Agent

Scope:

- Evaluation dataset
- RAGAS evaluation harness
- LLM-as-judge evaluation support
- Manual audit template 20%
- Retrieval metrics jika ground truth tersedia

Tidak boleh:

- Mengklaim sistem akurat menyeluruh dari automated metric saja.
- Menghapus manual audit 20%.
- Mengabaikan citation accuracy.
- Mengabaikan angka, periode, wilayah, satuan, dan definisi.

---

### 5.5 QA/Docs Agent

Scope:

- README
- Setup docs
- Architecture docs
- Task status updates
- Acceptance criteria checklist
- Smoke test notes
- Known limitations

Tidak boleh:

- Mengubah requirement utama tanpa approval.
- Menulis klaim fitur sudah selesai kalau belum diimplementasikan.
- Menghapus TBD yang memang belum diputuskan.

---

## 6. Non-Negotiable Project Constraints

### 6.1 Architecture Constraints

1. ASP.NET Core Web API adalah main backend/API dan source of truth untuk domain logic dan authorization.
2. Python RAG Worker adalah internal processing service, bukan public-facing backend utama.
3. Frontend MVP menggunakan Next.js + TypeScript dengan App Router sebagai presentation layer dan API consumer terhadap ASP.NET Core.
4. Monorepo wajib modular.
5. Deployment MVP menggunakan satu VPS.
6. Docker Compose digunakan untuk MVP.
7. PostgreSQL container digunakan untuk metadata/auth/job/log.
8. Qdrant container digunakan untuk vector database.
9. PDF storage berada di `/data/ringkas/pdfs`.
10. Object storage adalah future plan, bukan MVP core.

Next.js API Routes, Route Handlers, Server Actions, atau server-side features tidak boleh digunakan untuk mengambil alih core backend responsibilities dari ASP.NET Core tanpa keputusan arsitektur baru dan approval eksplisit.

### 6.2 RAG Constraints

1. MVP bersifat text-first.
2. OCR tidak masuk MVP.
3. PyMuPDF adalah parser utama MVP.
4. Docling hanya future plan / kandidat eksperimen.
5. PDF tanpa text layer diberi status `unsupported_or_extraction_failed`.
6. Chunking memakai recursive character/text splitter.
7. Chunk size awal 500–800 tokens.
8. Chunk overlap awal 20%.
9. Hybrid retrieval memakai dense + sparse retrieval di Qdrant.
10. Fusion memakai Reciprocal Rank Fusion/RRF.
11. Final top-K awal untuk generation adalah Top-10 chunks.
12. Retrieval sufficiency rule wajib ada sebelum generation.

### 6.3 Citation and Grounding Constraints

1. Semua jawaban substantif wajib memiliki citation.
2. Citation minimal mencakup judul dokumen, tahun, wilayah, halaman jika tersedia, URL sumber, dan excerpt.
3. Sistem tidak boleh membuat angka yang tidak ada di sumber.
4. Sistem tidak boleh membuat periode yang tidak ada di sumber.
5. Sistem tidak boleh membuat wilayah yang tidak ada di sumber.
6. Sistem tidak boleh membuat satuan yang tidak ada di sumber.
7. Sistem tidak boleh membuat definisi indikator yang tidak ada di sumber.
8. Sistem tidak boleh menyimpulkan tren/kausalitas tanpa sumber eksplisit.
9. Jika citation tidak tersedia, jawaban dianggap tidak memenuhi standar RINGKAS.

### 6.4 Evaluation Constraints

1. Evaluation approach adalah automated-first.
2. RAGAS digunakan sebagai evaluasi otomatis awal.
3. LLM-as-judge boleh digunakan sebagai bantuan.
4. Manual evaluation dibuat seminimal mungkin, tetapi tidak boleh dihapus.
5. Manual audit minimal 20% dari dataset evaluasi awal.
6. Dataset evaluasi awal berisi 100 pertanyaan.
7. Pertanyaan evaluasi dibuat dengan bantuan LLM dan diverifikasi manual.
8. Evidence chunk/reference source wajib ditandai dari dokumen BPS.
9. Hasil evaluasi disebut baseline awal MVP.
10. Automated score tidak boleh diklaim sebagai bukti akurasi menyeluruh.

---

## 7. Explicitly Out of Scope for MVP

Agents dilarang mengimplementasikan fitur berikut kecuali Supervisor memberi approval eksplisit setelah dokumen requirement diperbarui.

1. Upload dokumen oleh user.
2. OCR pipeline.
3. Docling sebagai parser production.
4. Ekstraksi tabel kompleks yang dijamin akurat.
5. Interpretasi grafik/gambar secara visual.
6. Query langsung database statistik BPS real-time.
7. Validasi angka ke sumber eksternal di luar dokumen corpus.
8. Mobile native app.
9. Payment/subscription.
10. Public API untuk pihak ketiga.
11. Multi-tenant organization management.
12. Dashboard analytics kompleks.
13. Fine-tuning LLM.
14. Training embedding model sendiri.
15. Mengganti ASP.NET backend utama dengan FastAPI/Node/Django.
16. Mengganti Qdrant dengan vector DB lain.
17. Mengganti PostgreSQL dengan database utama lain.

---

## 8. Task Execution Protocol

### 8.1 Before Starting a Task

Subagent wajib melakukan hal berikut sebelum mengedit file:

1. Baca assigned Task ID dari `RINGKAS_TASKS.md`.
2. Baca dependency task.
3. Baca expected output.
4. Baca acceptance criteria.
5. Baca risk.
6. Baca bagian Technical Spec yang relevan.
7. Pastikan task tidak blocked.
8. Laporkan rencana singkat ke Supervisor jika workflow mendukung.

Subagent tidak boleh mengerjakan task tanpa Task ID.

---

### 8.2 During Task Execution

Subagent wajib:

1. Mengubah file seminimal mungkin.
2. Tidak mengerjakan task lain yang tidak diminta.
3. Tidak menambah dependency baru tanpa alasan teknis.
4. Tidak mengubah arsitektur.
5. Tidak menghapus komentar/TBD penting.
6. Tidak menghapus guardrail citation/evaluation.
7. Menjaga naming konsisten dengan dokumen.
8. Menjalankan test/build/lint jika tersedia.

---

### 8.3 After Finishing a Task

Subagent wajib melaporkan:

```markdown
## Task Report

Task ID:
Status:
Files changed:
Summary:
Acceptance criteria checked:
Tests/build run:
Risks or follow-up:
Blocked items:
```

Supervisor wajib review hasil sebelum task dianggap `done`.

---

## 9. Task Assignment Template

Supervisor dapat memberikan task ke subagent dengan format berikut.

```markdown
You are the RINGKAS Subagent Executor.

Assigned Task ID:
- T-XXXX

Read first:
- RINGKAS_TASKS.md
- RINGKAS_TECHNICAL_SPEC.md
- Any file directly related to the assigned task

Scope:
- Only work on the assigned Task ID.
- Do not implement unrelated features.
- Do not modify project architecture.
- Do not add OCR, Docling production, upload feature, or out-of-scope features.

Expected output:
- <copy from TASKS.md>

Acceptance criteria:
- <copy from TASKS.md>

Report back with:
- files changed
- summary
- acceptance criteria status
- tests/build result
- unresolved issues
```

---

## 10. Supervisor Review Checklist

Supervisor wajib mengecek:

1. Apakah task sesuai Task ID?
2. Apakah file yang diubah sesuai scope?
3. Apakah dependency task terpenuhi?
4. Apakah acceptance criteria terpenuhi?
5. Apakah ada fitur out-of-scope?
6. Apakah arsitektur ASP.NET + Python Worker tetap dipatuhi?
7. Apakah citation policy tidak dilanggar?
8. Apakah OCR/Docling production tidak masuk MVP?
9. Apakah secrets tidak dikomit?
10. Apakah test/build/lint dijalankan jika tersedia?
11. Apakah documentation update diperlukan?
12. Apakah task status bisa diubah menjadi `done`, `review`, atau tetap `todo/blocked`?

---

## 11. File Ownership Guidelines

| Area | Path | Default Owner |
|---|---|---|
| Backend/API | `apps/api/` | Backend/API Agent or Subagent Executor |
| Frontend | `apps/web/` | Frontend Agent or Subagent Executor |
| RAG Worker | `services/rag-worker/` | RAG Worker Agent or Subagent Executor |
| Infrastructure | `infra/` | Supervisor or infra-aware subagent |
| Documentation | `docs/`, `*.md` | Supervisor or QA/Docs Agent |

Infrastructure changes require Supervisor review.

Requirement-changing documentation edits require Supervisor approval.

---

## 12. Dependency Policy

Agents may add dependencies only if:

1. The dependency is necessary for assigned task.
2. The dependency matches Technical Spec.
3. The dependency does not replace approved architecture.
4. The dependency is actively maintained or standard enough for MVP use.
5. The dependency does not introduce paid/closed-source lock-in without approval.
6. The reason is documented in the task report.

Examples allowed:

- ASP.NET Core Identity.
- EF Core PostgreSQL provider.
- Qdrant client.
- PyMuPDF.
- LangChain text splitter.
- RAGAS.
- PostgreSQL client for Python.
- Docker Compose.

Examples requiring approval:

- Replacing PostgreSQL.
- Replacing Qdrant.
- Adding Redis/RabbitMQ.
- Adding Celery/Hangfire/Quartz.
- Adding full analytics stack.
- Adding external auth provider like Clerk/Supabase Auth.
- Adding OCR library.
- Adding Docling as production parser.

---


## 13. Branch Policy

Recommended default:

```text
main
dev
feature/<task-id>-short-name
```

Example:

```text
feature/t-0101-api-scaffold
feature/t-0309-pymupdf-parser
feature/t-0504-chat-endpoint
```

Rules:

1. Subagent works on feature branch if Git workflow is available.
2. Supervisor reviews before merge.
3. Do not mix unrelated Task IDs in one branch unless approved.
4. Keep branch names tied to Task ID.
5. If using a single local branch during early setup, still group commits by Task ID.

---

## 14. Definition of Done

A task can be marked `done` only if:

1. Assigned task scope is completed.
2. Acceptance criteria from `TASKS.md` are satisfied.
3. Related docs or comments are updated if needed.
4. Test/build/lint has been run if available.
5. No known critical regression exists.
6. No out-of-scope feature was added.
7. No secrets are committed.
8. Supervisor reviewed the result.
9. Task report is complete.

---

## 15. Blocker Handling

If subagent encounters blocker, it must stop and report.

Common blockers:

1. Missing API key.
2. Unknown provider model name.
3. BPS API response differs from assumption.
4. Database schema conflict.
5. Qdrant collection schema issue.
6. Dependency installation failure.
7. Ambiguous requirement.
8. Task dependency not completed.
9. Test/build failure that cannot be resolved within scope.

Blocker report format:

```markdown
## Blocker Report

Task ID:
Blocker:
Evidence:
Attempted fix:
Suggested options:
Files affected:
Decision needed from Supervisor:
```

---

## 16. Handling TBDs

Agents must not invent final values for unresolved TBD items.

Known TBD examples:

1. Exact NVIDIA NIM generation model.
2. Live-verified output dimension for the approved Cloudflare embedding model.
3. Exact Cloudflare Workers AI generation fallback model.
4. Registered user daily quota.
5. Final session vs JWT strategy if not yet locked.
6. Domain and HTTPS provider.
7. Exact VPS size.
8. Exact BPS endpoint behavior if not verified.

Allowed approach:

- Create config placeholders.
- Add environment variable names.
- Add TODO/TBD comments.
- Implement safe mock/stub.
- Mark task as partially blocked if necessary.

Forbidden approach:

- Hardcoding fake provider model.
- Assuming API limit without evidence.
- Claiming external provider behavior without verification.
- Changing architecture to avoid a TBD without approval.

---

## 17. Security Rules

Agents must never commit:

1. API keys.
2. OAuth client secrets.
3. Database passwords.
4. JWT signing keys.
5. Provider tokens.
6. Personal data dumps.
7. Full downloaded PDF corpus if repository is public.
8. Production `.env` files.

Agents must use `.env.example` for documenting required variables.

Recommended environment variables:

```text
DATABASE_URL=
QDRANT_URL=
NVIDIA_NIM_API_KEY=
NVIDIA_NIM_GENERATION_MODEL=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_WORKERS_AI_GENERATION_MODEL=
CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL=@cf/qwen/qwen3-embedding-0.6b
QDRANT_COLLECTION_NAME=ringkas_chunks_cf_qwen3_embedding_v1
QDRANT_DENSE_VECTOR_SIZE=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTH_SECRET=
PDF_STORAGE_PATH=/data/ringkas/pdfs
```

---

## 18. Grounded Answer Generation Rules

Any agent working on generation must enforce these rules in prompt and code:

1. Answer only from retrieved chunks.
2. Include citation for substantive claims.
3. State limitations when evidence is weak.
4. Refuse substantive answer when evidence is insufficient.
5. Do not infer statistics beyond the source.
6. Do not fabricate numbers, years, regions, units, or definitions.
7. Do not summarize chart/image content unless available as extracted text/caption.
8. Prefer concise direct answer with citation.
9. Use table only when source supports structured comparison.
10. Use the user's language when clear; default to Bahasa Indonesia if unclear.

---

## 19. Admin UI Scope Rules

Admin UI MVP may include only:

1. Trigger ingestion.
2. View ingestion job status.
3. View short ingestion logs.

Admin UI MVP must not include:

1. Full analytics dashboard.
2. User management dashboard.
3. Full document management dashboard.
4. Mass edit/delete/reprocess UI.
5. Upload document UI.
6. Cost analytics dashboard.
7. Complex monitoring panel.

---

## 20. Recommended Workflow for Current Default Setup

Because current default is **1 Supervisor + 1 Subagent**, use this workflow:

```text
Step 1: Supervisor selects next unblocked task from TASKS.md.
Step 2: Supervisor prepares precise task prompt.
Step 3: Subagent executes only that task.
Step 4: Subagent reports changed files and acceptance criteria.
Step 5: Supervisor reviews.
Step 6: Supervisor updates task status.
Step 7: Repeat.
```

Recommended early execution order:

1. T-0001 to T-0007
2. T-0101 to T-0112
3. T-0201 to T-0209
4. T-0301 to T-0315
5. T-0401 to T-0413
6. T-0501 to T-0511
7. T-0601 to T-0609
8. T-0701 to T-0704

---

## 21. When to Add More Subagents

Add more subagents only if:

1. Backend and frontend tasks can run independently.
2. RAG worker task does not depend on unfinished database migration.
3. Supervisor has enough context to review all outputs.
4. Branch conflicts can be managed.
5. Each subagent receives clear Task IDs.

Recommended scaling path:

```text
Stage 1:
- 1 Supervisor
- 1 Subagent Executor

Stage 2:
- 1 Supervisor
- Backend/API Subagent
- Frontend Subagent

Stage 3:
- 1 Supervisor
- Backend/API Subagent
- Frontend Subagent
- RAG Worker Subagent
- QA/Docs Subagent
```

Do not start with too many subagents if repo is still empty.

---

## 22. Minimal Prompt for Supervisor Agent

```markdown
You are the RINGKAS Supervisor Agent.

Your job:
- Manage implementation using RINGKAS_TASKS.md.
- Enforce RINGKAS_PROJECT_BRIEF.md, RINGKAS_PRD.md, RINGKAS_SRD.md, and RINGKAS_TECHNICAL_SPEC.md.
- Assign one task at a time to the Subagent Executor.
- Review changes against acceptance criteria.
- Prevent scope creep.

Non-negotiable:
- ASP.NET Core Web API is the main backend/API and source of truth for domain logic and authorization.
- Python RAG Worker is an internal processing service only.
- Next.js + TypeScript with App Router is the frontend/web presentation layer and API consumer terhadap ASP.NET Core.
- Next.js must not access PostgreSQL or Qdrant directly or take over core backend responsibilities.
- PostgreSQL and Qdrant are required.
- OCR is out of MVP.
- Docling is future plan only.
- All substantive answers require citation.
```

---

## 23. Minimal Prompt for Subagent Executor

```markdown
You are the RINGKAS Subagent Executor.

You must:
- Work only on the assigned Task ID.
- Read RINGKAS_TASKS.md and RINGKAS_TECHNICAL_SPEC.md before editing.
- Do not change architecture.
- Do not add out-of-scope features.
- Do not add OCR.
- Do not make Docling production parser.
- Do not replace ASP.NET Core, PostgreSQL, Qdrant, or Next.js + TypeScript.
- Do not move core backend responsibilities into Next.js or access databases from `apps/web`.
- Report all changed files.
- Report acceptance criteria status.
- Stop and report blocker if requirement is ambiguous.
```

---

## 24. Final Rule

When in doubt, agents must choose the safer option:

1. Do not invent.
2. Do not overbuild.
3. Do not bypass citation.
4. Do not add features outside MVP.
5. Do not change architecture without approval.
6. Document uncertainty.
7. Ask Supervisor for decision.
