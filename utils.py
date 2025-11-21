# backend/utils.py
import cv2
import numpy as np

def preprocess_image_for_model(image_path, target_size=(128, 128)):
    """
    Loads image from disk, returns (tensor_batch, original_shape)
    - Ensures RGB ordering and same normalization as training (/255.0).
    """
    img = cv2.imread(image_path)  # BGR
    if img is None:
        raise FileNotFoundError(image_path)
    orig_h, orig_w = img.shape[:2]
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_resized = cv2.resize(img_rgb, target_size, interpolation=cv2.INTER_AREA)
    img_resized = img_resized.astype("float32") / 255.0
    # return batch dimension
    return np.expand_dims(img_resized, axis=0), (orig_h, orig_w)


def postprocess_mask(mask_bin, kernel_size=5, min_area=50):
    """
    mask_bin: binary 2D array 0/1 (numpy)
    Return cleaned binary mask (0/1 uint8).
    """
    # normalize to 0..255 uint8 for morphology
    mask = (mask_bin * 255).astype("uint8")
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    # remove small components
    contours_info = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # OpenCV version compatibility
    contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

    out = np.zeros_like(mask)
    for c in contours:
        if cv2.contourArea(c) >= min_area:
            cv2.drawContours(out, [c], -1, 255, -1)

    out = (out > 127).astype("uint8")
    return out


def estimate_leaf_mask_from_rgb(img_rgb):
    """
    Estimate leaf area using HSV color heuristic.
    img_rgb expected [H,W,3] uint8 or float scaled 0..1
    Returns binary mask (0/1 uint8).
    """
    if img_rgb.dtype != np.uint8:
        img = (np.clip(img_rgb, 0.0, 1.0) * 255).astype("uint8")
    else:
        img = img_rgb

    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

    # Tuned range for green leaves; adjust if needed for your dataset
    lower = np.array([25, 30, 20])
    upper = np.array([100, 255, 255])
    leaf_mask = cv2.inRange(hsv, lower, upper)
    leaf_mask = (leaf_mask > 0).astype("uint8")
    leaf_mask = postprocess_mask(leaf_mask, kernel_size=7, min_area=200)
    return leaf_mask


def calculate_severity_label_and_percent(disease_mask_full, orig_image_path, leaf_mask_from_model=None):
    """
    disease_mask_full: 2D binary (0/1) at original image size (H_orig, W_orig).
    If leaf_mask_from_model provided, use it; otherwise estimate from original image.
    Returns: (label_str, severity_percent_float, leaf_mask_used)
    """
    import cv2
    import numpy as np

    if leaf_mask_from_model is None:
        img = cv2.imread(orig_image_path)
        if img is None:
            raise FileNotFoundError(orig_image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        leaf_mask = estimate_leaf_mask_from_rgb(img_rgb)
    else:
        leaf_mask = (leaf_mask_from_model > 0).astype("uint8")

    leaf_px = int(np.sum(leaf_mask))
    disease_px = int(np.sum(disease_mask_full))

    if leaf_px == 0:
        severity_percent = 0.0
    else:
        severity_percent = (disease_px / leaf_px) * 100.0

    if severity_percent < 5.0:
        label = "Healthy (<5%)"
    elif severity_percent < 20.0:
        label = "Mild (5%-20%)"
    elif severity_percent < 50.0:
        label = "Moderate (20%-50%)"
    else:
        label = "Severe (>50%)"

    return label, severity_percent, leaf_mask
