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
- Create an nginx config file with `sudo nano /etc/nginx/sites-available/<name>` and replace with:
    ```
    server {
        listen 80;
        server_name <name>.xyz www.<name>.xyz;

        location / {
            # Rate limit
            limit_req zone=one burst=5 nodelay;
            # Block curl, wget, or any known scraping tools
            if ($http_user_agent ~* (curl|wget|bot|scrapy|python-requests)) {
                return 403;
            }
            # Block requests with empty User-Agent
            if ($http_user_agent = "") {
                return 403;
            }
            
            proxy_pass http://127.0.0.1:5000;
            
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Authorization $http_authorization;
        }
    }
    ```
- Link files with `sudo ln -s /etc/nginx/sites-available/<name> /etc/nginx/sites-enabled/`
- Validate config with `sudo nginx -t`
- Reload with `sudo systemctl reload nginx`

### HTTPS Setup
- Run this `sudo certbot --nginx -d <name>.xyz -d www.<name>.xyz`
- Check for cron job for auto reneew SSL cert with `sudo certbot renew --dry-run`

## Tasks

### To-Do
- [ ] Add logic to auto reindex vector db
- [ ] Add logic to avoid network block on sites
- [ ] Add logic to use redis celery for browser work

### Skipped
- [ ] Look into refresh token expiring
- [ ] Look into double tap gesture for launching something

### Done
- [x] Add pdf support?
- [x] Add text saving endpoint
- [x] Add systemd service and nginx config contents into files
- [x] Add better docs and README
- [x] Update server to combine time/semantic/color search
- [x] Add limit to response results
- [x] Check max cosine distance to be allowed to be considered similar
- [x] Update server to pull image colors too
- [x] Update server to allow for time filters
- [x] Create app logo
- [x] Update Android to remove unused xml
- [x] Update Android to show image in Pinterest grid
- [x] Update server to save posts with user id instead of username
- [x] Update server to move all posts to a new user with min 6 digit password 
- [x] Update system to relink posts even with new username
- [x] Update Android to retry for images
- [x] Added db backups
- [x] Added watchdog script and service
- [x] Add server code to GitHub
- [x] Update Android to allow zoom for image opened
- [x] Update Android to make all calls with authorization token
- [x] Update Android to allow user logout
- [x] Update Android to fix permission button color
- [x] Update Android to set min password length
- [x] Update Android to show link to open shared posts
- [x] Update Android to show placeholder blanks when no image
- [x] Update Android to move the logo up on scroll like in oneui
- [x] Update Android settings page to allow for username editing
- [x] Update Android settings to allow for image to not be saved but then show a warning modal
- [x] Update Android to have a searching page 
- [x] Update Android setup page to check for usernames against database
- [x] Validate the username with session token instead of just picking the username
- [x] Update endpoint so no un authorized access is possible
- [x] Improve rate limit and banned IP logic
- [x] Added simple check for multiple requests from same IP
- [x] Add system to avoid abuse my mass uploads
- [x] Split Android app into another
- [x] Update Android to allow for post sharing
- [x] Update database to allow for more save fields (URL)
- [x] How can I stop users from guessing other usernames?
- [x] Update Android to let MIA come into frequents of share menu
- [x] Added nginx
- [x] Added HTTPS
- [x] Added service for flask app