# digest.py

from datetime import datetime, UTC, timedelta
import html
import json
import random
import collections
from sqlalchemy import func, and_
from core.database.database import get_db_session
from core.database.models import DataEntry
from core.ai.ai import call_llm_api

# ---------- Helpers ----------

STOPWORDS = {
    "the", "and", "or", "to", "in", "of", "for", "with", "on", "a", "an",
    "untagged", "misc", "note", "other", "random", "file", "screenshot"
}

def split_tags(tag_str):
    if not tag_str:
        return []
    raw = [t.strip().lower() for t in tag_str.replace("|", ",").split(",")]
    return [t for t in raw if t and t not in STOPWORDS]

def epoch_range(period: str):
    now = datetime.now(UTC)
    if period == "weekly":
        start = now - timedelta(days=7)
        prev_start = start - timedelta(days=7)
    else:  # monthly
        start = now - timedelta(days=30)
        prev_start = start - timedelta(days=30)
    return int(start.timestamp()), int(now.timestamp()), int(prev_start.timestamp()), int(start.timestamp())

def nice_pct(delta: float) -> str:
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta):.0f}%"

def format_when(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")

def h(s: str) -> str:
    return html.escape(s, quote=True)

# ---------- Digest Generator ----------

def generate_digest(user_id: int, period="weekly"):
    session = get_db_session()

    period_start, period_end, prev_start, prev_end = epoch_range(period)

    # Current period
    now_rows = session.query(DataEntry).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= period_start,
             DataEntry.timestamp < period_end)
    ).order_by(DataEntry.timestamp.desc()).all()

    # Previous count
    prev_cnt = session.query(func.count(DataEntry.id)).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= prev_start,
             DataEntry.timestamp < prev_end)
    ).scalar()

    # Total archive
    total_cnt = session.query(func.count(DataEntry.id)).filter(
        DataEntry.user_id == user_id
    ).scalar()

    # Top tags
    tag_counter = collections.Counter()
    for r in now_rows:
        tag_counter.update(split_tags(r.tags))
    top_tags = tag_counter.most_common(5)

    # Spikes
    prev_tags = collections.Counter()
    prev_rows = session.query(DataEntry.tags).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= prev_start,
             DataEntry.timestamp < prev_end)
    ).all()
    for (tags,) in prev_rows:
        prev_tags.update(split_tags(tags))

    spikes = []
    for tag, c_now in tag_counter.most_common(20):
        c_prev = prev_tags.get(tag, 0)
        if c_prev == 0 and c_now >= 2:
            spikes.append((tag, "new ↑"))
        elif c_prev > 0:
            pct = (c_now - c_prev) / c_prev * 100.0
            if abs(pct) >= 50 and (c_now + c_prev) >= 3:
                spikes.append((tag, nice_pct(pct)))

    # Serendipity highlight (random old item >90 days old)
    cutoff = int((datetime.now(UTC) - timedelta(days=90)).timestamp())
    old_items = session.query(DataEntry).filter(
        and_(DataEntry.user_id == user_id, DataEntry.timestamp < cutoff)
    ).all()
    serendipity = random.choice(old_items) if old_items else None

    # Stats
    now_cnt = len(now_rows)
    pct_change = None
    if prev_cnt > 0:
        pct_change = (now_cnt - prev_cnt) / prev_cnt * 100.0

    # ---------------- LLM SYNTHESIS ----------------
    sysprompt = f"""
    You are generating a digest summary of a user's saved content.
    Focus on being concise, thematic, and easy to read.

    Data:
    - Total saves this period: {now_cnt}
    - Change vs last period: {nice_pct(pct_change) if pct_change is not None else "N/A"}
    - Total archive size: {total_cnt}
    - Top tags: {', '.join([f"{t} ({c})" for t, c in top_tags]) or "None"}
    - Serendipity highlight: {serendipity.tags if serendipity else "None"}

    Write a short readable summary with:
    * Themes / clusters
    * Top tags
    * Any spikes/trends
    * Mention the serendipity item
    """

    # Concatenate this period’s tags as context
    all_tags_text = "\n".join([r.tags or "" for r in now_rows])
    llm_output = call_llm_api(sysprompt, all_tags_text)
    llm_digest = json.loads(llm_output)["urls"][0]

    # ---- HTML ----
    period_label = "This Week" if period == "weekly" else "This Month"
    date_span = f"{datetime.fromtimestamp(period_start, UTC).date()} → {datetime.fromtimestamp(period_end, UTC).date()}"

    top_tags_html = (
        "".join(f"<li><strong>{h(t)}</strong> <span class='muted'>({c})</span></li>" for t,c in top_tags)
        if top_tags else "<li class='muted'>No tags this period</li>"
    )

    spikes_html = (
        "".join(f"<li><strong>{h(tag)}</strong> <span class='chip'>{h(label)}</span></li>" for tag,label in spikes)
        if spikes else "<li class='muted'>No notable spikes</li>"
    )

    ser_html = (
        f"<div><div class='muted'>{h(format_when(serendipity.timestamp))}</div>"
        f"<div>{h(serendipity.tags or '(untagged)')}</div>"
        f"<div class='tiny'>{h(serendipity.file_path or serendipity.thumbnail_path or '')}</div></div>"
        if serendipity else "<div class='muted'>No eligible older items</div>"
    )

    ai_html = f"<p>{h(llm_digest)}</p>" if llm_digest else "<p class='muted'>(No AI summary)</p>"

    html_out = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Forgor — Digest</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: #0b0b0c; color: #eaeaea; padding: 24px; }}
  .card {{ background:#141416; border:1px solid #242428; border-radius:14px; padding:20px; margin:14px 0; }}
  h1, h2 {{ margin: 0 0 8px 0; }}
  h1 {{ font-size:22px; }}
  h2 {{ font-size:16px; color:#d6d6d6; }}
  .muted {{ color:#9aa0a6; }}
  .row {{ display:flex; gap:22px; flex-wrap:wrap; }}
  ul {{ padding-left:18px; margin: 8px 0; }}
  .chip {{ background:#1e2a1e; color:#aef1ae; border:1px solid #274427; padding:1px 6px; border-radius:10px; font-size:12px; }}
  .statgrid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:12px; }}
  .stat {{ background:#111216; border:1px solid #20222a; border-radius:10px; padding:12px; }}
  .big {{ font-size:20px; font-weight:700; }}
  .tiny {{ font-size:12px; color:#7f858a; word-break:break-all; }}
</style>
</head>
<body>
  <div class="card">
    <h1>📰 Digest</h1>
    <div class="muted">{h(period_label)} · {h(date_span)}</div>
  </div>

  <div class="card">
    <h2>Basic stats</h2>
    <div class="statgrid">
      <div class="stat"><div class="muted">Saves this period</div><div class="big">{now_cnt}</div></div>
      <div class="stat"><div class="muted">Change vs last</div><div class="big">{h(nice_pct(pct_change) if pct_change is not None else "N/A")}</div></div>
      <div class="stat"><div class="muted">Total in archive</div><div class="big">{total_cnt}</div></div>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Top tags</h2>
      <ul>{top_tags_html}</ul>
    </div>

    <div class="card" style="flex:1; min-width:280px;">
      <h2>Spikes vs last period</h2>
      <ul>{spikes_html}</ul>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Serendipity</h2>
      {ser_html}
    </div>

    <div class="card" style="flex:2; min-width:280px;">
      <h2>AI summary</h2>
      {ai_html}
    </div>
  </div>
</body>
</html>"""
    print(html_out)

# ---------- Run directly ----------
if __name__ == "__main__":
    generate_digest(user_id=1, period="weekly")