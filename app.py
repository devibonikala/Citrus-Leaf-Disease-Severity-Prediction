# backend/app.py

import os
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import numpy as np
import cv2
import uuid
import traceback
import tensorflow as tf
from flask_cors import CORS

from utils import preprocess_image_for_model, postprocess_mask, calculate_severity_label_and_percent

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PRED_DIR = os.path.join(BASE_DIR, "predictions")
MODEL_PATH = os.path.join(BASE_DIR, "model", "citrus_model.h5")

IMG_SIZE = (128, 128)
THRESH = 0.5
ALLOWED_EXT = {"png", "jpg", "jpeg"}
CLASS_NAMES = ["Blackspot", "Canker", "Greening", "Healthy", "Melanose"]

# -------------------------------------------------------

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PRED_DIR, exist_ok=True)

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "..", "frontend"),
    static_url_path="/"
)

# Allow CORS for API (useful if frontend served from different origin)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---- LOAD MODEL ONCE ----
print("Loading model from:", MODEL_PATH)
model = tf.keras.models.load_model(MODEL_PATH, compile=False)
print("Model loaded.")

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# Serve frontend
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(app.static_folder, filename)

# API
@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        if "image" not in request.files:
            return jsonify({"error": "No file part named 'image'"}), 400

        f = request.files["image"]
        if f.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(f.filename):
            return jsonify({"error": "File type not allowed"}), 400

        # Save upload
        filename = secure_filename(f.filename)
        uid = str(uuid.uuid4())[:8]
        saved_name = f"{uid}_{filename}"
        saved_path = os.path.join(UPLOAD_DIR, saved_name)
        f.save(saved_path)

        # Preprocess (this returns a batch and original size)
        input_tensor, orig_shape = preprocess_image_for_model(saved_path, target_size=IMG_SIZE)

        # Predict
        preds = model.predict(input_tensor)

        # Support common output formats:
        pred_mask_probs = None
        pred_class_probs = None

        if isinstance(preds, (list, tuple)) and len(preds) == 2:
            pred_mask_probs, pred_class_probs = preds[0], preds[1]
        elif isinstance(preds, dict):
            # try common keys
            pred_mask_probs = preds.get("mask") or preds.get("pred_mask") or preds.get("seg")
            pred_class_probs = preds.get("class") or preds.get("pred_class") or preds.get("label")
            # If values are single arrays, wrap handling below will manage
        else:
            # single-array output -> assume mask (segmentation-only)
            pred_mask_probs = preds

        if pred_mask_probs is None:
            return jsonify({"error": "Model did not return segmentation output"}), 500

        # Get first (and only) sample
        mask_prob = pred_mask_probs[0]
        # if (H,W,1) convert to (H,W)
        if mask_prob.ndim == 3 and mask_prob.shape[-1] == 1:
            mask_prob = mask_prob[..., 0]

        # Threshold and postprocess
        mask_bin = (mask_prob > THRESH).astype(np.uint8)
        mask_bin = postprocess_mask(mask_bin)

        # Resize mask back to original image size
        orig_H, orig_W = orig_shape
        mask_resized = cv2.resize(mask_bin, (orig_W, orig_H), interpolation=cv2.INTER_NEAREST)

        disease_mask_full = mask_resized  # 0/1 uint8

        # Classification branch (if present)
        predicted_class = None
        predicted_class_prob = None
        if pred_class_probs is not None:
            probs = np.asarray(pred_class_probs)[0]
            idx = int(np.argmax(probs))
            if idx < len(CLASS_NAMES):
                predicted_class = CLASS_NAMES[idx]
            else:
                predicted_class = str(idx)
            predicted_class_prob = float(probs[idx])

        # Severity computation (leaf estimate inside utility if needed)
        severity_label, severity_percent, leaf_mask_used = calculate_severity_label_and_percent(
            disease_mask_full, saved_path, leaf_mask_from_model=None
        )

        # Save outputs: mask (single-channel) and overlay (bgr)
        base = f"{uid}_{os.path.splitext(filename)[0]}"
        mask_out_path = os.path.join(PRED_DIR, base + "_mask.png")
        overlay_out_path = os.path.join(PRED_DIR, base + "_overlay.png")

        # mask_out: 0/255 uint8
        cv2.imwrite(mask_out_path, (mask_resized * 255).astype("uint8"))

        # overlay: paint disease red on original image (BGR). We'll blend to be clearer.
        orig_bgr = cv2.imread(saved_path)  # BGR
        if orig_bgr is None:
            raise FileNotFoundError(saved_path)

        overlay = orig_bgr.copy()
        # paint mask pixels red (BGR space -> red = [0,0,255])
        overlay[mask_resized == 1] = [0, 0, 255]
        # blend original + overlay for semi-transparent effect
        blended = cv2.addWeighted(orig_bgr, 0.6, overlay, 0.4, 0)
        cv2.imwrite(overlay_out_path, blended)

        return jsonify({
            "status": "ok",
            "filename": filename,
            "predicted_class": predicted_class,
            "predicted_class_prob": predicted_class_prob,
            "severity_label": severity_label,
            "severity_percent": float(round(severity_percent, 2)),
            "mask_url": f"/predictions/{os.path.basename(mask_out_path)}",
            "overlay_url": f"/predictions/{os.path.basename(overlay_out_path)}"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# Serve prediction images
@app.route("/predictions/<path:fname>")
def serve_prediction(fname):
    return send_from_directory(PRED_DIR, fname)


if __name__ == "__main__":
    # debug True for local development. Set False (and use a WSGI server) in production.
    app.run(host="0.0.0.0", port=5000, debug=True)
