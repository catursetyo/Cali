---
name: personal-finance
description: Catat, audit, dan rangkum keuangan pribadi dengan dompet, budget, tagihan, utang, piutang, target tabungan, CSV, dan struk.
version: 1.0.0
author: Cali Finance Project
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [finance, expense, budgeting, debt, bills, savings, automation]
    category: productivity
    requires_toolsets: [terminal]
---

# Cali Personal Finance

Gunakan skill ini untuk semua pekerjaan keuangan pribadi: transaksi, saldo,
budget, tagihan belum dibayar, utang, piutang, target tabungan, laporan,
rekonsiliasi, import CSV, dan struk.

CLI yang wajib digunakan:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh COMMAND ...
```

Database SQLite lokal adalah satu-satunya sumber kebenaran. Jangan menganggap
pesan chat, memory, Markdown, atau jawaban model sebagai transaksi yang sudah
tercatat.

## Aturan yang Tidak Boleh Dilanggar

1. Jangan pernah mengarang nominal, tanggal, kategori, dompet, saldo, atau hasil.
2. Jangan mengatakan “tercatat”, “lunas”, atau “berhasil” sebelum CLI
   mengembalikan `"ok": true`.
3. Pengeluaran/pemasukan minimum membutuhkan nominal, kategori, dompet,
   deskripsi, dan tanggal. Tanggal default adalah sekarang di Asia/Jakarta.
4. Kategori boleh diinferensikan hanya jika jelas. Bila ambigu, tanyakan.
5. Dompet yang tidak disebutkan harus ditanyakan. Jangan otomatis memilih Cash.
6. Simpan ucapan asli pengguna melalui `--raw-input` bila command mendukungnya.
7. Jangan menulis SQL langsung. Selalu gunakan command tervalidasi.
8. Transfer antar-dompet bukan pengeluaran atau pemasukan.
9. Pembayaran pokok utang bukan pengeluaran konsumsi. Penagihan piutang bukan
   pemasukan usaha. CLI memisahkan arus pembiayaan tersebut.
10. Target tabungan adalah alokasi virtual; saldo dompet tidak berubah kecuali
    pengguna juga mencatat transfer nyata.
11. Untuk aksi berisiko, gunakan preview lalu minta konfirmasi:
    - dugaan transaksi duplikat;
    - penyesuaian hasil rekonsiliasi;
    - commit import CSV;
    - konfirmasi hasil OCR struk;
    - pembatalan transaksi, tagihan, atau utang.
12. Jangan kirim database atau rincian sensitif ke web/API eksternal tanpa
    permintaan eksplisit.

## Pencatatan Transaksi

Pengeluaran:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh add \
  --type expense \
  --amount 25000 \
  --category "Makan" \
  --wallet "Cash" \
  --description "Makan bakso" \
  --date "2026-07-14" \
  --raw-input "tadi makan bakso 25 ribu cash"
```

Pemasukan:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh add \
  --type income \
  --amount 750000 \
  --category "Freelance" \
  --wallet "BCA" \
  --description "Pembayaran proyek" \
  --raw-input "freelance masuk 750 ribu ke BCA"
```

Jika hasil berisi `code: possible_duplicate`, tampilkan kandidatnya dan tanyakan
apakah transaksi memang baru. Hanya setelah pengguna mengonfirmasi, ulangi
command dengan `--force-duplicate`.

Konfirmasi sukses harus ringkas:

```text
Tercatat #ID: Rp... — deskripsi
Kategori: ...
Dompet: ...
Tanggal: ...
Saldo dompet: ...
```

Boleh menambahkan satu komentar Cali yang ringan, tetapi angka dan status harus
tetap menjadi fokus.

## Transfer dan Dompet

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh transfer \
  --amount 100000 --from-wallet BCA --to-wallet GoPay \
  --description "Top up GoPay"
```

Lihat atau tambah dompet:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh wallets
${HERMES_SKILL_DIR}/scripts/finance.sh wallet-add \
  --name "DANA" --kind ewallet --opening-balance 50000
```

Saldo awal hanya untuk kondisi saat mulai memakai sistem, bukan untuk koreksi
saldo harian.

## Rekonsiliasi Saldo

Selalu preview dahulu:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh reconcile \
  --wallet "GoPay" --actual-balance 142500
```

Jika ada selisih, jelaskan saldo tercatat, saldo aktual, dan selisihnya. Tanyakan
apakah pengguna ingin mencari transaksi yang hilang atau membuat penyesuaian.
Hanya setelah persetujuan eksplisit:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh reconcile-adjust \
  --check-id ID --reason "Transaksi lama tidak tercatat" \
  --confirm-adjust YES
```

## Budget

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh budget-set \
  --category "Makan" --limit 800000 --period month
${HERMES_SKILL_DIR}/scripts/finance.sh budgets
```

Setelah mencatat pengeluaran, periksa `budget_warnings`. Beri peringatan ringan
pada 70%, tegas pada 90%, dan serius jika 100% atau lebih. Jangan menghakimi.

## Tagihan Belum Dibayar

Mencatat tagihan tidak langsung membuat transaksi pengeluaran:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh bill-add \
  --name "Internet Juli" --amount 275000 \
  --due-date 2026-07-15 --category Tagihan --wallet BCA
```

Ketika benar-benar dibayar:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligation-pay \
  --id ID --amount 275000 --wallet BCA
```

Pembayaran parsial didukung. Tampilkan sisa dan status setelah pembayaran.

## Utang dan Piutang

`payable` berarti pengguna berutang. `receivable` berarti orang lain berutang
kepada pengguna.

Utang tanpa pencatatan dana masuk:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh debt-add \
  --direction payable --name "Utang ke Umar" \
  --counterparty Umar --amount 500000 --due-date 2026-08-01
```

Jika uang pinjaman benar-benar masuk ke dompet yang dilacak, tambahkan
`--cash-wallet BCA`. Untuk piutang, `--cash-wallet Cash` berarti uang keluar dari
Cash saat dipinjamkan.

Pembayaran utang atau penagihan piutang memakai command yang sama:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligation-pay \
  --id ID --amount 100000 --wallet BCA
```

Lihat daftar:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligations
```

## Tagihan Berulang

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh recurring-add \
  --name "Netflix" --amount 65000 --category Langganan \
  --next-due-date 2026-08-07 --frequency monthly --wallet GoPay
```

`recurring-run` hanya membuat tagihan belum dibayar. Ia tidak menganggap tagihan
sudah dibayar.

## Target Tabungan

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh goal-add \
  --name "Laptop" --target 10000000 --target-date 2027-01-01
${HERMES_SKILL_DIR}/scripts/finance.sh goal-contribute \
  --goal "Laptop" --amount 200000 --wallet BCA
```

Selalu jelaskan bahwa kontribusi adalah alokasi virtual. Bila pengguna benar-benar
memindahkan uang ke rekening khusus, catat transfer terpisah.

## Laporan dan Pencarian

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh report --period week
${HERMES_SKILL_DIR}/scripts/finance.sh report --period month
${HERMES_SKILL_DIR}/scripts/finance.sh safe-to-spend
${HERMES_SKILL_DIR}/scripts/finance.sh search \
  --query kopi --from 2026-07-01 --to 2026-07-31 --wallet GoPay
```

Laporan harus memprioritaskan total pengeluaran, pemasukan, arus kas operasional,
perbandingan periode sebelumnya, perubahan kategori, budget, tagihan/utang, dan
rincian dompet. `safe-to-spend` selalu disebut sebagai perkiraan.

## Import CSV

Import wajib melalui preview:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-preview \
  --file /absolute/path/mutasi.csv --wallet BCA --source "bca-juli"
```

Tampilkan ringkasan ready, unresolved, duplicate, dan error. Jangan commit jika
masih ada kategori yang belum jelas. Perbaiki baris:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-row-set \
  --row-id ID --type expense --category "Lainnya"
```

Gunakan `Lainnya` hanya setelah pengguna menyetujuinya. Commit baru dilakukan
setelah konfirmasi:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-commit --batch-id ID
```

## Struk dari Telegram

Jika Telegram menyediakan path file attachment, lakukan preview lokal:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh receipt-scan \
  --file /absolute/path/receipt.jpg --wallet GoPay --ocr
```

OCR tidak boleh langsung disimpan sebagai transaksi. Tampilkan merchant,
nominal, tanggal, kategori, dan dompet yang terbaca, lalu minta pengguna
memeriksa. Setelah disetujui:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh receipt-confirm \
  --id ID --wallet GoPay --category Makan \
  --description "Belanja dari struk" --amount 74500 --date 2026-07-14
```

Jika OCR tidak tersedia atau hasilnya buram, minta nominal/data manual. Jangan
pura-pura bisa membaca gambar.

## Koreksi

Lihat transaksi lalu batalkan berdasarkan ID:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh list --limit 20
${HERMES_SKILL_DIR}/scripts/finance.sh void \
  --id ID --reason "Nominal salah; diganti transaksi baru"
```

Jangan mengedit histori secara langsung. Setelah void, buat transaksi pengganti.

## Mode Serius

Hentikan candaan bila hasil `alerts` atau `health` menunjukkan:

- database tidak sehat;
- saldo negatif yang tidak diharapkan;
- tagihan/utang lewat jatuh tempo bernilai besar;
- backup gagal atau terlalu lama;
- import massal bermasalah;
- potensi kehilangan atau kerusakan data.

Pada kondisi serius, sebutkan apa yang gagal, dampaknya, dan langkah konkret
berikutnya. Jangan menutupi masalah dengan personality.

## Verifikasi

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh health
${HERMES_SKILL_DIR}/scripts/finance.sh wallets
${HERMES_SKILL_DIR}/scripts/finance.sh obligations
${HERMES_SKILL_DIR}/scripts/finance.sh backup
```

Restore hanya dilakukan atas permintaan eksplisit, setelah gateway dihentikan dan
pengguna menyebut arsip yang benar. Gunakan `restore --confirm RESTORE`; jangan
menjalankannya sebagai tindakan otomatis atau berdasarkan asumsi.

Jika sebuah command mengembalikan `"ok": false`, sampaikan kegagalannya dan
jangan mengklaim tindakan selesai.
