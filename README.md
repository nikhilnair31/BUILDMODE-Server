# MIA-2 Server

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

## Environment
- Install these packages `pip install sqlalchemy psycopg2-binary pgvector werkzeug pillow google-genai python-dotenv flask` or from `requirements.txt`

## Service
- Run this command and copy the info in the service file
    - `sudo nano /etc/systemd/system/mia2.service`
- Run these commands to control the service
    - `sudo systemctl daemon-reexec`
    - `sudo systemctl daemon-reload`
    - `sudo systemctl enable mia2`
    - `sudo systemctl start mia2`
    - `sudo systemctl stop mia2`
    - `sudo systemctl restart mia2`
    - `journalctl -u mia2.service -f`

## Reverse Proxy

### NGINX Setup
- Have domain
- Set A address as the VPS's IP address
- Wait 15 min
- Create an nginx config file with `sudo nano /etc/nginx/sites-available/mia2` and replace with:
    ```
    server {
        listen 80;
        server_name mia2.xyz www.mia2.xyz;

        location / {
            proxy_pass http://127.0.0.1:5000;  # Flask app on Gunicorn
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
- Link files with `sudo ln -s /etc/nginx/sites-available/mia2 /etc/nginx/sites-enabled/`
- Validate config with `sudo nginx -t`
- Reload with `sudo systemctl reload nginx`

### HTTPS Setup
- `sudo certbot --nginx -d mia2.xyz -d www.mia2.xyz`
- Check for cron job for auto reneew SSL cert with `sudo certbot renew --dry-run`

## TO-DO
- [ ] Add systemd service and nginx config contents into files
- [ ] Add server code to GitHub
- [ ] Add better docs and README
- [ ] Look into refresh tokens
- [ ] Create app logo
- [ ] Update Android to retry for images
- [ ] Update server to save posts with user id instead of username
- [ ] Update server to move all posts to a new user with min 6 digit password 
- [ ] Update system to relink posts even with new username
- [ ] Update extension page to show image details on click
- [ ] Update extension to complete auth register/login/edit
- [ ] Update extension to allow for custom shortcuts
- [ ] Update extension to save data on shortcut
- [ ] Update extension page to show most recent images by default
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