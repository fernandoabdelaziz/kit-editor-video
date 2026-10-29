"""Mostruário da biblioteca de legendas: o MESMO quadro (e, opcionalmente, o mesmo trecho em vídeo) com
cada preset aplicado, para quem aparece no vídeo escolher. Base: um vídeo já renderizado SEM legenda + a EDL dele."""
import json
import subprocess
from pathlib import Path

from .comum import FORMATOS, caminho, saida_segura, ler_json, info, erro, esc_filtro, run
from . import edl as E, legendas

FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTE_N = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _esc_txt(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")


def gerar(a):
    edl = ler_json(a.edl)
    _, tot = E.offsets(edl)
    palavras = E.palavras_saida(edl)
    F = FORMATOS[a.formato]
    W, H = F["w"], F["h"]
    nomes = a.presets.split(",") if a.presets else legendas.listar_presets()
    pasta = caminho(a.saida_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / f"{a.nome}_tmp"
    if tmp.exists():
        erro(f"já existe: {tmp}")
    tmp.mkdir()
    folha = saida_segura(pasta / f"{a.nome}.png")
    # instante: meio de uma palavra longa, já com a transição concluída
    t = a.t
    if t is None:
        cand = [w for w in palavras if w["e"] - w["s"] >= 0.3 and 0.3 * tot < w["s"] < 0.7 * tot]
        w = max(cand, key=lambda w: len(w["w"])) if cand else palavras[len(palavras) // 2]
        t = round(w["s"] + 0.2, 2)
    base = caminho(a.video)
    quadro = tmp / "quadro.png"
    run(["ffmpeg", "-v", "error", "-n", "-ss", f"{t:.3f}", "-i", base, "-frames:v", "1", quadro])
    tiles = []
    meta = []
    for n in nomes:
        pr = json.loads((legendas.PASTA / "presets" / f"{n}.json").read_text())
        r = legendas.gerar(palavras, n, a.formato, str(tmp / n), paleta=a.paleta, duracao=tot)
        png = tmp / f"{n}.png"
        # a legenda é renderizada no instante t sobre o quadro parado
        run(["ffmpeg", "-v", "error", "-n", "-loop", "1", "-framerate", "30", "-t", f"{t + 0.05:.3f}", "-i", quadro,
             "-vf", f"ass={esc_filtro(tmp / (n + '.ass'))}", "-update", "1", "-frames:v", str(round((t + 0.05) * 30)), png])
        tiles.append(png)
        meta.append((n, r["paleta"], pr["origem"].split(":")[0].split("(")[0].split(",")[0].strip()))
    # folha de contato: 4 colunas; cada célula = quadro reduzido + rótulo
    cols = 4
    tw = 360
    th = round(tw * H / W)
    lab = 70
    linhas = (len(tiles) + cols - 1) // cols
    ins, fc = [], []
    for i, (png, (n, pal, org)) in enumerate(zip(tiles, meta)):
        ins += ["-i", png]
        fc.append(f"[{i}:v]scale={tw}:{th}:flags=lanczos,pad={tw}:{th + lab}:0:0:color=0xF4F1EA,"
                  f"drawtext=fontfile={FONTE}:text='{i + 1}. {_esc_txt(n)}':x=10:y={th + 8}:fontsize=20:fontcolor=0x1E1E1E,"
                  f"drawtext=fontfile={FONTE_N}:text='{_esc_txt(org)} · paleta {_esc_txt(pal)}':x=10:y={th + 38}:fontsize=15:fontcolor=0x555555[c{i}]")
    vazios = linhas * cols - len(tiles)
    for j in range(vazios):
        fc.append(f"color=c=0xF4F1EA:s={tw}x{th + lab}:d=1[c{len(tiles) + j}]")
    total = len(tiles) + vazios
    lay = "|".join(f"{(k % cols) * (tw + 8)}_{(k // cols) * (th + lab + 8)}" for k in range(total))
    fc.append("".join(f"[c{k}]" for k in range(total)) + f"xstack=inputs={total}:layout={lay}:fill=0xF4F1EA[g]")
    fc.append(f"[g]pad=iw+16:ih+86:8:78:color=0xF4F1EA,drawtext=fontfile={FONTE}:text='Mostruário de legendas · "
              f"mesmo quadro ({t:.2f} s do teste)':x=12:y=22:fontsize=30:fontcolor=0x1E3A2F")
    run(["ffmpeg", "-v", "error", "-n", *ins, "-filter_complex", ";".join(fc), "-frames:v", "1", folha])
    info(f"folha de contato: {folha}  (instante {t:.2f} s)")
    # folha de detalhe: só a faixa da legenda, a 50%, 2 colunas (dá para ler o acabamento)
    det = saida_segura(pasta / f"{a.nome}_detalhe.png")
    yb = int(H * 0.78)
    cy0 = max(0, min(H - 440, yb - 300)) // 2 * 2
    ins, fc = [], []
    for i, (png, (n, pal, org)) in enumerate(zip(tiles, meta)):
        ins += ["-i", png]
        fc.append(f"[{i}:v]crop={W}:440:0:{cy0},scale={W // 2}:220:flags=lanczos,pad={W // 2}:262:0:42:color=0xF4F1EA,"
                  f"drawtext=fontfile={FONTE}:text='{i + 1}. {_esc_txt(n)}':x=8:y=6:fontsize=20:fontcolor=0x1E1E1E,"
                  f"drawtext=fontfile={FONTE_N}:text='paleta {_esc_txt(pal)}':x=w-tw-8:y=10:fontsize=15:fontcolor=0x555555[d{i}]")
    n_ = len(tiles) + (len(tiles) % 2)
    if len(tiles) % 2:
        fc.append(f"color=c=0xF4F1EA:s={W // 2}x262:d=1[d{len(tiles)}]")
    lay = "|".join(f"{(k % 2) * (W // 2 + 8)}_{(k // 2) * 270}" for k in range(n_))
    fc.append("".join(f"[d{k}]" for k in range(n_)) + f"xstack=inputs={n_}:layout={lay}:fill=0xF4F1EA[g]")
    fc.append(f"[g]pad=iw+16:ih+70:8:62:color=0xF4F1EA,drawtext=fontfile={FONTE}:text='Legendas em detalhe (50%%) · "
              f"{t:.2f} s':x=12:y=18:fontsize=28:fontcolor=0x1E3A2F")
    run(["ffmpeg", "-v", "error", "-n", *ins, "-filter_complex", ";".join(fc), "-frames:v", "1", det])
    info(f"detalhe: {det}")
    if a.mp4:
        # ~3 s do mesmo trecho com cada preset, um depois do outro, com o nome no topo
        ini = max(0.0, t - 1.5)
        dur = min(3.2, tot - ini)
        partes = []
        for i, n in enumerate(nomes):
            p = tmp / f"{n}.mp4"
            vf = (f"ass={esc_filtro(tmp / (n + '.ass'))},drawbox=x=0:y=90:w=iw:h=86:color=black@0.55:t=fill,"
                  f"drawtext=fontfile={FONTE}:text='{i + 1}/{len(nomes)}  {_esc_txt(n)}':x=(w-tw)/2:y=112:fontsize=40:fontcolor=white")
            run(["ffmpeg", "-v", "error", "-n", "-i", base, "-vf", f"setpts=PTS,{vf},trim=start={ini:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS",
                 "-af", f"atrim=start={ini:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st={dur - 0.03:.3f}:d=0.03",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "160k", p])
            partes.append(p)
        lista = tmp / "lista.txt"
        lista.write_text("".join(f"file '{p}'\n" for p in partes))
        mp4 = saida_segura(pasta / f"{a.nome}.mp4")
        run(["ffmpeg", "-v", "error", "-n", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", "-movflags", "+faststart", mp4])
        info(f"vídeo: {mp4}")
