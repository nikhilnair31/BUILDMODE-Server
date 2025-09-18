import json
import math
import time
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional, Any
from core.database.database import get_db_session
from sqlalchemy import text
from sqlalchemy import func, cast
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sklearn.cluster import KMeans
from core.database.models import DataColor, DataEntry
from core.utils.config import Config
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

session = get_db_session()

# Predefined sets for theme/mood categorization (expanded for real-world use)
APP_NAMES = {
    'instagram', 'youtube', 'twitter', 'whatsapp', 'gmail', 'google', 'chrome', 'facebook',
    'reddit', 'pinterest', 'spotify', 'netflix', 'tiktok', 'snapchat', 'linkedin', 'discord',
    'slack', 'zoom', 'microsoft', 'apple', 'android', 'ios', 'windows', 'mac', 'linux',
    'ubunt', 'vscode', 'sublime', 'atom', 'notion', 'telegram', 'signal', 'twitch', 'steam',
    'epic', 'playstation', 'xbox', 'nintendo', 'amazon', 'ebay', 'walmart', 'target', 'bestbuy',
    'cvs', 'starbucks', 'mcdonalds', 'burgerking', 'kfc', 'pizzahut', 'dominoes', 'uber', 'lyft',
    'airbnb', 'booking', 'expedia', 'tripadvisor', 'yelp', 'imdb', 'rottentomatoes', 'metacritic',
    'wikipedia', 'github', 'gitlab', 'bitbucket', 'docker', 'kubernetes', 'aws', 'azure', 'gcp',
    'oracle', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'rabbitmq', 'kafka',
    'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy', 'matplotli', 'seaborn', 'plotly',
    'jupyter', 'pycharm', 'intellij', 'eclipse', 'vim', 'emacs', 'brackets', 'dreamweaver', 'figma',
    'sketch', 'adobe', 'photoshop', 'illustrator', 'indesign', 'premiere', 'aftereffects', 'lightroom',
    'audition', 'xd', 'animate', 'acrobat', 'corel', 'blender', 'maya', '3dsmax', 'cinema4d', 'zbrush',
    'substance', 'unity', 'unreal', 'godot', 'cryengine', 'gamemaker', 'rpmaker', 'construct', 'scratch',
    'code.org', 'khanacademy', 'coursera', 'edx', 'udemy', 'pluralsight', 'linkedinlearning', 'skillshare',
    'masterclass', 'safari', 'edge', 'brave', 'opera', 'firefox', 'outlook', 'dropbox', 'onedrive',
    'google drive', 'icloud', 'spotify', 'soundcloud', 'vimeo', 'dailymotion', 'tumblr', 'flickr',
    'deviantart', 'behance', 'dribbble', 'etsy', 'shopify', 'wordpress', 'wix', 'squarespace'
}
MOOD_WORDS = {
    'happy', 'sad', 'angry', 'excited', 'calm', 'peaceful', 'anxious', 'stressed', 'relaxed',
    'bored', 'tired', 'energetic', 'confused', 'curious', 'inspired', 'motivated', 'depressed',
    'lonely', 'loved', 'hated', 'scared', 'brave', 'shy', 'confident', 'proud', 'ashamed', 'guilty',
    'grateful', 'hopeful', 'hopeless', 'optimistic', 'pessimistic', 'nostalgic', 'sentimental',
    'romantic', 'funny', 'serious', 'playful', 'serene', 'chaotic', 'vibrant', 'dull', 'bright',
    'dark', 'light', 'heavy', 'soft', 'hard', 'warm', 'cold', 'hot', 'cool', 'fresh', 'stale',
    'new', 'old', 'young', 'mature', 'childish', 'professional', 'casual', 'formal', 'informal',
    'simple', 'complex', 'easy', 'difficult', 'challenging', 'interesting', 'thrilling', 'monotonous',
    'repetitive', 'unique', 'common', 'rare', 'frequent', 'occasional', 'regular', 'irregular',
    'consistent', 'inconsistent', 'stable', 'unstable', 'reliable', 'unreliable', 'trustworthy',
    'distrustful', 'friendly', 'hostile', 'welcoming', 'unwelcoming', 'open', 'closed', 'secretive',
    'transparent', 'honest', 'dishonest', 'truthful', 'lying', 'deceitful', 'sincere', 'insincere',
    'genuine', 'fake', 'real', 'artificial', 'natural', 'synthetic', 'organic', 'inorganic', 'pure',
    'impure', 'clean', 'dirty', 'tidy', 'messy', 'organized', 'disorganized', 'structured',
    'unstructured', 'flexible', 'rigid', 'strict', 'loose', 'tight', 'secure', 'insecure', 'safe',
    'dangerous', 'risky', 'protected', 'vulnerable', 'exposed', 'covered', 'uncovered', 'hidden',
    'visible', 'concealed', 'revealed', 'discovered', 'lost', 'found', 'known', 'unknown', 'familiar',
    'unfamiliar', 'strange', 'weird', 'odd', 'normal', 'abnormal', 'typical', 'atypical', 'standard',
    'non-standard', 'conventional', 'unconventional', 'traditional', 'modern', 'contemporary',
    'ancient', 'historical', 'mythical', 'legendary', 'fictional', 'realistic', 'imaginary', 'fantasy',
    'sciencefiction', 'horror', 'comedy', 'drama', 'tragedy', 'romance', 'adventure', 'mystery',
    'thriller', 'action', 'suspense', 'positive', 'negative', 'neutral', 'joyful', 'melancholic',
    'content', 'frustrated', 'amazed', 'disgusted', 'surprised', 'fearful', 'contemptuous', 'neutral'
}

periods = {"7d": 7, "30d": 30, "365d": 365}
current_time = time.time()

# Example user ID
USER_ID = 1

def get_user_interests() -> Dict[str, Any]:
    # Main computation pipeline
    keywords, themes, moods = _get_recency_decayed_tags()
    avg_embeddings = _get_avg_embeddings()
    top_colors = _get_top_clustered_colors()
    
    return {
        "keywords": keywords,
        "themes": themes,
        "moods": moods,
        "avg_embedding_7d": avg_embeddings["7d"],
        "avg_embedding_30d": avg_embeddings["30d"],
        "avg_embedding_365d": avg_embeddings["365d"],
        "top_colors": top_colors
    }

def _get_recency_decayed_tags() -> Tuple[List[str], List[str], List[str]]:
    """Compute recency-decayed top keywords, themes, and moods"""
    # Exponential decay parameters (half-life = 7 days)
    DECAY_HALF_LIFE = 7
    DECAY_LAMBDA = math.log(2) / DECAY_HALF_LIFE
    
    # Fetch relevant data entries (last 365 days)
    cutoff = current_time - (365 * 86400)
    entries = session.query(DataEntry).filter(
        DataEntry.user_id == USER_ID,
        DataEntry.timestamp >= cutoff
    ).all()
    
    # Aggregate weighted tag scores
    tag_scores = defaultdict(float)
    for entry in entries:
        try:
            tags = json.loads(entry.tags)
            days_ago = (current_time - entry.timestamp) / 86400
            weight = math.exp(-DECAY_LAMBDA * days_ago)
            
            for tag, score in tags.items():
                tag_scores[tag] += float(score) * weight
        except (json.JSONDecodeError, TypeError):
            continue
    
    # Sort and select top 50 keywords
    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    top_keywords = [tag for tag, _ in sorted_tags[:50]]
    
    # Categorize into themes (non-app) and moods
    themes = [
        tag for tag in top_keywords 
        if tag.lower() not in APP_NAMES and len(tag) > 2
    ][:20]
    
    moods = [
        tag for tag in top_keywords 
        if tag.lower() in MOOD_WORDS
    ][:10]
    
    return top_keywords, themes, moods

def _get_avg_embeddings() -> Dict[str, Optional[List[float]]]:
    """Compute average embedding vectors for different time windows"""
    results: Dict[str, Optional[List[float]]] = {}

    for period_key, days in periods.items():
        cutoff = current_time - (days * 86400)

        sql = text("""
            SELECT avg(tags_vector) AS avg_vec
            FROM data
            WHERE user_id = :uid AND timestamp >= :cutoff
        """)
        row = session.execute(sql, {"uid": USER_ID, "cutoff": cutoff}).first()

        if row and row.avg_vec is not None:
            # row.avg_vec is already a 768-d vector
            results[period_key] = [float(x) for x in row.avg_vec]
        else:
            results[period_key] = None

    return results

def _get_top_clustered_colors() -> List[List[float]]:
    """Compute top 10 clustered LAB colors from recent entries"""
    # Fetch color data (last 365 days)
    cutoff = current_time - (365 * 86400)
    color_data = session.query(DataColor.color_vector).join(
        DataEntry, DataColor.data_id == DataEntry.id
    ).filter(
        DataEntry.user_id == USER_ID,
        DataEntry.timestamp >= cutoff
    ).all()
    
    if not color_data:
        return []
    
    # Prepare LAB vectors
    lab_vectors = []
    for (vec,) in color_data:
        if vec is not None and len(vec) == 3:
            lab_vectors.append([float(x) for x in vec])
    
    if not lab_vectors:
        return []
    
    # Determine optimal clusters (max 10)
    n_samples = len(lab_vectors)
    n_clusters = min(10, n_samples)
    
    # Perform KMeans clustering
    kmeans = KMeans(
        n_clusters=n_clusters,
        random_state=42,
        n_init=10,
        init='k-means++'
    ).fit(lab_vectors)
    
    # Count cluster sizes and sort by frequency
    cluster_counts = Counter(kmeans.labels_)
    sorted_clusters = sorted(
        cluster_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    # Return top centroids (by cluster size)
    return [
        kmeans.cluster_centers_[cluster_id].tolist()
        for cluster_id, _ in sorted_clusters[:10]
    ]

if __name__ == "__main__":
    insights = get_user_interests()
    print("User Interest Insights:")
    print(f"Top Keywords: {insights['keywords'][:5]}...")
    print(f"Top Themes: {insights['themes']}")
    print(f"Top Moods: {insights['moods']}")
    print(f"7d Avg Embedding: {len(insights['avg_embedding_7d']) if insights['avg_embedding_7d'] else 0} dimensions")
    print(f"Top Color Clusters: {len(insights['top_colors'])} clusters")