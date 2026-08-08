#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国語 活用の種類・活用形 マークシートテスト（縦書き・20問・4/5/6択混在・解答用紙1枚）
マークシート（塗りつぶし式解答用紙）自動採点スクリプト。

小5国語_中間テスト_20問ver の grade_kokugo20.py（四隅マーカー較正付き）を、
「問題ごとに選択肢の数が4択・5択・6択と異なる」解答用紙に合わせて拡張したもの。
問１〜１０＝６択、問１１〜１６＝５択、問１７〜２０＝４択（mark.tex のレイアウトと対応）。

しくみ:
  1. mark.pdf（デジタル生成された基準PDF）の解答用紙ページから
     ○の中心座標をベクトル図形として読み取り、問1〜20・各問の選択肢に対応付ける。
  2. 生徒がぬりつぶした解答用紙をスキャンした画像/PDFを読み込む（1人1ページ）。
  3. 解答用紙四隅の■マーカー（\\drawmarkers）を使ってページの傾き・ズレを補正し、
     各○の位置の黒さ（濃さ）を測定して、最も濃い選択肢をぬりつぶされた解答と判定する。
  4. answer_key.json と照合して採点し、CSVに出力する。

使い方:
  python grade_katsuyokei20.py 生徒A.pdf 生徒B.pdf ...   （1人1ファイル、または1ページ=1名の複数ページPDF）
  python grade_katsuyokei20.py --dir スキャンフォルダ    # フォルダ内をまとめて採点

出力: 採点結果_活用形20問.csv （このスクリプトと同じフォルダに作成）
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import cv2
import fitz
import numpy as np

BASE_DIR = Path(__file__).parent
REF_PDF = BASE_DIR / "mark.pdf"
ANSWER_KEY_PATH = BASE_DIR / "answer_key.json"

# mark.pdf は8ページ構成：1=表紙, 2〜5=問題, 6=解答用紙, 7〜8=解答一覧
# 0始まりページ番号：
ANSWER_SHEET_PAGE_INDEX = 5

N_QUESTIONS = 20
POINTS_PER_QUESTION = 5  # 1問5点 (20問×5点=100点満点)
ALL_CHOICES = ["ア", "イ", "ウ", "エ", "オ", "カ"]

# 問番号(1始まり) -> その問の選択肢数。mark.tex の【1】【2】【3】の構成と対応。
CHOICE_COUNTS = {}
for q in range(1, 11):
    CHOICE_COUNTS[q] = 6
for q in range(11, 17):
    CHOICE_COUNTS[q] = 5
for q in range(17, 21):
    CHOICE_COUNTS[q] = 4

PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
MX, MY = 12.5 / PAGE_W_MM, 12.5 / PAGE_H_MM  # \drawmarkers の■中心は各辺から1.25cm
REF_CORNERS_FRAC = {
    "tl": (MX, MY), "tr": (1 - MX, MY),
    "bl": (MX, 1 - MY), "br": (1 - MX, 1 - MY),
}


def load_answer_key():
    data = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    return [data[str(i)] for i in range(1, N_QUESTIONS + 1)]


def _small_square_drawings(page):
    """ページ内の「一辺8〜16pt程度の正方形状ベクトル図形」を、ぬりつぶし（四隅マーカー＝
    \\drawmarkersの黒四角）と線のみ（解答用紙の○）に分けて返す。
    注意：LuaTeX(dvipdfmx)が出力するPDFでは、TikZの絶対配置図形の座標が、PyMuPDFの
    page.rect（0〜paperwidth/height）とは異なる原点オフセットを持つことがある
    （実測で確認済み）。そのため page.rect を使った単純な比率換算はできず、既知の物理位置を
    持つ四隅マーカー自身を基準に較正する（extract_circle_grid 参照）。"""
    fills, strokes = [], []
    for d in page.get_drawings():
        r = d["rect"]
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if 8 < w < 16 and 8 < h < 16 and abs(w - h) < 2:
            pt = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            if d.get("fill") is not None:
                fills.append(pt)
            else:
                strokes.append(pt)
    return fills, strokes


def _calibrate_from_markers(fills):
    """4つの四隅マーカー（生座標）から、生座標→ページ比率(0〜1)への線形変換を作る。
    マーカー中心は各辺から1.25cm（MX, MY）の位置にあるという既知の設計値を使う。"""
    if len(fills) < 4:
        raise RuntimeError(
            f"四隅マーカー（\\drawmarkers）候補が4個未満でした（検出数={len(fills)}）。"
        )
    cx = sum(p[0] for p in fills) / len(fills)
    cy = sum(p[1] for p in fills) / len(fills)
    quadrants = {"tl": [], "tr": [], "bl": [], "br": []}
    for p in fills:
        key = ("t" if p[1] < cy else "b") + ("l" if p[0] < cx else "r")
        quadrants[key].append(p)
    corners = {}
    for key, pts in quadrants.items():
        if not pts:
            raise RuntimeError(
                f"四隅マーカーの候補から「{key}」側の点が見つかりませんでした"
                f"（候補={fills}）。"
            )
        corners[key] = max(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    x_min = (corners["tl"][0] + corners["bl"][0]) / 2
    x_max = (corners["tr"][0] + corners["br"][0]) / 2
    y_min = (corners["tl"][1] + corners["tr"][1]) / 2
    y_max = (corners["bl"][1] + corners["br"][1]) / 2
    if x_max - x_min < 1 or y_max - y_min < 1:
        raise RuntimeError("四隅マーカーの検出位置が不正です（幅または高さがほぼ0）。")

    def to_frac(pt):
        x, y = pt
        fx = MX + (x - x_min) / (x_max - x_min) * (1 - 2 * MX)
        fy = MY + (y - y_min) / (y_max - y_min) * (1 - 2 * MY)
        return fx, fy

    return to_frac


def extract_circle_grid(ref_pdf_path):
    """基準PDFの解答用紙ページ（1枚）から○の中心座標(ページ比率、四隅マーカー基準で較正済み)を
    抽出し、{問番号1〜20: [(fx,fy)_ア, (fx,fy)_イ, ...]}（各問CHOICE_COUNTS[問]個）を返す。
    問番号は左ブロック（1〜10・各6択）→右ブロック（11〜20・11〜16は5択、17〜20は4択）の順。
    ○の並びは選択肢を左詰めで描画しているため（灰色の未使用○は描かない仕様）、各行の
    ○の個数がそのままその問の選択肢数と一致する。"""
    doc = fitz.open(str(ref_pdf_path))
    page = doc[ANSWER_SHEET_PAGE_INDEX]
    fills, strokes = _small_square_drawings(page)
    to_frac = _calibrate_from_markers(fills)

    pts = strokes
    pts.sort(key=lambda p: (round(p[1]), p[0]))
    rows, cur, last_y = [], [], None
    for x, y in pts:
        if last_y is not None and abs(y - last_y) > 6:
            rows.append(cur)
            cur = []
        cur.append((x, y))
        last_y = y
    if cur:
        rows.append(cur)

    def split_columns(row):
        row = sorted(row, key=lambda p: p[0])
        groups, cur = [], [row[0]]
        for prev, nxt in zip(row, row[1:]):
            if nxt[0] - prev[0] > 50:
                groups.append(cur)
                cur = []
            cur.append(nxt)
        groups.append(cur)
        return groups

    quads = []
    for row in rows:
        for grp in split_columns(row):
            if 4 <= len(grp) <= 6:
                quads.append(sorted(grp, key=lambda p: p[0]))

    if len(quads) != N_QUESTIONS:
        raise RuntimeError(
            f"○のかたまりを{N_QUESTIONS}問分検出できませんでした（検出数={len(quads)}）。"
            " mark.tex の解答用紙レイアウトが変更されていないか確認してください。"
        )

    x_mid = (min(p[0] for grp in quads for p in grp) + max(p[0] for grp in quads for p in grp)) / 2
    left = sorted([g for g in quads if g[0][0] < x_mid], key=lambda g: g[0][1])
    right = sorted([g for g in quads if g[0][0] >= x_mid], key=lambda g: g[0][1])
    if len(left) != N_QUESTIONS // 2 or len(right) != N_QUESTIONS // 2:
        raise RuntimeError(f"左右ブロックの行数が想定外です（左={len(left)}, 右={len(right)}）。")

    grid = {}
    for i, grp in enumerate(left):
        q = i + 1
        expected = CHOICE_COUNTS[q]
        if len(grp) != expected:
            raise RuntimeError(f"問{q}の○の数が想定と異なります（期待={expected}, 検出={len(grp)}）。")
        grid[q] = [to_frac(p) for p in grp]
    for i, grp in enumerate(right):
        q = i + 1 + N_QUESTIONS // 2
        expected = CHOICE_COUNTS[q]
        if len(grp) != expected:
            raise RuntimeError(f"問{q}の○の数が想定と異なります（期待={expected}, 検出={len(grp)}）。")
        grid[q] = [to_frac(p) for p in grp]
    return grid


def extract_score_box_position(ref_pdf_path, page_index=None):
    """基準PDFの解答用紙ページから「得点」欄（記入用の空欄セル）の中心位置を、
    ページ比率(0〜1、四隅マーカー基準で較正済み)で返す。採点後の答案画像に
    得点を書き込む（draw_overlay内）際の位置として使う。"""
    if page_index is None:
        page_index = ANSWER_SHEET_PAGE_INDEX
    doc = fitz.open(str(ref_pdf_path))
    page = doc[page_index]
    fills, _ = _small_square_drawings(page)
    to_frac = _calibrate_from_markers(fills)

    hits = page.search_for("得点")
    if not hits:
        raise RuntimeError("解答用紙に「得点」の文字が見つかりませんでした。")
    label = hits[0]
    label_xmid = (label.x0 + label.x1) / 2

    h_lines, v_lines = [], []
    for d in page.get_drawings():
        r = d["rect"]
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if h < 0.5 and w > 5:
            h_lines.append((r.y0, r.x0, r.x1))
        elif w < 0.5 and h > 5:
            v_lines.append((r.x0, r.y0, r.y1))

    below = sorted(
        y for (y, x0, x1) in h_lines if x0 - 2 <= label_xmid <= x1 + 2 and y > label.y1 - 1
    )
    if len(below) < 2:
        raise RuntimeError("得点欄のセル罫線（上下）を検出できませんでした。")
    cell_top, cell_bottom = below[0], below[1]

    xs_here = [x for (x, y0, y1) in v_lines if y0 - 2 <= label.y0 and y1 + 2 >= label.y1]
    left_candidates = [x for x in xs_here if x <= label_xmid]
    right_candidates = [x for x in xs_here if x >= label_xmid]
    if not left_candidates or not right_candidates:
        raise RuntimeError("得点欄のセル罫線（左右）を検出できませんでした。")
    cell_left, cell_right = max(left_candidates), min(right_candidates)

    cx = (cell_left + cell_right) / 2
    cy = (cell_top + cell_bottom) / 2
    return to_frac((cx, cy))


def detect_corner(gray, corner, roi_frac=0.15, dark_thresh=120):
    h, w = gray.shape
    rw, rh = int(w * roi_frac), int(h * roi_frac)
    if corner == "tl":
        roi, ox, oy = gray[0:rh, 0:rw], 0, 0
    elif corner == "tr":
        roi, ox, oy = gray[0:rh, w - rw:w], w - rw, 0
    elif corner == "bl":
        roi, ox, oy = gray[h - rh:h, 0:rw], 0, h - rh
    else:
        roi, ox, oy = gray[h - rh:h, w - rw:w], w - rw, h - rh
    _, mask = cv2.threshold(roi, dark_thresh, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < 20:
        return None
    M = cv2.moments(best)
    if M["m00"] == 0:
        return None
    return ox + M["m10"] / M["m00"], oy + M["m01"] / M["m00"]


def align_scan(img_bgr):
    """解答用紙四隅の■マーカーを検出し、傾き・ズレを射影変換で補正する。
    検出できなければ (元画像, None) を返す。"""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    detected = {}
    for corner in ("tl", "tr", "bl", "br"):
        pt = detect_corner(gray, corner)
        if pt is None:
            return img_bgr, None
        detected[corner] = pt
    src = np.float32([detected["tl"], detected["tr"], detected["bl"], detected["br"]])
    dst = np.float32([
        (REF_CORNERS_FRAC[c][0] * w, REF_CORNERS_FRAC[c][1] * h)
        for c in ("tl", "tr", "bl", "br")
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img_bgr, M, (w, h), borderValue=(255, 255, 255))
    return warped, (src, dst)


def read_page_as_bgr(page, dpi):
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)


def grade_one_page(gray, grid, radius_px, fill_thresh=35, ambiguous_gap=8):
    """解答用紙1枚（20問）を採点し、問1〜20順のmarksリストを返す。
    各問の選択肢数はCHOICE_COUNTSに従い、問ごとに可変（4/5/6択）。"""
    h, w = gray.shape
    marks = []
    for q in range(1, N_QUESTIONS + 1):
        n = CHOICE_COUNTS[q]
        readings = []
        for letter, (fx, fy) in zip(ALL_CHOICES[:n], grid[q]):
            cx, cy = int(fx * w), int(fy * h)
            y0, y1 = max(0, cy - radius_px), min(h, cy + radius_px)
            x0, x1 = max(0, cx - radius_px), min(w, cx + radius_px)
            patch = gray[y0:y1, x0:x1]
            darkness = 255 - float(patch.mean()) if patch.size else 0.0
            readings.append((letter, darkness))
        readings.sort(key=lambda t: -t[1])
        best_letter, best_dark = readings[0]
        second_dark = readings[1][1] if len(readings) > 1 else -1.0
        if best_dark < fill_thresh:
            marks.append("-")  # 無回答
        elif best_dark - second_dark < ambiguous_gap:
            marks.append("?")  # 複数塗り／判定困難
        else:
            marks.append(best_letter)
    return marks


def process_source(path, dpi):
    """1ファイル(画像 or 複数ページPDF)を読み込み、[(名前, グレースケール画像), ...] を返す。
    複数ページPDFは1ページ=1名分として扱う。"""
    path = Path(path)
    out = []
    if path.suffix.lower() == ".pdf":
        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            img_bgr = read_page_as_bgr(page, dpi)
            warped, info = align_scan(img_bgr)
            if info is None:
                print(f"  [警告] {path.name} p{i + 1}: 四隅マーカーを検出できず、補正なしで採点します。")
            label = path.stem if doc.page_count == 1 else f"{path.stem}_p{i + 1}"
            out.append((label, cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)))
    else:
        img_bgr = cv2.imread(str(path))
        if img_bgr is None:
            print(f"  [エラー] 読み込めません: {path}")
            return out
        warped, info = align_scan(img_bgr)
        if info is None:
            print(f"  [警告] {path.name}: 四隅マーカーを検出できず、補正なしで採点します。")
        out.append((path.stem, cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)))
    return out


def grade_student(name, gray, key, radius_px):
    marks = grade_one_page(gray, GRID, radius_px)
    correct = sum(1 for m, k in zip(marks, key) if m == k)
    score = correct * POINTS_PER_QUESTION
    wrong = [i + 1 for i, (m, k) in enumerate(zip(marks, key)) if m not in ("-", "?") and m != k]
    unclear = [i + 1 for i, m in enumerate(marks) if m in ("-", "?")]
    return {"marks": marks, "score": score, "correct": correct, "wrong": wrong, "unclear": unclear}


KEY = None
GRID = None


def _init_globals():
    global KEY, GRID
    if KEY is None:
        KEY = load_answer_key()
    if GRID is None:
        GRID = extract_circle_grid(REF_PDF)


def main():
    parser = argparse.ArgumentParser(
        description="国語 活用の種類・活用形 マークシートテスト(20問・4/5/6択混在) 自動採点"
    )
    parser.add_argument("sources", nargs="*", help="スキャンしたPDF/画像ファイル（複数指定可）")
    parser.add_argument("--dir", help="このフォルダ内の.pdf/.png/.jpgをまとめて採点")
    parser.add_argument("--dpi", type=int, default=200, help="スキャン解像度(デフォルト200dpi)")
    args = parser.parse_args()

    sources = [Path(s) for s in args.sources]
    if args.dir:
        d = Path(args.dir)
        sources += sorted(p for p in d.iterdir() if p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"))
    if not sources:
        parser.error("採点するファイルを指定してください（引数 または --dir）。")

    _init_globals()
    radius_px = max(6, round(args.dpi / 200 * 12))

    rows = []
    max_score = N_QUESTIONS * POINTS_PER_QUESTION
    print(f"{'name':<28}{'score':>6}  detail")
    print("-" * 100)
    for src in sources:
        for name, gray in process_source(src, args.dpi):
            result = grade_student(name, gray, KEY, radius_px)
            note = f"wrong={result['wrong']}" if result["wrong"] else "no wrong"
            if result["unclear"]:
                note += f" / unclear={result['unclear']}"
            print(f"{name:<28}{result['score']:>4}/{max_score}  {note}")
            rows.append([datetime.now().strftime("%Y-%m-%d"), name, result["score"]] + result["marks"])

    if rows:
        header = ["採点日", "ファイル名", "得点"] + [f"問{i}" for i in range(1, N_QUESTIONS + 1)]
        out_path = BASE_DIR / "採点結果_活用形20問.csv"
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        print(f"\nCSV出力: {out_path}")


if __name__ == "__main__":
    main()
