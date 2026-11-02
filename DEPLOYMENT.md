# JobFlow AI — Deployment & Hosting Guide

JobFlow AI is a production-ready FastAPI application with an integrated static frontend. It can be deployed to any modern cloud platform in just a few minutes.

---

## Recommended Free & Easy Hosting Options

### Option 1: Render (Recommended — Free & 2-Minute Setup)
1. Push your project code to a **GitHub** or **GitLab** repository.
2. Sign up or log in at [Render.com](https://render.com).
3. Click **New +** $\rightarrow$ **Web Service**.
4. Connect your GitHub repository.
5. Render will automatically detect `render.yaml` or configure:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. Click **Create Web Service**. Your live public URL (e.g. `https://jobflow-ai.onrender.com`) will be generated.

---

### Option 2: Railway (Zero-Config & Docker Native)
1. Push your repository to **GitHub**.
2. Sign in at [Railway.app](https://railway.app).
3. Click **New Project** $\rightarrow$ **Deploy from GitHub repo**.
4. Select your repository. Railway automatically reads `railway.json` and `Dockerfile`.
5. Under service settings, click **Generate Domain** to get your public `https://...up.railway.app` URL.

---

### Option 3: Run with Docker Anywhere (VPS, AWS, DigitalOcean, Local)
To build and run the container locally or on any server with Docker installed:

```bash
# 1. Build the Docker image
docker build -t jobflow-ai .

# 2. Run the container with persistent storage
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/tokens:/app/tokens \
  --name jobflow-ai-app \
  jobflow-ai
```

Access the app at `http://your-server-ip:8000`.

---

## Environment Variables (Optional)

| Variable | Description | Default |
|---|---|---|
| `PORT` | Web server listening port (automatically set by Render/Railway) | `8000` |
| `HOST` | Bind IP | `0.0.0.0` |
| `GEMINI_API_KEY` | Optional Google Gemini API key for AI drafting | None (uses heuristic engine) |
