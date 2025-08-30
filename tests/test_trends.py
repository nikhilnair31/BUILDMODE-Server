# trends.py

import datetime as dt
import collections
import html
from sqlalchemy import func, and_
from core.database.database import get_db_session
from core.database.models import DataEntry
from core.ai.ai import call_gemini_with_text

# ---------- Helpers ----------

STOPWORDS = {
    "the","and","or","to","in","of","for","with","on","a","an",
    "untagged","misc","note","other","random","file"
}

def split_tags(tag_str):
    if not tag_str:
        return []
    raw = [t.strip().lower() for t in tag_str.replace("|", ",").split(",")]
    return [t for t in raw if t and t not in STOPWORDS]

def epoch_range(period: str):
    now = dt.datetime.utcnow()
    if period == "weekly":
        start = now - dt.timedelta(days=7)
        prev_start = start - dt.timedelta(days=7)
    else:  # monthly
        start = now - dt.timedelta(days=30)
        prev_start = start - dt.timedelta(days=30)
    return int(start.timestamp()), int(now.timestamp()), int(prev_start.timestamp()), int(start.timestamp())

def nice_pct(delta: float) -> str:
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta):.0f}%"

def h(s: str) -> str:
    return html.escape(s, quote=True)

# ---------- Trends ----------

def personal_trends(user_id: int, period="weekly"):
    session = get_db_session()
    ps, pe, pps, ppe = epoch_range(period)

    now_tags = collections.Counter()
    for (tags,) in session.query(DataEntry.tags).filter(
        and_(DataEntry.user_id == user_id, DataEntry.timestamp >= ps, DataEntry.timestamp < pe)
    ).all():
        now_tags.update(split_tags(tags))

    prev_tags = collections.Counter()
    for (tags,) in session.query(DataEntry.tags).filter(
        and_(DataEntry.user_id == user_id, DataEntry.timestamp >= pps, DataEntry.timestamp < ppe)
    ).all():
        prev_tags.update(split_tags(tags))

    spikes = []
    for tag, c_now in now_tags.most_common(30):
        c_prev = prev_tags.get(tag, 0)
        if c_prev == 0 and c_now >= 2:
            spikes.append((tag, "new ↑"))
        elif c_prev > 0:
            pct = (c_now - c_prev) / c_prev * 100.0
            if abs(pct) >= 50 and (c_now + c_prev) >= 3:
                spikes.append((tag, nice_pct(pct)))

    return {
        "period": period,
        "now_top": now_tags.most_common(8),
        "spikes": spikes,
        "range": (ps, pe)
    }

def global_trends(period="weekly", user_id=None):
    session = get_db_session()
    ps, pe, pps, ppe = epoch_range(period)

    now_tags = collections.Counter()
    for (tags,) in session.query(DataEntry.tags).filter(
        and_(DataEntry.timestamp >= ps, DataEntry.timestamp < pe)
    ).all():
        now_tags.update(split_tags(tags))

    prev_tags = collections.Counter()
    for (tags,) in session.query(DataEntry.tags).filter(
        and_(DataEntry.timestamp >= pps, DataEntry.timestamp < ppe)
    ).all():
        prev_tags.update(split_tags(tags))

    spikes = []
    for tag, c_now in now_tags.most_common(30):
        c_prev = prev_tags.get(tag, 0)
        if c_prev == 0 and c_now >= 5:
            spikes.append((tag, "new ↑"))
        elif c_prev > 0:
            pct = (c_now - c_prev) / c_prev * 100.0
            if abs(pct) >= 50 and (c_now + c_prev) >= 10:
                spikes.append((tag, nice_pct(pct)))

    personal_relate = []
    if user_id:
        user_tagset = set()
        for (tags,) in session.query(DataEntry.tags).filter(DataEntry.user_id == user_id).all():
            user_tagset.update(split_tags(tags))
        for tag, label in spikes:
            if tag in user_tagset:
                personal_relate.append((tag, label))

    return {
        "period": period,
        "global_top": now_tags.most_common(8),
        "spikes": spikes,
        "relates_to_user": personal_relate,
        "range": (ps, pe)
    }

# ---------- HTML builder ----------

def build_trends_html(user_id: int, period="weekly", include_global=True) -> str:
    per = personal_trends(user_id, period)
    glob = global_trends(period, user_id=user_id) if include_global else None

    ps, pe = per["range"]
    date_span = f"{dt.datetime.utcfromtimestamp(ps).date()} → {dt.datetime.utcfromtimestamp(pe).date()}"
    period_label = "This Week" if period == "weekly" else "This Month"

    def list_items(pairs):
        if not pairs:
            return "<li class='muted'>None</li>"
        return "".join(f"<li><strong>{h(t)}</strong> <span class='muted'>({c})</span></li>" for t,c in pairs)

    def list_spikes(sp):
        if not sp:
            return "<li class='muted'>No notable spikes</li>"
        return "".join(f"<li><strong>{h(t)}</strong> <span class='chip'>{h(lbl)}</span></li>" for t,lbl in sp)

    # Optional LLM narrative
    try:
        sys_prompt = ("Summarize the user's personal and global tag trends in under 120 words. "
                     "Be concrete and friendly. Mention overlaps between global spikes and the user's history if any.")
        ctx = (f"Personal top: {per['now_top']}\n"
               f"Personal spikes: {per['spikes']}\n"
               f"Global top: {glob['global_top'] if glob else []}\n"
               f"Global spikes: {glob['spikes'] if glob else []}\n"
               f"Overlap: {glob['relates_to_user'] if glob else []}")
        ai_summary = call_gemini_with_text(sys_prompt, ctx)
    except Exception as e:
        ai_summary = f"(AI summary unavailable: {e})"

    global_section = ""
    if include_global and glob:
        g_top = list_items(glob["global_top"])
        g_spikes = list_spikes(glob["spikes"])
        overlap = ( "".join(f"<li>‘{h(t)}’ · <span class='chip'>{h(lbl)}</span></li>" for t,lbl in glob["relates_to_user"])
                    if glob["relates_to_user"] else "<li class='muted'>No direct overlap with your archive</li>" )
        global_section = f"""
        <div class="card">
          <h2>🌍 Global trends</h2>
          <ul class="tight">{g_top}</ul>
          <h3>Spiking globally</h3>
          <ul class="tight">{g_spikes}</ul>
          <h3>Connections to your archive</h3>
          <ul class="tight">{overlap}</ul>
        </div>"""

    html_out = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Forgor — Trends</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: #0b0b0c; color: #eaeaea; padding: 24px; }}
  .card {{ background:#141416; border:1px solid #242428; border-radius:14px; padding:20px; margin:14px 0; }}
  h1, h2, h3 {{ margin: 0 0 8px 0; }}
  h1 {{ font-size:22px; }}
  h2 {{ font-size:16px; color:#d6d6d6; }}
  h3 {{ font-size:14px; color:#cfd3d7; margin-top:10px; }}
  .muted {{ color:#9aa0a6; }}
  .chip {{ background:#1e2a1e; color:#aef1ae; border:1px solid #274427; padding:1px 6px; border-radius:10px; font-size:12px; }}
  ul.tight {{ padding-left:18px; margin: 6px 0; }}
</style>
</head>
<body>
  <div class="card">
    <h1>📈 Trends</h1>
    <div class="muted">{h(period_label)} · {h(date_span)}</div>
  </div>

  <div class="card">
    <h2>Personal trends</h2>
    <h3>Top this period</h3>
    <ul class="tight">{list_items(per['now_top'])}</ul>
    <h3>Spiking vs last period</h3>
    <ul class="tight">{list_spikes(per['spikes'])}</ul>
  </div>

  {global_section}

  <div class="card">
    <h2>AI summary</h2>
    <p>{h(ai_summary)}</p>
  </div>
</body>
</html>"""
    return html_out

# ---------- Run as script ----------

if __name__ == "__main__":
    user_id = 1
    html_body = build_trends_html(user_id, "weekly", True)
    print(html_body)