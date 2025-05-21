from PIL import Image
from sklearn.cluster import KMeans
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
import numpy as np

def rgb_to_lab(rgb):
    srgb = sRGBColor(rgb[0]/255, rgb[1]/255, rgb[2]/255)
    return convert_color(srgb, LabColor)

def merge_similar_colors(colors, threshold=20):
    distinct = []
    for color in colors:
        lab1 = rgb_to_lab(color)
        if all(delta_e_cie2000(lab1, rgb_to_lab(other)) > threshold for other in distinct):
            distinct.append(color)
    return distinct

def extract_distinct_colors(image_path, num_clusters=30, num_colors=10, merge_threshold=20):
    image = Image.open(image_path).convert('RGB')
    image = image.resize((100, 100))  # speed
    pixels = np.array(image).reshape(-1, 3)

    kmeans = KMeans(n_clusters=num_clusters, random_state=42).fit(pixels)
    centers = kmeans.cluster_centers_.astype(int)

    merged = merge_similar_colors(centers, threshold=merge_threshold)
    merged = sorted(merged, key=lambda c: -np.sum((pixels == c).all(axis=1)))  # sort by frequency

    # Count frequency of each merged color
    color_counts = []
    for color in merged:
        mask = np.linalg.norm(pixels - color, axis=1) < merge_threshold
        count = np.sum(mask)
        color_counts.append((color, count))

    # Sort by count descending
    color_counts.sort(key=lambda x: -x[1])
    top_colors = [tuple(map(int, color)) for color, _ in color_counts[:num_colors]]
    print(f"Num of colors: {num_colors}")
    print(f"Distinct colors: {top_colors}")

    # Pad to fixed length
    flat_rgb = [v for color in top_colors for v in color]
    padded_rgb = flat_rgb + [0] * (3 * num_colors - len(flat_rgb))
    print(f"Padded RGB: {padded_rgb}")

    flat_rgb = [v / 255.0 for color in top_colors for v in color]  # normalize to [0,1]
    padded_rgb = flat_rgb + [0.0] * (3 * num_colors - len(flat_rgb))
    return padded_rgb