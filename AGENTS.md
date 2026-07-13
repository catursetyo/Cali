# AGENTS.md

## Tujuan dokumen

File ini adalah instruksi utama bagi Codex saat membantu mengembangkan, menguji,
mendokumentasikan, dan memublikasikan **Cali Finance for Hermes Agent**.

Letakkan file ini di root repository, sejajar dengan `README.md`,
`finance.py`, dan folder `cali_finance/`.

Instruksi yang paling dekat dengan file yang sedang dikerjakan memiliki
prioritas lebih tinggi bila di masa depan terdapat `AGENTS.md` tambahan di
subfolder tertentu.

---

## Ringkasan proyek

Cali Finance adalah personal finance ledger lokal untuk Hermes Agent.

Pembagian tanggung jawabnya:

- Model AI memahami bahasa natural dan memilih command.
- Python memvalidasi input dan menjalankan business rules.
- SQLite menjadi sumber kebenaran untuk transaksi dan histori.
- Hermes skill menjelaskan kapan serta bagaimana command digunakan.
- Telegram hanya menjadi antarmuka percakapan.
- Azure VM menjadi runtime deployment.
- GitHub hanya menyimpan source code, dokumentasi, dan contoh yang sudah
  disanitasi.

Proyek ini **bukan**:

- aplikasi akuntansi bisnis;
- aplikasi pajak;
- penasihat investasi;
- sinkronisasi login bank langsung;
- tempat menyimpan data finansial pengguna di GitHub.

---

## Prioritas utama

Urutan prioritas ketika mengambil keputusan teknis:

1. Integritas data keuangan.
2. Keamanan dan privasi.
3. Backward compatibility dan migrasi yang aman.
4. Perilaku yang deterministik dan dapat diuji.
5. Kemudahan pemeliharaan.
6. Pengalaman penggunaan Hermes/Telegram.
7. Fitur baru dan kenyamanan.

Jangan mengorbankan lima prioritas pertama demi UI, personality, atau fitur yang
terlihat menarik.

---

## Aturan yang tidak boleh dilanggar

### Jangan pernah memasukkan data sensitif ke repository

Jangan membaca, menyalin, membuat fixture dari, atau melakukan commit terhadap:

- `~/.hermes/finance/finance.db`;
- file `*.db`, `*.sqlite`, `*.sqlite3`, WAL, atau SHM;
- backup database;
- foto struk asli;
- mutasi rekening asli;
- export transaksi asli;
- `~/.hermes/.env`;
- `~/.hermes/state.db`;
- token Telegram;
- token Nous Portal;
- API key model;
- credential Azure;
- GitHub token;
- private SSH key;
- private `age` key;
- `rclone.conf`;
- SAS token atau storage account key;
- informasi rekening, nomor kartu, PIN, atau password.

Gunakan data sintetis untuk test, contoh, dokumentasi, screenshot, dan issue.

### Jangan mengubah runtime Azure sebagai efek samping

Repository lokal adalah source of truth untuk source code.

Jangan mengedit file yang terpasang di:

```text
~/.hermes/finance/
~/.hermes/skills/
~/.hermes/scripts/
```

sebagai cara utama mengembangkan fitur. Edit source repository, jalankan test,
commit, lalu deploy melalui `install.sh`.

Jangan menjalankan SSH, `scp`, deployment Azure, restart gateway, atau command
remote kecuali pengguna memintanya secara eksplisit.

### Jangan melakukan operasi Git destruktif

Tanpa instruksi eksplisit pengguna, jangan:

- `git push`;
- membuat repository GitHub;
- membuat release atau tag;
- mengubah visibility repository;
- menghapus branch;
- melakukan force push;
- `git reset --hard`;
- `git clean -fd`;
- rewrite history;
- menghapus remote;
- menghapus file pengguna yang tidak terkait.

Jangan pernah force-push ke `main`.

### Jangan mengklaim sesuatu berhasil tanpa bukti

Sebuah perubahan dianggap berhasil hanya bila:

- command selesai dengan exit code `0`;
- test yang relevan lulus;
- output diperiksa;
- tidak ada perubahan tak sengaja pada `git diff`.

Jika test tidak dapat dijalankan, jelaskan penyebabnya secara jujur.

---

## Bahasa dan komunikasi

- Berkomunikasi dengan pengguna dalam bahasa Indonesia kecuali diminta lain.
- Gunakan bahasa yang lugas dan tidak terlalu formal.
- Source code, identifier, commit message, dan API/CLI option menggunakan
  bahasa Inggris.
- Dokumentasi pengguna boleh berbahasa Indonesia.
- Jangan menutupi risiko atau kegagalan dengan bahasa optimistis.
- Tampilkan ringkasan perubahan, file yang diubah, test yang dijalankan, dan
  risiko tersisa pada akhir tugas.

---

## Peta repository

Struktur utama yang diharapkan:

```text
.
├── AGENTS.md
├── CHANGELOG.md
├── LICENSE
├── README.md
├── SECURITY.md
├── .env.example
├── .gitattributes
├── .gitignore
├── .github/
│   └── workflows/
│       └── test.yml
├── cali_finance/
│   ├── __init__.py
│   ├── alerts.py
│   ├── backup.py
│   ├── budgets.py
│   ├── cli.py
│   ├── config.py
│   ├── dashboard.py
│   ├── db.py
│   ├── goals.py
│   ├── imports.py
│   ├── ledger.py
│   ├── money.py
│   ├── obligations.py
│   ├── receipts.py
│   ├── reports.py
│   └── settings.py
├── examples/
│   └── SOUL.example.md
├── finance.py
├── install.sh
├── install-ocr.sh
├── scripts/
├── skill/
│   ├── SKILL.md
│   └── scripts/
├── tests/
│   ├── migration_test.py
│   ├── restore_test.py
│   └── smoke_test.py
└── uninstall.sh
```

Jangan memindahkan file tanpa alasan kuat. Perubahan struktur harus memperbarui
installer, test, README, skill, dan workflow CI yang terdampak.

---

## Tanggung jawab setiap modul

Jaga batas tanggung jawab berikut:

- `cli.py`: parsing argument, routing command, dan serialisasi output.
- `db.py`: schema, koneksi, migrasi, integrity check, dan transaction boundary.
- `ledger.py`: transaksi, dompet, kategori, rekonsiliasi, pencarian, dan void.
- `money.py`: parsing serta formatting nominal.
- `budgets.py`: budget dan threshold.
- `obligations.py`: tagihan, utang, piutang, pembayaran, dan recurring obligation.
- `goals.py`: target tabungan virtual.
- `reports.py`: agregasi laporan dan safe-to-spend.
- `imports.py`: preview, review, commit, deduplication, dan export CSV.
- `receipts.py`: OCR preview dan konfirmasi struk.
- `backup.py`: backup, restore, offsite backup, dan retention.
- `alerts.py`: alert data serta text output.
- `dashboard.py`: dashboard statis dari data teragregasi.
- `settings.py`: konfigurasi yang tersimpan.
- `skill/SKILL.md`: instruksi penggunaan oleh Hermes, bukan business logic.
- `scripts/`: wrapper non-interaktif untuk cron.
- `tests/`: data sintetis dan isolated `HERMES_HOME`.

Business rule tidak boleh hanya hidup di prompt atau `SKILL.md`. Implementasikan
di Python agar dapat diuji.

---

## Prinsip arsitektur

### Local-first

Default-nya semua data keuangan tetap lokal di `HERMES_HOME`.

Fitur baru tidak boleh mengirim data ke:

- web API;
- analytics;
- telemetry;
- model lain;
- storage eksternal;

tanpa tindakan eksplisit dan terdokumentasi dari pengguna.

### SQLite adalah sumber kebenaran

Jangan menjadikan chat history, Markdown, memory, dashboard, CSV export, atau
response model sebagai sumber kebenaran.

Semua perubahan finansial harus menghasilkan record terstruktur dan audit trail
yang jelas.

### Nominal menggunakan integer rupiah

- Simpan nominal sebagai integer.
- Jangan gunakan float.
- Parsing singkatan seperti `25rb` atau `1,5jt` harus menghasilkan integer.
- Format tampilan menggunakan rupiah Indonesia.
- Nilai negatif hanya digunakan bila domain memang mengizinkan; transaksi
  normal harus memiliki amount positif dengan arah ditentukan oleh jenisnya.

### Tanggal dan waktu

- Gunakan timezone `Asia/Jakarta` sebagai default.
- Simpan datetime timezone-aware.
- CLI menerima tanggal absolut yang tervalidasi.
- Resolusi kata seperti “kemarin” dilakukan oleh agent sebelum memanggil CLI,
  bukan dengan tebakan di layer database.
- Laporan mingguan menggunakan Senin sampai Minggu kecuali requirement diubah
  secara eksplisit.

### Auditability

Hindari update atau delete yang menghilangkan histori.

Gunakan:

- void untuk transaksi salah;
- adjustment untuk rekonsiliasi;
- payment record untuk pelunasan;
- status untuk pembatalan;
- migration version untuk perubahan schema.

---

## Aturan domain keuangan

### Transaksi

- Pengeluaran dan pemasukan membutuhkan dompet, nominal, deskripsi, dan kategori.
- Transfer antar-dompet bukan pengeluaran atau pemasukan.
- Jangan menebak dompet yang tidak disebutkan.
- Jangan menebak nominal.
- Kategori boleh diinferensikan oleh Hermes, tetapi Python tetap memvalidasi
  kategori yang tersedia.
- Duplicate detection harus memperingatkan, bukan diam-diam menghapus transaksi
  yang mungkin valid.
- Override duplikat harus eksplisit.

### Tagihan

Tagihan belum dibayar adalah kewajiban, bukan pengeluaran aktual.

Pengeluaran dibuat saat:

- pembayaran benar-benar dilakukan; atau
- installment/partial payment dicatat.

Tagihan mendukung:

- jatuh tempo;
- pembayaran parsial;
- status open, paid, overdue, atau cancelled;
- dompet default;
- kategori;
- counterparty atau provider;
- audit payment.

### Utang dan piutang

Bedakan secara eksplisit:

- `payable`: pengguna berutang kepada pihak lain;
- `receivable`: pihak lain berutang kepada pengguna.

Dana pinjaman:

- dana pinjaman masuk menambah saldo dompet tetapi bukan income;
- dana yang dipinjamkan keluar mengurangi saldo tetapi bukan expense;
- pembayaran pokok utang/piutang bukan expense/income;
- biaya, bunga, atau penalti harus dicatat terpisah bila fitur tersebut ada.

### Budget

- Budget tidak mengubah saldo.
- Threshold harus deterministik.
- Peringatan tidak boleh dikirim berulang tanpa kontrol yang jelas.
- Periode dan timezone harus konsisten.
- Budget overall dan per-category tidak boleh saling menciptakan double counting
  pada laporan.

### Goal

- Goal adalah bucket virtual.
- Kontribusi goal tidak boleh mengubah saldo dompet kecuali ada transfer nyata.
- UI dan response harus selalu menjelaskan sifat virtual ini.

### Safe-to-spend

Safe-to-spend adalah estimasi, bukan fakta absolut.

Rumus dan komponen harus:

- terimplementasi di Python;
- dapat diuji;
- dijelaskan pada dokumentasi;
- tidak menyembunyikan asumsi.

---

## Database dan migrasi

### Aturan schema

Sebelum mengubah schema:

1. Pelajari schema dan migration saat ini di `db.py`.
2. Pastikan database v1/v2 yang valid masih dapat dimigrasikan.
3. Jangan drop tabel atau kolom berisi data tanpa migration plan.
4. Migration harus idempotent.
5. Migration harus aman dijalankan ulang setelah kegagalan parsial sejauh
   memungkinkan.
6. Gunakan SQLite transaction untuk perubahan multi-step.
7. Perbarui schema version.
8. Tambahkan atau perbarui migration test.

### Backward compatibility

Setiap perubahan schema atau semantics harus menguji minimal:

- instalasi database baru;
- migrasi database versi lama;
- data lama tetap tersedia;
- saldo setelah migrasi tetap benar;
- foreign key check;
- `PRAGMA integrity_check`;
- backup sebelum migrasi tetap dapat dibuat.

### Restore

Perubahan backup atau restore wajib mempertahankan:

- validasi input;
- explicit confirmation;
- integrity check sesudah restore;
- larangan overwrite diam-diam;
- test yang memakai direktori sementara.

---

## Kontrak CLI

CLI adalah antarmuka antara Hermes dan business logic.

Aturan:

- Option name stabil dan konsisten.
- Output machine-readable menggunakan JSON bila bukan laporan text.
- Error operasional keluar dengan non-zero exit code.
- Error message harus actionable dan tidak membocorkan secret.
- Jangan mencetak traceback untuk error input normal.
- Jangan mengubah field JSON yang sudah dipakai skill tanpa compatibility plan.
- Command yang berbahaya harus memerlukan konfirmasi eksplisit.
- Command cron harus non-interaktif.
- `--help` wajib tetap berguna.
- Tambahkan command baru di `cli.py` dan dokumentasikan di `README.md` serta
  `skill/SKILL.md`.

Entrypoint utama:

```bash
python3 finance.py
```

Runtime terpasang:

```bash
python3 ~/.hermes/finance/finance.py
```

---

## Hermes skill

`skill/SKILL.md` harus:

- menjelaskan kapan skill digunakan;
- memberikan prosedur yang deterministik;
- menyuruh agent bertanya bila data material kurang;
- melarang agent mengarang hasil;
- menggunakan command CLI yang benar;
- menyimpan raw user input bila relevan;
- meminta preview dan konfirmasi untuk OCR/import/rekonsiliasi;
- membedakan tagihan, utang, piutang, transfer, pemasukan, dan pengeluaran;
- menjaga response Telegram ringkas;
- tidak memuat secret atau data pribadi.

Setelah mengubah command CLI, audit seluruh contoh pada `skill/SKILL.md`.

Personality tidak boleh mengubah business rules. Candaan Cali tidak boleh
menggantikan validasi, angka, error, atau konfirmasi.

---

## OCR dan import

### OCR

- Tesseract adalah dependency opsional.
- Core test tidak boleh bergantung pada Tesseract.
- OCR hanya menghasilkan preview.
- Jangan mencatat transaksi otomatis dari OCR.
- Konfirmasi minimal: amount, date, wallet, category, dan description.
- Simpan file receipt hanya di runtime data directory.
- Jangan memasukkan receipt asli ke test atau repository.

### Import CSV

Gunakan alur:

```text
preview -> inspect/update rows -> explicit commit
```

Syarat:

- file tidak langsung menciptakan transaksi pada preview;
- source dan batch dapat diaudit;
- duplicate detection menggunakan external ID dan/atau fingerprint;
- baris ambigu tidak boleh diam-diam masuk kategori `Lainnya`;
- commit harus idempotent sejauh mungkin;
- test menggunakan CSV sintetis di temporary directory.

---

## Backup dan offsite backup

Backup lokal dan offsite adalah dua hal berbeda.

- Backup lokal tetap diperlukan.
- Backup offsite harus terenkripsi sebelum upload.
- Jangan menyimpan private encryption key di repository.
- Jangan memasukkan credential `rclone`.
- Restore harus dapat dilakukan tanpa network setelah file backup tersedia.
- Retention policy harus terdokumentasi.
- Alert backup harus memperhitungkan backup age.
- Jangan menyebut backup aman sebelum integrity check berhasil.

---

## Coding style

### Python

- Targetkan Python 3.11 dan 3.12.
- Utamakan standard library.
- Dependency baru harus benar-benar diperlukan dan dijelaskan.
- Gunakan type hints untuk public function dan struktur kompleks.
- Gunakan `pathlib.Path`.
- Gunakan context manager atau penutupan koneksi yang jelas.
- Hindari global mutable state.
- Hindari SQL string interpolation untuk value; gunakan parameter binding.
- Untuk identifier SQL dinamis, gunakan allowlist eksplisit.
- Buat function kecil dengan tanggung jawab tunggal.
- Jangan menambahkan abstraction hanya untuk terlihat rapi.
- Pertahankan error message yang spesifik.
- Jangan menonaktifkan foreign key.
- Jangan gunakan `except Exception` kecuali di boundary yang memang harus
  mengubah error menjadi output CLI; tetap jangan menelan error diam-diam.

### Shell

- Gunakan:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

- Quote variable expansion.
- Hindari command destruktif tanpa guard.
- Script cron harus non-interaktif.
- Script installer harus dapat dijalankan ulang.
- Installer tidak boleh menghapus database aktif.
- Jaga line ending LF.

### SQL

- Gunakan transaction untuk operasi multi-table.
- Tambahkan index berdasarkan query yang benar-benar digunakan.
- Jangan menambahkan index berlebihan.
- Foreign key dan constraint adalah bagian business rule, bukan dekorasi.
- Jelaskan perubahan schema yang tidak trivial.

---

## Testing

### Command wajib

Dari root repository:

```bash
python3 -m compileall -q cali_finance finance.py
python3 tests/smoke_test.py
python3 tests/migration_test.py
python3 tests/restore_test.py
```

Hasil yang diharapkan:

```text
SMOKE_OK
MIGRATION_OK
RESTORE_OK
```

### Isolasi test

Semua test harus menggunakan temporary `HERMES_HOME`.

Test tidak boleh:

- membaca `~/.hermes` asli;
- mengubah database pengguna;
- menggunakan credential;
- memerlukan internet;
- menghubungi Telegram;
- mengakses Azure;
- mengirim data keluar;
- bergantung pada urutan eksekusi test lain.

### Test baru

Tambahkan test ketika mengubah:

- parsing uang;
- saldo;
- duplicate detection;
- laporan;
- budget;
- tagihan/utang/piutang;
- recurring obligations;
- safe-to-spend;
- import;
- receipt confirmation;
- backup/restore;
- migration;
- CLI output contract.

Bug fix harus memiliki regression test bila memungkinkan.

### Sebelum menyelesaikan tugas

Jalankan:

```bash
git status --short
git diff --check
git diff --stat
```

Lalu periksa diff aktual.

---

## Dokumentasi

Perubahan behavior wajib memperbarui dokumentasi yang relevan:

- `README.md`: instalasi, penggunaan, command, limitation.
- `skill/SKILL.md`: instruksi Hermes.
- `CHANGELOG.md`: perubahan user-facing.
- `SECURITY.md`: bila ada perubahan threat model.
- `.env.example`: bila ada konfigurasi baru.
- script cron: bila command berubah.
- contoh sanitized: bila menambah workflow baru.

Jangan mendokumentasikan command yang belum diuji.

Jangan menyertakan:

- IP server;
- username pribadi;
- token;
- path lokal spesifik pengguna;
- nominal atau transaksi asli;
- screenshot dengan data pribadi.

Gunakan placeholder:

```text
USER_VM
PUBLIC_IP
USERNAME
NAMA_KEY.pem
```

---

## Git workflow

### Sebelum mulai

Periksa:

```bash
git status --short
git branch --show-current
git remote -v
```

Jangan menimpa perubahan pengguna yang belum di-commit.

Jika working tree memiliki perubahan yang tidak terkait, pertahankan dan hindari
mengedit file tersebut kecuali diperlukan.

### Branch

Untuk pekerjaan non-trivial, sarankan branch:

```text
feat/<nama-fitur>
fix/<nama-bug>
docs/<nama-perubahan>
chore/<nama-tugas>
```

Jangan membuat branch bila pengguna meminta perubahan kecil langsung di branch
aktif, kecuali ada risiko tinggi.

### Commit

Gunakan Conventional Commits:

```text
feat: add debt repayment tracking
fix: preserve wallet balance during migration
docs: add GitHub publishing guide
test: cover partial bill payments
refactor: isolate report aggregation
chore: configure GitHub Actions
```

Commit harus:

- fokus pada satu tujuan;
- tidak memuat secret;
- tidak memuat runtime data;
- memiliki test yang relevan;
- tidak menggabungkan formatting massal dengan behavior change tanpa alasan.

Jangan membuat commit kecuali diminta atau jelas menjadi bagian tugas pengguna.

### Sebelum push

Jalankan:

```bash
git status
git diff --cached --check
git diff --cached --stat
git diff --cached
```

Lakukan secret scan lokal:

```bash
grep -RInE \
  'AIza|GEMINI_API_KEY|GOOGLE_API_KEY|TELEGRAM.*TOKEN|ghp_|github_pat_|BEGIN .*PRIVATE KEY|ACCOUNT_KEY|SAS_TOKEN' \
  . \
  --exclude-dir=.git
```

Cari file sensitif:

```bash
find . -type f \( \
  -name '*.db' -o \
  -name '*.sqlite*' -o \
  -name '.env' -o \
  -name '*.pem' -o \
  -name '*.key' -o \
  -name 'rclone.conf' \
\)
```

Nilai placeholder pada dokumentasi boleh muncul. Nilai credential asli tidak
boleh muncul.

---

## GitHub repository setup

Bila file berikut belum ada, Codex boleh membantu membuatnya:

- `.gitignore`;
- `.gitattributes`;
- `.env.example`;
- `SECURITY.md`;
- `.github/workflows/test.yml`;
- `examples/SOUL.example.md`.

### `.gitignore`

Minimal harus mengabaikan:

- Python cache dan virtualenv;
- `.env` asli;
- database dan WAL/SHM;
- backup;
- receipt;
- import/export asli;
- credential;
- private key;
- release archive;
- editor metadata.

Contoh sanitized di `examples/` dan dokumentasi di `docs/` boleh dilacak.

### GitHub Actions

CI minimal harus:

- berjalan pada push dan pull request;
- menggunakan Python 3.11 dan 3.12;
- menjalankan compileall;
- menjalankan smoke, migration, dan restore test;
- hanya memiliki permission `contents: read`;
- tidak membutuhkan repository secret;
- tidak menggunakan data nyata.

### Repository visibility

Rekomendasikan repository **private** pada awal publikasi.

Jangan mengubah menjadi public sampai pengguna memeriksa:

- license;
- README;
- security policy;
- seluruh git history;
- secret scanning;
- contoh data;
- attribution;
- kesiapan menerima issue dari publik.

---

## Release dan versioning

Gunakan Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

- `PATCH`: bug fix backward-compatible.
- `MINOR`: fitur backward-compatible.
- `MAJOR`: breaking change atau migration yang mengubah kontrak secara material.

Version source berada di:

```text
cali_finance/__init__.py
```

Saat menyiapkan release:

1. Pastikan working tree bersih.
2. Tentukan versi berikutnya.
3. Perbarui `cali_finance/__init__.py`.
4. Perbarui `CHANGELOG.md`.
5. Perbarui README jika perlu.
6. Jalankan seluruh test pada Python yang tersedia.
7. Jalankan `git diff --check`.
8. Buat commit release.
9. Buat annotated tag `vX.Y.Z`.
10. Push commit dan tag hanya setelah persetujuan pengguna.
11. Buat GitHub Release dari tag.
12. Sertakan ringkasan perubahan, migration note, upgrade steps, dan known
    limitations.
13. Bila membuat archive, hasilkan SHA-256 checksum.
14. Jangan menyertakan database, config runtime, receipt, atau secret.

Contoh tag:

```bash
git tag -a v2.1.0 -m "Cali Finance v2.1.0"
```

Jangan menjalankan command tersebut tanpa instruksi eksplisit pengguna.

---

## Checklist publikasi GitHub

Sebelum publikasi, verifikasi:

- [ ] `AGENTS.md` tersedia di root.
- [ ] `README.md` menjelaskan tujuan, fitur, instalasi, upgrade, dan batasan.
- [ ] `LICENSE` memakai nama pemilik yang benar.
- [ ] `SECURITY.md` tersedia.
- [ ] `.gitignore` mencakup runtime data dan secrets.
- [ ] `.env.example` tidak berisi nilai secret.
- [ ] `examples/SOUL.example.md` sudah disanitasi.
- [ ] Seluruh test lulus.
- [ ] Tidak ada database di working tree atau history.
- [ ] Tidak ada receipt/mutasi asli.
- [ ] Tidak ada credential.
- [ ] GitHub Actions berhasil.
- [ ] Default branch adalah `main`.
- [ ] Secret scanning dan push protection diaktifkan bila tersedia.
- [ ] Repository masih private bila audit publik belum selesai.
- [ ] Upgrade instructions dari versi sebelumnya tersedia.
- [ ] Release note menjelaskan migration dan breaking changes.
- [ ] Archive release memiliki checksum bila didistribusikan langsung.

---

## Deployment ke Azure

Deployment adalah langkah terpisah dari publish GitHub.

Alur yang diharapkan:

```text
ubah source lokal
-> jalankan test
-> commit
-> push ke GitHub
-> pull di Azure
-> hentikan gateway
-> jalankan install.sh
-> hidupkan gateway
-> health check
```

Command deployment contoh hanya boleh dijalankan setelah pengguna meminta:

```bash
hermes gateway stop
./install.sh
hermes gateway start
hermes gateway status
python3 ~/.hermes/finance/finance.py health
```

Installer harus:

- membuat pre-upgrade backup;
- menjaga database lama;
- memigrasikan schema;
- memasang source, skill, dan script;
- tidak menimpa `SOUL.md`;
- tidak menghapus data pengguna.

Setelah deployment, sarankan pengguna menjalankan `/reset` di Telegram bila
`SKILL.md` berubah.

---

## Workflow Codex untuk setiap tugas

Ikuti urutan berikut:

### 1. Pahami permintaan

- Identifikasi apakah tugas menyentuh uang, schema, backup, security, atau release.
- Cari requirement ambigu yang dapat mengubah hasil secara material.
- Jangan bertanya bila jawabannya dapat diperoleh dengan membaca repository.

### 2. Inspeksi repository

Baca file yang relevan dan periksa git state.

Jangan menebak struktur atau API yang sudah ada.

### 3. Buat rencana kecil

Untuk perubahan non-trivial, jelaskan secara singkat:

- file yang akan disentuh;
- behavior yang berubah;
- test yang akan ditambahkan;
- risiko migration/security.

### 4. Implementasi minimal

- Ubah hanya file yang diperlukan.
- Pertahankan API lama bila memungkinkan.
- Jangan melakukan refactor luas tanpa alasan.
- Jangan menambahkan dependency untuk masalah yang dapat diselesaikan dengan
  standard library secara jelas.

### 5. Test

Jalankan test paling spesifik terlebih dahulu, kemudian seluruh suite.

### 6. Review diff

Periksa:

- data leak;
- command yang salah;
- migration risk;
- output contract;
- typo dokumentasi;
- line ending;
- executable bit pada shell script;
- file baru yang belum dilacak;
- file runtime yang ikut masuk.

### 7. Laporkan hasil

Format akhir yang diharapkan:

```text
Perubahan:
- ...

Test:
- `command` — lulus
- `command` — lulus

Catatan/Risiko:
- ...

Langkah berikutnya:
- ...
```

Jangan mengatakan “selesai” bila masih ada test gagal atau requirement belum
terpenuhi.

---

## Definition of done

Sebuah tugas dianggap selesai bila:

- behavior sesuai permintaan;
- business rule berada di Python, bukan hanya prompt;
- test relevan tersedia dan lulus;
- migration aman bila schema berubah;
- dokumentasi dan Hermes skill sinkron;
- tidak ada secret atau data nyata;
- `git diff --check` bersih;
- perubahan tidak merusak installer atau cron;
- output CLI tetap dapat digunakan Hermes;
- risiko yang belum selesai dijelaskan;
- publish/deploy hanya dilakukan setelah persetujuan eksplisit pengguna.

---

## Instruksi terakhir

Bertindak sebagai maintainer yang konservatif terhadap data keuangan.

Lebih baik:

- menolak input ambigu;
- meminta konfirmasi;
- menambahkan regression test;
- mempertahankan histori;
- memberi tahu risiko secara jujur;

daripada menghasilkan fitur cepat yang dapat merusak saldo, transaksi, backup,
atau privasi pengguna.
