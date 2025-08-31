# digest.py

import html, json, random, re, logging, collections
from datetime import datetime, UTC, timedelta
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy import func, and_, create_engine, desc
from core.database.database import get_db_session
from core.database.models import DataEntry, User
from core.notifications.emails import is_valid_email, send_email
from core.utils.config import Config
from core.ai.ai import call_gemini_with_text

# ---------- Rendering ----------
PALETTE = {
    "base_0": "#1e1c2c",
    "base_1": "#221f31",
    "base_2": "#7b7889",
    "accent_0": "#deff96",
    "accent_0x": "#ECFFCF",
    "accent_1": "#A67BF2",
    "accent_1t": "#337553B0",
}

BASE_CSS = f"""
  :root {{
    --base-0:{PALETTE["base_0"]};
    --base-1:{PALETTE["base_1"]};
    --base-2:{PALETTE["base_2"]};
    --acc-0:{PALETTE["accent_0"]};
    --acc-0x:{PALETTE["accent_0x"]};
    --acc-1:{PALETTE["accent_1"]};
    --acc-1t:{PALETTE["accent_1t"]};
  }}
  * {{ box-sizing:border-box; border-radius:0 !important; }}
  body {{ margin:0; background:var(--base-0); color:var(--acc-0x);
          font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ padding:24px; display:grid; gap:16px; }}
  .card {{ background:var(--base-1); border:1px solid var(--base-2); padding:16px; }}
  h1 {{ margin:0 0 6px 0; font-size:20px; color:var(--acc-0x); }}
  .muted {{ color:var(--base-2); }}
  .grid {{ display:grid; grid-auto-flow:dense; grid-auto-rows:60px;
           grid-template-columns:repeat(12, minmax(0,1fr)); gap:6px; }}
  .tile {{ display:flex; flex-direction:column; justify-content:space-between; padding:8px; border:1px solid var(--base-2); }}
  .tile-empty {{ background:var(--base-1); color:var(--base-2); border:1px dashed var(--base-2); display:flex; align-items:center; justify-content:center; }}
  .t-label {{ font-size:12px; line-height:1.2; }}
  .t-count {{ font-size:11px; color:var(--base-2); }}
  ul.list {{ margin:0; padding-left:18px; }}
  ul.list li {{ margin:4px 0; color:var(--acc-0x); }}
"""

def _mosaic_tiles(pairs:List[Tuple[str,int]], max_span:int=4)->str:
    if not pairs:
        return "<div class='tile tile-empty'>None</div>"
    mx=max(c for _,c in pairs) or 1
    out=[]
    bg_cycle=[PALETTE["base_1"], PALETTE["accent_1"], PALETTE["accent_0"], PALETTE["accent_0x"]]
    for i,(label,count) in enumerate(pairs):
        r=count/mx
        span = 4 if r>=0.80 else 3 if r>=0.50 else 2 if r>=0.25 else 1
        bg=bg_cycle[i % len(bg_cycle)]
        text = (PALETTE["base_0"] if bg in (PALETTE["accent_0"],PALETTE["accent_0x"]) else PALETTE["accent_0x"])
        out.append(
            f"<div class='tile' style='grid-column: span {span}; grid-row: span {span};"
            f"background:{bg}; color:{text};' title='{h(label)} · {count}'>"
            f"<div class='t-label'>{h(label)}</div>"
            f"<div class='t-count'>{count}</div>"
            f"</div>"
        )
    return "".join(out)

def render_section(pairs:List[Tuple[str,int]], mode:str="mosaic")->str:
    """Generic section renderer for themes/moods/topics/apps. mode: 'mosaic'|'list'."""
    if mode=="list":
        if not pairs: return "<ul class='list'><li class='muted'>None</li></ul>"
        return "<ul class='list'>" + "".join(
            f"<li><strong>{h(k)}</strong> <span class='muted'>({v})</span></li>"
            for k,v in pairs
        ) + "</ul>"
    # default: mosaic
    return f"<div class='grid'>{_mosaic_tiles(pairs)}</div>"

# ---------- Helpers ----------

STOPWORDS = {
    "the", "and", "or", "to", "in", "of", "for", "with", "on", "a", "an",
    "untagged", "misc", "note", "other", "random", "file", "screenshot"
}

NUM_RE = re.compile(r"([\d.,]+)\s*([kKmMbB]?)")

def split_tags(tag_str: str) -> List[str]:
    if not tag_str:
        return []
    raw = [t.strip().lower() for t in tag_str.replace("|", ",").split(",")]
    return [t for t in raw if t and t not in STOPWORDS]

def epoch_range(period: str) -> Tuple[int,int,int,int]:
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
    return html.escape(s or "", quote=True)

def parse_jsonish(s: Optional[str]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    s = s.strip()
    if not s or s[0] not in "{[":
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def parse_num_token(token: str) -> int:
    """
    Convert '24K', '5,769', '1.2M' -> int
    """
    m = NUM_RE.search(token or "")
    if not m:
        return 0
    num = float(m.group(1).replace(",", ""))
    suffix = m.group(2).lower()
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    elif suffix == "b":
        num *= 1_000_000_000
    return int(num)

def parse_engagement(tokens: List[str]) -> Dict[str, int]:
    """
    Try to map list like ["24K Views","83 Reposts","902 Likes"] to totals.
    """
    agg = {"views": 0, "reposts": 0, "quotes": 0, "likes": 0, "bookmarks": 0}
    key_map = {
        "view": "views", "views": "views",
        "repost": "reposts", "reposts": "reposts", "rt": "reposts",
        "quote": "quotes", "quotes": "quotes",
        "like": "likes", "likes": "likes",
        "bookmark": "bookmarks", "bookmarks": "bookmarks",
    }
    for t in tokens or []:
        parts = t.strip().split()
        if not parts:
            continue
        n = parse_num_token(parts[0])
        tail = " ".join(parts[1:]).lower()
        # pick the first known key present
        for k, norm in key_map.items():
            if k in tail:
                agg[norm] += n
                break
    return agg

def bucket_hour(ts: int) -> int:
    return datetime.fromtimestamp(ts, UTC).hour

def bucket_weekday(ts: int) -> int:
    # Monday=0 ... Sunday=6
    return datetime.fromtimestamp(ts, UTC).weekday()

# ---------- Digest Generator ----------

def generate_digest(user_id: int, period="weekly"):
    session = get_db_session()

    period_start, period_end, prev_start, prev_end = epoch_range(period)

    # Current period rows (full)
    now_rows: List[DataEntry] = session.query(DataEntry).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= period_start,
             DataEntry.timestamp < period_end)
    ).order_by(DataEntry.timestamp.desc()).all()

    # Previous period count (for % change)
    prev_cnt = session.query(func.count(DataEntry.id)).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= prev_start,
             DataEntry.timestamp < prev_end)
    ).scalar() or 0

    # Total archive
    total_cnt = session.query(func.count(DataEntry.id)).filter(
        DataEntry.user_id == user_id
    ).scalar() or 0

    # ---------- Aggregate (legacy tags + JSON blobs) ----------
    tag_counter = collections.Counter()
    theme_counter = collections.Counter()
    mood_counter = collections.Counter()
    keyword_counter = collections.Counter()
    color_counter = collections.Counter()
    app_counter = collections.Counter()
    domain_counter = collections.Counter()
    hour_counter = collections.Counter()
    weekday_counter = collections.Counter()

    engagement_totals = {"views": 0, "reposts": 0, "quotes": 0, "likes": 0, "bookmarks": 0}

    def extract_domain(url: str) -> Optional[str]:
        try:
            # crude, avoids importing urllib just for netloc
            if "://" in url:
                host = url.split("://", 1)[1].split("/", 1)[0]
            else:
                host = url.split("/", 1)[0]
            return host.lower()
        except Exception:
            return None

    # Build "previous" counters for spike detection
    prev_rows = session.query(DataEntry.tags).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= prev_start,
             DataEntry.timestamp < prev_end)
    ).all()
    prev_tag_counter = collections.Counter()
    prev_theme_counter = collections.Counter()
    prev_mood_counter = collections.Counter()
    prev_keyword_counter = collections.Counter()
    for (tags_str,) in prev_rows:
        blob = parse_jsonish(tags_str)
        if blob:
            prev_theme_counter.update([t.lower() for t in blob.get("themes", [])])
            prev_mood_counter.update([m.lower() for m in blob.get("moods", [])])
            prev_keyword_counter.update([k.lower() for k in blob.get("keywords", [])])
            # Fallback to "keywords" for generic tag spikes too
            prev_tag_counter.update([k.lower() for k in blob.get("keywords", [])])
        else:
            prev_tag_counter.update(split_tags(tags_str))

    # Current-period extraction
    for r in now_rows:
        hour_counter[bucket_hour(r.timestamp)] += 1
        weekday_counter[bucket_weekday(r.timestamp)] += 1

        blob = parse_jsonish(r.tags)
        if blob:
            # app / engagement
            app = (blob.get("app_name") or "").strip()
            if app:
                app_counter[app] += 1
            engagement = parse_engagement(blob.get("engagement_counts") or [])
            for k in engagement_totals:
                engagement_totals[k] += engagement[k]

            # themes / moods / keywords / colors
            theme_counter.update([t.lower() for t in (blob.get("themes") or [])])
            mood_counter.update([m.lower() for m in (blob.get("moods") or [])])
            keyword_counter.update([k.lower() for k in (blob.get("keywords") or [])])
            color_counter.update([c.upper() for c in (blob.get("accent_colors") or [])])

            # domains
            for url in (blob.get("links") or []):
                d = extract_domain(url)
                if d:
                    domain_counter[d] += 1

            # also treat keywords as generic "tags" for top-tags parity
            tag_counter.update([k.lower() for k in (blob.get("keywords") or [])])
        else:
            # legacy text tags
            tag_counter.update(split_tags(r.tags))

    # Top lists
    top_tags = tag_counter.most_common(8)
    top_themes = theme_counter.most_common(8)
    top_moods = mood_counter.most_common(8)
    top_keywords = keyword_counter.most_common(12)
    top_colors = color_counter.most_common(8)
    top_apps = app_counter.most_common(6)
    top_domains = domain_counter.most_common(6)

    # Novelty / spike detection (themes + moods + keywords + generic tags)
    def compute_spikes(now_ctr: collections.Counter, prev_ctr: collections.Counter, label: str):
        out = []
        for k, c_now in now_ctr.most_common(20):
            c_prev = prev_ctr.get(k, 0)
            if c_prev == 0 and c_now >= 2:
                out.append((label, k, "new ↑"))
            elif c_prev > 0:
                pct = (c_now - c_prev) / c_prev * 100.0
                if abs(pct) >= 50 and (c_now + c_prev) >= 3:
                    out.append((label, k, nice_pct(pct)))
        return out

    spikes = []
    spikes += compute_spikes(theme_counter, prev_theme_counter, "theme")
    spikes += compute_spikes(mood_counter, prev_mood_counter, "mood")
    spikes += compute_spikes(keyword_counter, prev_keyword_counter, "topic")
    spikes += compute_spikes(tag_counter, prev_tag_counter, "tag")

    # Serendipity: random item older than 90 days
    cutoff = int((datetime.now(UTC) - timedelta(days=90)).timestamp())
    old_items = session.query(DataEntry).filter(
        and_(DataEntry.user_id == user_id, DataEntry.timestamp < cutoff)
    ).all()
    serendipity = random.choice(old_items) if old_items else None

    # Basic stats
    now_cnt = len(now_rows)
    pct_change = None
    if prev_cnt > 0:
        pct_change = (now_cnt - prev_cnt) / prev_cnt * 100.0

    # Streak (days with at least one save, counted backwards)
    days_with_saves = {datetime.fromtimestamp(r.timestamp, UTC).date() for r in now_rows}
    streak = 0
    day_cursor = datetime.now(UTC).date()
    while day_cursor in days_with_saves:
        streak += 1
        day_cursor = day_cursor - timedelta(days=1)

    # ---------- LLM Synthesis ----------
    # Build compact, structured context
    synth_ctx = {
        "counts": {
            "period_saves": now_cnt,
            "vs_last_pct": (f"{pct_change:.0f}%" if pct_change is not None else "N/A"),
            "archive_total": total_cnt
        },
        "themes_top": top_themes[:5],
        "moods_top": top_moods[:5],
        "topics_top": top_keywords[:10],
        "colors_top": top_colors[:6],
        "apps_top": top_apps[:4],
        "domains_top": top_domains[:4],
        "spikes": spikes[:10],
        "engagement_totals": engagement_totals,
        "time_buckets": {
            "by_hour": sorted(hour_counter.items()),
            "by_weekday": sorted(weekday_counter.items()),
        },
        "serendipity": {
            "when": format_when(serendipity.timestamp) if serendipity else None,
            "tags_or_blob": serendipity.tags if serendipity else None
        },
        "notes": "Summarize in 4-6 bullet points: themes, mood, color palette vibe, what stood out (spikes/novelty), and 2-3 actionable nudges for next week."
    }

    sys_prompt = (
        "You are generating a digest summary of a user's saved content for the past period.\n"
        "Be concise, specific, and pattern-focused. Prefer concrete nouns over vague phrasing.\n"
        "Use short bullets. If something is clearly dominant, say so. If novelty spikes exist, call them out briefly.\n"
        "Close with 2-3 lightweight, personalized nudges the user could try next week."
    )
    llm_digest = call_gemini_with_text(sys_prompt, json.dumps(synth_ctx, ensure_ascii=False))

    # ---------- HTML ----------
    period_label = "This Week" if period == "weekly" else "This Month"
    date_span = f"{datetime.fromtimestamp(period_start, UTC).date()} → {datetime.fromtimestamp(period_end, UTC).date()}"

    def li_list(pairs: List[Tuple[str,int]], empty_msg="None"):
        if not pairs:
            return f"<li class='muted'>{h(empty_msg)}</li>"
        return "".join(f"<li><strong>{h(k)}</strong> <span class='muted'>({v})</span></li>" for k, v in pairs)

    spikes_html = (
        "".join(
            f"<li><span class='label'>{h(kind)}</span> <strong>{h(name)}</strong> "
            f"<span class='chip'>{h(lbl)}</span></li>"
            for (kind, name, lbl) in spikes[:12]
        ) or "<li class='muted'>No notable spikes</li>"
    )

    ser_html = (
        f"<div><div class='muted'>{h(format_when(serendipity.timestamp))}</div>"
        f"<div class='wrap'>{h(serendipity.tags or '(untagged)')}</div>"
        f"<div class='tiny'>{h(serendipity.file_path or serendipity.thumbnail_path or '')}</div></div>"
        if serendipity else "<div class='muted'>No eligible older items</div>"
    )

    # color swatches
    color_swatches = "".join(
        f"<div class='swatch' title='{h(c)}' style='background:{h(c)}'></div>"
        for c, _ in top_colors
    ) or "<div class='muted'>No colors detected</div>"

    # engagement quick chips
    eng = engagement_totals
    eng_html = (
        f"<span class='pill'>👁 {eng['views']}</span>"
        f"<span class='pill'>❤️ {eng['likes']}</span>"
        f"<span class='pill'>🔁 {eng['reposts']}</span>"
        f"<span class='pill'>💬 {eng['quotes']}</span>"
        f"<span class='pill'>🔖 {eng['bookmarks']}</span>"
    )

    # time-of-week bands
    def band(items, size):
        total = sum(v for _, v in items) or 1
        # normalized tiny bars
        bars = []
        for i, v in items:
            w = max(2, int(100 * (v / total)))
            bars.append(f"<div class='bar' style='width:{w}px' title='{i}: {v}'></div>")
        return "".join(bars)

    hours_sorted = [(i, hour_counter.get(i, 0)) for i in range(24)]
    weekdays_sorted = [(i, weekday_counter.get(i, 0)) for i in range(7)]  # 0=Mon

    ai_html = f"<div class='bullets'>{h(llm_digest)}</div>" if llm_digest else "<p class='muted'>(No AI summary)</p>"

    html_out = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Forgor — Digest</title>
<style>{BASE_CSS}</style>
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
      <div class="stat"><div class="muted">Save streak (days)</div><div class="big">{streak}</div></div>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Themes</h2>
      <ul>{li_list(top_themes, "No themes detected")}</ul>
    </div>
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Moods</h2>
      <ul>{li_list(top_moods, "No moods detected")}</ul>
    </div>
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Interesting topics</h2>
      <ul>{li_list(top_keywords, "No topics detected")}</ul>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Colors</h2>
      {color_swatches}
    </div>
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Spikes & novelty</h2>
      <ul>{spikes_html}</ul>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Sources</h2>
      <ul>{li_list(top_apps, "No sources recorded")}</ul>
      <div style="margin-top:8px;">{eng_html}</div>
    </div>
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Top domains</h2>
      <ul>{li_list(top_domains, "No links recorded")}</ul>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:280px;">
      <h2>Time of week</h2>
      <div class="muted" style="margin:6px 0 4px;">By hour (UTC)</div>
      <div class="bands">{band(hours_sorted, 24)}</div>
      <div class="muted" style="margin:10px 0 4px;">By weekday (Mon=0)</div>
      <div class="bands">{band(weekdays_sorted, 7)}</div>
    </div>

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
    # print(html_out)

    return html_out

# ---------- Run directly ----------

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

engine = create_engine(Config.ENGINE_URL)
Session = sessionmaker(bind=engine)

if __name__ == "__main__":
    session = Session()

    try:
        now = int(datetime.now(UTC).timestamp())
        
        all_users = session.query(User).all()

        for user in all_users:
            # check email validity
            if not is_valid_email(user.email):
                print(f"Skipping user {user.id}: invalid or missing email ({user.email})")
                continue
            
            freq_name = user.frequency.name if user.frequency else "unspecified"

            # decide if digest is due
            last_sent = user.last_digest_sent or 0
            due = False

            if freq_name == "weekly":
                due = now - last_sent >= 604800  # 7 days
            elif freq_name == "monthly":
                due = now - last_sent >= 2592000 # ~30 days

            if due:
                logger.info(f"Sending digest to {user.username} ({user.email}) [{freq_name}]")

                digest_content = generate_digest(user_id=user.id, period=freq_name)
                # print(f"digest_content\n{digest_content[:100]}")
                if digest_content:
                    send_email(user.email, f"Your {freq_name} FORGOR Digest", digest_content)
                    user.last_digest_sent = now
                    session.add(user)
                else:
                    logger.warning(f"No digest content generated for {user.username}")

                # update last sent timestamp
                user.last_digest_sent = now
                session.add(user)

        session.commit()
        session.close()
            
    except Exception as e:
        print(f"Error creating digest: {e}")
        session.close()