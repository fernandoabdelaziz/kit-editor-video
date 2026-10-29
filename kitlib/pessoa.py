"""Regra permanente do kit: nenhum overlay cobre o apresentador (rosto, cabeça, corpo, braços, mãos).

- Elementos pequenos (fichas, etiquetas, lower third) só em espaço livre (fundo, mesa, ao lado da pessoa).
- Cartão grande (documento/datilografado) nunca sobre a pessoa: vira RECORTE (cutaway: fundo neutro em tela
  cheia, cartão centrado, voz continua, corte seco de volta) ou encolhe até caber no espaço livre.

Como confere: a silhueta é segmentada por quadro no vídeo-base SEM overlays (MediaPipe selfie_segmenter, local,
.venv-pessoa), dilatada pela margem; o alfa de cada overlay é lido no mesmo quadro. Interseção acima de
`tolerancia` px (em 1/4 da resolução) = reprovado. Quadro em que o overlay cobre ≥ 98% da tela é recorte
(a pessoa não aparece) e passa. Usado por kit.py motion --base, kit.py renderizar --overlays e kit.py conferir.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from .comum import FPS, KIT, VENV_PESSOA, MODELO_PESSOA, erro, info

VENV = VENV_PESSOA
SCRIPT = KIT / "pessoa_seg.py"
ESCALA = 4


def _alfas(mov, W, H, quadros):
    ws, hs = W // ESCALA, H // ESCALA
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(mov), "-vf",
                             f"format=yuva444p,alphaextract,scale={ws}:{hs}:flags=area,format=gray",
                             "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    alvo, out, n, tam = set(quadros), {}, 0, ws * hs
    ult = max(quadros)
    while n <= ult:
        b = proc.stdout.read(tam)
        if len(b) < tam:
            break
        if n in alvo:
            out[n] = np.frombuffer(b, np.uint8).reshape(hs, ws)
        n += 1
    proc.stdout.close(); proc.wait()
    return out


def conferir(base, overlays, janelas=None, margem=28, tolerancia=6, pasta_png=None, reflexo=False, isencoes=None):
    """base: vídeo sem overlays (linha do tempo da saída). overlays: .mov com alfa. janelas: [(ini,fim)] onde há
    overlay (padrão: lê os .motion.json). Devolve dict(ok, problemas, recortes, quadros)."""
    if not VENV.exists():
        erro(f"falta o ambiente da silhueta: {VENV} (rode o install.sh; veja README.md)")
    if not MODELO_PESSOA.exists():
        erro(f"falta o modelo da silhueta: {MODELO_PESSOA} (rode o install.sh; veja README.md)")
    base = Path(base)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "json", str(base)], capture_output=True, text=True)
    st = json.loads(r.stdout)["streams"][0]
    W, H = st["width"], st["height"]
    jan = list(janelas or [])
    iso = list(isencoes or [])  # (ini, fim, y_min): exceção pedida por quem aparece no vídeo (painel sobre o torso): ignora a silhueta de y_min para baixo
    if not jan or isencoes is None:
        for o in overlays:
            mj = Path(o).with_suffix(".motion.json")
            if mj.exists():
                efs = json.loads(mj.read_text())["efeitos"]
                if not janelas:
                    jan += [(e["ini"], e["fim"]) for e in efs]
                if isencoes is None:
                    iso += [(e["ini"], e["fim"], e["torso_y"]) for e in efs if e.get("torso_y")]
    if not jan:
        jan = [(0, 9999)]
    quadros = set()
    for a, b in jan:
        f0, f1 = int(round(a * FPS)), int(round(b * FPS))
        quadros.update(range(f0, f1 + 1, 4))          # a cada 4 quadros (0,13 s)
        quadros.update({f0, f0 + 1, max(f0, f1 - 1)})  # bordas de entrada/saída
    quadros = sorted(q for q in quadros if q >= 0)
    npz = Path("/tmp") / f"pessoa_{base.stem}_{abs(hash(str(base.resolve()))) % 10**8}.npz"
    info(f"silhueta: segmentando {len(quadros)} quadros de {base.name} (local, MediaPipe) ...")
    cmd = [str(VENV), str(SCRIPT), str(base), str(npz), "--quadros", ",".join(map(str, quadros)),
           "--escala", str(ESCALA), "--margem", str(margem)] + (["--reflexo"] if reflexo else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:]); erro("segmentação da silhueta falhou")
    M = np.load(npz)
    problemas, recortes, pior = [], 0, (0, None, None)
    amostras = []  # quadros com overlay parcial (para o PNG de diagnóstico mesmo quando passa)
    alfas = [_alfas(o, W, H, quadros) for o in overlays]
    for q in quadros:
        k = f"q{q}"
        if k not in M.files:
            continue
        pm = M[k].astype(bool).copy()
        for a_, b_, ymin in iso:
            if a_ - 0.05 <= q / FPS <= b_ + 0.05:
                pm[int(ymin) // ESCALA:, :] = False
        tot = np.zeros(pm.shape, bool)
        for al in alfas:
            if q in al:
                tot |= al[q] > 16
        if not tot.any():
            continue
        if tot.mean() >= 0.98:
            recortes += 1
            continue
        inter = int((tot & pm).sum())
        amostras.append(q)
        if inter > pior[0]:
            pior = (inter, q, None)
        if inter > tolerancia:
            ys, xs = np.nonzero(tot & pm)
            bb = [int(xs.min()) * ESCALA, int(ys.min()) * ESCALA, int(xs.max() + 1) * ESCALA, int(ys.max() + 1) * ESCALA]
            problemas.append(dict(t=round(q / FPS, 3), px=inter * ESCALA * ESCALA, area=bb))
    if pasta_png and (problemas or pior[1] is not None or amostras):
        q_diag = problemas[0]["t"] * FPS if problemas else (pior[1] if pior[1] is not None else amostras[len(amostras) // 2])
        _png(base, overlays, M, q_diag / FPS, Path(pasta_png), W, H)
    res = dict(ok=not problemas, quadros=len(quadros), recortes=recortes, margem_px=margem,
               tolerancia_px=tolerancia * ESCALA * ESCALA, problemas=problemas[:40],
               pior_px=pior[0] * ESCALA * ESCALA, pior_t=round(pior[1] / FPS, 3) if pior[1] is not None else None)
    info(f"silhueta x overlays: {'OK' if res['ok'] else 'REPROVADO'} ({len(quadros)} quadros, {recortes} em recorte, "
         f"pior interseção {res['pior_px']} px em {res['pior_t']} s)")
    for p in problemas[:8]:
        info(f"  overlay sobre o apresentador em {p['t']:.2f} s: {p['px']} px, área {p['area']}")
    return res


def _png(base, overlays, M, t, pasta, W, H):
    """Quadro de diagnóstico: base + overlays + silhueta (vermelho) no pior instante."""
    pasta.mkdir(parents=True, exist_ok=True)
    q = int(round(t * FPS))
    chaves = sorted((int(k[1:]) for k in M.files if k.startswith("q")), key=lambda x: abs(x - q))
    if not chaves:
        return
    m = M[f"q{chaves[0]}"]
    mp_ = pasta / "silhueta_tmp.pgm"
    hs, ws = m.shape
    mp_.write_bytes(f"P5 {ws} {hs} 255\n".encode() + (m * 255).astype(np.uint8).tobytes())
    ins = ["-ss", f"{t:.3f}", "-i", str(base)]
    for o in overlays:
        ins += ["-ss", f"{t:.3f}", "-i", str(o)]
    ins += ["-i", str(mp_)]
    fc, cur = [], "[0:v]"
    for k in range(len(overlays)):
        fc.append(f"[{k+1}:v]format=yuva444p[o{k}];{cur}[o{k}]overlay[b{k}]"); cur = f"[b{k}]"
    n = len(overlays) + 1
    fc.append(f"[{n}:v]scale={W}:{H}:flags=neighbor,format=gray[ma0];color=c=red:s={W}x{H}:d=1[r];"
              f"[r][ma0]alphamerge,colorchannelmixer=aa=0.45[ma];{cur}[ma]overlay,scale=540:-1[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-frames:v", "1",
                    str(pasta / f"silhueta_{t:06.2f}s.png")])
    mp_.unlink(missing_ok=True)
