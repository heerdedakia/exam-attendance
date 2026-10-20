# Examination Attendance System — Complete Deployment Guide

This guide details how to deploy the **Barcode-Based Digital Examination Attendance System** for live faculty evaluations, mobile testing, and production college environments.

---

## ⚡ Important Note for Mobile Phone Camera Scanning

> Modern mobile browsers (iOS Safari, Android Chrome) **require HTTPS** to grant camera permissions for barcode scanning. 
> To test phone camera scanning without SSL warnings, use **Method 1 (Instant HTTPS Tunnel)** or **Method 2 (Cloud Deploy with Free SSL)**.

---

## Method 1: Instant Live HTTPS Tunnel (Recommended for Demo & Evaluators)

If your Flask server is already running on your laptop via `START_SYSTEM.bat`:

1. Keep `START_SYSTEM.bat` running in the background.
2. Double-click **`START_PUBLIC_HTTPS_TUNNEL.bat`** (or open a terminal and run `npx localtunnel --port 5000`).
3. It will display a public HTTPS address:
   ```text
   your url is: https://exam-attendance-demo.loca.lt
   ```
4. **Share this link with your evaluators or open it on your phone!**
   - Works on any mobile device (even on cellular data).
   - Camera barcode scanner activates immediately with full HTTPS permission.

---

## Method 2: Free Cloud Deployment on Render.com (Permanent 24/7 Web App)

Render provides free hosting with automatic HTTPS SSL certificates.

### Step 1: Upload Project to GitHub
1. Create a free account at [GitHub.com](https://github.com) and create a new repository (e.g., `exam-attendance-system`).
2. In your project folder, open terminal and run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of examination attendance system"
   git branch -M main
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/exam-attendance-system.git
   git push -u origin main
   ```

### Step 2: Deploy on Render
1. Go to [Render.com](https://render.com) and sign in with GitHub.
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select your repository.
4. Set the following configuration:
   * **Name**: `college-exam-attendance` (or your choice)
   * **Environment**: `Python 3`
   * **Region**: Nearest to you (e.g., Singapore or Frankfurt)
   * **Branch**: `main`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `gunicorn app:app`
   * **Plan**: `Free`
5. Click **Deploy Web Service**.
6. Within 2 minutes, Render will assign a public HTTPS link:
   ```text
   https://college-exam-attendance.onrender.com
   ```

---

## Method 3: Deploy on PythonAnywhere.com (Best for SQLite & Flask)

PythonAnywhere is specifically built for Python and provides free persistent storage:

1. Sign up for a free account at [PythonAnywhere.com](https://www.pythonanywhere.com).
2. Go to the **Web** tab and click **Add a new web app**.
3. Select **Flask** and **Python 3.10 / 3.11**.
4. Open the **Bash Console** and clone your repository or upload the project ZIP:
   ```bash
   git clone https://github.com/YOUR_USERNAME/exam-attendance-system.git mysite
   cd mysite
   pip install -r requirements.txt
   ```
5. In the Web tab:
   * Set **Source code**: `/home/yourusername/mysite`
   * Set **Working directory**: `/home/yourusername/mysite`
   * Edit WSGI file:
     ```python
     import sys
     path = '/home/yourusername/mysite'
     if path not in sys.path:
         sys.path.append(path)
     from app import app as application
     ```
6. Click **Reload yourusername.pythonanywhere.com** and your portal is live!

---

## Method 4: Docker Container Deployment (College Campus Server)

For institutional deployment on college servers or VPS (AWS, Azure, DigitalOcean):

### Build and Run:
```bash
# 1. Build the Docker image
docker build -t exam-attendance-portal .

# 2. Run the container
docker run -d -p 5000:5000 --name exam_attendance_app --restart unless-stopped exam-attendance-portal
```

### Access:
* Open `http://<SERVER_IP>:5000` or configure Nginx with Certbot for SSL.

---

## Deployment Artifacts Provided in Repository:
* [`Dockerfile`](file:///c:/Users/User/OneDrive/Desktop/hallticket/Dockerfile) — Production multi-threaded Gunicorn image
* [`Procfile`](file:///c:/Users/User/OneDrive/Desktop/hallticket/Procfile) — Standard cloud process runner
* [`render.yaml`](file:///c:/Users/User/OneDrive/Desktop/hallticket/render.yaml) — 1-click Render blueprint specification
* [`requirements.txt`](file:///c:/Users/User/OneDrive/Desktop/hallticket/requirements.txt) — Includes Flask, Werkzeug, OpenPyXL, and Gunicorn
* [`START_PUBLIC_HTTPS_TUNNEL.bat`](file:///c:/Users/User/OneDrive/Desktop/hallticket/START_PUBLIC_HTTPS_TUNNEL.bat) — Instant HTTPS link generator for phone demo
