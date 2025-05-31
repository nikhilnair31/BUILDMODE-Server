# BUILDMODE-Server

## Initial
- Run these at first
    - `sudo apt update`
    - `sudo apt full-upgrade`

## DB

### Install
- Run this to install postgres package `sudo apt install -y postgresql`
- Run this to install pgvector extension `sudo apt install -y postgresql-17-pgvector`

### Check
- To check for version of postgres `psql --version`
- To check for database status run this command `sudo systemctl status postgresql`
- To start run this `sudo systemctl start postgresql` and `sudo systemctl enable postgresql`

### Credentials
- Log in with `sudo -u postgres psql`
- Set password with `ALTER USER postgres WITH PASSWORD '<YOUR_NEW_PASSWORD>';`

### Create
- Run the following commands to create a db
    ```sql
    CREATE DATABASE mia2;
    \c mia2
    CREATE EXTENSION vector;
    \q
    ```

### Backup

- Create script `sudo nano /opt/pg_backup.sh`

### Control
- Open db with `psql -U your_db_user -d your_db_name`

### Delete
- To drop a table run this:
    - ?
- To remove the whole database run this:
    - `sudo -u postgres dropdb <YOUR_DB_NAME>`
- To completely nuke postgres from the server run this:
    - `sudo apt remove --purge -y postgresql*`
    - `sudo apt autoremove --purge -y`

### Reindex
- Run the below to use IVFFlat
```sql
CREATE INDEX tags_vector_idx ON data
USING ivfflat (tags_vector vector_cosine_ops)
WITH (lists = 50);

CREATE INDEX swatch_vector_idx ON data
USING ivfflat (swatch_vector vector_l2_ops)
WITH (lists = 50);
```
- Adjust the lists value based on your dataset size:
    - Small (<=10K rows): 10–50
    - Medium (10K–100K): 50–100
- Make sure data is analyzed so the query planner has up-to-date statistics
```sql
ANALYZE data;
```

## Systemd Service Setup

- Create a systemd Service with `sudo nano /etc/systemd/system/forgor-api.service`
- Enable and Start the Service
    ```bash
    sudo systemctl daemon-reexec && sudo systemctl daemon-reload
    sudo systemctl enable forgor-api.service && sudo systemctl start forgor-api.service
    sudo systemctl restart forgor-api.service
    ```
- Check Status and Logs
    ```bash
    sudo systemctl status forgor-api
    journalctl -u forgor-api.service -f
    ```

## Watchdog Setup

- Place the Script
    ```bash
    sudo mkdir -p /opt/flask_watchdog
    sudo cp watch_flask_restart.py /opt/flask_watchdog/
    sudo chmod +x /opt/flask_watchdog/watch_flask_restart.py
    ```
- Create a systemd Service with `sudo nano /etc/systemd/system/flask-watchdog.service`
- Enable and Start the Service
    ```bash
    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload
    sudo systemctl enable flask-watchdog.service
    sudo systemctl start flask-watchdog.service
    ```
- Check Status and Logs
    ```bash
    sudo systemctl status flask-watchdog
    tail -f /var/log/flask_watchdog.log
    journalctl -u flask-watchdog.service
    ```

## Reverse Proxy

### NGINX Setup
- Have domain
- Set A address as the VPS's IP address
- Wait 15 min
- Create an nginx config file with `sudo nano /etc/nginx/sites-available/<name>` 
- Use content in `nginx.config`
- Link files with `sudo ln -s /etc/nginx/sites-available/<name> /etc/nginx/sites-enabled/`
- Validate config with `sudo nginx -t`
- Start with `sudo systemctl start nginx`
- Check with `sudo systemctl status nginx`
- Reload with `sudo systemctl reload nginx`

### HTTPS Setup
- Run this `sudo certbot --nginx -d <name>.xyz -d www.<name>.xyz`
- Check for cron job for auto reneew SSL cert with `sudo certbot renew --dry-run`