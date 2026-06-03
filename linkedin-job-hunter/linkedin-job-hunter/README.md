# LinkedIn Job Hunter 🔍

A self-hosted tool to search LinkedIn public job posts by keywords, location, and experience level.
Combines **LinkedIn's public guest API** + **Google site:search** for maximum results.

---

## 🚀 Quick Start (VPS)

### 1. Copy files to your VPS
```bash
scp -r linkedin-job-hunter/ user@your-vps-ip:~/
```

### 2. SSH into your VPS
```bash
ssh user@your-vps-ip
cd linkedin-job-hunter
```

### 3. Build and run
```bash
docker compose up -d --build
```

### 4. Open in your browser
```
http://your-vps-ip:8000
```

---

## 🛠 Usage

1. Type keywords: `DevOps Engineer, Cloud, Kubernetes`
2. Select location: Tunisia / Tunis / Remote / Worldwide
3. Select experience level: Junior / Mid / Senior
4. Click **Search** — results come from both LinkedIn and Google
5. Click any result to open the original LinkedIn post

---

## ⚙️ Configuration

### Change port
Edit `docker-compose.yml`:
```yaml
ports:
  - "80:8000"   # serve on port 80
```

### Run behind Nginx (recommended for production)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📦 Project Structure

```
linkedin-job-hunter/
├── backend/
│   ├── main.py           # FastAPI app — search logic
│   └── requirements.txt
├── frontend/
│   └── index.html        # Full UI (single file)
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🔍 How It Works

| Source | Method | Notes |
|--------|--------|-------|
| **LinkedIn** | Public guest jobs API (`/jobs-guest/jobs/api/...`) | No login needed, returns structured cards |
| **Google** | `site:linkedin.com/jobs/view {keywords} {location}` | Catches posts LinkedIn guest API misses |

Results are deduplicated and merged automatically.

---

## ⚠️ Notes

- This uses LinkedIn's **public, unauthenticated** jobs endpoint — no login or scraping required.
- Google search may occasionally return fewer results if rate-limited. Adding a delay or rotating User-Agents can help.
- For best results, be specific: `DevOps Engineer Tunisia` returns better results than just `DevOps`.

---

## 🔄 Update

```bash
git pull   # if using git
docker compose up -d --build
```

## 🛑 Stop

```bash
docker compose down
```
