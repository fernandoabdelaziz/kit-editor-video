"""Autochecagem do vídeo renderizado (ideia do self-eval do video-use, reescrita) ANTES de mostrar a quem pediu o vídeo.
Gera, para cada ponto de corte, um PNG com tira de quadros + forma de onda (antes/depois do corte) e roda
checagens automáticas: estalo de áudio no corte, quadro preto/congelado, legenda dentro da safe area,
duração, resolução, fps, cor bt709, loudness ~-14 LUFS e true peak <= -1 dBTP. Usa também o check.py do
ffmpeg-skill (opcional; só leitura do arquivo). Escreve <video>_conferir/relatorio.md e relatorio.json."""
import array
import json
import re
import subprocess
from pathlib import Path

from .comum import FORMATOS, RAIZ, CHECK_PY, PY_SKILL, ffprobe, ler_json, info, saida_segura, esc_filtro
_LIMIAR = bytes(0 if v <= 20 else 1 for v in range(256))   # qualquer pixel não preto (inclui caixas escuras)

FONTE_ROTULO = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _r(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def _pcm(video, a, dur):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(a, 0):.4f}", "-i", str(video), "-t", f"{dur:.4f}",
                        "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"], capture_output=True)
    x = array.array("h"); x.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    return x


def estalo(video, t):
    """Descontinuidade no corte: 2ª diferença (x[n] - 2x[n-1] + x[n-2]) perto do corte, comparada ao
    percentil 99,9 do resto da janela. Fala é suave nessa medida; um corte sem fade vira um pico isolado."""
    x = _pcm(video, t - 0.3, 0.6)
    if len(x) < 1000:
        return dict(t=t, ok=True, razao=0, nota="sem áudio suficiente")
    d = [abs(x[i] - 2 * x[i - 1] + x[i - 2]) for i in range(2, len(x))]
    c = min(len(d) - 1, int(0.3 * 48000))
    perto = d[max(0, c - 240): c + 240]           # ±5 ms
    resto = sorted(d[: max(0, c - 960)] + d[c + 960:]) or [1]
    ref = max(resto[int(len(resto) * 0.999)], 1)
    razao = max(perto) / ref
    return dict(t=round(t, 3), ok=not (razao > 2.5 and max(perto) > 150), razao=round(razao, 2), pico=max(perto))


def tira(video, t, dest, rotulo, w, h, janela=0.6):
    offs = [-janela, -janela / 2, -1.5 / 30, 1.5 / 30, janela / 2, janela]
    ins = []
    for o in offs:
        ins += ["-ss", f"{max(t + o, 0):.3f}", "-i", str(video)]
    ins += ["-ss", f"{max(t - janela, 0):.3f}", "-t", f"{2 * janela:.3f}", "-i", str(video)]
    fh = round(180 * h / w / 2) * 2
    fc = ";".join(f"[{i}:v]trim=end_frame=1,scale=180:{fh},setsar=1[f{i}]" for i in range(6))
    fc += ";" + "".join(f"[f{i}]" for i in range(6)) + "hstack=inputs=6[topo]"
    fc += (f";[6:a]showwavespic=s=1080x160:colors=0xE8DCC4:split_channels=0,format=rgba[w0];"
           f"color=c=0x202020:s=1080x160:d=1,format=rgba[fw];[fw][w0]overlay=format=auto,"
           f"drawbox=x=539:y=0:w=2:h=160:color=red@0.9:t=fill[onda]")
    fc += (f";[topo]format=rgba[t2];[t2][onda]vstack,drawbox=x=539:y=0:w=2:h={fh}:color=red@0.6:t=fill,"
           f"pad=1080:{fh + 160 + 40}:0:40:color=0x202020,"
           f"drawtext=fontfile={FONTE_ROTULO}:text='{rotulo}':x=12:y=10:fontsize=22:fontcolor=white")
    r = _r(["ffmpeg", "-v", "error", "-n", *ins, "-filter_complex", fc, "-frames:v", "1", dest])
    return r.returncode == 0


def caixas_legenda(ass, grupos, W, H, dur):
    """Renderiza só a legenda (sobre preto) no meio de cada grupo e mede a caixa ocupada."""
    ts = [round((g["ini"] + g["fim"]) / 2 * 30) for g in grupos]
    if not ts:
        return []
    sel = "+".join(f"eq(n\\,{n})" for n in ts)
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r=30:d={dur:.3f}",
                        "-vf", f"ass={esc_filtro(ass)},select='{sel}',format=gray", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-"], capture_output=True)
    tam = W * H
    out = []
    for k in range(len(r.stdout) // tam):
        q = r.stdout[k * tam:(k + 1) * tam].translate(_LIMIAR)
        rows = [i for i in range(0, H, 2) if b"\x01" in q[i * W:(i + 1) * W]]
        if not rows:
            out.append(None); continue
        x0 = min(q[i * W:(i + 1) * W].find(b"\x01") for i in rows)
        x1 = max(q[i * W:(i + 1) * W].rfind(b"\x01") for i in rows)
        out.append((x0, rows[0], x1 + 1, rows[-1] + 2))
    return out


def conferir(video, manifesto_path=None, plataforma=None):
    video = Path(video).resolve()
    man = ler_json(manifesto_path or video.with_suffix(".render.json"))
    pasta = saida_segura(video.with_name(video.stem + "_conferir"))
    pasta.mkdir()
    res, linhas = {}, []
    def item(nome, ok, valor, alvo):
        res[nome] = dict(ok=ok, valor=valor, alvo=alvo)
        linhas.append(f"| {'OK' if ok else 'FALHA'} | {nome} | {valor} | {alvo} |")

    d = ffprobe(video)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), {})
    dur = float(d["format"]["duration"])
    W, H = man["w"], man["h"]
    item("duração", abs(dur - man["duracao_esperada"]) <= 0.1, f"{dur:.3f} s", f"{man['duracao_esperada']:.3f} s ±0,1")
    item("resolução", (v["width"], v["height"]) == (W, H), f"{v['width']}x{v['height']}", f"{W}x{H}")
    item("fps", v["r_frame_rate"] in ("30/1",), v["r_frame_rate"], "30/1")
    item("codec/pixel", v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f"{v['codec_name']} {v['pix_fmt']}", "h264 yuv420p")
    cores = (v.get("color_primaries"), v.get("color_transfer"), v.get("color_space"))
    item("cor", cores == ("bt709", "bt709", "bt709"), "/".join(str(c) for c in cores), "bt709")
    item("áudio", a.get("codec_name") == "aac" and a.get("sample_rate") == "48000", f"{a.get('codec_name')} {a.get('sample_rate')}", "aac 48000")
    if man["formato"] == "reels":
        item("duração máx. reels", dur <= 90, f"{dur:.1f} s", "≤ 90 s")

    r = _r(["ffmpeg", "-nostats", "-i", video, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"])
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
    TP = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)[-1])
    item("loudness", abs(I + 14) <= 1.0, f"{I:.1f} LUFS", "-14 ±1")
    item("true peak", TP <= -1.0, f"{TP:.1f} dBTP", "≤ -1,0")

    r = _r(["ffmpeg", "-nostats", "-i", video, "-vf", "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=0.001:d=0.6",
            "-an", "-f", "null", "-"])
    pretos = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)
    congel = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
    item("quadro preto", not pretos, pretos or "nenhum", "nenhum")
    item("imagem congelada", not congel, congel or "nenhuma", "nenhuma (≥ 0,6 s)")

    estalos = [estalo(video, c["t"]) for c in man["cortes"]]
    ruins = [e for e in estalos if not e["ok"]]
    item("estalo nos cortes", not ruins,
         f"{len(estalos)} cortes, pior razão {max([e['razao'] for e in estalos] or [0]):.2f}" + (f"; problema em {[e['t'] for e in ruins]}" if ruins else ""),
         "razão ≤ 2,5")

    gj = ler_json(man["grupos"])
    bbs = caixas_legenda(man["legenda_ass"], gj["grupos"], W, H, dur)
    sf = FORMATOS[man["formato"]]["safe"]
    fora = [(g["texto"], bb) for g, bb in zip(gj["grupos"], bbs)
            if bb and (bb[0] < sf["x0"] or bb[2] > sf["x1"] or bb[1] < sf["y0"] or bb[3] > sf["y1"])]
    vazios = sum(1 for bb in bbs if bb is None)
    ext = [min(b[0] for b in bbs if b), min(b[1] for b in bbs if b), max(b[2] for b in bbs if b), max(b[3] for b in bbs if b)] if any(bbs) else None
    item("legenda na safe area", not fora and not vazios,
         f"{len(bbs)} grupos, área ocupada x {ext[0]}-{ext[2]}, y {ext[1]}-{ext[3]}" + (f"; fora: {fora[:3]}" if fora else "") +
         (f"; {vazios} grupos sem texto" if vazios else ""), f"x {sf['x0']}-{sf['x1']}, y {sf['y0']}-{sf['y1']}")

    # regra permanente do kit: nenhum overlay sobre o apresentador (silhueta x alfa dos overlays, no vídeo-base)
    if man.get("overlays"):
        from . import pessoa
        base = Path(man["temporarios"]) / "base.mkv"
        if base.exists():
            rp = pessoa.conferir(base, man["overlays"], pasta_png=pasta)
            item("overlay fora do apresentador", rp["ok"],
                 f"{rp['quadros']} quadros, {rp['recortes']} em recorte, pior interseção {rp['pior_px']} px"
                 + (f" em {rp['pior_t']} s" if rp["pior_t"] is not None else "")
                 + (f"; sobre o apresentador em {[x['t'] for x in rp['problemas'][:5]]}" if rp["problemas"] else ""),
                 f"0 px além de {rp['tolerancia_px']} px (margem {rp['margem_px']} px)")
        else:
            item("overlay fora do apresentador", False, f"vídeo-base não encontrado ({base})", "base.mkv da renderização")

    # ffmpeg-skill check.py (só lê o arquivo)
    plat = plataforma or {"reels": "reels", "linkedin": "linkedin", "paisagem": "youtube"}[man["formato"]]
    if not (CHECK_PY.exists() and PY_SKILL.exists()):
        item("ffmpeg-skill check.py", True, f"não instalado ({CHECK_PY}); pulado", "opcional")
    else:
        r = _r([PY_SKILL, CHECK_PY, video, "--platform", plat, "--json"])
        try:
            js = json.loads(r.stdout)
            rows = js.get("checks") or js.get("rows") or []
            cont = {}
            for row in rows:
                st = str(row.get("status", "")).upper(); cont[st] = cont.get(st, 0) + 1
            falhas = [f"{row.get('check', row.get('name'))}: {row.get('actual', row.get('value'))}" for row in rows
                      if str(row.get("status", "")).upper() == "FAIL"]
            item(f"ffmpeg-skill check.py --platform {plat}", not falhas, f"{cont}" + (f" falhas: {falhas}" if falhas else ""), "sem FAIL")
        except Exception as ex:
            item(f"ffmpeg-skill check.py --platform {plat}", True, f"não lido ({ex}); exit {r.returncode}", "informativo")

    # imagens: um PNG por corte (tira + onda), começo/fim e 3 quadros inteiros
    pngs = []
    for n, c in enumerate(man["cortes"], 1):
        p = pasta / f"corte_{n:02d}_{c['t']:06.2f}s.png"
        tira(video, c["t"], p, f"corte {n} ({c['tipo']}) em {c['t']:.2f} s", W, H)
        pngs.append(p.name)
    tira(video, 0.6, pasta / "inicio.png", "inicio (0-1,2 s)", W, H)
    tira(video, max(dur - 0.7, 0.6), pasta / "fim.png", "fim", W, H)
    quadros = []
    for frac in (0.2, 0.5, 0.8):
        t = dur * frac
        p = pasta / f"quadro_{t:05.2f}s.png"
        _r(["ffmpeg", "-v", "error", "-n", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", p])
        quadros.append(p.name)

    ok = all(x["ok"] for x in res.values())
    md = [f"# Conferência: {video.name}", "", f"Resultado: **{'PASSOU' if ok else 'FALHOU'}**  ·  preset {man['preset']} / paleta {man['paleta']}", "",
          "| | checagem | medido | alvo |", "|---|---|---|---|", *linhas, "",
          "Imagens (abra e olhe: corte limpo, sem salto, legenda legível):", *[f"- {p}" for p in pngs + ["inicio.png", "fim.png"] + quadros]]
    (pasta / "relatorio.md").write_text("\n".join(md), encoding="utf-8")
    (pasta / "relatorio.json").write_text(json.dumps(dict(ok=ok, checagens=res, estalos=estalos, pngs=pngs, quadros=quadros),
                                                     ensure_ascii=False, indent=1))
    info("\n".join(md))
    info(f"\npasta: {pasta}")
    return ok
