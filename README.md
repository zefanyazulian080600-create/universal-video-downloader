# LinkGrabber Bot — Universal Telegram Video Downloader

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://python.org)
[![Framework](https://img.shields.io/badge/aiogram-3.x-blueviolet.svg)](https://docs.aiogram.dev/)
[![Engine](https://img.shields.io/badge/yt--dlp-latest-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![Media Processing](https://img.shields.io/badge/FFmpeg-7.x-green.svg)](https://ffmpeg.org)
[![Database](https://img.shields.io/badge/SQLAlchemy-2.x%20Async-brightgreen.svg)](https://www.sqlalchemy.org)
[![Tests](https://img.shields.io/badge/Tests-27%20Passed-success.svg)](./tests)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**LinkGrabber Bot** adalah aplikasi Telegram Bot asynchronous tingkat produksi (*production-grade*) yang dirancang untuk mengunduh video dan audio dari berbagai platform media sosial dan situs web populer secara aman, cepat, dan terisolasi.

Aplikasi ini dibangun menggunakan arsitektur non-blocking berbasis antrean (*bounded worker pool*), dilengkapi sistem perlindungan SSRF, sanitasi nama file ketat, penanganan error berbahasa Indonesia yang ramah, serta dukungan penuh untuk deployment lokal (Windows / Linux) maupun Docker Compose.

---

## Daftar Isi
1. [Fitur Utama](#fitur-utama)
2. [Platform yang Didukung & Batasan](#platform-yang-didukung--batasan)
3. [Arsitektur Sistem](#arsitektur-sistem)
4. [Persyaratan Sistem](#persyaratan-sistem)
5. [Panduan Instalasi & Menjalankan](#panduan-instalasi--menjalankan)
   - [A. Windows (Lokal)](#a-instalasi-di-windows-lokal)
   - [B. Linux / Server VPS](#b-instalasi-di-linux-ubuntu--debian)
   - [C. Docker & Docker Compose](#c-instalasi-menggunakan-docker-compose)
6. [Konfigurasi BotFather & BOT_TOKEN](#panduan-membuat-bot-melalui-botfather)
7. [Panduan Memasang FFmpeg](#panduan-memasang-ffmpeg)
8. [Daftar Perintah (Commands) & Cara Penggunaan](#daftar-perintah-commands)
9. [Penanganan File Besar & Batas Upload Telegram](#penanganan-file-besar--batas-upload-telegram)
10. [Logging & Monitoring](#logging-dan-monitoring)
11. [Menjalankan Pengujian Otomatis](#menjalankan-pengujian-otomatis)
12. [Pemecahan Masalah (Troubleshooting)](#pemecahan-masalah-troubleshooting)
13. [Praktik Keamanan](#praktik-keamanan)
14. [Etika, Hak Cipta & Ketentuan Layanan](#etika-hak-cipta--ketentuan-layanan)

---

## Fitur Utama

- ⚡️ **Asynchronous & Non-Blocking**: Menggunakan `aiogram 3.x` dan `asyncio` agar bot tetap responsif memproses pesan ratusan pengguna tanpa terhambat oleh proses download.
- 🎯 **Inspeksi Metadata Lengkap**: Menampilkan judul video, durasi, pembuat konten/channel, estimasi ukuran file, dan pilihan resolusi dinamis sebelum mengunduh.
- 🎬 **Dukungan Format Dinamis**: Pengguna dapat memilih kualitas terbaik (*Best*), 1080p, 720p, 480p, 360p, atau versi Audio Saja (*MP3/M4A*).
- 📊 **Live Progress Bar Throttled**: Pembaruan status persentase unduhan dan kecepatan secara berkala dengan interval pelindung anti-*flood limit* Telegram.
- 🛡 **Keamanan Tingkat Tinggi (SSRF & Injection Defense)**:
  - Validasi ketat skema URL (`http://` dan `https://` saja).
  - Penolakan akses ke `localhost`, private network (RFC 1918), link-local, dan endpoint metadata cloud (`169.254.169.254`).
  - Resolusi DNS untuk mencegah *DNS rebinding attack*.
  - Eksekusi subprocess tanpa shell (`shell=False`) guna mencegah shell command injection.
  - Direktori kerja sementara terisolasi per pekerjaan unduhan (`downloads/<job_id>/`).
- ⏹ **Pembatalan Aman (/cancel)**: Pengguna dapat membatalkan proses unduhannya tanpa memengaruhi atau membatalkan pekerjaan pengguna lain.
- 💾 **Database SQLAlchemy 2.x Async**: Menggunakan SQLite async via `aiosqlite` secara default dan siap dimigrasikan ke PostgreSQL (`asyncpg`) hanya dengan mengubah konfigurasi `DATABASE_URL`.
- 🗜 **Kompresi Opsional**: Mendukung kompresi video menggunakan FFmpeg H.264 jika file melebihi batas pengiriman bot.
- 🧹 **Pembersihan Otomatis**: Menghapus file sementara segera setelah file terkirim atau gagal, serta membersihkan file sisa (*orphaned files*) saat bot dinyalakan (*startup cleanup*).

---

## Platform yang Didukung & Batasan

### Platform Prioritas Utama:
- **YouTube**: Video standar publik, YouTube Shorts, dan audio stream.
- **TikTok**: Video publik tanpa watermark (selama extractor didukung).
- **Instagram**: Reels, postingan video publik, dan klip video.
- **Facebook**: Video publik dan link reels publik.
- **X / Twitter**: Video pada tweet/post publik.
- **Vimeo**: Video publik.

### Platform Tambahan:
- Reddit, Pinterest, Threads, Dailymotion, Twitch Clips, SoundCloud.
- Tautan langsung ke file media seperti `.mp4`, `.webm`, `.mkv`, `.mp3`, `.m4a`.
- Semua platform lain yang didukung secara teknis oleh `yt-dlp`.

### Batasan Penting:
> [!IMPORTANT]
> - Konten privat, konten berbayar (*paywall*), akun yang terkunci, atau konten berpelindung DRM **TIDAK DIDUKUNG**.
> - Bot ini **TIDAK** meminta atau menyimpan password, sesi login, atau cookie pengguna.

---

## Arsitektur Sistem

```
                               ┌────────────────────────────────┐
                               │     Telegram Cloud Server      │
                               └───────────────┬────────────────┘
                                               │ (Long Polling / HTTPS)
                                               ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               LINKGRABBER BOT APPLICATION                              │
│                                                                                        │
│  ┌──────────────────────┐      ┌─────────────────────────┐      ┌──────────────────┐  │
│  │ Throttling Middleware│ ───► │  UserTracker Middleware │ ───► │ Dispatcher /     │  │
│  │ (Sliding Window Rate)│      │  (Ensure User Profile)  │      │ Handlers Router  │  │
│  └──────────────────────┘      └─────────────────────────┘      └────────┬─────────┘  │
│                                                                          │            │
│                 ┌────────────────────────────────────────────────────────┘            │
│                 ▼                                                                     │
│  ┌───────────────────────────────┐               ┌─────────────────────────────────┐  │
│  │ URL Validator & SSRF Guard    │               │ Metadata Extractor              │  │
│  │ - Scheme & Host Inspection    │ ────────────► │ - yt-dlp Fast Probe             │  │
│  │ - DNS Rebinding & IP Defense  │               │ - Resolution & Format Mapper    │  │
│  └───────────────────────────────┘               └────────────────┬────────────────┘  │
│                                                                   │                   │
│                                                                   ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Bounded Job Queue & Concurrency Controller (asyncio.Semaphore)                  │  │
│  │                                                                                 │  │
│  │  ┌──────────────────┐   ┌───────────────────────────┐   ┌───────────────────┐   │  │
│  │  │ Downloader       │   │ FFmpeg Stream Merge &     │   │ Telegram Delivery │   │  │
│  │  │ Worker Pool      │──►│ Probing Verification      │──►│ Service           │   │  │
│  │  │ (Isolated Dirs)  │   │ (ffprobe / libx264)       │   │ (Video/Audio API) │   │  │
│  │  └──────────────────┘   └───────────────────────────┘   └───────────────────┘   │  │
│  └────────────────────────────────────────┬────────────────────────────────────────┘  │
│                                           │                                           │
│                                           ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Persistence & Monitoring Layer                                                  │  │
│  │ - SQLite (aiosqlite) / PostgreSQL                                               │  │
│  │ - Safe Cleanup Routines (Bounded Temp Dir)                                      │  │
│  │ - Structured Rotating File & Console Logger                                     │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Persyaratan Sistem

- **Python**: Versi `3.12+` (atau Python 3.11/3.14).
- **FFmpeg & ffprobe**: Versi 5.x, 6.x, atau 7.x (wajib ada di `PATH` sistem untuk penggabungan video-audio dan ekstrak thumbnail).
- **Koneksi Internet**: Akses stabil ke Telegram Bot API (`api.telegram.org`) dan domain platform media.
- **Ruang Disk Bebas**: Minimal 1 GB untuk direktori penampungan sementara unduhan.

---

## Panduan Instalasi & Menjalankan

### A. Instalasi di Windows (Lokal)

#### 1. Buka PowerShell dan Masuk ke Direktori Proyek
```powershell
cd C:\Users\ASUS\.gemini\antigravity\scratch\universal-video-downloader
```

#### 2. Buat dan Aktifkan Virtual Environment (Python 3.12)
Jika menggunakan `uv`:
```powershell
uv venv --python 3.12
.\.venv\Scripts\activate
```
Atau menggunakan Python standar:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

#### 3. Pasang Seluruh Dependensi
```powershell
pip install -r requirements.txt
```

#### 4. Konfigurasi File Lingkungan (.env)
Salin contoh konfigurasi ke `.env`:
```powershell
Copy-Item .env.example .env
```
Buka file `.env` dengan Notepad atau editor kode, lalu isi:
```env
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
BOT_OWNER_ID=123456789
```

#### 5. Pastikan FFmpeg Tersedia
Uji di PowerShell:
```powershell
ffmpeg -version
```
Jika belum terpasang, lihat bagian [Panduan Memasang FFmpeg](#panduan-memasang-ffmpeg).

#### 6. Jalankan Bot
```powershell
python -m app.main
```
Bot akan menginisialisasi database, membersihkan temporary folder, dan mulai mendengarkan pesan masuk dari Telegram!

---

### B. Instalasi di Linux (Ubuntu / Debian)

#### 1. Pasang Dependensi Sistem
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ffmpeg curl git
```

#### 2. Clone atau Salin Proyek
```bash
git clone <URL_REPOSITORY_ANDA> /opt/universal-video-downloader
cd /opt/universal-video-downloader
```

#### 3. Buat Virtual Environment & Pasang Dependensi
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Buat File .env
```bash
cp .env.example .env
nano .env
```
Isi `BOT_TOKEN` dan parameter lain yang diperlukan.

#### 5. Jalankan Bot (atau gunakan Systemd)
```bash
python -m app.main
```

Untuk menjalankan di latar belakang menggunakan **Systemd**, buat service:
```bash
sudo nano /etc/systemd/system/linkgrabber.service
```
Isi file service:
```ini
[Unit]
Description=LinkGrabber Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/universal-video-downloader
ExecStart=/opt/universal-video-downloader/.venv/bin/python -m app.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Aktifkan service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable linkgrabber
sudo systemctl start linkgrabber
sudo systemctl status linkgrabber
```

---

### C. Instalasi Menggunakan Docker Compose

Metode ini paling direkomendasikan untuk deployment server produksi karena mengisolasi seluruh dependensi (termasuk FFmpeg dan user non-root) secara otomatis.

#### 1. Salin dan Sesuaikan `.env`
```bash
cp .env.example .env
nano .env
```

#### 2. Bangun dan Jalankan Kontainer
```bash
docker compose up -d --build
```

#### 3. Periksa Log Berjalan
```bash
docker compose logs -f linkgrabber-bot
```

#### 4. Hentikan Kontainer
```bash
docker compose down
```

---

### D. Deploy Otomatis di Cloud Menggunakan GitHub

Anda dapat mengaktifkan bot ini di cloud 24/7 langsung dari repository GitHub ini melalui beberapa platform cloud populer:

#### Opsi 1: Railway (Sangat Direkomendasikan & Paling Mudah)
1. Buka [Railway.app](https://railway.app) dan login dengan akun GitHub Anda.
2. Klik **"New Project"** -> **"Deploy from GitHub repo"**.
3. Pilih repository ini (`universal-video-downloader` atau `linkgrabber-bot`).
4. Buka tab **Variables** di dashboard Railway, lalu tambahkan environment variables:
   - `BOT_TOKEN`: Token bot Telegram Anda dari `@BotFather`
   - `BOT_OWNER_ID`: ID Telegram Anda
   - `MAX_UPLOAD_MB`: `50`
5. Railway akan mendeteksi `Dockerfile` secara otomatis, membangun kontainer, dan menjalankan bot 24 jam nonstop!

#### Opsi 2: Render (Menggunakan render.yaml)
1. Buka [Render.com](https://render.com) dan login dengan GitHub.
2. Klik **"New +"** -> **"Blueprint"**.
3. Hubungkan ke repository ini. Render akan membaca file `render.yaml` otomatis.
4. Masukkan variabel `BOT_TOKEN` di dashboard Render.
5. Klik **"Apply"** untuk memulai worker background.

#### Opsi 3: Koyeb
1. Buka [Koyeb.com](https://koyeb.com) dan login dengan GitHub.
2. Buat App baru -> Pilih **GitHub** sebagai sumber deployment.
3. Pilih repository ini, builder akan otomatis memilih **Dockerfile**.
4. Di bagian **Environment Variables**, masukkan `BOT_TOKEN` dan `BOT_OWNER_ID`.
5. Klik **"Deploy"**.

#### Opsi 4: VPS / Server Pribadi via Git
Di VPS Ubuntu/Debian Anda:
```bash
git clone https://github.com/zefanyazulian080600-create/universal-video-downloader.git
cd universal-video-downloader
cp .env.example .env
# Edit .env dan isi BOT_TOKEN Anda
docker compose up -d --build
```
Setiap kali Anda melakukan `git push` ke GitHub, cukup jalankan `git pull && docker compose up -d --build` di VPS Anda.

---

### E. GitHub Actions (CI/CD & Docker Registry)
Repository ini telah dilengkapi dengan dua workflow otomatis di `.github/workflows/`:
1. **CI Test Suite (`ci.yml`)**: Secara otomatis menjalankan unit test `pytest` (27 pengujian) di runner Ubuntu setiap kali ada `git push` atau *pull request*.
2. **Build & Publish Docker Image (`docker-build.yml`)**: Secara otomatis membangun image Docker dan menerbitkannya ke **GitHub Container Registry (GHCR)** di `ghcr.io/<username>/<repo>:latest`.

---

## Panduan Membuat Bot Melalui BotFather

1. Buka aplikasi Telegram dan cari **`@BotFather`** (pastikan bercentang biru).
2. Kirim perintah `/newbot`.
3. Masukkan nama tampilan bot Anda (contoh: `LinkGrabber Bot`).
4. Masukkan username bot (harus berakhiran `bot`, contoh: `linkgrabber_downloader_bot`).
5. BotFather akan memberikan **API Token** berupa kombinasi teks seperti:
   `7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`
6. Salin token tersebut dan tempel ke parameter `BOT_TOKEN` di file `.env`.
7. **JANGAN PERNAH** membagikan token ini kepada orang lain atau mengunggahnya ke GitHub!

---

## Panduan Memasang FFmpeg

### Di Windows:
1. Unduh build siap pakai dari situs resmi Gyan.dev: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
2. Ekstrak file zip ke folder tetap (misalnya `C:\ffmpeg`).
3. Tambahkan folder `C:\ffmpeg\bin` ke dalam **System Environment Variables -> Path**.
4. Buka PowerShell baru dan jalankan `ffmpeg -version` untuk memverifikasi.

### Di Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install -y ffmpeg
```

---

## Daftar Perintah (Commands)

| Perintah | Fungsi |
| :--- | :--- |
| `/start` | Memulai interaksi, menampilkan pesan sambutan, panduan singkat, dan menu utama. |
| `/help` | Menampilkan panduan lengkap, cara unduh, batasan platform, dan tips penggunaan. |
| `/platforms` | Menampilkan daftar lengkap platform media yang didukung oleh bot. |
| `/settings` | Membuka menu pengaturan interaktif (kualitas bawaan, format utama, kompresi). |
| `/quality` | Pintasan cepat untuk mengubah resolusi video default (Best, 1080p, 720p, 480p, Audio). |
| `/status` | Melihat daftar pekerjaan unduhan yang sedang berjalan atau mengantre milik Anda. |
| `/cancel` | Membatalkan seluruh proses unduhan aktif milik Anda dan membersihkan file sementara. |
| `/history` | Menampilkan riwayat 8 unduhan terakhir Anda secara pribadi (aman & terisolasi). |
| `/about` | Informasi teknis bot, arsitektur, versi dependensi, dan kontak pengembang. |
| `/admin` | *(Khusus Administrator)* Menampilkan metrik penggunaan disk, total job, uptime, dan statistik server. |

---

## Penanganan File Besar & Batas Upload Telegram

### Ketentuan Batas Upload:
- **Telegram Bot API Standar (Hosted)**: Memiliki batas pengiriman file maksimum **50 MB** untuk bot.
- **Telegram Bot API Server Lokal**: Jika Anda menjalankan self-hosted Local Telegram Bot API Server, batas upload dapat dinaikkan hingga **2000 MB (2 GB)**.

### Strategi LinkGrabber Bot:
1. Sebelum mengirimkan video, bot secara ketat mengukur ukuran file aktual hasil unduhan.
2. Jika ukuran file melebihi nilai `MAX_UPLOAD_MB`:
   - Jika `ENABLE_COMPRESSION=true`, bot akan mencoba melakukan transcoding otomatis via FFmpeg H.264 ke bitrate yang sesuai dengan batas ukuran.
   - Jika kompresi dinonaktifkan atau file tetap melebihi batas setelah dikompresi, bot akan membatalkan pengiriman dengan sopan dan menyarankan pengguna memilih resolusi lebih rendah (misal 480p atau versi audio).
3. Bot tidak pernah berpura-pura berhasil mengunggah jika pengiriman gagal.

---

## Logging dan Monitoring

Log dicatat secara terstruktur dengan format:
```
YYYY-MM-DD HH:MM:SS [LEVEL  ] [logger.name] Message
```

Fitur logging mencakup:
- **Redaksi Kredensial Otomatis**: Token bot, query params rahasia (`token=...`, `key=...`), dan data sensitif secara otomatis disensor menjadi `[REDACTED]`.
- **Rotasi File Terkendali**: Log disimpan di `logs/bot.log` dengan ukuran maksimum 10 MB per file dan retensi 5 file cadangan.
- **Pemeriksaan Admin**: Gunakan perintah `/admin` di Telegram untuk melihat performa real-time server (Uptime, RAM/Disk Usage, Active Workers).

---

## Menjalankan Pengujian Otomatis

Proyek ini dilengkapi dengan test suite lengkap berbasis `pytest` dan `pytest-asyncio` yang mencakup **27 skenario pengujian komprehensif** (termasuk SSRF, anti-injeksi, perutean antrean, isolasi data pengguna, dan pemulihan pasca restart).

Jalankan test suite menggunakan virtual environment:
```powershell
.\.venv\Scripts\pytest.exe -v
```

Hasil verifikasi:
```
collected 27 items

tests/test_cleanup.py::TestCleanupSafety::test_cleanup_cannot_escape_base_directory PASSED
tests/test_cleanup.py::TestCleanupSafety::test_startup_cleanup PASSED
tests/test_database.py::TestDatabase::test_user_and_job_crud PASSED
tests/test_database.py::TestDatabase::test_user_history_isolation PASSED
tests/test_database.py::TestDatabase::test_restart_recovery_resets_interrupted_jobs PASSED
tests/test_downloader.py::TestDownloader::test_extractor_timeout_handled PASSED
tests/test_downloader.py::TestDownloader::test_downloader_failure_handled PASSED
tests/test_downloader.py::TestDownloader::test_empty_output_file_rejected PASSED
tests/test_downloader.py::TestDownloader::test_file_too_large_handled PASSED
tests/test_downloader.py::TestFFmpeg::test_ffmpeg_not_found_raises_informative_error PASSED
tests/test_handlers.py::TestHandlersAndCallbacks::test_navigation_callbacks_answered PASSED
tests/test_handlers.py::TestHandlersAndCallbacks::test_telegram_upload_failure_handled PASSED
tests/test_middlewares.py::TestMiddlewares::test_throttling_middleware_rate_limiting PASSED
tests/test_queue.py::TestQueueAndManager::test_job_cancellation_terminates_process PASSED
tests/test_queue.py::TestProgressTracker::test_progress_tracker_raises_on_cancellation PASSED
tests/test_validator.py::TestURLValidation::test_youtube_url_recognized PASSED
tests/test_validator.py::TestURLValidation::test_tiktok_url_recognized PASSED
tests/test_validator.py::TestURLValidation::test_instagram_url_recognized PASSED
tests/test_validator.py::TestURLValidation::test_facebook_url_recognized PASSED
tests/test_validator.py::TestURLValidation::test_malformed_url_rejected PASSED
tests/test_validator.py::TestURLValidation::test_file_scheme_rejected PASSED
tests/test_validator.py::TestURLValidation::test_localhost_rejected PASSED
tests/test_validator.py::TestURLValidation::test_private_ip_rejected PASSED
tests/test_validator.py::TestURLValidation::test_private_ip_helper PASSED
tests/test_validator.py::TestURLValidation::test_special_characters_handling PASSED
tests/test_validator.py::TestURLValidation::test_unsupported_platform_detection PASSED
tests/test_validator.py::TestURLValidation::test_url_extraction_from_conversation PASSED

============================= 27 passed in 1.06s =============================
```

---

## Pemecahan Masalah (Troubleshooting)

### 1. `BOT_TOKEN is missing or not configured!`
- **Penyebab**: File `.env` belum dibuat atau variabel `BOT_TOKEN` masih berisi nilai default placeholder.
- **Solusi**: Pastikan file bernama `.env` (bukan `.env.example`) berada di direktori utama bot dan masukkan token asli dari BotFather.

### 2. FFmpeg Tidak Ditemukan (`FFmpegNotFoundError`)
- **Penyebab**: Eksekusi `ffmpeg` atau `ffprobe` tidak terdaftar pada PATH sistem.
- **Solusi**: Di Windows, tambahkan folder `bin` FFmpeg ke PATH dan restart terminal PowerShell. Di Linux, jalankan `sudo apt install ffmpeg`.

### 3. Ekstraksi atau Unduhan Mengalami Timeout
- **Penyebab**: Server platform (misalnya YouTube atau TikTok) lambat merespons atau membatasi permintaan IP server.
- **Solusi**: Coba naikkan batas `DOWNLOAD_TIMEOUT_SECONDS=900` dan `METADATA_TIMEOUT_SECONDS=45` di file `.env`. Pastikan paket `yt-dlp` selalu diperbarui ke versi terbaru (`pip install -U yt-dlp`).

### 4. Video Berukuran Lebih dari 50 MB Ditolak
- **Penyebab**: Batasan default Telegram Bot API adalah 50 MB per file.
- **Solusi**: Pilih opsi resolusi 480p/360p pada bot, pilih opsi "Audio Saja", atau aktifkan fitur kompresi `ENABLE_COMPRESSION=true`.

---

## Praktik Keamanan

1. **Prinsip Hak Akses Minimal (*Least Privilege*)**: Image Docker dikonfigurasi berjalan di bawah user non-root `appuser`.
2. **SSRF Defense-in-Depth**: Bot tidak hanya memeriksa nama domain, tetapi juga memverifikasi hasil IP DNS untuk memblokir alamat lokal dan link-local cloud.
3. **Pemberian Nama File Aman**: Fungsi `sanitize_filename` membersihkan seluruh karakter berbahaya, mencegah path traversal (`../`), serta menolak reserved name pada Windows.
4. **Isolasi Riwayat Pengguna**: Database query untuk history dan status selalu menyertakan `telegram_id` pengirim pesan, mencegah kebocoran data antarpengguna.

---

## Etika, Hak Cipta & Ketentuan Layanan

- Bot ini dibuat untuk keperluan pengarsipan pribadi (*personal backup*) dan penelitian teknis.
- Pengguna bertanggung jawab penuh atas setiap konten yang diunduh menggunakan bot ini.
- Jangan gunakan bot ini untuk mengunduh karya berhak cipta tanpa izin tertulis dari pemilik sah konten, atau melanggar ketentuan layanan platform terkait.
- Pengembang tidak bertanggung jawab atas segala bentuk penyalahgunaan bot oleh pihak ketiga.

---

**LinkGrabber Bot** — Dibuat dengan standar kualitas dan rekayasa perangkat lunak terbaik.
