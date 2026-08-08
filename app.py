#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国語 活用の種類・活用形 マークシートテスト（縦書き・20問・4/5/6択混在・解答用紙1枚）採点
— ブラウザ用APIサーバー（ローカル実行 / Renderなどへのデプロイ両対応）。

ローカル起動:
  python app.py
起動後 http://127.0.0.1:8016 をブラウザで開く。

Renderなどにデプロイする場合は環境変数 PORT が自動的に使われる
（gunicorn app:app で起動する場合はこのブロックは実行されない）。

採点ロジック本体は grade_katsuyokei20.py のものをそのまま再利用する。
アップロードは1人1ファイル（画像 または 1ページのPDF）。複数ページPDFは1ページ=1名分。
"""
import base64
import os
from pathlib import Path

import cv2
import fitz
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from grade_katsuyokei20 import (
    ALL_CHOICES,
    CHOICE_COUNTS,
    N_QUESTIONS,
    POINTS_PER_QUESTION,
    REF_PDF,
    align_scan,
    extract_circle_grid,
    extract_score_box_position,
    grade_one_page,
    load_answer_key,
    read_page_as_bgr,
)

BASE_DIR = Path(__file__).parent
JPEG_QUALITY = [int(cv2.IMWRITE_JPEG_QUALITY), 80]

app = Flask(__name__, static_folder=None)

KEY = load_answer_key()
GRID = extract_circle_grid(REF_PDF)
SCORE_BOX_FRAC = extract_score_box_position(REF_PDF)


def format_score(score):
    return str(int(score)) if float(score) == int(score) else f"{score:.1f}"


def draw_score_text(img_bgr, score, frac_pos):
    """解答用紙の「得点」欄（空欄セル）に得点を書き込む。"""
    fx, fy = frac_pos
    h, w = img_bgr.shape[:2]
    cx, cy = int(fx * w), int(fy * h)
    text = format_score(score)
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = h / 850.0
    thickness = max(2, round(font_scale * 2))
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    org = (cx - tw // 2, cy + th // 2)
    cv2.putText(img_bgr, text, org, font, font_scale, (0, 0, 200), thickness, cv2.LINE_AA)


def draw_overlay(img_bgr, marks, radius_px, score):
    """解答用紙に、選んだ記号の○を緑（正解）／赤（誤答）で塗りつぶし、得点欄に得点を書き込んで返す。"""
    img = img_bgr.copy()
    h, w = img.shape[:2]
    mark_radius = radius_px + 5
    for q in range(1, N_QUESTIONS + 1):
        m, k = marks[q - 1], KEY[q - 1]
        if m in ("-", "?"):
            continue
        n = CHOICE_COUNTS[q]
        idx = ALL_CHOICES[:n].index(m)
        fx, fy = GRID[q][idx]
        cx, cy = int(fx * w), int(fy * h)
        color = (0, 150, 0) if m == k else (0, 0, 255)
        cv2.circle(img, (cx, cy), mark_radius, color, -1)
    draw_score_text(img, score, SCORE_BOX_FRAC)
    return img


def to_data_url(img_bgr):
    _, buf = cv2.imencode(".jpg", img_bgr, JPEG_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")


@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/api/answer_key")
def api_answer_key():
    return jsonify({"n_questions": N_QUESTIONS, "key": KEY, "choice_counts": CHOICE_COUNTS})


@app.route("/api/grade", methods=["POST"])
def api_grade():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "採点するファイルがアップロードされていません。"}), 400

    try:
        dpi = int(request.form.get("dpi", 200))
    except ValueError:
        dpi = 200
    radius_px = max(6, round(dpi / 200 * 12))

    results = []
    for f in files:
        data = f.read()
        suffix = Path(f.filename or "").suffix.lower()

        if suffix == ".pdf":
            try:
                doc = fitz.open(stream=data, filetype="pdf")
            except Exception as e:
                results.append({"name": f.filename, "error": f"PDFを読み込めませんでした: {e}"})
                continue
            pages = [(f"{f.filename} (p{i + 1})", read_page_as_bgr(doc[i], dpi)) for i in range(doc.page_count)]
        else:
            arr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                results.append({"name": f.filename, "error": "画像を読み込めませんでした。"})
                continue
            pages = [(f.filename, img)]

        for name, img_bgr in pages:
            warped, info = align_scan(img_bgr)
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            marks = grade_one_page(gray, GRID, radius_px)
            correct = sum(1 for m, k in zip(marks, KEY) if m == k)
            score = correct * POINTS_PER_QUESTION
            total = N_QUESTIONS * POINTS_PER_QUESTION
            wrong = [i + 1 for i, (m, k) in enumerate(zip(marks, KEY)) if m not in ("-", "?") and m != k]
            unclear = [i + 1 for i, m in enumerate(marks) if m in ("-", "?")]
            overlay = draw_overlay(warped, marks, radius_px, score)

            results.append({
                "name": name,
                "score": score,
                "total": total,
                "marks": marks,
                "answer_key": KEY,
                "wrong": wrong,
                "unclear": unclear,
                "aligned": info is not None,
                "overlay_image": to_data_url(overlay),
            })

    return jsonify({"results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8016))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    app.run(host=host, port=port, debug=False)
