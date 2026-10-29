"""Render a partir da EDL (método do video-use reescrito): extrai cada trecho já com tone mapping,
reenquadramento, zoom e fades de áudio de 30 ms; junta (corte seco ou dissolve); trata a voz com a cadeia
aprovada; gera a legenda do preset escolhido e queima a legenda POR ÚLTIMO. Entrega sempre a versão com
legenda e a _sem-legenda. Nunca sobrescreve, nunca escreve em brutos/."""
import json
import shutil
from pathlib import Path

from .comum import (FORMATOS, FPS, BT709, TONEMAP, RAIZ, caminho, saida_segura, run, video_info, ler_json,
                    erro, info, esc_filtro)
from . import edl as E
from . import audio_voz, legendas


def _reenquadrar(src, F, foco):
    TW, TH = F["w"], F["h"]
    W, H = src["w"], src["h"]
    fx, fy = foco.get("foco_x", 0.5), foco.get("foco_y", 0.35)
    if (W >= H) != (TW >= TH) and abs(W / H - TW / TH) > 0.3 and foco.get("modo", "auto") != "preencher":
        # orientação diferente (ex.: vertical -> 16:9): imagem inteira + fundo desfocado
        s = min(TW / W, TH / H)
        fw, fh = int(W * s) // 2 * 2, int(H * s) // 2 * 2
        return (f"split[a][b];[a]scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH},"
                f"boxblur=30:2,eq=brightness=-0.08[fundo];[b]scale={fw}:{fh}:flags=lanczos[frente];"
                f"[fundo][frente]overlay=(W-w)/2:(H-h)/2")
    s = max(TW / W, TH / H)
    sw, sh = max(TW, round(W * s / 2) * 2), max(TH, round(H * s / 2) * 2)
    x, y = round((sw - TW) * fx), round((sh - TH) * fy)
    return f"scale={sw}:{sh}:flags=lanczos,crop={TW}:{TH}:{x}:{y}"


def _zoom(zooms, off, dur, F, foco):
    """Punch zoom discreto (tempo da saída), com rampa ease in-out; centro levemente acima (rosto)."""
    zs = [z for z in zooms if z["de"] < off + dur and z["ate"] > off]
    if not zs:
        return None
    TW, TH = F["w"], F["h"]
    termos = []
    for z in zs:
        # rampa de entrada/saída separadas: 0 = corte seco (punch-in de jump cut); longa = push-in lento
        r = z.get("rampa", 0.25)
        ri = max(float(z.get("rampa_entrada", r)), 0.001)
        ro = max(float(z.get("rampa_saida", r)), 0.001)
        T = f"(t+{off:.4f})"
        p = f"min(clip(({T}-{z['de']})/{ri},0,1),clip(({z['ate']}-{T})/{ro},0,1))"
        termos.append(f"({z['escala'] - 1:.4f})*(0.5-0.5*cos(PI*{p}))")
    Z = "(1+" + "+".join(termos) + ")"
    fy = foco.get("foco_y_zoom", 0.4)
    # centro_x_zoom (0 a 1, opcional): posição horizontal dele no quadro; o corte do zoom se centra aí
    # (preso às bordas) em vez de no meio do quadro. Sem o campo, mantém o corte centrado como antes.
    cxz = foco.get("centro_x_zoom")
    xe = (f"clip(iw*{float(cxz):.4f}-{TW}/2,0,iw-{TW})" if cxz is not None else f"(iw-{TW})/2")
    return (f"scale=w='2*trunc({TW}*{Z}/2)':h='2*trunc({TH}*{Z}/2)':eval=frame:flags=bicubic,"
            f"crop={TW}:{TH}:'{xe}':'(ih-{TH})*{fy}'")


def renderizar(edl_path, formato, saida, preset, paleta=None, previa=False, ass_extra=None, y_legenda=None, y_janelas=None,
               grupos_json=None, overlays=None):
    edl = ler_json(edl_path)
    E.validar(edl)
    F = FORMATOS[formato]
    saida = caminho(saida)
    em_editados = (RAIZ / "editados") in saida.resolve().parents
    if em_editados and not edl.get("aprovacao"):
        erro("recusado: a EDL não tem 'aprovacao'. Mostre o plano (kit.py plano) a quem aparece no vídeo e registre o OK antes "
             "de renderizar para editados/. Para prévia, renderize em trabalho/ com --previa.")
    if em_editados and previa:
        erro("prévia não vai para editados/")
    sem = saida.with_name(saida.stem + "_sem-legenda" + saida.suffix)
    saida = saida_segura(saida)
    sem = saida_segura(sem)
    tmp = saida.with_name(saida.stem + "_tmp")
    if tmp.exists():
        erro(f"pasta temporária já existe: {tmp} (apague ou use outro nome)")
    tmp.mkdir(parents=True)
    fontes = {f: caminho(p) for f, p in edl["fontes"].items()}
    info_f = {f: video_info(p) for f, p in fontes.items()}
    off, total = E.offsets(edl)
    enq = edl.get("enquadramento", {})
    crf_seg, preset_x = ("16", "ultrafast") if previa else ("10", "veryfast")

    # 1) trechos
    segs = []
    for i, s in enumerate(edl["segmentos"]):
        src = info_f[s["fonte"]]
        a, b = E.q(s["in"]), E.q(s["out"])
        dur = b - a
        n = round(dur * FPS)
        foco = enq.get(s["fonte"], {})
        vf = ["setpts=PTS-STARTPTS"]
        if src["hdr"]:
            vf.append(TONEMAP)
        else:  # fonte SDR sem marcação de cor: marca bt709 nos quadros (senão o ffmpeg 7 grava "unknown")
            vf.append("setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709")
        vf.append(_reenquadrar(src, F, foco))
        z = _zoom(edl.get("zooms", []), off[i], dur, F, foco)
        if z:
            vf.append(z)
        vf.append(f"fps={FPS},setsar=1,format=yuv420p")
        af = (f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
              f"afade=t=in:st=0:d=0.03,afade=t=out:st={dur - 0.03:.4f}:d=0.03")
        p = tmp / f"trecho_{i:03d}.mkv"
        info(f"trecho {i+1}/{len(edl['segmentos'])}: {s['fonte']} {a:.3f}-{b:.3f} ({dur:.2f} s)")
        run(["ffmpeg", "-v", "error", "-n", "-ss", f"{a:.4f}", "-i", fontes[s["fonte"]], "-t", f"{dur:.4f}",
             "-filter_complex", f"[0:v:0]{','.join(vf)}[v];[0:a:0]{af}[a]", "-map", "[v]", "-map", "[a]",
             "-frames:v", str(n), "-c:v", "libx264", "-preset", preset_x, "-crf", crf_seg, *BT709,
             "-c:a", "pcm_s24le", "-t", f"{dur:.4f}", p])
        segs.append((p, dur))

    # 2) junção: corridas de corte seco com concat; dissolve entre corridas com xfade/acrossfade
    fc, ins = [], []
    for i, (p, _) in enumerate(segs):
        ins += ["-i", p]
    corridas = [[0]]
    for i in range(1, len(segs)):
        if E.trans_dur(edl["segmentos"][i]):
            corridas.append([i])
        else:
            corridas[-1].append(i)
    rot = []
    for c, idx in enumerate(corridas):
        if len(idx) == 1:
            fc.append(f"[{idx[0]}:v]null[v{c}];[{idx[0]}:a]anull[a{c}]")
        else:
            fc.append("".join(f"[{i}:v][{i}:a]" for i in idx) + f"concat=n={len(idx)}:v=1:a=1[v{c}][a{c}]")
        rot.append(sum(segs[i][1] for i in idx))
    cur_v, cur_a, L = "[v0]", "[a0]", rot[0]
    for c in range(1, len(corridas)):
        d = E.trans_dur(edl["segmentos"][corridas[c][0]])
        fc.append(f"{cur_v}[v{c}]xfade=transition=fade:duration={d}:offset={L - d:.4f}[xv{c}];"
                  f"{cur_a}[a{c}]acrossfade=d={d}:c1=tri:c2=tri[xa{c}]")
        cur_v, cur_a, L = f"[xv{c}]", f"[xa{c}]", L + rot[c] - d
    base, bruto = tmp / "base.mkv", tmp / "audio_sem_tratamento.wav"
    info("juntando trechos")
    run(["ffmpeg", "-v", "error", "-n", *ins, "-filter_complex", ";".join(fc), "-map", cur_v, "-c:v", "libx264",
         "-preset", preset_x, "-crf", crf_seg, *BT709, base, "-map", cur_a, "-c:a", "pcm_s24le", bruto])

    # 3) voz
    trs = {f: ler_json(p) for f, p in edl["transcricoes"].items()}
    if edl.get("ruido"):
        r = edl["ruido"]
        ruido = (fontes[r["fonte"]], r["de"], r["ate"])
    else:
        ruido = audio_voz.achar_silencio(trs, fontes)
    info(f"voz: cadeia aprovada (perfil de ruído: {ruido})")
    audio = tmp / "audio_tratado.wav"
    est_audio = audio_voz.tratar(bruto, audio, ruido, perfil=edl.get("audio_perfil", "padrao"))

    # 4) legenda (preset da biblioteca) na linha do tempo da saída
    palavras = E.palavras_saida(edl)
    grupos_fixos = None
    if grupos_json:
        grupos_fixos = [g["palavras"] for g in ler_json(grupos_json)["grupos"]]
    leg_base = tmp / f"legenda_{preset}"
    resumo = legendas.gerar(palavras, preset, formato, leg_base, paleta=paleta, grupos_fixos=grupos_fixos,
                            y=y_legenda, duracao=total, y_janelas=y_janelas)

    # 5) entregas: sem legenda e com legenda (legenda sempre por último)
    extra = [caminho(a) for a in (ass_extra or [])]
    ovs = [caminho(o) for o in (overlays or [])]
    for o in ovs:
        if not o.exists():
            erro(f"overlay não existe: {o} (gere com kit.py motion)")
    for o in ovs:
        mj = o.with_suffix(".motion.json")
        if em_editados and mj.exists() and ler_json(mj).get("exemplo"):
            erro(f"recusado: {o.name} é overlay de EXEMPLO (dados fictícios da biblioteca de aberturas/gráficos). "
                 "Refaça o motion com os textos e números da fala (sem 'exemplo').")
    res_pessoa = None
    if ovs:
        # regra permanente: overlay nenhum sobre o apresentador (só espaço livre ou recorte em tela cheia)
        from . import pessoa
        res_pessoa = pessoa.conferir(base, ovs, pasta_png=tmp / "silhueta")
        if not res_pessoa["ok"]:
            erro(f"recusado: overlay cobre o apresentador em {[p_['t'] for p_ in res_pessoa['problemas'][:6]]} s. "
                 f"Diagnóstico: {tmp / 'silhueta'}. Mova para espaço livre, encolha ou use recorte (cutaway).")

    def entrega(dest, asses, rotulo):
        # ordem das camadas: vídeo -> overlays de motion (HyperFrames, alfa) -> títulos .ass -> legenda por último
        from .motion import filtro_overlays
        ov_in = [x for o in ovs for x in ("-i", o)]
        fc_ov, cur = filtro_overlays(2, ovs) if ovs else ("", "[0:v]")
        vf = ",".join([f"ass={esc_filtro(a)}" for a in asses] + ["format=yuv420p"])
        fc = (fc_ov + ";" if fc_ov else "") + f"{cur}{vf}[vout]"
        info(f"codificando {rotulo}: {dest}" + (f" (+{len(ovs)} overlay)" if ovs else ""))
        run(["ffmpeg", "-v", "error", "-n", "-i", base, "-i", audio, *ov_in, "-filter_complex", fc,
             "-map", "[vout]", "-map", "1:a",
             "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast" if previa else "slow", "-crf", "18",
             "-pix_fmt", "yuv420p", "-r", str(FPS), *BT709, "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-t", f"{total:.4f}", dest])
    entrega(sem, extra, "sem legenda")
    entrega(saida, extra + [Path(f"{leg_base}.ass")], f"com legenda ({preset}, paleta {resumo['paleta']})")
    shutil.copy(f"{leg_base}.srt", saida.with_suffix(".srt")) if not saida.with_suffix(".srt").exists() else None

    cortes = []
    for i in range(1, len(segs)):
        cortes.append(dict(t=round(off[i] + E.trans_dur(edl["segmentos"][i]) / 2, 3),
                           tipo="dissolve" if E.trans_dur(edl["segmentos"][i]) else "corte"))
    manifesto = dict(edl=str(caminho(edl_path)), formato=formato, w=F["w"], h=F["h"], fps=FPS,
                     duracao_esperada=round(total, 3), cortes=cortes, preset=preset, paleta=resumo["paleta"],
                     legenda_ass=f"{leg_base}.ass", grupos=f"{leg_base}_grupos.json", audio=est_audio,
                     ruido=[str(x) for x in ruido] if ruido else None, saida=str(saida), sem_legenda=str(sem),
                     previa=previa, temporarios=str(tmp), overlays=[str(o) for o in ovs],
                     pessoa=res_pessoa)
    (saida.with_suffix(".render.json")).write_text(json.dumps(manifesto, ensure_ascii=False, indent=1))
    info(f"pronto: {saida}\n       {sem}\n       manifesto: {saida.with_suffix('.render.json')}")
    return manifesto
