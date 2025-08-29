import os, smtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = "mail.smtp2go.com"
SMTP_PORT   = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER   = os.getenv("SMTP2GO_SMTP_USER")
SMTP_PASS   = os.getenv("SMTP2GO_SMTP_PASS")

FROM_EMAIL  = "nikhil@forgor.space"
TO_EMAIL    = "niknair31898@gmail.com"
SUBJECT     = "Your Monthly FORGOR Digest"

HTML_BODY = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Forgor — Digest</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: #0b0b0c; color: #eaeaea; padding: 24px; }
  .card { background:#141416; border:1px solid #242428; border-radius:14px; padding:20px; margin:14px 0; }
  h1, h2 { margin: 0 0 8px 0; }
  h1 { font-size:22px; }
  h2 { font-size:16px; color:#d6d6d6; }
  .muted { color:#9aa0a6; }
  .row { display:flex; gap:22px; flex-wrap:wrap; }
  ul { padding-left:18px; margin: 8px 0; }
  .chip { background:#1e2a1e; color:#aef1ae; border:1px solid #274427; padding:1px 6px; border-radius:10px; font-size:12px; }
  .statgrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:12px; }
  .stat { background:#111216; border:1px solid #20222a; border-radius:10px; padding:12px; }
  .big { font-size:20px; font-weight:700; }
  .tiny { font-size:12px; color:#7f858a; word-break:break-all; }
</style>
</head>
<body>
  <div class="card">
    <h1>📰 Digest</h1>
    <div class="muted">This Week · 2025-08-21 → 2025-08-28</div>
  </div>

  <div class="card">
    <h2>Basic stats</h2>
    <div class="statgrid">
      <div class="stat"><div class="muted">Saves this period</div><div class="big">1</div></div>
      <div class="stat"><div class="muted">Change vs last</div><div class="big">−97%</div></div>
      <div class="stat"><div class="muted">Total in archive</div><div class="big">314</div></div>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Top tags</h2>
      <ul><li><strong>```
&lt;tags&gt;
twitter</strong> <span class='muted'>(1)</span></li><li><strong>social media</strong> <span class='muted'>(1)</span></li><li><strong>post</strong> <span class='muted'>(1)</span></li><li><strong>ray_ervian</strong> <span class='muted'>(1)</span></li><li><strong>@ray_ervian</strong> <span class='muted'>(1)</span></li></ul>
    </div>

    <div class="card" style="flex:1; min-width:280px;">
      <h2>Spikes vs last period</h2>
      <ul><li><strong>```
&lt;tags&gt;
twitter</strong> <span class='chip'>−91%</span></li><li><strong>social media</strong> <span class='chip'>−96%</span></li><li><strong>post</strong> <span class='chip'>−95%</span></li><li><strong>follow</strong> <span class='chip'>−50%</span></li><li><strong>horror</strong> <span class='chip'>−50%</span></li><li><strong>character design</strong> <span class='chip'>−67%</span></li><li><strong>game development</strong> <span class='chip'>−75%</span></li><li><strong>retro</strong> <span class='chip'>−50%</span></li><li><strong>vintage</strong> <span class='chip'>−50%</span></li></ul>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Serendipity</h2>
      <div><div class='muted'>2025-05-29</div><div>```text
&lt;tags&gt;
Twitter, X, post, Alzea Arafat, @helloalzea, wallpaper, app design, mobile app, user interface, UI, UX, design, illustrations, flat design, icons, dashboard, collection, Ethereum, cryptocurrency, digital wallet, transactions, send, request, balance, payments, financial app, Duolingo, language learning, Japanese, English, Indonesian, Arabic, lessons, daily check-in, sleep tracking, energy tracking, hydration, coffee consumption, step counter, fitness tracking, music streaming, Spotify, Apple Music, subscription, expenses, transport, electricity, groceries, music, white, blue, yellow, black, green, pink, purple, playful, modern, clean, sign up, login, terms of service, privacy policy, google sign up, apple sign up, create account, error message, retry button
&lt;/tags&gt;
```</div><div class='tiny'>./uploads/2c6affa85582496aaeb6b9e0ce635fa1.jpg</div></div>
    </div>

    <div class="card" style="flex:2; min-width:280px;">
      <h2>AI summary</h2>
      <p>This week&#x27;s save activity was significantly lower than usual. Predominant themes include social media, particularly Twitter posts, and a cluster around unsettling low-poly 3D art reminiscent of 1990s horror games. Top tags include &quot;twitter&quot;, &quot;social media&quot;, &quot;post&quot;, &quot;ray_ervian&quot;, and &quot;@ray_ervian&quot;. A serendipitous save featured a Twitter post by Artosa (@ArthurTonetti) showcasing low-res characters.</p>
    </div>
  </div>
</body>
</html>
"""

assert SMTP_USER and SMTP_PASS, "Missing SMTP2GO_SMTP_USER/SMTP2GO_SMTP_PASS"

def send_email1():
    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg["Subject"] = SUBJECT
    msg.attach(MIMEText(HTML_BODY, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())

    print(f"Backup email sent successfully to {TO_EMAIL}")

def send_email1a():
    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg["Subject"] = SUBJECT
    msg.attach(MIMEText(HTML_BODY, "html"))

    # Attachment
    part = MIMEBase("application", "zip")
    part.set_payload(zip_bytes.getvalue())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f'attachment; filename="FORGOR_backup.zip"',
    )
    msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())

    print(f"Backup email sent successfully to {TO_EMAIL}")

def send_email2():
    client = Smtp2goClient(api_key = SMTP_API_KEY)
    payload = {
        'sender': FROM_EMAIL,
        'recipients': [TO_EMAIL],
        'subject': SUBJECT,
        'html': HTML_BODY
    }
    response = client.send(**payload)
    print(response)
    print(response.success)
    print(response.json)
    print(response.errors)
    print(response.rate_limit)

send_email1()