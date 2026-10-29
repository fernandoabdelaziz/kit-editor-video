"""Silhueta do apresentador por quadro (roda no .venv-pessoa, MediaPipe Tasks local, modelo selfie_segmenter).

Uso: .venv-pessoa/bin/python pessoa_seg.py VIDEO SAIDA.npz --quadros 0,8,15,... [--escala 4] [--margem 28]
Decodifica o vídeo uma vez (ffmpeg, 1/2 da resolução), segmenta só os quadros pedidos, fica com a maior
mancha (a pessoa; o reflexo solto na mesa fica de fora, a não ser com --reflexo), fecha buracos, dilata pela margem
e grava as máscaras em 1/escala da resolução (uint8 0/1) num .npz. Nada sai da máquina: o modelo está em
<raiz>/.modelos-pessoa/ (baixado uma vez pelo install.sh do repositório público do MediaPipe, com sha256 conferido).
O caminho pode ser trocado com --modelo ou com a variável KIT_RAIZ.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kitlib.comum import MODELO_PESSOA  # noqa: E402  (só stdlib)

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("saida")
ap.add_argument("--quadros", required=True)
ap.add_argument("--escala", type=int, default=4)
ap.add_argument("--margem", type=int, default=28, help="px na resolução cheia")
ap.add_argument("--modelo", default=str(MODELO_PESSOA), help="selfie_segmenter.tflite")
ap.add_argument("--reflexo", action="store_true", help="considera também manchas soltas (ex.: reflexo na mesa)")
a = ap.parse_args()
pedidos = sorted({int(x) for x in a.quadros.split(",") if x != ""})
p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                    "-of", "json", a.video], capture_output=True, text=True)
st = json.loads(p.stdout)["streams"][0]
W, H = st["width"], st["height"]
w2, h2 = W // 2, H // 2
proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"scale={w2}:{h2}", "-f", "rawvideo",
                         "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=BaseOptions(model_asset_path=a.modelo), output_confidence_masks=True, output_category_mask=False))
alvo = set(pedidos)
ws, hs = W // a.escala, H // a.escala
r_dil = max(1, round(a.margem / a.escala))
ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_dil + 1, 2 * r_dil + 1))
out, n, ultimo = {}, 0, max(pedidos)
tam = w2 * h2 * 3
while n <= ultimo:
    buf = proc.stdout.read(tam)
    if len(buf) < tam:
        break
    if n in alvo:
        img = np.frombuffer(buf, np.uint8).reshape(h2, w2, 3)
        r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)))
        m = (r.confidence_masks[0].numpy_view().squeeze() > 0.5).astype(np.uint8)
        m = cv2.resize(m, (ws, hs), interpolation=cv2.INTER_NEAREST)
        k, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        if k > 1:
            maior = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            if not a.reflexo:
                m = (lab == maior).astype(np.uint8)
            # fecha buracos (gravata, vão entre braço e corpo pequeno)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
            cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(m, cs, -1, 1, thickness=cv2.FILLED)
        m = cv2.dilate(m, ker)
        out[f"q{n}"] = m
    n += 1
proc.stdout.close(); proc.wait()
seg.close()
falta = [q for q in pedidos if f"q{q}" not in out]
if falta:
    print(f"aviso: quadros além do fim: {falta[:5]}", file=sys.stderr)
np.savez_compressed(a.saida, W=W, H=H, escala=a.escala, margem=a.margem, **out)
print(json.dumps(dict(quadros=len(out), W=W, H=H, escala=a.escala, margem=a.margem)))
