"""Mede texto renderizado pelo próprio libass (o mesmo motor que queima a legenda): cada pedido vira
um evento ASS num quadro próprio; o ffmpeg devolve os quadros em cinza cru e calculamos a caixa do que
ficou branco. Só stdlib + ffmpeg."""
import subprocess
import tempfile
from pathlib import Path

from .comum import ts_ass

_LIMIAR = bytes(0 if v <= 128 else 1 for v in range(256))


def medir(cabecalho, textos, W, H, faixa=None):
    """cabecalho: texto ASS até a linha 'Format:' de [Events] (inclusive).
    textos: lista de (estilo, texto_dialogue). Devolve lista de bbox (x0, y0, x1, y1) ou None.
    faixa: (y0, y1) para recortar e acelerar."""
    if not textos:
        return []
    y0, y1 = faixa if faixa else (0, H)
    y0, y1 = max(0, int(y0)) // 2 * 2, min(H, int(y1) + 1) // 2 * 2
    hh = y1 - y0
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.ass"
        dt = 0.1
        corpo = "".join(f"Dialogue: 0,{ts_ass(i * dt)},{ts_ass((i + 1) * dt)},{est},,0,0,0,,{txt}\n"
                        for i, (est, txt) in enumerate(textos))
        p.write_text(cabecalho + corpo, encoding="utf-8")
        n = len(textos)
        cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r=10:d={n * dt + 0.05:.2f}",
               "-vf", f"ass={p},crop={W}:{hh}:0:{y0},format=gray", "-frames:v", str(n),
               "-f", "rawvideo", "-"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode()[-1500:])
    buf = r.stdout
    tam = W * hh
    out = []
    for i in range(n):
        q = buf[i * tam:(i + 1) * tam].translate(_LIMIAR)
        if b"\x01" not in q:
            out.append(None)
            continue
        ys = []
        xs0, xs1 = W, -1
        for row in range(hh):
            linha = q[row * W:(row + 1) * W]
            a = linha.find(b"\x01")
            if a >= 0:
                ys.append(row)
                xs0 = min(xs0, a)
                xs1 = max(xs1, linha.rfind(b"\x01"))
        out.append((xs0, ys[0] + y0, xs1 + 1, ys[-1] + 1 + y0))
    return out
