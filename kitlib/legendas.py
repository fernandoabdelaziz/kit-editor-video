"""Motor da biblioteca de legendas. Lê um preset (legendas/presets/<nome>.json) e uma paleta
(legendas/paletas.json), recebe as palavras já na linha do tempo da SAÍDA e gera .ass + .srt + grupos.json.

Cada quadro (30 fps) tem um "estado" calculado em Python (palavra ativa, caixa, entrada, revelação);
estados iguais seguidos viram um único evento ASS. Medidas de texto vêm do próprio libass (medir.py),
então a caixa fica exatamente atrás da palavra. Tudo stdlib + ffmpeg.
"""
import json
import math
import re
from pathlib import Path

from .comum import KIT, FORMATOS, FPS, ass_cor, ass_alfa, ts_ass, ts_srt, hex_rgb, erro, info
from .medir import medir

PASTA = KIT / "legendas"
PADRAO = {
    "fonte": "Inter Bold", "negrito": 0, "tamanho": 64, "espacamento": 0,
    "contorno": 1.5, "cor_contorno": "@contorno", "sombras": [],
    "caixa_alta": False, "pontuacao": "tirar_final",
    "posicao": {"y": 0.781, "y_paisagem": 0.87},
    "agrupamento": {"regra": "palavras", "max_palavras": 4, "max_seg": 2.6, "pausa_quebra": 0.4,
                    "quebra_pontuacao": True, "min_dur": 0.0, "chave_sozinha": False, "atravessa_corte": False,
                    "segura_fim": 0.35},
    "cores": {"texto": "@texto", "ativo": None, "passado": None, "futuro": None},
    "destaque": {"tipo": "nenhum"},
    "fundo": None,
    "entrada": {"tipo": "nenhuma", "dur": 0.2},
    "saida": {"tipo": "nenhuma", "dur": 0.2},
    # palavra-chave com cor/tamanho próprios o tempo todo (ideia: reels da humantrack.io). "auto": números, siglas
    # e palavras longas (e_chave); "lista": palavras extras (sem acento/caixa); "excluir": nunca destacar.
    "chave": None,
}


# ---------------------------------------------------------------- presets e paletas
def listar_presets():
    return sorted(p.stem for p in (PASTA / "presets").glob("*.json"))


def carregar_paletas():
    return json.loads((PASTA / "paletas.json").read_text(encoding="utf-8"))


def _mescla(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _mescla(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def carregar_preset(nome, paleta=None):
    p = PASTA / "presets" / f"{nome}.json"
    if not p.exists():
        erro(f"preset '{nome}' não existe. Opções: {', '.join(listar_presets())}")
    pr = _mescla(PADRAO, json.loads(p.read_text(encoding="utf-8")))
    pals = carregar_paletas()
    nome_pal = paleta or pr.get("paleta_padrao", "verde-bege")
    if nome_pal not in pals:
        erro(f"paleta '{nome_pal}' não existe. Opções: {', '.join(k for k in pals if not k.startswith('_'))}")
    pr["_paleta_nome"] = nome_pal
    pr["_paleta"] = pals[nome_pal]
    return pr


def cor(pr, ref, padrao="#FFFFFF"):
    if ref is None:
        return None
    if isinstance(ref, str) and ref.startswith("@"):
        return pr["_paleta"].get(ref[1:]) or pr["_paleta"].get("texto", padrao)
    return ref


# ---------------------------------------------------------------- texto e grupos
def token_exibido(w, pr):
    t = w.strip()
    if pr["pontuacao"] == "tirar_final":
        t = re.sub(r"[,.;:…]+$", "", t)
    elif pr["pontuacao"] == "tirar_tudo":
        t = re.sub(r"[,.;:…!?\"“”]+", "", t)
    if pr["caixa_alta"]:
        t = t.upper()
    return t


def corpo(t):
    c = t.rstrip("?!,.;:…\"”")
    return c, t[len(c):]


def e_chave(t):
    c = re.sub(r"[^\wÀ-ú]", "", t)
    return bool(c) and (any(ch.isdigit() for ch in c) or (c.isupper() and len(c) >= 2) or len(c) >= 11)


# palavras que não fecham grupo (ideia do --wrap phrase do ffmpeg-skill: nunca terminar linha em artigo/preposição)
FUNCAO = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos",
          "nas", "num", "numa", "por", "pelo", "pela", "para", "pra", "com", "sem", "que", "e", "ou", "se", "ao", "à",
          "aos", "às", "seu", "sua", "the", "of", "to"}


def _funcao(w):
    return re.sub(r"[^\wÀ-ú]", "", w["orig"].lower()) in FUNCAO and not re.search(r"[.,;:?!]$", w["orig"])


def agrupar(P, ag):
    """P: palavras de saída (t, s, e, seg, orig). Devolve lista de listas de índices."""
    grupos, cur = [], []
    ultimo_chave = -9
    if ag["regra"] == "paginas":
        janela = ag.get("janela_ms", 1400) / 1000
        for i, w in enumerate(P):
            if cur and (w["s"] - P[cur[0]]["s"] > janela or (not ag["atravessa_corte"] and w["seg"] != P[cur[-1]]["seg"])
                        or w["s"] - P[cur[-1]]["e"] >= ag["pausa_quebra"]):
                grupos.append(cur); cur = []
            cur.append(i)
        if cur:
            grupos.append(cur)
        return grupos
    mx = ag["max_palavras"]
    for i, w in enumerate(P):
        if cur:
            ant = P[cur[-1]]
            quebra = (len(cur) >= mx or w["s"] - ant["e"] >= ag["pausa_quebra"]
                      or w["e"] - P[cur[0]]["s"] > ag["max_seg"]
                      or (not ag["atravessa_corte"] and w["seg"] != ant["seg"])
                      or (ag["quebra_pontuacao"] and re.search(r"[.?!]$", ant["orig"]))
                      or (ag["quebra_pontuacao"] and re.search(r"[,;:]$", ant["orig"]) and len(cur) >= 2))
            if quebra:
                pausa_ou_pont = (w["s"] - ant["e"] >= ag["pausa_quebra"] or re.search(r"[.,;:?!]$", ant["orig"])
                                 or (not ag["atravessa_corte"] and w["seg"] != ant["seg"]))
                leva = []
                while not pausa_ou_pont and len(cur) > 1 and _funcao(P[cur[-1]]):
                    leva.insert(0, cur.pop())
                grupos.append(cur); cur = leva
        if ag.get("chave_sozinha") and e_chave(w["orig"]) and len(grupos) - ultimo_chave >= 3:
            junto = []
            if cur and all(_funcao(P[j]) for j in cur) and len(cur) <= 2:
                junto, cur = cur, []          # "o prazo?" fica junto, nunca um "o" sozinho
            if cur:
                grupos.append(cur); cur = []
            grupos.append(junto + [i]); ultimo_chave = len(grupos) - 1
            continue
        cur.append(i)
    if cur:
        grupos.append(cur)
    # grupo curto demais (pisca): junta ao seguinte, se couber e não atravessar corte
    md = ag.get("min_dur", 0)
    if md:
        out = []
        for g in grupos:
            if out and (P[out[-1][-1]]["e"] - P[out[-1][0]]["s"] < md) and len(out[-1]) < mx + 1 \
                    and (ag["atravessa_corte"] or P[g[0]]["seg"] == P[out[-1][-1]]["seg"]):
                out[-1] = out[-1] + g
            else:
                out.append(g)
        grupos = out
    return grupos


# ---------------------------------------------------------------- ASS
def cabecalho(pr, W, H, k):
    tc = cor(pr, pr["cores"]["texto"])
    oc = cor(pr, pr["cor_contorno"]) or "#000000"
    est = (f"Style: Leg,{pr['fonte']},{pr['tamanho'] * k:.1f},&H00{ass_cor(tc)[2:-1]},&H00{ass_cor(tc)[2:-1]},"
           f"&H00{ass_cor(oc)[2:-1]},&H00000000,{pr['negrito']},0,0,0,100,100,{pr['espacamento']},0,1,"
           f"{pr['contorno'] * k:.2f},0,2,0,0,0,1")
    return ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\nYCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n" + est + "\n"
            "Style: Desenho,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def ret_arred(x0, y0, x1, y1, r):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r < 0.5:
        return f"m {x0:.1f} {y0:.1f} l {x1:.1f} {y0:.1f} l {x1:.1f} {y1:.1f} l {x0:.1f} {y1:.1f}"
    return (f"m {x0+r:.1f} {y0:.1f} l {x1-r:.1f} {y0:.1f} b {x1:.1f} {y0:.1f} {x1:.1f} {y0:.1f} {x1:.1f} {y0+r:.1f} "
            f"l {x1:.1f} {y1-r:.1f} b {x1:.1f} {y1:.1f} {x1:.1f} {y1:.1f} {x1-r:.1f} {y1:.1f} l {x0+r:.1f} {y1:.1f} "
            f"b {x0:.1f} {y1:.1f} {x0:.1f} {y1:.1f} {x0:.1f} {y1-r:.1f} l {x0:.1f} {y0+r:.1f} "
            f"b {x0:.1f} {y0:.1f} {x0:.1f} {y0:.1f} {x0+r:.1f} {y0:.1f}")


def ease_io(p):
    p = min(max(p, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * p)


def ease_out(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def lerp(a, b, p):
    return a + (b - a) * p


def lerp_cor(c1, c2, p):
    a, b = hex_rgb(c1), hex_rgb(c2)
    return "#%02X%02X%02X" % tuple(round(lerp(x, y, p)) for x, y in zip(a, b))


# ---------------------------------------------------------------- geração
def gerar(palavras, preset, formato, destino_base, paleta=None, grupos_fixos=None, y=None, duracao=None, y_janelas=None):
    """palavras: [{w, s, e, seg}] na linha do tempo da saída. destino_base: caminho sem extensão.
    Gera <base>.ass, <base>.srt e <base>_grupos.json. Devolve dict com resumo."""
    pr = carregar_preset(preset, paleta)
    F = FORMATOS[formato]
    W, H = F["w"], F["h"]
    k = min(W, H) / 1080
    paisagem = W > H
    P = []
    for w in palavras:
        t = token_exibido(w["w"], pr)
        if t:
            P.append(dict(t=t, s=w["s"], e=max(w["e"], w["s"] + 0.04), seg=w.get("seg", 0), orig=w["w"].strip(),
                          seg_fim=w.get("seg_fim")))
    # palavra com duração ~zero colada na seguinte: divide o trecho pelas letras (como na v4)
    for a, c in zip(P, P[1:]):
        if c["s"] - a["s"] < 0.03:
            la, lc = len(a["t"]), len(c["t"])
            c["s"] = a["e"] = a["s"] + max(c["e"] - a["s"], 0.08) * la / (la + lc)
    ag = pr["agrupamento"]
    G = grupos_fixos if grupos_fixos else agrupar(P, ag)
    cab = cabecalho(pr, W, H, k)
    fs = pr["tamanho"] * k

    # posição (base do texto), presa na safe area
    yb = (y if y is not None else (pr["posicao"]["y_paisagem"] if paisagem else pr["posicao"]["y"])) * H
    safe = F["safe"]
    cx = W / 2
    pos = lambda dy=0: f"\\an2\\pos({cx:.1f},{yb + dy:.1f})"
    ref = medir(cab, [("Leg", "{" + pos() + "\\bord0}ÁÉpgjq|")], W, H, (yb - 3 * fs, yb + fs))[0]
    lt, lb = ref[1], ref[3]
    d = pr["destaque"]
    fd = pr["fundo"]
    pad_box = d.get("pad", [12, 6])
    pad_fd = (fd or {}).get("pad", [0, 0])
    folga_baixo = max(pad_box[1], pad_fd[1]) * k + 6
    if lb + folga_baixo > safe["y1"]:
        desl = lb + folga_baixo - safe["y1"]
        info(f"aviso: legenda subiu {desl:.0f} px para ficar dentro da safe area")
        yb -= desl; lt -= desl; lb -= desl
    faixa = (lt - 60 * k, lb + 60 * k)

    # medir grupos inteiros; quebra os que estouram a largura útil
    larg_max = safe["x1"] - safe["x0"] - 2 * max(pad_box[0], pad_fd[0]) * k
    def texto_grupo(g): return " ".join(P[i]["t"] for i in g)
    for _ in range(6):
        bbs = medir(cab, [("Leg", "{" + pos() + "\\bord0}" + texto_grupo(g)) for g in G], W, H, faixa)
        novo, mudou = [], False
        for g, bb in zip(G, bbs):
            if bb and bb[2] - bb[0] > larg_max and len(g) > 1:
                m = len(g) // 2
                novo += [g[:m], g[m:]]; mudou = True
            else:
                novo.append(g)
        G = novo
        if not mudou:
            break
    GB = bbs
    precisa_palavras = d["tipo"] in ("caixa", "marca-texto", "sublinhado") or bool((pr.get("chave") or {}).get("caixa"))
    XW = []
    if precisa_palavras:
        pedidos = []
        for g in G:
            for j in range(len(g)):
                partes = []
                for jj, i in enumerate(g):
                    c, pz = corpo(P[i]["t"])
                    partes.append(("{\\1c&HFFFFFF&}" if jj == j else "{\\1c&H000000&}") + c + "{\\1c&H000000&}" + pz)
                pedidos.append(("Leg", "{" + pos() + "\\bord0}" + " ".join(partes)))
        bbs = medir(cab, pedidos, W, H, faixa)
        it = iter(bbs)
        for g in G:
            XW.append([(lambda b: (b[0], b[2]) if b else (cx, cx))(next(it)) for _ in g])

    # tempos dos grupos
    fim_total = duracao if duracao else (P[-1]["e"] + 1.0 if P else 0)
    GR = []
    for n, g in enumerate(G):
        ini = P[g[0]]["s"]
        ult = P[g[-1]]["e"]
        prox = P[G[n + 1][0]]["s"] if n + 1 < len(G) else None
        fim = prox if (prox is not None and prox - ult < 0.6) else ult + ag.get("segura_fim", 0.35)
        if prox is not None:
            fim = min(fim, prox)
        if P[g[-1]].get("seg_fim") and not ag["atravessa_corte"]:
            fim = min(fim, P[g[-1]]["seg_fim"])   # legenda não passa do corte
        GR.append(dict(w=g, ini=ini, fim=min(fim, fim_total), bb=GB[n], x=XW[n] if XW else None))

    # cores
    c_txt = cor(pr, pr["cores"]["texto"])
    c_ativo = cor(pr, pr["cores"].get("ativo"))
    c_pass = cor(pr, pr["cores"].get("passado"))
    c_fut = cor(pr, pr["cores"].get("futuro"))
    c_box = cor(pr, d.get("cor", "@caixa"))
    c_txt_box = cor(pr, d.get("texto", "@texto_caixa"))
    op_box = d.get("opacidade", 1.0)
    trans = d.get("transicao", 0.1)
    ent, sai = pr["entrada"], pr["saida"]
    ch_cfg = pr.get("chave")
    ch_cx = (ch_cfg or {}).get("caixa")
    c_chave = cor(pr, ch_cfg.get("cor", "@destaque")) if ch_cfg else None
    c_chave_cx = cor(pr, ch_cx.get("cor", "@caixa")) if ch_cx else None
    if ch_cfg:
        def _n(t): return re.sub(r"[^\wÀ-ú]", "", t.lower())
        lista = {_n(x) for x in ch_cfg.get("lista", [])}
        excl = {_n(x) for x in ch_cfg.get("excluir", [])}
        for w in P:
            nn = _n(w["orig"])
            w["chave"] = nn not in excl and (nn in lista or (ch_cfg.get("auto", True) and e_chave(w["orig"])))
    ly0, ly1 = lt - pad_box[1] * k, lb + pad_box[1] * k

    def estado(gr, t):
        g = gr["w"]
        ks = [j for j, i in enumerate(g) if P[i]["s"] <= t + 1e-6]
        kk = ks[-1] if ks else 0
        sk = P[g[kk]]["s"]
        p = ease_io((t - sk) / trans) if trans > 0 else 1.0
        vivo = True
        if d.get("so_durante_palavra"):
            vivo = t <= P[g[kk]]["e"] + 0.06
        # entrada/saída
        qi = ease_out((t - gr["ini"]) / ent["dur"]) if ent["tipo"] != "nenhuma" else 1.0
        qo = min(max((gr["fim"] - t) / sai["dur"], 0), 1) if sai["tipo"] != "nenhuma" else 1.0
        alfa = 1.0
        dy = 0.0
        blur = 0.0
        esc = 100.0
        if ent["tipo"] in ("fade", "slide", "blur", "pop", "subir-desfocar"):
            alfa = qi
        if ent["tipo"] in ("slide", "subir-desfocar"):
            dy = ent.get("dy", 14) * k * (1 - qi)
        if ent["tipo"] in ("blur", "subir-desfocar"):
            blur = ent.get("blur", 6) * (1 - qi)
        if ent["tipo"] == "pop":
            tt = t - gr["ini"]
            esc = 60 + 50 * min(tt / 0.12, 1) if tt < 0.12 else (110 - 10 * min((tt - 0.12) / 0.08, 1))
            alfa = min(1.0, tt / 0.08) if tt < 0.08 else 1.0
        alfa *= qo
        # palavras
        tok = []
        caixas_ch = []
        for j, i in enumerate(g):
            c = c_txt
            a = 1.0
            e = 100
            if d["tipo"] in ("caixa", "marca-texto"):
                if d["tipo"] == "caixa":
                    peso = (p if j == kk else (1 - p if (j == kk - 1 and kk > 0) else 0.0))
                    if kk == 0 and j == 0 and not d.get("fade_primeiro"):
                        peso = 1.0
                else:
                    peso = 1.0 if j < kk else (p if j == kk else 0.0)
                    if kk == 0 and j == 0 and not d.get("fade_primeiro"):
                        peso = 1.0
                c = lerp_cor(c_txt, c_txt_box, peso) if c_txt_box else c_txt
            elif d["tipo"] in ("cor", "revelar", "sublinhado"):
                if j < kk and c_pass:
                    c = c_pass
                elif j > kk and c_fut:
                    c = c_fut
                if j == kk and vivo and c_ativo:
                    c = c_ativo
                if j == kk and vivo and d.get("escala"):
                    e = d["escala"]
                if d["tipo"] == "revelar":
                    a = 0.0 if j > kk else (ease_out((t - P[i]["s"]) / d.get("dur_palavra", 0.12)) if j == kk else 1.0)
            if ch_cfg and P[i]["chave"]:
                c = c_chave
                e = max(e, ch_cfg.get("escala", 100))
                if ch_cx and gr["x"] and a > 0.001:
                    px_, py_ = ch_cx.get("pad", [12, 4])
                    xa, xb = gr["x"][j]
                    caixas_ch.append((round(xa - px_ * k, 1), round(lt - py_ * k, 1), round(xb + px_ * k, 1),
                                      round(lb + py_ * k, 1), round(a, 3)))
            tok.append((P[i]["t"], c, a, e))
        # caixa / marca-texto / sublinhado
        forma = None
        if d["tipo"] in ("caixa", "marca-texto", "sublinhado") and gr["x"]:
            X = gr["x"]
            px = pad_box[0] * k
            if d["tipo"] == "caixa":
                if kk == 0:
                    bx0, bx1 = X[0][0] - px, X[0][1] + px
                else:
                    bx0 = lerp(X[kk - 1][0], X[kk][0], p) - px
                    bx1 = lerp(X[kk - 1][1], X[kk][1], p) + px
                fa = op_box * (p if (kk == 0 and d.get("fade_primeiro")) else 1.0)
                forma = (bx0, ly0, bx1, ly1, fa)
            elif d["tipo"] == "marca-texto":
                dir_ant = X[kk - 1][1] if kk else X[0][0]
                bx0, bx1 = X[0][0] - px, lerp(dir_ant, X[kk][1], p if kk or d.get("fade_primeiro") else 1.0) + px
                forma = (bx0, ly0, bx1, ly1, op_box)
            else:  # sublinhado crescendo da esquerda (0,4 s) sob a palavra ativa
                q = ease_out((t - sk) / d.get("dur_sublinhado", 0.4))
                h = d.get("altura", 6) * k
                yy = lb + d.get("dist", 6) * k
                if vivo:
                    forma = (X[kk][0], yy, lerp(X[kk][0], X[kk][1], q), yy + h, op_box)
        return (round(alfa, 3), round(dy, 1), round(blur, 2), round(esc, 1), tuple(tok), tuple(caixas_ch),
                tuple(round(v, 1) if isinstance(v, float) else v for v in forma) if forma else None)

    def a_ass(est, gr):
        alfa, dy, blur, esc, tok, caixas_ch, forma = est
        ev = []
        if alfa <= 0.001:
            return ev
        sc = f"\\fscx{esc}\\fscy{esc}" if esc != 100 else ""
        bl = f"\\blur{blur}" if blur > 0.05 else ""
        # sombras (camada 0)
        for sh in pr["sombras"]:
            partes = []
            for (t, c, a, e) in tok:
                aa = ass_alfa(sh["opacidade"] * a * alfa)
                partes.append(f"{{\\1a{aa}" + (f"\\fscx{e}\\fscy{e}" if e != 100 else "") + f"}}{t}")
            ev.append((0, "Leg", "{\\an2\\pos(%.1f,%.1f)\\1c&H000000&\\3a&HFF&\\bord0\\blur%s%s}" %
                       (cx + sh["dx"] * k, yb + dy + sh["dy"] * k, sh.get("blur", 3), sc) + " ".join(partes)))
        # fundo do grupo (camada 1)
        if fd and gr["bb"]:
            x0, _, x1, _ = gr["bb"]
            pxf, pyf = fd["pad"][0] * k, fd["pad"][1] * k
            sh_ = ret_arred(x0 - pxf, lt - pyf + dy, x1 + pxf, lb + pyf + dy, fd.get("raio", 0) * k)
            bd = fd.get("borda")
            bt = (f"\\bord{bd['largura'] * k:.1f}\\3c{ass_cor(cor(pr, bd['cor']))}\\3a{ass_alfa(bd['opacidade'] * alfa)}"
                  if bd else "\\bord0")
            ev.append((1, "Desenho", f"{{\\an7\\pos(0,0)\\p1\\shad0{bt}\\1c{ass_cor(cor(pr, fd['cor']))}"
                                     f"\\1a{ass_alfa(fd.get('opacidade', 1) * alfa)}}}{sh_}{{\\p0}}"))
        # caixa da palavra-chave (camada 2), aparece junto com a palavra
        for (x0, y0, x1, y1, fa) in caixas_ch:
            ev.append((2, "Desenho", f"{{\\an7\\pos(0,{dy:.1f})\\p1\\shad0\\bord0\\1c{ass_cor(c_chave_cx)}"
                                     f"\\1a{ass_alfa(fa * alfa * ch_cx.get('opacidade', 1.0))}}}{ret_arred(x0, y0, x1, y1, ch_cx.get('raio', 10) * k)}{{\\p0}}"))
        # destaque (camada 2)
        if forma:
            x0, y0, x1, y1, fa = forma
            r = d.get("raio", 10) * k
            bd = d.get("borda")
            bt = (f"\\bord{bd['largura'] * k:.1f}\\3c{ass_cor(cor(pr, bd['cor']))}\\3a{ass_alfa(bd['opacidade'] * fa * alfa)}"
                  if bd else "\\bord0")
            ev.append((2, "Desenho", f"{{\\an7\\pos(0,{dy:.1f})\\p1\\shad0{bt}\\1c{ass_cor(c_box)}"
                                     f"\\1a{ass_alfa(fa * alfa)}}}{ret_arred(x0, y0, x1, y1, r)}{{\\p0}}"))
        # texto (camada 3)
        partes = []
        for (t, c, a, e) in tok:
            aa = ass_alfa(a * alfa)
            partes.append(f"{{\\1c{ass_cor(c)}\\1a{aa}\\3a{aa}" + (f"\\fscx{e}\\fscy{e}" if e != 100 else "") + f"}}{t}")
        ev.append((3, "Leg", "{" + pos(dy) + bl + sc + "}" + " ".join(partes)))
        return ev

    linhas = []
    if d["tipo"] == "sweep":
        # varredura de cor nativa do libass (\kf), como o --karaoke do ffmpeg-skill
        for gr in GR:
            g = gr["w"]
            fx = ""
            if ent["tipo"] == "pop":
                fx = "\\fad(80,120)\\fscx60\\fscy60\\t(0,120,\\fscx110\\fscy110)\\t(120,200,\\fscx100\\fscy100)"
            elif ent["tipo"] == "fade":
                fx = f"\\fad({int(ent['dur'] * 1000)},0)"
            partes = []
            for j, i in enumerate(g):
                fim_w = P[g[j + 1]]["s"] if j + 1 < len(g) else P[i]["e"]
                ini_w = gr["ini"] if j == 0 else P[i]["s"]
                partes.append(f"{{\\kf{max(1, round((fim_w - ini_w) * 100))}}}{P[i]['t']}")
            txt = (f"{{{pos()}\\1c{ass_cor(cor(pr, d.get('cor', '@destaque')))}\\2c{ass_cor(c_txt)}{fx}}}"
                   + " ".join(partes))
            for sh in pr["sombras"]:
                linhas.append((gr["ini"], gr["fim"], 0, "Leg",
                               "{\\an2\\pos(%.1f,%.1f)\\1c&H000000&\\1a%s\\3a&HFF&\\bord0\\blur%s%s}%s" %
                               (cx + sh["dx"] * k, yb + sh["dy"] * k, ass_alfa(sh["opacidade"]), sh.get("blur", 3),
                                fx.replace("\\fscx60\\fscy60", "\\fscx60\\fscy60"), texto_grupo(g))))
            linhas.append((gr["ini"], gr["fim"], 3, "Leg", txt))
    else:
        for gr in GR:
            _n0 = len(linhas)
            f0 = math.ceil(gr["ini"] * FPS - 1e-6)
            f1 = math.ceil(gr["fim"] * FPS - 1e-6) - 1
            atual = None
            for f in range(f0, f1 + 1):
                st = estado(gr, f / FPS)
                if atual and atual[2] == st:
                    atual[1] = f
                else:
                    if atual:
                        for camada, est_, txt in a_ass(atual[2], gr):
                            linhas.append(((atual[0] - 0.5) / FPS, (atual[1] + 0.5) / FPS, camada, est_, txt))
                    atual = [f, f, st]
            if atual:
                for camada, est_, txt in a_ass(atual[2], gr):
                    linhas.append(((atual[0] - 0.5) / FPS, (atual[1] + 0.5) / FPS, camada, est_, txt))
            # janelas de posição: o grupo inteiro sobe/desce (ex.: legenda no topo enquanto um painel ocupa o torso)
            for (j0, j1, jy) in (y_janelas or []):
                if j0 - 0.01 <= gr["ini"] < j1:
                    delta = jy * H - yb
                    for n in range(_n0, len(linhas)):
                        a_, z_, c_, e_, t_ = linhas[n]
                        t_ = re.sub(r"\\pos\(([-\d.]+),([-\d.]+)\)",
                                    lambda m: "\\pos(%s,%.1f)" % (m.group(1), float(m.group(2)) + delta), t_)
                        linhas[n] = (a_, z_, c_, e_, t_)
                    break

    ass_txt = cab + "".join(f"Dialogue: {c},{ts_ass(a)},{ts_ass(z)},{e},,0,0,0,,{t}\n"
                            for a, z, c, e, t in sorted(linhas, key=lambda x: (x[0], x[2])))
    base = Path(destino_base)
    Path(f"{base}.ass").write_text(ass_txt, encoding="utf-8")
    srt = []
    for n, gr in enumerate(GR, 1):
        srt.append(f"{n}\n{ts_srt(gr['ini'])} --> {ts_srt(gr['fim'])}\n{' '.join(P[i]['orig'] for i in gr['w'])}\n")
    Path(f"{base}.srt").write_text("\n".join(srt), encoding="utf-8")
    resumo = dict(preset=preset, paleta=pr["_paleta_nome"], formato=formato, y_base=round(yb, 1),
                  faixa_texto=[lt, lb], grupos=[dict(ini=round(g["ini"], 3), fim=round(g["fim"], 3),
                                                     palavras=g["w"], texto=" ".join(P[i]["t"] for i in g["w"]),
                                                     bbox=g["bb"]) for g in GR],
                  tokens=[dict(t=w["t"], s=round(w["s"], 3), e=round(w["e"], 3)) for w in P])
    Path(f"{base}_grupos.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo
