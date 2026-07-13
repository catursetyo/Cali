# Cali Finance for Hermes Agent

Cali Finance v2 adalah personal finance ledger lokal untuk Hermes Agent. Model
AI memahami bahasa natural dan memilih command, sedangkan SQLite dan Python
menangani validasi, saldo, laporan, duplikat, serta histori.

## Fitur

- Pemasukan, pengeluaran, dan transfer multi-dompet.
- Kategori otomatis dengan validasi.
- Deteksi transaksi duplikat dan override setelah konfirmasi.
- Rekonsiliasi saldo dengan audit trail penyesuaian.
- Budget mingguan/bulanan dan peringatan 70/90/100%.
- Tagihan belum dibayar dan pembayaran parsial.
- Utang pengguna (`payable`) dan piutang (`receivable`).
- Tagihan berulang yang menghasilkan kewajiban, bukan transaksi fiktif.
- Laporan mingguan/bulanan dan perbandingan periode sebelumnya.
- Estimasi aman dibelanjakan.
- Target tabungan virtual.
- Pencarian transaksi dengan filter tervalidasi.
- Import CSV melalui preview, review, dan commit.
- Preview struk dengan OCR Tesseract opsional.
- Dashboard HTML statis.
- Backup lokal dan backup offsite terenkripsi melalui `age` + `rclone`.
- Alert proaktif untuk budget, jatuh tempo, saldo negatif, backup, dan kesehatan DB.

## Batasan yang Perlu Dipahami

Ini bukan sistem akuntansi bisnis, aplikasi pajak, atau penasihat investasi.
Sinkronisasi login bank langsung tidak disertakan; import bank menggunakan CSV.
OCR struk bersifat heuristik dan selalu memerlukan konfirmasi. Target tabungan
adalah bucket virtual, bukan perpindahan uang nyata.

## Instalasi atau Upgrade dari v1

Upload ZIP ke Azure VM, lalu:

```bash
unzip -o cali-finance-v2.zip
cd cali-finance-v2

# Hindari transaksi masuk saat migrasi database.
hermes gateway stop

chmod +x install.sh
./install.sh

hermes gateway start
hermes gateway status
```

Installer:

- mempertahankan `~/.hermes/finance/finance.db`;
- membuat backup pra-upgrade di `~/.hermes/finance/upgrades/`;
- memigrasikan tabel transaksi v1;
- tidak mengubah `SOUL.md` atau personality Cali.

Setelah itu kirim di Telegram:

```text
/reset
/personal-finance tampilkan saldo semua dompet
```

## Verifikasi

```bash
python3 ~/.hermes/finance/finance.py health
python3 ~/.hermes/finance/finance.py wallets
python3 ~/.hermes/finance/finance.py categories --type expense
python3 ~/.hermes/finance/finance.py backup
```

## Contoh Penggunaan

### Transaksi

```text
Catat makan ayam geprek 25 ribu dari GoPay.
Dapat uang freelance 750 ribu masuk BCA.
Top up GoPay 100 ribu dari BCA.
Cari semua pembelian kopi bulan ini.
```

### Budget

```text
Batasi pengeluaran makan bulan ini menjadi 800 ribu.
Bagaimana status semua budgetku?
```

### Tagihan, utang, dan piutang

```text
Catat tagihan internet 275 ribu jatuh tempo 15 Juli dari BCA.
Tagihan internet tadi sudah kubayar lunas dari BCA.
Aku berutang 500 ribu ke Umar, jatuh tempo 1 Agustus.
Zaki berutang 200 ribu kepadaku dan uangnya keluar dari Cash.
Aku baru menerima cicilan Zaki 50 ribu ke Cash.
```

### Rekonsiliasi

```text
Saldo GoPay asliku 142.500. Cocokkan dengan catatanmu.
```

Cali akan menampilkan selisih terlebih dahulu. Penyesuaian tidak dibuat tanpa
konfirmasi.

### Laporan

```text
Rangkum keuanganku minggu ini.
Bandingkan pengeluaran bulan ini dengan bulan sebelumnya.
Berapa uang yang aman kubelanjakan sampai akhir bulan?
```

## Command CLI Penting

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP add --type expense --amount 25000 --category Makan \
  --wallet Cash --description "Makan bakso"

$APP transfer --amount 100000 --from-wallet BCA --to-wallet GoPay

$APP reconcile --wallet GoPay --actual-balance 142500
$APP reconcile-adjust --check-id 1 --reason "Transaksi hilang" --confirm-adjust YES

$APP budget-set --category Makan --limit 800000 --period month
$APP budgets

$APP bill-add --name "Internet Juli" --amount 275000 \
  --due-date 2026-07-15 --category Tagihan --wallet BCA

$APP debt-add --direction payable --name "Utang Umar" \
  --amount 500000 --counterparty Umar --due-date 2026-08-01

$APP debt-add --direction receivable --name "Pinjaman Zaki" \
  --amount 200000 --counterparty Zaki --cash-wallet Cash

$APP obligations
$APP obligation-pay --id 1 --amount 100000 --wallet BCA

$APP recurring-add --name Netflix --amount 65000 \
  --category Langganan --next-due-date 2026-08-07 \
  --frequency monthly --wallet GoPay

$APP goal-add --name Laptop --target 10000000 --target-date 2027-01-01
$APP goal-contribute --goal Laptop --amount 200000 --wallet BCA

$APP report --period week
$APP report --period month
$APP safe-to-spend
```

## Konfigurasi Safe-to-Spend

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP config-set --key minimum_reserve --value 400000
$APP config-set --key monthly_savings_target --value 500000
$APP config
```

Perhitungan mengurangi saldo likuid dengan tagihan/utang yang jatuh tempo,
cadangan minimum, target tabungan tersisa, dan alokasi goal virtual. Hasilnya
selalu merupakan perkiraan.

## Import CSV

Format CSV bank berbeda-beda. Sistem mencoba mendeteksi header umum seperti
`tanggal`, `keterangan`, `debit`, `credit`, `amount`, dan `reference`.

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP import-preview \
  --file ~/mutasi-bca.csv \
  --wallet BCA \
  --source "bca-2026-07" \
  --date-format '%d/%m/%Y'
```

Lihat baris:

```bash
$APP import-rows --batch-id 1
```

Perbaiki kategori yang belum jelas:

```bash
$APP import-row-set --row-id 3 --type expense --category Belanja
```

Commit setelah review:

```bash
$APP import-commit --batch-id 1
```

External ID dan fingerprint dipakai untuk mencegah import ganda.

## OCR Struk

Pasang dependency opsional:

```bash
cd ~/cali-finance-v2
./install-ocr.sh
```

Preview:

```bash
APP="python3 ~/.hermes/finance/finance.py"
$APP receipt-scan --file ~/receipt.jpg --wallet GoPay --ocr
```

Konfirmasi hanya setelah nominal, tanggal, kategori, dan dompet diperiksa:

```bash
$APP receipt-confirm --id 1 --wallet GoPay --category Makan \
  --description "Belanja dari struk" --amount 74500 --date 2026-07-14
```

Hermes Telegram mendukung image/file attachment, tetapi skill tetap memerlukan
path file yang tersedia di server. Bila attachment tidak bisa diakses atau OCR
buram, masukkan data secara manual.

## Dashboard Lokal

```bash
python3 ~/.hermes/finance/finance.py dashboard-generate
cd ~/.hermes/finance/dashboard
python3 -m http.server 8765 --bind 127.0.0.1
```

Dari laptop, gunakan SSH tunnel:

```bash
ssh -L 8765:127.0.0.1:8765 -i ~/Downloads/azure-key.pem azureuser@PUBLIC_IP
```

Lalu buka `http://127.0.0.1:8765`. Jangan membuka port 8765 ke internet publik.

## Cron Hermes

Script-only cron tidak memakai token model. Script wajib berada di
`~/.hermes/scripts/`, dan installer sudah menyalinnya ke sana.

### Alert harian pukul 08.00

```bash
hermes cron create "0 8 * * *" \
  --no-agent \
  --script finance-daily-alerts.sh \
  --deliver telegram \
  --name "Cali finance alerts"
```

### Laporan Minggu pukul 20.00

```bash
hermes cron create "0 20 * * 0" \
  --no-agent \
  --script finance-weekly-report.sh \
  --deliver telegram \
  --name "Laporan keuangan mingguan"
```

### Laporan bulan sebelumnya pada tanggal 1 pukul 08.10

```bash
hermes cron create "10 8 1 * *" \
  --no-agent \
  --script finance-monthly-report.sh \
  --deliver telegram \
  --name "Laporan keuangan bulanan"
```

### Backup lokal setiap malam

```bash
hermes cron create "30 2 * * *" \
  --no-agent \
  --script finance-backup.sh \
  --deliver local \
  --name "Backup database keuangan"
```

### Refresh dashboard

```bash
hermes cron create "15 7 * * *" \
  --no-agent \
  --script finance-dashboard-refresh.sh \
  --deliver local \
  --name "Refresh dashboard keuangan"
```

Pastikan timezone VM:

```bash
sudo timedatectl set-timezone Asia/Jakarta
```

## Backup Offsite

Setiap backup lokal berupa arsip `.tar.gz` yang memuat snapshot SQLite dan file
struk. Dashboard tidak disimpan karena dapat dibuat ulang. Backup di VM yang sama
belum cukup. Dukungan offsite memakai `rclone` dan, secara default, mewajibkan
enkripsi `age`.

```bash
sudo apt install -y rclone age
rclone config
```

Atur remote, idealnya `crypt` di atas Azure Blob atau storage lain:

```bash
cat >> ~/.hermes/.env <<'EOF'
FINANCE_RCLONE_REMOTE=mycrypt:cali-finance
FINANCE_BACKUP_AGE_RECIPIENT=age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
```

Lalu tes:

```bash
set -a
source ~/.hermes/.env
set +a
python3 ~/.hermes/finance/finance.py backup --offsite
```

Jangan commit `.env`, SAS token, atau kunci privat ke Git.

## Menjalankan Test

Dari folder hasil ekstrak:

```bash
python3 tests/smoke_test.py
python3 tests/migration_test.py
python3 tests/restore_test.py
```

## File Penting

```text
~/.hermes/finance/finance.py
~/.hermes/finance/cali_finance/
~/.hermes/finance/finance.db
~/.hermes/finance/backups/
~/.hermes/finance/receipts/
~/.hermes/finance/dashboard/index.html
~/.hermes/skills/productivity/personal-finance/SKILL.md
~/.hermes/scripts/finance-*.sh
```

## Restore Backup

Restore bersifat destruktif. Hentikan gateway agar tidak ada transaksi yang masuk:

```bash
hermes gateway stop
python3 ~/.hermes/finance/finance.py restore \
  --archive ~/.hermes/finance/backups/cali-finance-YYYYMMDD-HHMMSS.tar.gz \
  --confirm RESTORE
hermes gateway start
```

Command restore membuat safety backup dari database saat ini, memeriksa integritas
database dalam arsip, lalu memulihkan database dan file struk.
