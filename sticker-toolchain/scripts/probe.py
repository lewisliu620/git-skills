# -*- coding: utf-8 -*-
"""背景色采样诊断：角点中位数背景色、到纯白的距离、背景像素占比。用于确定去底 T0/T1。"""
import os, sys, glob
from PIL import Image
import numpy as np

def main(raw_dir=None, limit=5):
    raw_dir = raw_dir or os.path.join(os.getcwd(), "01_raw")
    files = sorted(glob.glob(os.path.join(raw_dir, "*.png")))
    if not files:
        print("未找到 PNG，请传原始生成图目录或确认 01_raw 存在"); return
    for fp in files[:limit]:
        im = Image.open(fp).convert("RGB")
        a = np.asarray(im)
        h, w, _ = a.shape
        corners = []
        for (y0, x0) in [(0, 0), (0, w - 10), (h - 10, 0), (h - 10, w - 10)]:
            patch = a[y0:y0 + 10, x0:x0 + 10].reshape(-1, 3)
            corners.append(np.median(patch, axis=0))
        bg = np.median(np.array(corners), axis=0)
        d_white = np.linalg.norm(np.array([255, 255, 255]) - bg)
        d_all = np.linalg.norm(a.astype(float) - bg, axis=2)
        frac_bg = (d_all < 12).mean()
        print(os.path.basename(fp), "bg=", bg.round(1), "d_white=%.1f" % d_white, "frac_bg12=%.3f" % frac_bg)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
