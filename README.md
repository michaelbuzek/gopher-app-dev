# 🚀 Gopher Minigolf - Render.com Deployment Guide

## 📋 Requirements.txt

```txt
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Werkzeug==2.3.7
gunicorn==21.2.0
psycopg2-binary==2.9.7
python-dotenv==1.0.0
```

## 🗂️ Datei-Struktur

```
gopher-app/
├── app.py                 # Haupt Flask App
├── models.py              # SQLAlchemy Models
├── migrate.py             # Migration Script
├── requirements.txt       # Python Dependencies
├── templates/
│   ├── index.html
│   ├── history.html
│   ├── score_detail.html
│   └── results.html
└── static/
    ├── gopher_main.png
    └── track-icons/
        └── *.png
```

## 🔧 Render.com Setup

### 1. **Web Service erstellen:**

1. Gehe zu [render.com](https://render.com) und logge dich ein
2. Klicke **"New +"** → **"Web Service"**
3. Verbinde dein GitHub Repository
4. Wähle `gopher-app` Repository

### 2. **Service Configuration:**

```yaml
Name: gopher-minigolf
Environment: Python 3
Region: Frankfurt (EU Central)
Branch: main
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
```

### 3. **Environment Variables:**

```bash
# REQUIRED: PostgreSQL Connection
DATABASE_URL=<wird automatisch gesetzt durch PostgreSQL Add-on>

# OPTIONAL: App Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=production
```

### 4. **PostgreSQL Database hinzufügen:**

1. Klicke **"New +"** → **"PostgreSQL"**
2. Wähle **Free Tier** (für Development)
3. Name: `gopher-minigolf-db`
4. Region: Frankfurt (EU Central)

### 5. **Database mit Web Service verbinden:**

1. Gehe zu deinem Web Service
2. **Environment** Tab → **Add Environment Variable**
3. Key: `DATABASE_URL`
4. Value: Wähle aus der Dropdown deine PostgreSQL Database

## 🔄 Deployment Process

### **Automatische Migration:**

Die App führt automatisch die Datenbank-Migration beim ersten Start aus:

```python
# In app.py - läuft automatisch
@app.before_first_request
def setup_database():
    init_database()  # Erstellt Tables + Default Data
```

### **Manuelle Migration (Falls nötig):**

Falls du die Migration manuell ausführen musst:

```bash
# In Render Shell
python migrate.py
```

## ✅ Deployment Checklist

- [ ] **Repository** auf GitHub gepusht
- [ ] **PostgreSQL Database** erstellt  
- [ ] **Web Service** konfiguriert
- [ ] **DATABASE_URL** Environment Variable gesetzt
- [ ] **Build** erfolgreich
- [ ] **Migration** erfolgreich
- [ ] **App** läuft auf `https://gopher-minigolf.onrender.com`

## 🔍 Troubleshooting

### **"Tables Missing" Error:**

```bash
# Check database status
curl https://gopher-minigolf.onrender.com/api/status

# Expected response:
{
  "status": "healthy",
  "places": 4,
  "track_types": 8,
  "games": 0,
  "players": 0,
  "scores": 0
}
```

### **Database Connection Error:**

1. Prüfe `DATABASE_URL` Environment Variable
2. Stelle sicher dass PostgreSQL Service läuft
3. Prüfe Region-Kompatibilität (beide EU Central)

### **Build Failures:**

1. Prüfe `requirements.txt` Syntax
2. Stelle sicher dass alle Dependencies aktuell sind
3. Check Python Version (3.8+ empfohlen)

### **Migration Issues:**

Manueller Reset falls nötig:

```sql
-- In PostgreSQL Dashboard
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

Dann App neu deployen.

## 🎯 Production Optimizations

### **Performance Settings:**

```python
# In models.py - bereits optimiert
'SQLALCHEMY_ENGINE_OPTIONS': {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 20,
    'max_overflow': 0,
}
```

### **Security Headers:**

```python
# Zusätzlich in app.py
@app.after_request
def after_request(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response
```

### **Monitoring:**

```bash
# Check app health
curl https://gopher-minigolf.onrender.com/api/status

# Check logs in Render Dashboard
Logs → View recent activity
```

## 🔄 Updates & Maintenance

### **Code Updates:**

```bash
git add .
git commit -m "Update: feature description"
git push origin main
# Render auto-deploys from main branch
```

### **Database Backup:**

```bash
# In Render PostgreSQL Dashboard
# Download backup manually or setup automated backups
```

### **Scaling:**

- **Free Tier:** Sleeps after 15min inactivity
- **Paid Tier:** Always-on, faster performance
- **Database:** Free 1GB → Paid plans für mehr Storage

## 🎉 Success!

Nach erfolgreichem Deployment ist deine Gopher Minigolf App verfügbar unter:

**🔗 https://gopher-minigolf.onrender.com**

**Features:**
✅ Vollständige PostgreSQL Integration  
✅ Automatische Migrations  
✅ Mobile-optimiert  
✅ Track Icons Support  
✅ Spiel History  
✅ Real-time Score Updates  

**Ready to play! 🏌️⛳**