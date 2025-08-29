# BUILDMODE-Server

This repository contains setup instructions for configuring the **BUILDMODE Server**, including database, services, watchdogs, and NGINX with HTTPS support.

---

## To-Do

- [ ] Setup digest sending system based on user's selected frequency
- [ ] Improve data extraction from posts to include account identifiers and filterable tags 
- [ ] Confirm visual color code extraction

## Setup

### 1. Update the Server

```bash
sudo apt update
sudo apt full-upgrade
```

---

### 2. Database (PostgreSQL + pgvector)

#### Install

```bash
sudo apt install -y postgresql
sudo apt install -y postgresql-17-pgvector
```

#### Configure

1. Log into Postgres:

   ```bash
   sudo -u postgres psql
   ```
2. Set a password:

   ```sql
   ALTER USER postgres WITH PASSWORD '<YOUR_NEW_PASSWORD>';
   ```

#### Create Database

```sql
CREATE DATABASE mia2;
\c mia2
CREATE EXTENSION vector;
\q
```

#### Useful Commands

* Open DB:

  ```bash
  psql -U <DB_USER> -d <DB_NAME>
  ```
* Drop a **table**:

  ```sql
  DROP TABLE <table_name>;
  ```
* Drop the **database**:

  ```bash
  sudo -u postgres dropdb <DB_NAME>
  ```
* Completely remove PostgreSQL:

  ```bash
  sudo apt remove --purge -y postgresql*
  sudo apt autoremove --purge -y
  ```

#### Indexing with IVFFlat

```sql
CREATE INDEX tags_vector_idx ON data
USING ivfflat (tags_vector vector_cosine_ops)
WITH (lists = 50);

CREATE INDEX swatch_vector_idx ON data
USING ivfflat (swatch_vector vector_l2_ops)
WITH (lists = 50);
```

* **Tuning `lists`:**

  * Small datasets (≤10K rows): 10–50
  * Medium datasets (10K–100K rows): 50–100

Update planner statistics:

```sql
ANALYZE data;
```

---

### 3. Services (Systemd)

#### Create Service

```bash
sudo nano /etc/systemd/system/forgor-api.service
```

#### Enable & Start

```bash
sudo systemctl daemon-reexec && sudo systemctl daemon-reload
sudo systemctl enable forgor-api.service
sudo systemctl start forgor-api.service
sudo systemctl restart forgor-api.service
```

#### Check Logs

```bash
sudo systemctl status forgor-api
journalctl -u forgor-api.service -f
```

---

### 4. Watchdog (Auto-Restart Flask)

#### Place Script

```bash
sudo mkdir -p /opt/flask_watchdog
sudo cp watch_flask_restart.py /opt/flask_watchdog/
sudo chmod +x /opt/flask_watchdog/watch_flask_restart.py
```

#### Create Service

```bash
sudo nano /etc/systemd/system/flask-watchdog.service
```

#### Enable & Start

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable flask-watchdog.service
sudo systemctl start flask-watchdog.service
```

#### Check Logs

```bash
sudo systemctl status flask-watchdog
tail -f /var/log/flask_watchdog.log
journalctl -u flask-watchdog.service
```

---

### 5. NGINX + HTTPS

#### Setup Domain

* Point your **domain A record** to the VPS IP.
* Wait \~15 minutes for DNS propagation.

#### Configure NGINX

```bash
sudo nano /etc/nginx/sites-available/<name>
```

* Use the template in `nginx.config`.

```bash
sudo ln -s /etc/nginx/sites-available/<name> /etc/nginx/sites-enabled/
sudo nginx -t        # Validate config
sudo systemctl start nginx
sudo systemctl status nginx
sudo systemctl reload nginx
```

#### Enable HTTPS (Certbot)

```bash
sudo certbot --nginx -d <domain>.xyz -d www.<domain>.xyz
```

Verify auto-renewal:

```bash
sudo certbot renew --dry-run
```

---

Got it 👍 — I’ll expand the **Logs & Checks** section so you have a quick reference for:

* **Postgres logs**
* **Systemd service logs**
* **Quick SQL connect + SELECT examples**

Here’s the improved bottom section of your README:

---

## Quick Commands

### PostgreSQL

* Check version:

  ```bash
  psql --version
  ```
* Status:

  ```bash
  sudo systemctl status postgresql
  ```
* Start & enable:

  ```bash
  sudo systemctl start postgresql
  sudo systemctl enable postgresql
  ```
* Show Postgres logs (last 50 lines, live):

  ```bash
  journalctl -u postgresql.service -n 50 -f
  ```
* Connect to DB:

  ```bash
  psql -U <DB_USER> -d <DB_NAME>
  ```
* List databases:

  ```sql
  \l
  ```
* List tables:

  ```sql
  \dt
  ```
* Inspect schema of a table:

  ```sql
  \d <table_name>
  ```
* Run quick query:

  ```sql
  SELECT * FROM <table_name> LIMIT 10;
  ```

---

### API / Flask Service

* Check status:

  ```bash
  sudo systemctl status forgor-api
  ```
* Show logs (last 100 lines, live):

  ```bash
  journalctl -u forgor-api.service -n 100 -f
  ```
* Restart service:

  ```bash
  sudo systemctl restart forgor-api.service
  ```

---

### Watchdog Service

* Status:

  ```bash
  sudo systemctl status flask-watchdog
  ```
* Logs:

  ```bash
  journalctl -u flask-watchdog.service -n 50 -f
  tail -f /var/log/flask_watchdog.log
  ```

---

### NGINX

* Status:

  ```bash
  sudo systemctl status nginx
  ```
* Reload config:

  ```bash
  sudo nginx -t && sudo systemctl reload nginx
  ```
* Logs:

  ```bash
  sudo tail -f /var/log/nginx/access.log
  sudo tail -f /var/log/nginx/error.log
  ```