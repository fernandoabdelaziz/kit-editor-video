"""Motion graphics do kit-editor via HyperFrames LOCAL (HTML + GSAP -> ProRes 4444 com alfa).

Uma "spec" JSON pequena descreve os efeitos (nomes do nosso vocabulário). O módulo gera um projeto
HyperFrames em <saida>_projeto/ (GSAP e fonte Inter vendorizados, nada de CDN), renderiza com o
wrapper isolado <raiz>/ferramentas/hyperframes-run/hf.sh (telemetria/updates desligados, sem rede via
unshare -n) e confere a área ocupada contra as safe areas. A sobreposição no vídeo é feita pelo ffmpeg
(`kit.py sobrepor` ou `kit.py renderizar --overlays`).

Formato da spec (ver motion/exemplos/*.json):
{
  "formato": "reels",              # reels | linkedin | paisagem
  "paleta": "verde-bege",          # legendas/paletas.json
  "edl": "trabalho/T/edl.json",    # opcional: tempos das palavras na linha do tempo da SAÍDA
  "duracao": 21.6,                 # opcional (senão: total da EDL)
  "efeitos": [
    {"efeito": "lower-third", "texto": "Nome Sobrenome", "apoio": "Profissão",
     "inicio": 0.4, "duracao": 3.4, "texto_aprovado": "nome e cargo de quem fala"},
    {"efeito": "count-up", "texto": "19 de outubro", "sincronizar": true},
    {"efeito": "typewriter-highlight", "texto": "o prazo é de trinta dias", "destaque": "trinta dias", "sincronizar": true}
  ]
}
Campos comuns de efeito: inicio/duracao (s, saída) OU sincronizar (true = procura `texto` na fala; ou
uma frase), entrada (s, padrão 0.5), saida (padrão 70% da entrada), manter (s após a última palavra,
padrão 0.7), posicao ("terco-superior" | "centro" | "terco-inferior" | {"x":..,"y":..}), alinhar
("esquerda" | "centro"), tamanho (px do texto principal), ease (padrão "power2.inOut").
Regra de conteúdo: o texto precisa estar na fala (EDL) — senão o efeito exige "texto_aprovado" com o
motivo (ex.: nome e cargo). Nada de informação técnica inventada na tela.
"""
import html
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from .comum import FORMATOS, FPS, KIT, RAIZ, HF_DIR, caminho, erro, info, ler_json, run, saida_segura
from . import edl as E

HF = HF_DIR / "hf.sh"
MOTORES = ("hyperframes",)
GSAP = HF_DIR / "vendor" / "gsap-3.15.0" / "gsap.min.js"
FONTE = KIT / "motion" / "fontes" / "Inter-Variable.ttf"
PALETAS = KIT / "legendas" / "paletas.json"

EFEITOS = {
    "lower-third": "nome/cargo em cartão no terço inferior: slide + fade, linhas sobem de máscara",
    "count-up": "número conta até o valor dito (ex.: 19) e o resto da frase entra por máscara",
    "typewriter-highlight": "frase datilografada no ritmo da fala; uma palavra ganha marca-texto",
    "mask-reveal": "frase revelada por máscara (cortina da esquerda para a direita), no tempo da fala",
    "painel-crescente": "painel compacto no topo: título + pontos que entram um a um (e crescem o painel) quando cada ponto é dito",
    "stagger-topicos": "lista de tópicos entrando em sequência (fade + sobe 24 px), cada um quando é dito",
    "titulo-cinetico": "título palavra a palavra (sobe e desfoca), cada palavra quando é dita",
    "chips-topo": "fichas de tópico (pílulas) no topo, entrando em sequência quando cada palavra é dita e acumulando",
    "cartao-documento": "cartão claro flutuante (cantos arredondados, sombra suave) sobe com frase datilografada e marca-texto",
}


def _norm(w):
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", w)


def _achar(palavras, frase):
    alvo = [t for t in (_norm(x) for x in frase.split()) if t]
    seq = [_norm(p["w"]) for p in palavras]
    for i in range(len(seq) - len(alvo) + 1):
        if seq[i:i + len(alvo)] == alvo:
            return palavras[i:i + len(alvo)]
    return None


def _achar_apos(palavras, frase, t_min=-1.0):
    """Como _achar, mas a primeira ocorrência que começa em/apos t_min (tópicos ditos em momentos diferentes)."""
    alvo = [t for t in (_norm(x) for x in frase.split()) if t]
    seq = [_norm(p["w"]) for p in palavras]
    for i in range(len(seq) - len(alvo) + 1):
        if seq[i:i + len(alvo)] == alvo and palavras[i]["s"] >= t_min:
            return palavras[i:i + len(alvo)]
    return None


def _paleta(nome):
    pals = json.loads(PALETAS.read_text(encoding="utf-8"))
    if nome not in pals or nome.startswith("_"):
        erro(f"paleta desconhecida: {nome} (kit.py paletas)")
    p = dict(pals[nome])
    # realce: se a caixa é igual ao fundo do cartão, o marca-texto usa o destaque com texto escuro
    if p["caixa"].lower() == p["fundo"].lower():
        p["realce"], p["realce_texto"] = p["destaque"], p["fundo"]
    else:
        p["realce"], p["realce_texto"] = p["caixa"], p["texto_caixa"]
    return p


def _pos(fx, F):
    W, H, s = F["w"], F["h"], F["safe"]
    pos = fx.get("posicao", fx.get("_pos_padrao", "terco-superior"))
    if isinstance(pos, dict):
        return int(pos["x"]), int(pos["y"]), None
    tops = {"terco-superior": s["y0"] + 30, "centro": int(H * 0.40), "terco-inferior": int(H * 0.60)}
    if pos not in tops:
        erro(f"posicao inválida: {pos}")
    return s["x0"] + 12, tops[pos], pos


def _medir(texto, tam, peso=700, espac_em=0.0):
    """Largura (px) do texto em Inter (mesma fonte vendorizada que o Chrome usa; eixo opsz = tamanho, até 32)."""
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONTE), tam)
    try:
        f.set_variation_by_axes([min(32, max(14, tam)), peso])
    except Exception:
        pass
    return f.getlength(texto) + espac_em * tam * len(texto)


def _esc(t):
    return html.escape(str(t), quote=True)


def _js(v):
    return json.dumps(v, ensure_ascii=False)


class _Montador:
    def __init__(self, spec, F, pal, palavras, total):
        self.spec, self.F, self.pal, self.palavras, self.total = spec, F, pal, palavras, total
        self.html, self.css, self.js, self.resumo = [], [], [], []
        self.dados = {}  # dados já resolvidos (tempos, textos, medidas) de cada efeito

    # ---- tempo ---------------------------------------------------------------------------------
    def tempos(self, i, fx):
        ent = float(fx.get("entrada", 0.5))
        sai = float(fx.get("saida", round(ent * 0.7, 3)))
        palavras = None
        if fx.get("sincronizar"):
            if not self.palavras:
                erro(f"efeito {i}: 'sincronizar' precisa de 'edl' na spec")
            frase = fx["sincronizar"] if isinstance(fx["sincronizar"], str) else fx.get("texto") or " ".join(fx.get("itens", []))
            palavras = _achar(self.palavras, frase)
            if not palavras:
                erro(f"efeito {i}: não achei na fala: «{frase}»")
        if "inicio" in fx:
            ini = float(fx["inicio"])
        elif palavras:
            ini = max(0.0, palavras[0]["s"] - float(fx.get("antecipar", 0.15)) - ent * 0.5)
        else:
            erro(f"efeito {i}: informe 'inicio' ou 'sincronizar'")
        if "duracao" in fx:
            fim = ini + float(fx["duracao"])
        elif palavras:
            fim = palavras[-1]["e"] + float(fx.get("manter", 0.7)) + sai
        else:
            erro(f"efeito {i}: informe 'duracao' ou 'sincronizar'")
        fim = min(fim, self.total - 1.0 / FPS)
        ini, fim = round(ini * FPS) / FPS, round(fim * FPS) / FPS
        if fim - ini < ent + sai + 0.3:
            erro(f"efeito {i}: duração curta demais ({fim - ini:.2f} s) para entrada+saída")
        return ini, fim, ent, sai, palavras

    def conferir_texto(self, i, fx, textos):
        if fx.get("texto_aprovado"):
            return f"aprovado: {fx['texto_aprovado']}"
        for t in textos:
            if not t:
                continue
            if not self.palavras or not _achar(self.palavras, t):
                erro(f"efeito {i}: «{t}» não está na fala. Só texto falado (ou 'texto_aprovado' com o motivo, "
                     "ex.: nome e cargo). Não inventar informação na tela.")
        return "na fala"

    # ---- efeitos -------------------------------------------------------------------------------
    def wrapper(self, i, ini, fim, corpo, alinhar, x, y, larg):
        W = self.F["w"]
        if alinhar == "centro":
            estilo = f"position:absolute;left:0;top:{y}px;width:{W}px;display:flex;justify-content:center;"
        else:
            estilo = f"position:absolute;left:{x}px;top:{y}px;width:{larg}px;"
        self.html.append(
            f'<div id="fx{i}" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" '
            f'data-track-index="{i + 1}" data-layout-allow-overflow style="{estilo}">{corpo}</div>')

    def saida_tl(self, alvo, fim, sai, dx=0, dy=0, ease="power2.inOut"):
        t0 = fim - sai - 1.0 / FPS
        self.js.append(f'tl.to({_js(alvo)},{{opacity:0,x:{dx},y:{dy},duration:{sai},ease:{_js(ease)}}},{t0:.4f});')

    def fx_lower_third(self, i, fx):
        p, s = self.pal, self.F["safe"]
        fx.setdefault("_pos_padrao", "terco-inferior")
        ini, fim, ent, sai, _ = self.tempos(i, fx)
        origem = self.conferir_texto(i, fx, [fx["texto"], fx.get("apoio")])
        x, y, _ = _pos(fx, self.F)
        if not isinstance(fx.get("posicao"), dict):
            x = s["x0"] + 40  # folga para o slide de 36 px não sair da safe area
        tam = int(fx.get("tamanho", 54))
        ease = fx.get("ease", "power2.inOut")
        if fx.get("uma_linha"):
            # etiqueta compacta numa linha só (nome · cargo), para caber no espaço livre acima da cabeça
            tam = int(fx.get("tamanho", 34))
            sep = " · "
            larg = (_medir(fx["texto"], tam, 700) + (_medir(sep + fx.get("apoio", ""), tam, 500) if fx.get("apoio") else 0)
                    + 22 + 7 + 30 + 36)
            if fx.get("alinhar") == "centro":
                x = round((self.F["w"] - larg) / 2)
            corpo = (f'<div id="fx{i}-c" class="lt lt1"><div class="lt-barra"></div><div class="lt-l">'
                     f'<span id="fx{i}-a" class="lt-in lt-nome">{_esc(fx["texto"])}</span>'
                     + (f'<span id="fx{i}-b" class="lt-in lt-apoio">{_esc(sep + fx["apoio"])}</span>' if fx.get("apoio") else "")
                     + '</div></div>')
            self.css.append(
                f".lt1{{display:inline-flex;gap:22px;align-items:stretch;background:{p['fundo']};border-radius:10px;"
                f"padding:14px 30px 15px 18px;color:{p['texto']};box-shadow:0 6px 18px rgba(0,0,0,0.22);white-space:nowrap;}}"
                f".lt-barra{{width:7px;border-radius:4px;background:{p['apoio']};}}"
                f".lt-l{{overflow:hidden;line-height:1.15;}} .lt-in{{display:inline-block;}}"
                f"#fx{i}-a{{font-weight:700;font-size:{tam}px;}} #fx{i}-b{{font-weight:500;font-size:{tam}px;color:{p['apoio']};white-space:pre;}}")
            self.wrapper(i, ini, fim, corpo, "esquerda", x, y, round(larg) + 40)
            self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,y:-14}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
            alvos = [f"#fx{i}-a"] + ([f"#fx{i}-b"] if fx.get("apoio") else [])
            self.js.append(f'tl.fromTo({_js(alvos)},{{yPercent:110}},{{yPercent:0,duration:{ent * 0.9:.3f},ease:{_js(ease)},stagger:0.08}},{ini + ent * 0.3:.4f});')
            self.saida_tl(f"#fx{i}-c", fim, sai, dy=-10, ease=ease)
            self.dados[i] = dict(tipo="etiqueta", ini=ini, fim=fim, ent=ent, sai=sai, texto=fx["texto"],
                                 apoio=(sep + fx["apoio"]) if fx.get("apoio") else "", tam=tam, x=x, y=y)
            return ini, fim, origem
        apoio = f'<div class="lt-l"><span id="fx{i}-b" class="lt-in">{_esc(fx["apoio"])}</span></div>' if fx.get("apoio") else ""
        corpo = (f'<div id="fx{i}-c" class="lt"><div class="lt-barra"></div><div>'
                 f'<div class="lt-l"><span id="fx{i}-a" class="lt-in lt-nome">{_esc(fx["texto"])}</span></div>{apoio}</div></div>')
        self.css.append(
            f".lt{{display:inline-flex;gap:22px;align-items:stretch;background:{p['fundo']};border-radius:12px;"
            f"padding:24px 40px 26px 26px;color:{p['texto']};}}"
            f".lt-barra{{width:7px;border-radius:4px;background:{p['apoio']};}}"
            f".lt-l{{overflow:hidden;line-height:1.18;}} .lt-in{{display:inline-block;}}"
            f".lt-nome{{font-weight:700;font-size:{tam}px;letter-spacing:0.005em;}}"
            f"#fx{i}-b{{font-weight:500;font-size:{round(tam * 0.66)}px;color:{p['apoio']};margin-top:4px;}}")
        self.wrapper(i, ini, fim, corpo, "esquerda", x, y, s["x1"] - x)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,x:-36}},{{opacity:1,x:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
        alvos = [f"#fx{i}-a"] + ([f"#fx{i}-b"] if fx.get("apoio") else [])
        self.js.append(f'tl.fromTo({_js(alvos)},{{yPercent:110}},{{yPercent:0,duration:{ent * 0.9:.3f},ease:{_js(ease)},stagger:0.08}},{ini + ent * 0.3:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, dx=-24, ease=ease)
        return ini, fim, origem

    def _cartao_frase(self, i, fx, inner_html, ini, fim, larg_padrao=None):
        p, s = self.pal, self.F["safe"]
        x, y, _ = _pos(fx, self.F)
        alinhar = fx.get("alinhar", "esquerda")
        larg = s["x1"] - x - 12
        self.css.append(f"#fx{i}-c{{background:{p['fundo']};color:{p['texto']};border-radius:12px;padding:{fx.get('padding', '26px 38px 30px')};"
                        f"box-sizing:border-box;max-width:{s['x1'] - s['x0'] - 24}px;display:inline-block;}}")
        self.wrapper(i, ini, fim, f'<div id="fx{i}-c">{inner_html}</div>', alinhar, x, y, larg)

    def fx_count_up(self, i, fx):
        p = self.pal
        ini, fim, ent, sai, pals = self.tempos(i, fx)
        origem = self.conferir_texto(i, fx, [fx["texto"]])
        toks = fx["texto"].split()
        k = next((j for j, t in enumerate(toks) if re.fullmatch(r"\d+([.,]\d+)?", t.strip(",."))), None)
        if k is None:
            erro(f"efeito {i}: count-up precisa de um número no texto")
        alvo_num = toks[k].strip(",.")
        valor = float(alvo_num.replace(".", "").replace(",", ".")) if "," in alvo_num else float(alvo_num)
        casas = len(alvo_num.split(",")[1]) if "," in alvo_num else 0
        de = float(fx.get("de", 0 if valor > 100 else 1))
        antes, depois = " ".join(toks[:k]), " ".join(toks[k + 1:])
        # sincronia: o número chega ao valor quando a palavra do número termina; o resto entra quando é dito
        t_num_fim = pals[k]["e"] if pals else ini + ent + 0.6
        t_cont_ini = max(ini + ent * 0.6, t_num_fim - float(fx.get("contagem", 0.7)))
        t_resto = pals[k + 1]["s"] if pals and depois else t_num_fim + 0.1
        tam = int(fx.get("tamanho", 150))
        largura_num = len(alvo_num) * 0.62 + 0.1
        inner = (f'<div class="cu">'
                 + (f'<span class="cu-l"><span id="fx{i}-p" class="cu-t">{_esc(antes)}</span></span>' if antes else "")
                 + f'<span id="fx{i}-n" class="cu-n" style="min-width:{largura_num:.2f}em">{_esc(alvo_num if de == valor else int(de) if not casas else de)}</span>'
                 + (f'<span class="cu-l"><span id="fx{i}-r" class="cu-t">{_esc(depois)}</span></span>' if depois else "")
                 + "</div>")
        self.css.append(f".cu{{display:flex;align-items:baseline;gap:22px;}}"
                        f".cu-n{{font-weight:700;font-size:{tam}px;line-height:1;font-variant-numeric:tabular-nums;color:{p['texto']};text-align:right;}}"
                        f".cu-l{{overflow:hidden;display:inline-block;padding-bottom:6px;}} .cu-t{{display:inline-block;font-weight:600;font-size:{round(tam * 0.46)}px;color:{p['apoio']};}}")
        fx.setdefault("alinhar", "centro")
        self._cartao_frase(i, fx, inner, ini, fim)
        ease = fx.get("ease", "power2.inOut")
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,y:30}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
        fmt = f"(v)=>v.toFixed({casas}).replace('.',',')" if casas else "(v)=>String(Math.round(v))"
        self.js.append(
            f'(function(){{const el=document.getElementById("fx{i}-n");const o={{v:{de}}};const f={fmt};'
            f'tl.fromTo(o,{{v:{de}}},{{v:{valor},duration:{t_num_fim - t_cont_ini:.3f},ease:"power2.out",'
            f'onUpdate:()=>{{el.textContent=f(o.v);}}}},{t_cont_ini:.4f});}})();')
        if antes:
            self.js.append(f'tl.fromTo("#fx{i}-p",{{yPercent:110}},{{yPercent:0,duration:0.35,ease:{_js(ease)}}},{ini + ent * 0.4:.4f});')
        if depois:
            self.js.append(f'tl.fromTo("#fx{i}-r",{{yPercent:110}},{{yPercent:0,duration:0.4,ease:{_js(ease)}}},{t_resto - 0.05:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, dy=-16, ease=ease)
        return ini, fim, origem

    def _palavras_html(self, i, fx, texto, destaque=None, cls="w", j0=0):
        out, alvo = [], _norm(destaque) if destaque else None
        def _ch(t):
            return "".join(f'<span class="ch">{_esc(c)}</span>' for c in t) if cls == "tw" else _esc(t)
        for j, w in enumerate(texto.split(), start=j0):
            hl = alvo and _norm(w) == alvo
            inner = _ch(w)
            if hl:
                m = re.match(r"^(\W*)(.*?)(\W*)$", w)
                pre, nucleo, pos = m.group(1), m.group(2), m.group(3)
                out.append(f'<span id="fx{i}-w{j}" class="{cls}">{_ch(pre)}<span class="hlw"><span id="fx{i}-hl" class="hl"></span>'
                           f'<span class="hlt" id="fx{i}-ht">{_ch(nucleo)}</span></span>{_ch(pos)}</span>')
            else:
                out.append(f'<span id="fx{i}-w{j}" class="{cls}">{inner}</span>')
        return " ".join(out)

    def fx_typewriter_highlight(self, i, fx):
        p = self.pal
        ini, fim, ent, sai, pals = self.tempos(i, fx)
        origem = self.conferir_texto(i, fx, [fx["texto"]])
        tam = int(fx.get("tamanho", 60))
        ease = fx.get("ease", "power2.inOut")
        inner = f'<div class="twl" style="font-size:{tam}px">{self._palavras_html(i, fx, fx["texto"], fx.get("destaque"), "tw")}</div>'
        self.css.append(f".twl{{font-weight:700;line-height:1.28;}} .tw{{display:inline-block;position:relative;white-space:nowrap;}}"
                        f".hlw{{position:relative;display:inline-block;margin:0 0.14em;}}"
                        f".hl{{position:absolute;left:-0.12em;right:-0.12em;top:4%;bottom:0;background:{p['realce']};border-radius:8px;transform-origin:0 50%;z-index:0;}}"
                        f".hlt{{position:relative;z-index:1;}} .ch{{opacity:0;}}")
        self._cartao_frase(i, fx, inner, ini, fim)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,y:24}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
        t = ini + ent * 0.8
        cps = float(fx.get("cps", 22))
        for j, w in enumerate(fx["texto"].split()):
            if pals:
                t0 = max(pals[j]["s"], ini + ent * 0.6)
                dur = min(max(pals[j]["e"] - pals[j]["s"], 0.12), len(w) / cps * 1.6)
            else:
                t0, dur = t, len(w) / cps
                t = t0 + dur + 2.0 / cps
            passo = dur / max(1, len(w))
            self.js.append(f'document.querySelectorAll("#fx{i}-w{j} .ch").forEach((c,k)=>tl.set(c,{{opacity:1}},{t0:.4f}+k*{passo:.4f}));')
            if fx.get("destaque") and _norm(w) == _norm(fx["destaque"]):
                th = t0 + dur + 0.04
                self.js.append(f'tl.fromTo("#fx{i}-hl",{{scaleX:0}},{{scaleX:1,duration:0.32,ease:{_js(ease)}}},{th:.4f});')
                self.js.append(f'tl.fromTo("#fx{i}-ht",{{color:{_js(p["texto"])}}},{{color:{_js(p["realce_texto"])},duration:0.2,ease:"none"}},{th + 0.1:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, dy=-12, ease=ease)
        return ini, fim, origem

    def fx_painel_crescente(self, i, fx):
        """Painel compacto (topo, centrado) que cresce a cada ponto citado: título + itens {texto, fala, subs:[{texto, fala}]}.
        Cada item/sub entra (altura 0→auto + fade) quando a `fala` é dita; o painel sai inteiro no fim."""
        p = self.pal
        itens = fx["itens"]
        ent = float(fx.get("entrada", 0.45))
        sai = float(fx.get("saida", round(ent * 0.7, 3)))
        ease = fx.get("ease", "power2.out")
        textos = [fx["titulo"]] if fx.get("titulo") else []
        for it in itens:
            textos.append(it["texto"])
            textos += [sb["texto"] for sb in it.get("subs", [])]
        origem = self.conferir_texto(i, fx, textos)
        ini = float(fx["inicio"])
        fim = ini + float(fx["duracao"])
        fim = round(min(fim, self.total - 1.0 / FPS) * FPS) / FPS
        ini = round(ini * FPS) / FPS
        t_min, tempos = ini, []
        def _quando(fr):
            nonlocal t_min
            ws = _achar_apos(self.palavras, fr, t_min)
            if not ws:
                erro(f"efeito {i}: «{fr}» não achada na fala (depois de {t_min:.2f} s)")
            t_min = ws[0]["s"] + 0.01
            return ws[0]["s"] - float(fx.get("antecipar", 0.08))
        html_it = ""
        for k, it in enumerate(itens):
            tk = float(it["inicio"]) if "inicio" in it else _quando(it.get("fala", it["texto"]))
            subs = ""
            ts = []
            for m, sb in enumerate(it.get("subs", [])):
                tm = float(sb["inicio"]) if "inicio" in sb else _quando(sb.get("fala", sb["texto"]))
                ts.append(tm)
                subs += (f'<div id="fx{i}-s{k}_{m}" class="pc-g"><div class="pc-gi"><div class="pc-s">{_esc(sb["texto"])}</div></div></div>')
            tempos.append((tk, ts))
            html_it += (f'<div id="fx{i}-g{k}" class="pc-g"><div class="pc-gi"><div class="pc-i">{_esc(it["texto"])}</div>{subs}</div></div>')
        larg = int(fx.get("largura", 900))
        ti, ts_ = int(fx.get("tamanho", 36)), int(fx.get("tamanho_sub", 28))
        self.css.append(
            f"#fx{i}-c{{width:{larg}px;box-sizing:border-box;background:{p['fundo']};color:{p['texto']};border-radius:12px;"
            f"padding:{fx.get('padding', '24px 36px 26px')};opacity:0;}}"
            f".pc-t{{font-weight:650;font-size:30px;letter-spacing:0.12em;text-transform:uppercase;color:{p['apoio']};}}"
            f".pc-g{{display:grid;grid-template-rows:0fr;opacity:0;}} .pc-gi{{overflow:hidden;min-height:0;}}"
            f".pc-i{{font-weight:650;font-size:{ti}px;line-height:1.25;margin-top:16px;padding-left:18px;border-left:4px solid {p['destaque']};}}"
            f".pc-s{{font-weight:500;font-size:{ts_}px;line-height:1.25;color:{p['apoio']};margin-top:6px;padding-left:22px;}}")
        x, y, _ = _pos(fx, self.F)
        titulo = f'<div class="pc-t">{_esc(fx["titulo"])}</div>' if fx.get("titulo") else ""
        if fx.get("subtitulo"):
            titulo += f'<div class="pc-u">{_esc(fx["subtitulo"])}</div>'
            self.css.append(f".pc-u{{font-weight:650;font-size:{ti}px;line-height:1.25;margin-top:10px;}}")
        corpo = f'<div id="fx{i}-c">{titulo}{html_it}</div>'
        self.wrapper(i, ini, fim, corpo, "centro", x, y, larg)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,y:20}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
        cres = lambda sel, t: self.js.append(
            f'tl.fromTo("{sel}",{{gridTemplateRows:"0fr",opacity:0}},{{gridTemplateRows:"1fr",opacity:1,duration:0.5,ease:{_js(ease)}}},{max(t, ini + ent):.4f});')
        for k, (tk, ts) in enumerate(tempos):
            cres(f"#fx{i}-g{k}", tk)
            for m, tm in enumerate(ts):
                cres(f"#fx{i}-s{k}_{m}", tm)
        self.saida_tl(f"#fx{i}-c", fim, sai, dy=-12, ease="power2.inOut")
        return ini, fim, origem

    def fx_mask_reveal(self, i, fx):
        ini, fim, ent, sai, pals = self.tempos(i, fx)
        origem = self.conferir_texto(i, fx, [fx["texto"]])
        tam = int(fx.get("tamanho", 60))
        ease = fx.get("ease", "power2.inOut")
        inner = f'<div id="fx{i}-m" class="mr" style="font-size:{tam}px">{_esc(fx["texto"])}</div>'
        self.css.append(f".mr{{font-weight:700;line-height:1.25;}}")
        self._cartao_frase(i, fx, inner, ini, fim)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0}},{{opacity:1,duration:{ent * 0.6:.3f},ease:{_js(ease)}}},{ini:.4f});')
        t0 = max(pals[0]["s"], ini + ent * 0.4) if pals else ini + ent * 0.4
        t1 = pals[-1]["e"] if pals else t0 + float(fx.get("revelar", 0.8))
        self.js.append(f'tl.fromTo("#fx{i}-m",{{clipPath:"inset(0% 100% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:{max(0.3, t1 - t0):.3f},ease:{_js(ease)}}},{t0:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, ease=ease)
        return ini, fim, origem

    def fx_stagger_topicos(self, i, fx):
        p = self.pal
        itens = fx["itens"]
        sinc = fx.get("sincronizar")
        fx2 = dict(fx); fx2["sincronizar"] = " ".join(itens) if sinc is True else sinc
        ini, fim, ent, sai, pals = self.tempos(i, fx2)
        origem = self.conferir_texto(i, fx, itens)
        tam = int(fx.get("tamanho", 50))
        ease = fx.get("ease", "power2.inOut")
        linhas = "".join(f'<div id="fx{i}-i{j}" class="st"><span class="st-b"></span><span>{_esc(t)}</span></div>' for j, t in enumerate(itens))
        self.css.append(f".st{{display:flex;align-items:center;gap:20px;font-weight:600;font-size:{tam}px;line-height:1.3;margin:6px 0;}}"
                        f".st-b{{width:14px;height:14px;border-radius:3px;background:{p['apoio']};flex:none;}}")
        self._cartao_frase(i, fx, linhas, ini, fim)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0}},{{opacity:1,duration:{ent * 0.6:.3f},ease:{_js(ease)}}},{ini:.4f});')
        pos = 0
        for j, t in enumerate(itens):
            n = len(t.split())
            tj = max(pals[pos]["s"] - 0.05, ini + ent * 0.3) if pals else ini + ent * 0.5 + j * float(fx.get("intervalo", 0.15))
            pos += n
            self.js.append(f'tl.fromTo("#fx{i}-i{j}",{{opacity:0,y:24}},{{opacity:1,y:0,duration:0.4,ease:{_js(ease)}}},{tj:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, ease=ease)
        return ini, fim, origem

    def fx_titulo_cinetico(self, i, fx):
        ini, fim, ent, sai, pals = self.tempos(i, fx)
        origem = self.conferir_texto(i, fx, [fx["texto"]])
        tam = int(fx.get("tamanho", 64))
        ease = fx.get("ease", "power2.inOut")
        inner = f'<div class="tc" style="font-size:{tam}px">{self._palavras_html(i, fx, fx["texto"], None, "tcw")}</div>'
        self.css.append(".tc{font-weight:700;line-height:1.22;} .tcw{display:inline-block;}")
        self._cartao_frase(i, fx, inner, ini, fim)
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0}},{{opacity:1,duration:{ent * 0.6:.3f},ease:{_js(ease)}}},{ini:.4f});')
        for j, _w in enumerate(fx["texto"].split()):
            tj = max(pals[j]["s"] - 0.04, ini + ent * 0.3) if pals else ini + ent * 0.4 + j * 0.12
            self.js.append(f'tl.fromTo("#fx{i}-w{j}",{{opacity:0,y:30,filter:"blur(6px)"}},{{opacity:1,y:0,filter:"blur(0px)",duration:0.32,ease:{_js(ease)}}},{tj:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, ease=ease)
        return ini, fim, origem

    def fx_chips_topo(self, i, fx):
        """Fichas de tópico no topo (ideia: reels da humantrack.io). Cada ficha entra quando a palavra é dita
        (fade + sobe 18 px), as anteriores ficam (acumulam) e todas saem juntas. Itens: str ou
        {"texto": "prazo", "depois_de": 3.0} (ocorrência dita depois de tal segundo)."""
        p, s, W = self.pal, self.F["safe"], self.F["w"]
        itens = [it if isinstance(it, dict) else {"texto": it} for it in fx["itens"]]
        origem = self.conferir_texto(i, fx, [it["texto"] for it in itens])
        ent = float(fx.get("entrada", 0.45))
        sai = float(fx.get("saida", 0.35))
        ease = fx.get("ease", "power2.out")
        tchip = []
        t_min = -1.0
        for j, it in enumerate(itens):
            if "inicio" in it:
                tchip.append(float(it["inicio"])); continue
            if not self.palavras:
                erro(f"efeito {i}: chips sincronizados precisam de 'edl' na spec")
            ws = _achar_apos(self.palavras, it.get("fala", it["texto"]), max(t_min, float(it.get("depois_de", -1))))
            if not ws:
                erro(f"efeito {i}: ficha «{it['texto']}» não achada na fala (depois de {t_min:.2f} s)")
            tchip.append(ws[0]["s"] - float(fx.get("antecipar", 0.08)))
            t_min = ws[0]["s"] + 0.01
        ini = round(max(0.0, min(tchip) - 0.02) * FPS) / FPS
        if "fim" in fx:
            fim = float(fx["fim"])
        elif "duracao" in fx:
            fim = ini + float(fx["duracao"])
        else:
            fim = max(tchip) + float(fx.get("manter", 2.5)) + sai
        fim = round(min(fim, self.total - 1.0 / FPS) * FPS) / FPS
        tam = int(fx.get("tamanho", 34))
        y = int(fx.get("y", s["y0"] + 22))
        fichas = "".join(f'<div id="fx{i}-i{j}" class="chip"><span class="chip-p"></span>{_esc(it["texto"])}</div>'
                         for j, it in enumerate(itens))
        self.css.append(
            f".chips{{display:flex;gap:16px;justify-content:center;flex-wrap:nowrap;}}"
            f".chip{{display:inline-flex;align-items:center;gap:12px;background:{p['texto']};color:{p['fundo']};"
            f"font-weight:650;font-size:{tam}px;line-height:1;padding:{round(tam*0.42)}px {round(tam*0.72)}px;border-radius:999px;"
            f"box-shadow:0 6px 18px rgba(0,0,0,0.22),0 1px 3px rgba(0,0,0,0.18);letter-spacing:0.01em;white-space:nowrap;}}"
            f".chip-p{{width:{round(tam*0.28)}px;height:{round(tam*0.28)}px;border-radius:50%;background:{p['fundo']};flex:none;}}")
        self.html.append(
            f'<div id="fx{i}" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" data-track-index="{i + 1}" '
            f'data-layout-allow-overflow style="position:absolute;left:{s["x0"]}px;top:{y}px;width:{s["x1"] - s["x0"]}px;">'
            f'<div id="fx{i}-c" class="chips">{fichas}</div></div>')
        # o grupo fica sempre centrado: a fileira é montada com todas as fichas e deslocada (x) para centrar as já
        # visíveis; quando entra a próxima, o grupo desliza junto (medida com a mesma fonte, PIL)
        larg = [_medir(it["texto"], tam, 650, 0.01) + 2 * round(tam * 0.72) + round(tam * 0.28) + 12 for it in itens]
        tot = lambda n: sum(larg[:n]) + 16 * (n - 1)
        dx = [(tot(len(itens)) - tot(n)) / 2 for n in range(1, len(itens) + 1)]
        self.js.append(f'tl.set("#fx{i}-c",{{x:{dx[0]:.1f}}},{ini:.4f});')
        for j, tj in enumerate(tchip):
            tj = max(tj, ini)
            if j:
                self.js.append(f'tl.to("#fx{i}-c",{{x:{dx[j]:.1f},duration:{ent},ease:"power2.inOut"}},{tj:.4f});')
            self.js.append(f'tl.fromTo("#fx{i}-i{j}",{{opacity:0,y:18}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{tj:.4f});')
        self.saida_tl(f"#fx{i}-c", fim, sai, dx=dx[-1], dy=-10, ease="power2.inOut")
        self.dados[i] = dict(tipo="chips", ini=ini, fim=fim, ent=ent, sai=sai, itens=[it["texto"] for it in itens],
                             t=[max(tj, ini) for tj in tchip], dx=dx, tam=tam, y=y, x0=s["x0"], larg=s["x1"] - s["x0"])
        return ini, fim, origem

    def fx_cartao_documento(self, i, fx):
        """Cartão claro tipo documento (ideia: humantrack.io): flutua com sombra suave, sobe 70 px + fade; cabeçalho
        pequeno opcional (também precisa estar na fala; partes separadas por ' · '); frase datilografada no ritmo
        da fala; uma palavra ganha marca-texto."""
        p, s, W = self.pal, self.F["safe"], self.F["w"]
        fx.setdefault("entrada", 0.55)
        ini, fim, ent, sai, pals = self.tempos(i, fx)
        cab = fx.get("cabecalho")
        origem = self.conferir_texto(i, fx, [fx["texto"]] + ([c.strip() for c in cab.split("·")] if cab else []))
        tam = int(fx.get("tamanho", 54))
        ease = fx.get("ease", "power2.out")
        larg = int(fx.get("largura", s["x1"] - s["x0"] - 60))
        x = (W - larg) // 2
        y = int(fx["y"]) if "y" in fx else int(self.F["h"] * 0.56)
        papel = fx.get("papel", "#F4EEE2")
        realce = {"destaque": p["destaque"], "fundo": p["fundo"]}.get(fx.get("realce", "destaque"), fx.get("realce"))
        realce_txt = p["fundo"] if realce == p["destaque"] else p["texto"]
        cab_html = (f'<div class="cd-cab"><span class="cd-pt"></span>{_esc(cab)}</div><div class="cd-reg"></div>' if cab else "")
        # linhas explícitas: quebra determinística e o cartão cresce linha a linha (nada de cartão meio vazio)
        linhas = fx.get("linhas") or [fx["texto"]]
        if [_norm(w) for w in " ".join(linhas).split()] != [_norm(w) for w in fx["texto"].split()]:
            erro(f"efeito {i}: 'linhas' precisa ser o mesmo 'texto' quebrado em partes")
        util = larg - 92
        for ln in linhas:
            if len(linhas) > 1 and _medir(ln, tam, 700) * 1.03 > util:
                erro(f"efeito {i}: a linha «{ln}» não cabe no cartão ({_medir(ln, tam, 700):.0f} > {util} px); quebre de outro jeito")
        LH = round(tam * 1.3)
        corpo, j0, prim = "", 0, []
        for ln in linhas:
            prim.append(j0)
            corpo += f'<div class="cd-ln">{self._palavras_html(i, fx, ln, fx.get("destaque"), "tw", j0)}</div>'
            j0 += len(ln.split())
        self.css.append(
            f"#fx{i}-c{{background:{papel};color:{p['fundo']};border-radius:28px;padding:38px 46px 42px;box-sizing:border-box;width:{larg}px;"
            f"box-shadow:0 28px 60px rgba(0,0,0,0.30),0 6px 16px rgba(0,0,0,0.16);}}"
            f".cd-cab{{display:flex;align-items:center;gap:12px;font-weight:650;font-size:{round(tam*0.52)}px;letter-spacing:0.06em;"
            f"text-transform:uppercase;color:{p['fundo']};opacity:0.72;}}"
            f".cd-pt{{width:10px;height:10px;border-radius:3px;background:{p['destaque']};}}"
            f".cd-reg{{height:2px;background:{p['fundo']};opacity:0.12;margin:18px 0 20px;}}"
            f".twl{{font-weight:700;line-height:{LH}px;overflow:hidden;}} .cd-ln{{height:{LH}px;white-space:nowrap;}}"
            f" .tw{{display:inline-block;position:relative;white-space:nowrap;}}"
            f".hlw{{position:relative;display:inline-block;margin:0 0.07em 0 0.12em;}}"
            f".hl{{position:absolute;left:-0.10em;right:-0.07em;top:6%;bottom:2%;background:{realce};border-radius:8px;transform-origin:0 50%;z-index:0;}}"
            f".hlt{{position:relative;z-index:1;}} .ch{{opacity:0;}}")
        recorte = bool(fx.get("recorte"))
        if x < s["x0"] or x + larg > s["x1"] or y < s["y0"]:
            erro(f"efeito {i}: cartão fora da safe area (x {x}-{x + larg}, y {y})")
        if recorte:
            # RECORTE (cutaway): fundo neutro da paleta em tela cheia entra e sai em CORTE SECO; a voz continua por
            # baixo. Regra do kit: cartão grande nunca sobre o apresentador.
            H = self.F["h"]
            self.css.append(f"#fx{i}-bg{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;"
                            f"background:radial-gradient(120% 80% at 50% 38%, {fx.get('fundo_claro', '#2A4A3C')} 0%, {p['fundo']} 55%, {p['contorno']} 100%);}}")
            self.html.append(f'<div id="fx{i}-bg" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" '
                             f'data-track-index="{i + 1}"></div>')
        self.html.append(
            f'<div id="fx{i}" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" data-track-index="{i + 41}" '
            f'data-layout-allow-overflow style="position:absolute;left:{x}px;top:{y}px;width:{larg}px;">'
            f'<div id="fx{i}-c">{cab_html}<div id="fx{i}-t" class="twl" style="font-size:{tam}px;height:{LH if len(linhas) > 1 else "auto"}{"px" if len(linhas) > 1 else ""}">{corpo}</div></div></div>')
        self.js.append(f'tl.fromTo("#fx{i}-c",{{opacity:0,y:70}},{{opacity:1,y:0,duration:{ent},ease:{_js(ease)}}},{ini:.4f});')
        dd = dict(tipo="cartao", ini=ini, fim=fim, ent=ent, sai=sai, cab=cab or "", tam=tam, larg=larg, x=x, y=y, LH=LH,
                  papel=papel, realce=realce, realce_txt=realce_txt, recorte=recorte, push=float(fx.get("push", 1.04)),
                  fundo_claro=fx.get("fundo_claro", "#2A4A3C"), destaque=_norm(fx.get("destaque") or ""),
                  linhas=[ln.split() for ln in linhas], palavras=[], cresce=[], th=None)
        self.dados[i] = dd
        for j, w in enumerate(fx["texto"].split()):
            t0 = max(pals[j]["s"], ini + ent * 0.6) if pals else ini + ent + j * 0.2
            dur = min(max(pals[j]["e"] - pals[j]["s"], 0.12), len(w) / 22 * 1.6) if pals else len(w) / 22
            if j in prim[1:]:
                n = prim.index(j) + 1
                self.js.append(f'tl.to("#fx{i}-t",{{height:{n * LH},duration:0.28,ease:"power2.out"}},{t0 - 0.2:.4f});')
            passo = dur / max(1, len(w))
            dd["palavras"].append(dict(t0=t0, passo=passo))
            if j in prim[1:]:
                dd["cresce"].append(dict(t=t0 - 0.2, n=prim.index(j) + 1))
            self.js.append(f'document.querySelectorAll("#fx{i}-w{j} .ch").forEach((c,k)=>tl.set(c,{{opacity:1}},{t0:.4f}+k*{passo:.4f}));')
            if fx.get("destaque") and _norm(w) == _norm(fx["destaque"]):
                th = t0 + dur + 0.04
                dd["th"] = th
                self.js.append(f'tl.fromTo("#fx{i}-hl",{{scaleX:0}},{{scaleX:1,duration:0.32,ease:"power2.inOut"}},{th:.4f});')
                self.js.append(f'tl.fromTo("#fx{i}-ht",{{color:{_js(p["fundo"])}}},{{color:{_js(realce_txt)},duration:0.2,ease:"none"}},{th + 0.1:.4f});')
        if not recorte:
            self.saida_tl(f"#fx{i}-c", fim, sai, dy=20, ease="power2.inOut")
        else:
            # push-in lento no recorte (como a câmera "chegando" na tela de UI da humantrack): tela nunca congela
            esc = float(fx.get("push", 1.04))
            self.js.append(f'tl.fromTo("#fx{i}",{{scale:1}},{{scale:{esc},duration:{fim - ini:.3f},ease:"sine.inOut",transformOrigin:"50% 50%"}},{ini:.4f});')
            self.js.append(f'tl.fromTo("#fx{i}-bg",{{scale:1}},{{scale:{1 + (esc - 1) * 1.5:.3f},duration:{fim - ini:.3f},ease:"sine.inOut",transformOrigin:"50% 40%"}},{ini:.4f});')
        return ini, fim, origem

    def montar(self):
        for i, fx in enumerate(self.spec["efeitos"]):
            nome = fx["efeito"]
            if nome not in EFEITOS:
                erro(f"efeito desconhecido: {nome} (opções: {', '.join(EFEITOS)})")
            ini, fim, origem = getattr(self, "fx_" + nome.replace("-", "_"))(i, fx)
            self.resumo.append(dict(i=i, efeito=nome, ini=round(ini, 3), fim=round(fim, 3), texto=fx.get("texto") or fx.get("itens"),
                                    conteudo=origem, recorte=bool(fx.get("recorte")),
                                    **({"torso_y": int(fx["torso_y"])} if fx.get("torso_y") else {})))
        W, H = self.F["w"], self.F["h"]
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<!-- gerado por kit-editor/kitlib/motion.py — não editar à mão; edite a spec e gere de novo -->
<style>
@font-face{{font-family:"Kit Inter";src:url("assets/fonts/Inter-Variable.ttf") format("truetype");font-weight:100 900;font-style:normal;}}
html,body{{margin:0;padding:0;background:transparent;}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:transparent;font-family:"Kit Inter";}}
{chr(10).join(self.css)}
</style>
<script src="assets/gsap.min.js"></script>
</head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{self.total:.4f}" data-width="{W}" data-height="{H}">
{chr(10).join(self.html)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{chr(10).join(self.js)}
window.__timelines["main"] = tl;
</script>
</body></html>
"""


def _bbox_alfa(mov, W, H, tempos):
    """Caixa ocupada (alfa > 16) em cada instante. Devolve lista de (t, bbox|None)."""
    out = []
    lim = bytes(0 if v <= 16 else 1 for v in range(256))
    for t in tempos:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mov), "-frames:v", "1",
                            "-vf", "format=yuva444p,alphaextract,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        q = r.stdout.translate(lim)
        if len(q) < W * H or b"\x01" not in q:
            out.append((t, None)); continue
        ys, x0, x1 = [], W, -1
        for row in range(H):
            ln = q[row * W:(row + 1) * W]
            a = ln.find(b"\x01")
            if a >= 0:
                ys.append(row); x0 = min(x0, a); x1 = max(x1, ln.rfind(b"\x01"))
        out.append((t, (x0, ys[0], x1 + 1, ys[-1] + 1)))
    return out



def gerar(spec_path, saida, so_projeto=False, base=None, motor=None):
    spec = ler_json(spec_path)
    formato = spec.get("formato", "reels")
    F = FORMATOS[formato]
    pal = _paleta(spec.get("paleta", "verde-bege"))
    palavras, total = None, spec.get("duracao")
    if spec.get("edl"):
        edl = ler_json(spec["edl"])
        palavras = E.palavras_saida(edl)
        _, tot = E.offsets(edl)
        total = total or tot
    if not total:
        erro("informe 'duracao' ou 'edl' na spec")
    saida = caminho(saida)
    if saida.suffix != ".mov":
        erro("a saída do motion é .mov (ProRes 4444 com alfa)")
    mov = saida_segura(saida)
    proj = mov.with_name(mov.stem + "_projeto")
    if proj.exists():
        erro(f"já existe: {proj} (o kit não sobrescreve; use outro nome)")
    (proj / "assets" / "fonts").mkdir(parents=True)
    shutil.copy(GSAP, proj / "assets" / "gsap.min.js")
    # plugins GSAP vendorizados (DrawSVG, SplitText, MotionPath, MorphSVG, Flip, CustomEase); carregar só se o efeito pedir
    for _pl in GSAP.parent.glob("*.min.js"):
        if _pl.name != "gsap.min.js":
            shutil.copy(_pl, proj / "assets" / _pl.name)
    shutil.copy(FONTE, proj / "assets" / "fonts" / "Inter-Variable.ttf")
    m = _Montador(spec, F, pal, palavras, float(total))
    (proj / "index.html").write_text(m.montar(), encoding="utf-8")
    shutil.copy(caminho(spec_path), proj / "spec.json")
    for r in m.resumo:
        info(f"  {r['i']}: {r['efeito']:22s} {r['ini']:6.2f}-{r['fim']:6.2f}  [{r['conteudo']}]  {r['texto']}")
    motor = motor or spec.get("motor", "hyperframes")
    if motor not in MOTORES:
        erro(f"motor desconhecido: {motor} (opções: {', '.join(MOTORES)})")
    import time as _time
    t_ini = _time.time()
    _render_hf(proj, mov, so_projeto)
    if so_projeto:
        return None
    t_render = round(_time.time() - t_ini, 1)
    return _conferir_overlay(spec, spec_path, F, formato, total, m, proj, mov, base, motor, t_render)


def _render_hf(proj, mov, so_projeto):
    lint = subprocess.run([str(HF), "lint", str(proj)], capture_output=True, text=True)
    erros_lint = re.findall(r"(\d+) error", lint.stdout + lint.stderr)
    if erros_lint and int(erros_lint[0]) > 0:
        print(lint.stdout[-3000:])
        erro("lint do HyperFrames falhou")
    if so_projeto:
        info(f"projeto: {proj}"); return None
    log = proj / "render.log"
    info(f"renderizando com HyperFrames local, sem rede ({proj.name}) ...")
    env = dict(os.environ, NODE_OPTIONS=f"--require={HF.parent / 'rede-log.cjs'}", HF_REDE_LOG=str(proj / "rede.log"))
    with open(log, "w") as lf:
        r = subprocess.run([str(HF), "render", str(proj), "--format", "mov", "--fps", str(FPS), "-o", str(mov)],
                           stdout=lf, stderr=subprocess.STDOUT, env=env)
    if r.returncode or not mov.exists():
        print(log.read_text()[-3000:])
        erro(f"render do HyperFrames falhou (log: {log})")


def _conferir_overlay(spec, spec_path, F, formato, total, m, proj, mov, base, motor, t_render):
    rede = (proj / "rede.log").read_text().splitlines() if (proj / "rede.log").exists() else []
    externas = [l for l in rede if not re.search(r" (connect|connect-erro|dns\.lookup|fetch) (https?://)?(\[?::1\]?|127\.0\.0\.1|0\.0\.0\.0|localhost|unix:)", l)]
    # conferência: área ocupada x safe area, a cada 0,25 s dentro de cada efeito
    s = F["safe"]
    problemas, caixas = [], []
    for rr in m.resumo:
        ts = [rr["ini"] + k * 0.25 for k in range(int((rr["fim"] - rr["ini"]) / 0.25) + 1)]
        for t, bb in _bbox_alfa(mov, F["w"], F["h"], ts):
            if bb and rr.get("recorte") and bb == (0, 0, F["w"], F["h"]):
                caixas.append(dict(efeito=rr["i"], t=round(t, 2), bbox=bb, recorte=True))
                continue  # recorte: fundo em tela cheia de propósito (o cartão é posicionado dentro da safe area)
            if bb:
                caixas.append(dict(efeito=rr["i"], t=round(t, 2), bbox=bb))
                if bb[0] < s["x0"] or bb[2] > s["x1"] or bb[1] < s["y0"] or bb[3] > s["y1"]:
                    problemas.append(f"efeito {rr['i']} em {t:.2f} s: {bb} fora da safe area {s}")
    manifesto = dict(spec=str(caminho(spec_path)), projeto=str(proj), overlay=str(mov), formato=formato,
                     paleta=spec.get("paleta", "verde-bege"), duracao=total, efeitos=m.resumo,
                     safe_area=s, fora_da_safe=problemas, conexoes_externas=externas, conexoes_total=len(rede),
                     exemplo=bool(spec.get("_exemplo")),
                     motor=motor, tempo_render_s=t_render,
                     versao="hyperframes 0.8.185 (local, telemetria desligada, sem rede)")
    base = base or spec.get("base")
    if base:
        from . import pessoa
        manifesto["pessoa"] = pessoa.conferir(caminho(base), [mov], janelas=[(r["ini"], r["fim"]) for r in m.resumo],
                                              isencoes=[(r["ini"], r["fim"], r["torso_y"]) for r in m.resumo if r.get("torso_y")],
                                              pasta_png=proj / "silhueta")
    else:
        manifesto["pessoa"] = None
        info("aviso: silhueta não conferida aqui (sem --base); kit.py renderizar --overlays confere e reprova se cobrir o apresentador")
    mov.with_suffix(".motion.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    info(f"overlay: {mov}  (motor {motor}, {t_render} s)")
    info(f"rede: {len(rede)} tentativas registradas no processo Node, externas: {len(externas)}")
    info("safe area: OK" if not problemas else "safe area: PROBLEMAS\n  " + "\n  ".join(problemas[:10]))
    if manifesto["pessoa"] and not manifesto["pessoa"]["ok"]:
        erro(f"overlay cobre o apresentador (regra permanente). Mova para espaço livre, encolha ou use recorte. "
             f"Diagnóstico: {proj / 'silhueta'}")
    return manifesto


def filtro_overlays(n_base_inputs, overlays):
    """Filtro ffmpeg que sobrepõe os .mov (alfa) na entrada 0, na ordem. Entradas extras começam em n_base_inputs."""
    fc, cur = [], "[0:v]"
    for k, _ in enumerate(overlays):
        idx = n_base_inputs + k
        fc.append(f"[{idx}:v]format=yuva444p[ov{k}];{cur}[ov{k}]overlay=x=0:y=0:eof_action=pass:format=auto[b{k}]")
        cur = f"[b{k}]"
    return ";".join(fc), cur


def sobrepor(video, overlays, saida):
    from .comum import BT709, video_info
    video, saida = caminho(video), saida_segura(caminho(saida))
    if (RAIZ / "editados") in saida.parents:
        erro("sobrepor é para trabalho/ (prévia/teste). Para editados/ use renderizar --overlays com EDL aprovada.")
    ins = []
    for o in overlays:
        ins += ["-i", str(caminho(o))]
    fc, cur = filtro_overlays(1, overlays)
    vi = video_info(video)
    run(["ffmpeg", "-v", "error", "-n", "-i", str(video), *ins, "-filter_complex", fc + f";{cur}format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), *BT709, "-c:a", "copy", "-movflags", "+faststart",
         "-t", f"{vi['dur']:.4f}", str(saida)])
    info(f"pronto: {saida}")
    return saida


# ---- biblioteca de aberturas, gráficos animados e fechamentos (17 efeitos; ver kitlib/motion_graficos.py) ----
from .motion_graficos import GraficosMixin  # noqa: E402

for _nome, _fn in vars(GraficosMixin).items():
    if callable(_fn) and not _nome.startswith("__"):
        setattr(_Montador, _nome, _fn)

BIBLIOTECA_JSON = KIT / "motion" / "biblioteca.json"


def biblioteca():
    """Catálogo (motion/biblioteca.json): lista de dicts com id, grupo, pt, en, serve, quando, duracao, easing, ..."""
    return json.loads(BIBLIOTECA_JSON.read_text(encoding="utf-8"))["opcoes"] if BIBLIOTECA_JSON.exists() else []


for _o in biblioteca():
    EFEITOS[_o["id"]] = f"[{_o['grupo']}] {_o['pt']} / {_o['en']}: {_o['serve']}"
