from PIL import Image
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from core.content.images import extract_distinct_colors
import cv2

file_path = "/root/projects/BUILDMODE-Server/uploads/0a8e38e2493743538499dfa6726f5417.jpg"

def extract_distinct_colors2(image_path, num_clusters=30, num_colors=10):
    # Load and shrink
    img = Image.open(image_path).convert('RGB').resize((160, 160))
    rgb = np.array(img)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3)

    km = MiniBatchKMeans(n_clusters=num_clusters, random_state=42, batch_size=4096)
    labels = km.fit_predict(lab)
    centers_lab = km.cluster_centers_

    # Count cluster frequency
    counts = np.bincount(labels, minlength=num_clusters)
    top_idx = counts.argsort()[::-1][:num_colors]
    top_lab = centers_lab[top_idx].astype(np.float32)[None, :, :]  # (1,N,3)

    # Convert back to RGB
    top_lab_img = top_lab.repeat(10, axis=0)  # fake small image for conversion stability
    top_rgb_img = cv2.cvtColor(top_lab_img.astype(np.uint8), cv2.COLOR_Lab2RGB)
    top_rgb = top_rgb_img[0].astype(np.float32) / 255.0  # (N,3) in [0,1]

    # Flatten & pad to fixed length
    vec = top_rgb.reshape(-1).tolist()  # length = 3*num_colors
    if len(vec) < 3*num_colors:
        vec += [0.0] * (3*num_colors - len(vec))
    print(f"vec: {vec}")
    return vec

extract_distinct_colors(image_path=file_path)
extract_distinct_colors2(image_path=file_path)