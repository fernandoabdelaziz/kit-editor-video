"""Biblioteca de ABERTURAS (hooks), GRÁFICOS ANIMADOS e FECHAMENTOS discretos do kit-editor.

17 efeitos para o `kit.py motion` (motor HyperFrames local). São ideias
reescritas do zero a partir de dois repositórios públicos MIT (lidos só como texto, nenhum código copiado ou
executado): yihui-dev/awesome-opus5-5-videos e elayadesign/ai-design-skills (design-to-motion). Créditos em
NOTICE.md; tabela completa: `kit.py biblioteca --md` e motion/biblioteca.json.

Padrão sóbrio do kit, aplicado a todos:
  - sem bounce/elastic/pop (só ease-out e in-out; nada passa do alvo), no máximo 2 efeitos por elemento;
  - saída com ~70% do tempo da entrada; cascata sempre na ordem de leitura;
  - NADA sobre o apresentador: elementos pequenos só em espaço livre; gráficos grandes são RECORTE (cutaway):
    fundo neutro da paleta em tela cheia, corte seco de ida e volta, a voz continua (`recorte`: true é o padrão
    dos efeitos grandes; `recorte: false` encolhe o gráfico num cartão em espaço livre, e o kit confere a
    silhueta dele com --base);
  - texto da tela só com o que ele fala (o kit confere contra a EDL; números e valores usam `fala` quando o texto
    falado é outro, ex.: valor 12000 / fala "doze mil"). Fora da fala: só com `texto_aprovado` (motivo).
    Fechamentos só com frase neutra da lista FECHOS_NEUTROS, ou `texto_aprovado`;
  - `exemplo: true` marca o gráfico com a etiqueta "EXEMPLO · dados fictícios" e o manifesto fica marcado: o
    `kit.py renderizar` RECUSA entregar em editados/ um overlay de exemplo.
"""
from .comum import FPS, erro
from .motion import _achar_apos, _norm, _medir, _esc, _js

FECHOS_NEUTROS = {"vale guardar esse video", "fica de olho nisso"}


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _misturar(a, b, k):
    ra, rb = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(x * (1 - k) + y * k) for x, y in zip(ra, rb))


def _num_pt(v, casas=0):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


JS_FMT = ("(v,c)=>{let s=Math.abs(v).toFixed(c);let a=s.split('.');let i=a[0].replace(/\\B(?=(\\d{3})+(?!\\d))/g,'.');"
          "return (v<0?'-':'')+(a[1]?i+','+a[1]:i);}")

TITULO_CSS = ("font-weight:650;font-size:34px;letter-spacing:0.12em;text-transform:uppercase;"
              "color:%s;margin-bottom:28px;text-align:center;opacity:0;")


class GraficosMixin:
    # ------------------------------------------------------------------ infraestrutura comum
    def _g_janela(self, i, fx, frases, ent_padrao=0.6, manter_padrao=0.8, intervalo_padrao=0.5, antecipar=0.25):
        """Tempos do efeito. `frases`: uma frase falada por item (ou None). Com `sincronizar` e `edl`, cada item
        entra quando a frase é dita (ordem de leitura); senão usa `inicio`, `duracao` e `intervalo` (s entre itens)."""
        ent = float(fx.get("entrada", ent_padrao))
        sai = float(fx.get("saida", round(ent * 0.7, 3)))
        n = len(frases)
        ts, te = [None] * n, [None] * n
        sinc = bool(fx.get("sincronizar"))
        if sinc and not self.palavras:
            erro(f"efeito {i}: 'sincronizar' precisa de 'edl' na spec")
        if sinc:
            t_min = -1.0
            for k, fr in enumerate(frases):
                if not fr:
                    continue
                ws = _achar_apos(self.palavras, fr, t_min)
                if not ws:
                    erro(f"efeito {i}: não achei na fala: «{fr}» (depois de {t_min:.2f} s)")
                ts[k], te[k] = ws[0]["s"], ws[-1]["e"]
                t_min = ws[0]["s"] + 0.01
        if "inicio" in fx:
            ini = float(fx["inicio"])
        elif sinc and any(t is not None for t in ts):
            ini = max(0.0, min(t for t in ts if t is not None) - float(fx.get("antecipar", antecipar)) - ent * 0.5)
        else:
            erro(f"efeito {i}: informe 'inicio' (ou 'sincronizar' com 'edl')")
        inter = float(fx.get("intervalo", intervalo_padrao))
        for k in range(n):
            if ts[k] is None:
                ts[k] = ini + ent * 0.6 + k * inter
                te[k] = ts[k] + 0.4
        if "duracao" in fx:
            fim = ini + float(fx["duracao"])
        elif sinc:
            fim = max(te) + float(fx.get("manter", manter_padrao)) + sai
        else:
            erro(f"efeito {i}: informe 'duracao'")
        fim = min(fim, self.total - 1.0 / FPS)
        ini, fim = round(ini * FPS) / FPS, round(fim * FPS) / FPS
        if fim - ini < ent + sai + 0.3:
            erro(f"efeito {i}: duração curta demais ({fim - ini:.2f} s) para entrada+saída")
        return dict(ini=ini, fim=fim, ent=ent, sai=sai, ts=ts, te=te, sinc=sinc)

    def _g_fecha(self, i, j, t_final, hard_cut=False):
        """A animação precisa terminar antes de a saída começar (senão o gráfico sai pela metade)."""
        limite = j["fim"] - (0.0 if hard_cut else j["sai"]) - 0.05
        if t_final > limite + 1e-6:
            erro(f"efeito {i}: a animação só termina em {t_final:.2f} s, mas a saída começa em {limite:.2f} s. "
                 f"Aumente 'duracao' para pelo menos {t_final - j['ini'] + (0.05 if hard_cut else j['sai'] + 0.05):.2f} s "
                 "ou use intervalos menores.")

    def _ft(self, sel, de, para, dur, ease, t):
        to = dict(para)
        to["duration"] = round(dur, 3)
        to["ease"] = ease
        self.js.append(f"tl.fromTo({_js(sel)},{_js(de)},{_js(to)},{t:.4f});")

    def _g_cena(self, i, fx, j, corpo, recorte_padrao=True, larg=None, push=1.03):
        """Monta o contêiner. recorte: fundo neutro em tela cheia (corte seco), conteúdo centrado na safe area.
        Sem recorte: cartão da paleta em espaço livre (topo), com fade+sobe na entrada e saída com 70%."""
        p, s, W, H = self.pal, self.F["safe"], self.F["w"], self.F["h"]
        ini, fim, ent, sai = j["ini"], j["fim"], j["ent"], j["sai"]
        recorte = bool(fx.setdefault("recorte", recorte_padrao))
        sw = s["x1"] - s["x0"]
        tag = (f'<div id="fx{i}-tag" class="g-tag">EXEMPLO · dados fictícios</div>' if fx.get("exemplo") else "")
        self.css.append(f".g-ti{{{TITULO_CSS % p['apoio']}}}")
        if fx.get("exemplo"):
            self.css.append(f".g-tag{{font-weight:650;font-size:24px;letter-spacing:0.16em;text-transform:uppercase;"
                            f"color:{p['apoio']};opacity:0;margin-bottom:26px;text-align:center;}}")
            self.spec["_exemplo"] = True
        if recorte:
            claro = fx.get("fundo_claro") or _misturar(p["fundo"], "#FFFFFF", 0.12)
            self.css.append(f"#fx{i}-bg{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;"
                            f"background:radial-gradient(120% 80% at 50% 38%, {claro} 0%, {p['fundo']} 55%, {p['contorno']} 100%);}}"
                            f"#fx{i}-c{{width:{sw - 60}px;display:flex;flex-direction:column;align-items:center;}}")
            self.html.append(f'<div id="fx{i}-bg" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" '
                             f'data-track-index="{i + 1}"></div>')
            self.html.append(
                f'<div id="fx{i}" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" '
                f'data-track-index="{i + 41}" data-layout-allow-overflow style="position:absolute;left:{s["x0"]}px;'
                f'top:{s["y0"]}px;width:{sw}px;height:{s["y1"] - s["y0"]}px;"><div style="width:100%;height:100%;display:flex;'
                f'align-items:center;justify-content:center;"><div id="fx{i}-c">{tag}{corpo}</div></div></div>')
            esc = float(fx.get("push", push))
            d = fim - ini
            self.js.append(f'tl.fromTo("#fx{i}",{{scale:1}},{{scale:{esc},duration:{d:.3f},ease:"sine.inOut",transformOrigin:"50% 50%"}},{ini:.4f});')
            self.js.append(f'tl.fromTo("#fx{i}-bg",{{scale:1}},{{scale:{1 + (esc - 1) * 1.5:.3f},duration:{d:.3f},ease:"sine.inOut",transformOrigin:"50% 40%"}},{ini:.4f});')
        else:
            lg = int(fx.get("largura", larg or sw - 80))
            pos = fx.get("posicao", fx.get("_pos_padrao", "terco-superior"))
            if isinstance(pos, dict):
                x, y = int(pos["x"]), int(pos["y"])
            else:
                tops = {"terco-superior": s["y0"] + 30, "centro": int(H * 0.40), "terco-inferior": int(H * 0.60)}
                if pos not in tops:
                    erro(f"posicao inválida: {pos}")
                x, y = (W - lg) // 2, tops[pos]
            self.css.append(f"#fx{i}-c{{background:{p['fundo']};border-radius:16px;padding:30px 38px 34px;box-sizing:border-box;"
                            f"width:{lg}px;display:flex;flex-direction:column;align-items:center;"
                            f"box-shadow:0 8px 22px rgba(0,0,0,0.24);}}")
            self.html.append(
                f'<div id="fx{i}" class="clip" data-start="{ini:.4f}" data-duration="{fim - ini:.4f}" '
                f'data-track-index="{i + 1}" data-layout-allow-overflow style="position:absolute;left:{x}px;top:{y}px;width:{lg}px;">'
                f'<div id="fx{i}-c">{tag}{corpo}</div></div>')
            self._ft(f"#fx{i}-c", {"opacity": 0, "y": 24}, {"opacity": 1, "y": 0}, ent, "power3.out", ini)
            self.saida_tl(f"#fx{i}-c", fim, sai, dy=-12, ease="power2.inOut")
        if tag:
            self._ft(f"#fx{i}-tag", {"opacity": 0}, {"opacity": 0.85}, 0.4, "power2.out", ini + 0.1)
        return recorte

    def _g_ajusta(self, texto, tam, peso, disponivel):
        w = _medir(texto, tam, peso)
        return tam if w <= disponivel else max(24, int(tam * disponivel / w))

    def _g_titulo(self, i, fx, j):
        if fx.get("titulo"):
            self._ft(f"#fx{i}-ti", {"opacity": 0}, {"opacity": 1}, 0.4, "power2.out", j["ini"] + 0.15)

    def _g_titulo_html(self, i, fx):
        est = ""
        if fx.get("titulo_tamanho"): est += f"font-size:{int(fx['titulo_tamanho'])}px;"
        if fx.get("titulo_espaco") is not None: est += f"margin-bottom:{int(fx['titulo_espaco'])}px;"
        return (f'<div id="fx{i}-ti" class="g-ti" style="{est}">{_esc(fx["titulo"])}</div>' if fx.get("titulo") else "")

    # ------------------------------------------------------------------ ABERTURAS
    def fx_palavra_revelada(self, i, fx):
        """Palavra-chave revelada (keyword reveal): as letras sobem por uma linha de máscara, uma a uma, e uma régua fina
        se desenha embaixo. Linha de apoio opcional acima."""
        p, s = self.pal, self.F["safe"]
        fx.setdefault("_pos_padrao", "terco-superior")
        j = self._g_janela(i, fx, [fx["texto"]], ent_padrao=0.5)
        origem = self.conferir_texto(i, fx, [fx["texto"], fx.get("apoio")])
        sw = s["x1"] - s["x0"]
        tam = self._g_ajusta(fx["texto"], int(fx.get("tamanho", 120)), 800, sw - 280)
        n, grupos = 0, []
        for w in fx["texto"].split():
            ch = "".join(f'<span class="pr-ch">{_esc(c)}</span>' for c in w)
            grupos.append(f'<span class="pr-m">{ch}</span>')
            n += len(w)
        corpo = ((f'<div id="fx{i}-ap" class="pr-ap">{_esc(fx["apoio"])}</div>') if fx.get("apoio") else "") + \
            f'<div class="pr-w" style="font-size:{tam}px">{" ".join(grupos)}</div><div id="fx{i}-reg" class="pr-reg"></div>'
        self.css.append(
            f".pr-ap{{font-weight:650;font-size:30px;letter-spacing:0.14em;text-transform:uppercase;color:{p['apoio']};margin-bottom:10px;opacity:0;}}"
            f".pr-w{{font-weight:700;line-height:1.05;color:{p['texto']};text-align:center;}}"
            f".pr-m{{display:inline-block;overflow:hidden;padding:0.06em 0.02em 0.16em;vertical-align:top;}}"
            f".pr-ch{{display:inline-block;}}"
            f".pr-reg{{height:4px;width:44%;border-radius:2px;background:{p['destaque']};margin-top:2px;transform-origin:50% 50%;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        t0 = max(j["ts"][0] - 0.05, j["ini"] + j["ent"] * 0.5) if j["sinc"] else j["ini"] + j["ent"] * 0.6
        passo = min(0.045, 0.6 / max(1, n))
        if fx.get("apoio"):
            self._ft(f"#fx{i}-ap", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", max(j["ini"], t0 - 0.25))
        self.js.append(f'document.querySelectorAll("#fx{i}-c .pr-ch").forEach((c,k)=>tl.fromTo(c,{{yPercent:118}},'
                       f'{{yPercent:0,duration:0.55,ease:"power3.out"}},{t0:.4f}+k*{passo:.4f}));')
        t_fim_letras = t0 + passo * (n - 1) + 0.55
        self._ft(f"#fx{i}-reg", {"scaleX": 0}, {"scaleX": 1}, 0.55, "power2.inOut", t_fim_letras - 0.2)
        self._g_fecha(i, j, t_fim_letras + 0.35, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_numero_rolando(self, i, fx):
        """Número em contagem (rolling counter): os dígitos rolam na vertical, como hodômetro, e assentam da esquerda
        para a direita no fim da palavra falada. Rótulo embaixo. Para valor/prazo que abre o vídeo."""
        p, s = self.pal, self.F["safe"]
        casas = int(fx.get("casas", 0))
        txt = _num_pt(float(fx["valor"]), casas)
        fala = fx.get("fala") or txt
        j = self._g_janela(i, fx, [fala], ent_padrao=0.5)
        origem = self.conferir_texto(i, fx, [fala, fx.get("rotulo")])
        recorte_prev = bool(fx.get("recorte", True))
        tam = int(fx.get("tamanho", 210 if recorte_prev else 130))
        pre, suf = fx.get("prefixo", ""), fx.get("sufixo", "")
        pequeno = round(tam * 0.36)
        wd = round(tam * 0.64)
        cols, strips, ci = [], [], 0
        for c in txt:
            if c.isdigit():
                cells = "".join(f'<span class="nr-c">{d % 10}</span>' for d in range(20))
                cols.append(f'<span class="nr-col" style="width:{wd}px"><span id="fx{i}-d{ci}" class="nr-strip">{cells}</span></span>')
                strips.append((ci, int(c)))
                ci += 1
            else:
                cols.append(f'<span class="nr-sep" style="width:{round(tam * 0.26)}px">{_esc(c)}</span>')
        corpo = ('<div class="nr">'
                 + (f'<span class="nr-p" style="font-size:{pequeno}px">{_esc(pre)}</span>' if pre else "")
                 + "".join(cols)
                 + (f'<span class="nr-p" style="font-size:{pequeno}px">{_esc(suf)}</span>' if suf else "")
                 + "</div>"
                 + (f'<div id="fx{i}-rot" class="nr-rot">{_esc(fx["rotulo"])}</div>' if fx.get("rotulo") else ""))
        self.css.append(
            f".nr{{display:flex;align-items:flex-end;justify-content:center;gap:4px;color:{p['texto']};font-weight:700;font-feature-settings:'tnum';font-size:{tam}px;line-height:{tam}px;}}"
            f".nr-col{{display:inline-block;overflow:hidden;text-align:center;height:{tam}px;}}"
            f".nr-strip{{display:block;}} .nr-c{{display:block;height:{tam}px;line-height:{tam}px;}}"
            f".nr-sep{{display:inline-block;text-align:center;height:{tam}px;line-height:{tam}px;}}"
            f".nr-p{{font-weight:650;color:{p['apoio']};padding:0 10px {round(tam * 0.14)}px;line-height:1;white-space:nowrap;}}"
            f".nr-rot{{font-weight:600;font-size:46px;line-height:1.2;color:{p['apoio']};margin-top:22px;text-align:center;opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        roll = float(fx.get("contagem", 1.1))
        t_fim = j["te"][0] if j["sinc"] else j["ini"] + j["ent"] * 0.6 + roll
        t_ini = max(t_fim - roll, j["ini"] + 0.05)
        n = len(strips)
        for (c, d) in strips:
            alvo = d + (10 if n > 1 and c >= n - 2 else 0)
            dur = roll * (0.72 + 0.28 * (c / max(1, n - 1)))
            self._ft(f"#fx{i}-d{c}", {"y": 0}, {"y": -alvo * tam}, dur, "power3.out", t_ini)
        if fx.get("rotulo"):
            self._ft(f"#fx{i}-rot", {"opacity": 0, "y": 14}, {"opacity": 1, "y": 0}, 0.45, "power2.out", t_ini + roll * 0.55)
        self._g_fecha(i, j, t_ini + roll + 0.5, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_pergunta_resolve(self, i, fx):
        """Pergunta que se resolve (question → answer): a pergunta entra palavra a palavra; na hora da resposta ela
        esmaece e a resposta sobe por uma máscara, com uma régua fina."""
        p = self.pal
        fx.setdefault("_pos_padrao", "terco-superior")
        resolve = float(fx.get("resolve_em", 2.0))
        j = self._g_janela(i, fx, [fx["pergunta"], fx["resposta"]], ent_padrao=0.5, intervalo_padrao=resolve)
        origem = self.conferir_texto(i, fx, [fx["pergunta"], fx["resposta"]])
        tam = int(fx.get("tamanho", 62))
        pals = fx["pergunta"].split()
        ph = "".join(f'<span id="fx{i}-q{k}" class="pq-w">{_esc(w)}</span> ' for k, w in enumerate(pals))
        corpo = (f'<div id="fx{i}-q" class="pq-q" style="font-size:{tam}px">{ph}</div>'
                 f'<div class="pq-am"><div id="fx{i}-a" class="pq-a" style="font-size:{round(tam * 1.18)}px">{_esc(fx["resposta"])}</div></div>'
                 f'<div id="fx{i}-reg" class="pq-reg"></div>')
        self.css.append(
            f".pq-q{{font-weight:600;line-height:1.2;color:{p['texto']};text-align:center;}} .pq-w{{display:inline-block;opacity:0;}}"
            f".pq-am{{overflow:hidden;margin-top:20px;padding:0.05em 0.04em 0.14em;}}"
            f".pq-a{{font-weight:700;line-height:1.1;color:{p['destaque']};text-align:center;}}"
            f".pq-reg{{height:4px;width:34%;border-radius:2px;background:{p['destaque']};margin-top:4px;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        if j["sinc"]:
            tw = [w["s"] for w in _achar_apos(self.palavras, fx["pergunta"], -1.0)]
        else:
            tw = [j["ts"][0] + k * 0.12 for k in range(len(pals))]
        for k, t in enumerate(tw):
            self._ft(f"#fx{i}-q{k}", {"opacity": 0, "y": 14}, {"opacity": 1, "y": 0}, 0.35, "power2.out", max(t - 0.05, j["ini"] + j["ent"] * 0.4))
        t_r = j["ts"][1] if j["sinc"] else j["ts"][0] + resolve
        self._ft(f"#fx{i}-q", {"opacity": 1}, {"opacity": 0.38}, 0.5, "power2.inOut", t_r - 0.1)
        self._ft(f"#fx{i}-a", {"yPercent": 118}, {"yPercent": 0}, 0.6, "power3.out", t_r)
        self._ft(f"#fx{i}-reg", {"scaleX": 0}, {"scaleX": 1}, 0.55, "power2.inOut", t_r + 0.35)
        self._g_fecha(i, j, t_r + 0.95, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_titulo_reguas(self, i, fx):
        """Título entre réguas (ruled title slot): duas réguas finas partem do centro, abrem uma janela e o título sobe
        dentro dela. Sobretítulo opcional. Abertura de tema."""
        p, s = self.pal, self.F["safe"]
        fx.setdefault("_pos_padrao", "terco-superior")
        linhas = fx.get("linhas") or [fx["texto"]]
        j = self._g_janela(i, fx, [fx["texto"]], ent_padrao=0.5)
        origem = self.conferir_texto(i, fx, [fx["texto"], fx.get("sobretitulo")])
        sw = s["x1"] - s["x0"]
        tam = self._g_ajusta(max(linhas, key=len), int(fx.get("tamanho", 84)), 800, sw - 200)
        LH = round(tam * 1.18)
        alt = LH * len(linhas) + 36
        corpo = ((f'<div id="fx{i}-so" class="tr-so">{_esc(fx["sobretitulo"])}</div>') if fx.get("sobretitulo") else "") + (
            f'<div class="tr-box" style="height:{alt}px"><div id="fx{i}-r1" class="tr-r" style="top:0"></div>'
            f'<div id="fx{i}-sl" class="tr-sl" style="height:{alt}px"><div id="fx{i}-t" class="tr-t" style="font-size:{tam}px;line-height:{LH}px;padding-top:18px">'
            + "<br>".join(_esc(l) for l in linhas) + f'</div></div><div id="fx{i}-r2" class="tr-r" style="bottom:0"></div></div>')
        self.css.append(
            f".tr-so{{font-weight:650;font-size:28px;letter-spacing:0.16em;text-transform:uppercase;color:{p['apoio']};margin-bottom:18px;opacity:0;}}"
            f".tr-box{{position:relative;width:100%;}} .tr-r{{position:absolute;left:0;right:0;height:3px;background:{p['destaque']};transform-origin:50% 50%;}}"
            f".tr-sl{{position:absolute;left:0;right:0;top:0;overflow:hidden;}}"
            f".tr-t{{font-weight:700;color:{p['texto']};text-align:center;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        t0 = max(j["ts"][0] - 0.1, j["ini"] + j["ent"] * 0.4) if j["sinc"] else j["ini"] + j["ent"] * 0.5
        if fx.get("sobretitulo"):
            self._ft(f"#fx{i}-so", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t0)
        self._ft(f"#fx{i}-r1", {"scaleX": 0, "y": alt / 2 - 2}, {"scaleX": 1, "y": 0}, 0.7, "power2.inOut", t0)
        self._ft(f"#fx{i}-r2", {"scaleX": 0, "y": -(alt / 2 - 2)}, {"scaleX": 1, "y": 0}, 0.7, "power2.inOut", t0)
        self._ft(f"#fx{i}-sl", {"clipPath": "inset(50% 0% 50% 0%)"}, {"clipPath": "inset(0% 0% 0% 0%)"}, 0.7, "power2.inOut", t0)
        self._ft(f"#fx{i}-t", {"opacity": 0, "y": 30}, {"opacity": 1, "y": 0}, 0.6, "power3.out", t0 + 0.25)
        self._g_fecha(i, j, t0 + 0.95, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_afirmacao_corrigida(self, i, fx):
        """Afirmação riscada e corrigida (strike & correct): a ideia comum entra, uma linha a risca e a versão correta
        sobe embaixo. Para desfazer um mito sem tom de promessa."""
        p = self.pal
        fx.setdefault("_pos_padrao", "terco-superior")
        corrige = float(fx.get("corrige_em", 2.0))
        j = self._g_janela(i, fx, [fx["errada"], fx["certa"]], ent_padrao=0.5, intervalo_padrao=corrige)
        origem = self.conferir_texto(i, fx, [fx["errada"], fx["certa"]])
        tam = int(fx.get("tamanho", 56))
        corpo = (f'<div class="ac-e"><div id="fx{i}-e" class="ac-et" style="font-size:{tam}px"><span id="fx{i}-et" class="ac-s">{_esc(fx["errada"])}</span></div></div>'
                 f'<div class="ac-cm"><div id="fx{i}-c2" class="ac-c" style="font-size:{round(tam * 1.12)}px">{_esc(fx["certa"])}</div></div>')
        self.css.append(
            f".ac-e{{text-align:center;margin-bottom:22px;}} .ac-et{{display:inline-block;font-weight:600;line-height:1.3;color:{p['texto']};opacity:0;}}"
            f".ac-s{{background-image:linear-gradient({p['destaque']},{p['destaque']});background-repeat:no-repeat;background-position:0 58%;background-size:0% 5px;"
            f"-webkit-box-decoration-break:clone;box-decoration-break:clone;}}"
            f".ac-cm{{overflow:hidden;padding:0.05em 0.04em 0.14em;}} .ac-c{{font-weight:700;line-height:1.15;color:{p['destaque']};text-align:center;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        t_e = max(j["ts"][0] - 0.05, j["ini"] + j["ent"] * 0.4)
        t_c = j["ts"][1] if j["sinc"] else j["ts"][0] + corrige
        self._ft(f"#fx{i}-e", {"opacity": 0, "y": 16}, {"opacity": 1, "y": 0}, 0.45, "power2.out", t_e)
        self._ft(f"#fx{i}-et", {"backgroundSize": "0% 5px", "opacity": 1}, {"backgroundSize": "100% 5px", "opacity": 0.5}, 0.55, "power2.inOut", t_c - 0.5)
        self._ft(f"#fx{i}-c2", {"yPercent": 118}, {"yPercent": 0}, 0.6, "power3.out", t_c)
        self._g_fecha(i, j, t_c + 0.65, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    # ------------------------------------------------------------------ GRÁFICOS
    def fx_barras_crescendo(self, i, fx):
        """Barra crescendo (growing bars): barras horizontais enchem como progresso (in-out), uma por vez, na ordem de
        leitura; o valor conta junto. Um item pode ficar em destaque (`destaque`: índice)."""
        p, s = self.pal, self.F["safe"]
        itens = fx["itens"]
        j = self._g_janela(i, fx, [it.get("fala") or it["rotulo"] for it in itens], intervalo_padrao=0.7)
        textos = [fx.get("titulo")]
        for it in itens:
            textos += [it["fala"]] if "fala" in it else [it["rotulo"], it.get("texto_valor")]
        origem = self.conferir_texto(i, fx, textos)
        mx = float(fx.get("max", max(float(it["valor"]) for it in itens)))
        lw = (s["x1"] - s["x0"]) - 80
        casas = int(fx.get("casas", 0))
        unid = fx.get("unidade", "")
        pref = fx.get("prefixo", "")
        dest = fx.get("destaque")
        blocos = []
        for k, it in enumerate(itens):
            blocos.append(
                f'<div id="fx{i}-b{k}" class="br-b"><div class="br-l"><span class="br-r{" br-d" if dest == k else ""}">{_esc(it["rotulo"])}</span>'
                f'<span id="fx{i}-v{k}" class="br-v">{_esc(pref + _num_pt(0, casas) + unid)}</span></div>'
                f'<div class="br-t"><div id="fx{i}-f{k}" class="br-f{" br-fd" if dest == k else ""}"></div></div></div>')
        corpo = self._g_titulo_html(i, fx) + f'<div style="width:{lw}px">' + "".join(blocos) + "</div>"
        self.css.append(
            f".br-b{{margin:0 0 34px;opacity:0;}} .br-l{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;}}"
            f".br-r{{font-weight:600;font-size:42px;color:{p['texto']};}} .br-d{{font-weight:700;}}"
            f".br-v{{font-weight:700;font-size:46px;color:{p['texto']};font-feature-settings:'tnum';}}"
            f".br-t{{height:34px;border-radius:9px;background:{_misturar(p['fundo'], p['texto'], 0.14)};overflow:hidden;}}"
            f".br-f{{height:100%;width:100%;border-radius:9px;background:{p['apoio']};transform-origin:0 50%;transform:scaleX(0);opacity:0.78;}}"
            f".br-fd{{background:{p['texto']};opacity:1;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        self._g_titulo(i, fx, j)
        t_last = 0
        for k, it in enumerate(itens):
            t = max(j["ts"][k] - 0.05, j["ini"] + 0.35)
            frac = float(it["valor"]) / mx
            self._ft(f"#fx{i}-b{k}", {"opacity": 0, "y": 14}, {"opacity": 1, "y": 0}, 0.4, "power3.out", t)
            d = 0.9
            self._ft(f"#fx{i}-f{k}", {"scaleX": 0}, {"scaleX": frac}, d, "power2.inOut", t + 0.15)
            self.js.append(f'(function(){{const el=document.getElementById("fx{i}-v{k}");const o={{v:0}};const f={JS_FMT};'
                           f'tl.fromTo(o,{{v:0}},{{v:{float(it["valor"])},duration:{d},ease:"power2.inOut",'
                           f'onUpdate:()=>{{el.textContent={_js(pref)}+f(o.v,{casas})+{_js(unid)};}}}},{t + 0.15:.4f});}})();')
            t_last = max(t_last, t + 0.15 + d)
        self._g_fecha(i, j, t_last + 0.3, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_linha_desenhando(self, i, fx):
        """Linha se desenhando (line draw-on): grade fina, depois a linha se desenha da esquerda para a direita; o ponto
        final aparece quando ela chega, com o valor. Sem números nos eixos (só os rótulos que ele falar)."""
        p, s = self.pal, self.F["safe"]
        pts = [float(v) for v in fx["pontos"]]
        if len(pts) < 3:
            erro(f"efeito {i}: linha precisa de ao menos 3 pontos")
        rx = fx.get("rotulos_x") or []
        rf = fx.get("rotulo_final")
        frase = fx.get("fala") or rf or fx.get("titulo")
        j = self._g_janela(i, fx, [frase], ent_padrao=0.6)
        origem = self.conferir_texto(i, fx, [fx.get("titulo"), fx.get("fala") or rf] + list(rx))
        Wc = (s["x1"] - s["x0"]) - 90
        Hc = int(fx.get("altura", 520))
        ml, mr, mt, mb = 24, 70, 70, 74
        lo, hi = min(pts), max(pts)
        rng = (hi - lo) or 1.0
        X = lambda k: ml + (Wc - ml - mr) * k / (len(pts) - 1)
        Y = lambda v: mt + (Hc - mt - mb) * (1 - (v - lo) / rng)
        d = "M" + " L".join(f"{X(k):.1f} {Y(v):.1f}" for k, v in enumerate(pts))
        area = d + f" L{X(len(pts) - 1):.1f} {Hc - mb} L{X(0):.1f} {Hc - mb} Z"
        grade = "".join(f'<line id="fx{i}-g{g}" x1="{ml}" x2="{Wc - mr + 20}" y1="{mt + (Hc - mt - mb) * g / 3:.1f}" y2="{mt + (Hc - mt - mb) * g / 3:.1f}" '
                        f'stroke="{p["texto"]}" stroke-opacity="0.16" stroke-width="2"/>' for g in range(4))
        ex, ey = X(len(pts) - 1), Y(pts[-1])
        xl = "".join(f'<text id="fx{i}-x{k}" x="{X(k):.1f}" y="{Hc - 22}" text-anchor="middle" font-size="30" font-weight="600" fill="{p["apoio"]}" opacity="0">{_esc(t)}</text>'
                     for k, t in enumerate(rx) if t)
        rtxt = (f'<text id="fx{i}-rf" x="{min(ex, Wc - 8):.1f}" y="{ey - 30:.1f}" text-anchor="end" font-size="50" font-weight="800" fill="{p["texto"]}" opacity="0">{_esc(rf)}</text>' if rf else "")
        corpo = self._g_titulo_html(i, fx) + (
            f'<svg width="{Wc}" height="{Hc}" viewBox="0 0 {Wc} {Hc}" style="overflow:visible">{grade}'
            f'<path id="fx{i}-ar" d="{area}" fill="{p["apoio"]}" fill-opacity="0"/>'
            f'<path id="fx{i}-li" d="{d}" fill="none" stroke="{p["texto"]}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" '
            f'pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>'
            f'<circle id="fx{i}-mk" cx="{ex:.1f}" cy="{ey:.1f}" r="13" fill="{p["destaque"]}" opacity="0"/>{rtxt}{xl}</svg>')
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        self._g_titulo(i, fx, j)
        t0 = j["ini"] + 0.2
        for g in range(4):
            self._ft(f"#fx{i}-g{g}", {"opacity": 0}, {"opacity": 1}, 0.4, "power2.out", t0 + 0.08 * g)
        dur = float(fx.get("desenho", 1.6))
        t_l = max(j["ts"][0] - dur + 0.3, t0 + 0.5) if j["sinc"] else t0 + 0.6
        self._ft(f"#fx{i}-li", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, dur, "power2.inOut", t_l)
        self._ft(f"#fx{i}-ar", {"fillOpacity": 0}, {"fillOpacity": 0.12}, 0.6, "power2.out", t_l + dur - 0.3)
        self._ft(f"#fx{i}-mk", {"opacity": 0}, {"opacity": 1}, 0.35, "power2.out", t_l + dur - 0.05)
        if rf:
            self._ft(f"#fx{i}-rf", {"opacity": 0, "y": 8}, {"opacity": 1, "y": 0}, 0.45, "power2.out", t_l + dur)
        for k, t in enumerate(rx):
            if t:
                self._ft(f"#fx{i}-x{k}", {"opacity": 0}, {"opacity": 1}, 0.35, "power2.out", t0 + 0.4 + 0.12 * k)
        self._g_fecha(i, j, t_l + dur + 0.6, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_linha_do_tempo_prazos(self, i, fx):
        """Linha do tempo de prazos (deadline timeline): a linha desce e cada marco aparece quando é dito (data à esquerda,
        descrição à direita). `ativo: true` num marco o destaca com um anel."""
        p, s = self.pal, self.F["safe"]
        marcos = fx["marcos"]
        j = self._g_janela(i, fx, [m.get("fala") or m["texto"] for m in marcos], intervalo_padrao=0.9)
        textos = [fx.get("titulo")]
        for m in marcos:
            textos += [m["fala"]] if "fala" in m else [m["texto"], m["data"]]
        origem = self.conferir_texto(i, fx, textos)
        sw = s["x1"] - s["x0"] - 60
        gap = int(fx.get("espaco", 150))
        n = len(marcos)
        alt = gap * (n - 1) + 90
        xs = 270
        itens = ""
        for k, m in enumerate(marcos):
            y = 45 + gap * k
            ativo = m.get("ativo")
            anel = (f'<circle id="fx{i}-an{k}" cx="{xs}" cy="{y}" r="25" fill="none" stroke="{p["destaque"]}" stroke-width="3" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" '
                    f'transform="rotate(-90 {xs} {y})"/>' if ativo else "")
            itens += (f'<div id="fx{i}-d{k}" class="lt-d" style="top:{y - 30}px;width:{xs - 50}px">{_esc(m["data"])}</div>'
                      f'<div id="fx{i}-t{k}" class="lt-t{" lt-ta" if ativo else ""}" style="top:{y - 30}px;left:{xs + 50}px;width:{sw - xs - 50}px">{_esc(m["texto"])}</div>'
                      f'<svg style="position:absolute;left:0;top:0;overflow:visible" width="{sw}" height="{alt}"><circle id="fx{i}-n{k}" cx="{xs}" cy="{y}" r="13" fill="{p["destaque"] if ativo else p["texto"]}" opacity="0"/>{anel}</svg>')
        corpo = self._g_titulo_html(i, fx) + (
            f'<div style="position:relative;width:{sw}px;height:{alt}px"><div id="fx{i}-sp" class="lt-sp" style="left:{xs - 2}px;top:45px;height:{gap * (n - 1)}px"></div>{itens}</div>')
        self.css.append(
            f".lt-sp{{position:absolute;width:4px;border-radius:2px;background:{p['apoio']};opacity:0.7;transform-origin:50% 0;transform:scaleY(0);}}"
            f".lt-d{{position:absolute;left:0;text-align:right;font-weight:700;font-size:44px;line-height:60px;color:{p['destaque']};font-feature-settings:'tnum';opacity:0;}}"
            f".lt-t{{position:absolute;font-weight:600;font-size:40px;line-height:60px;color:{p['texto']};opacity:0;}} .lt-ta{{font-weight:700;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        self._g_titulo(i, fx, j)
        t_last, prev_t = 0, j["ini"] + 0.3
        for k, m in enumerate(marcos):
            t = max(j["ts"][k] - 0.05, j["ini"] + 0.4)
            if k:
                dd = min(0.6, max(0.25, t - prev_t))
                self.js.append(f'tl.to("#fx{i}-sp",{{scaleY:{k / (n - 1):.4f},duration:{dd:.3f},ease:"power2.inOut"}},{max(prev_t, t - dd):.4f});')
            self._ft(f"#fx{i}-n{k}", {"opacity": 0}, {"opacity": 1}, 0.35, "power2.out", t)
            self._ft(f"#fx{i}-d{k}", {"opacity": 0, "y": 12}, {"opacity": 1, "y": 0}, 0.45, "power3.out", t)
            self._ft(f"#fx{i}-t{k}", {"opacity": 0, "y": 12}, {"opacity": 1, "y": 0}, 0.45, "power3.out", t + 0.08)
            if m.get("ativo"):
                self._ft(f"#fx{i}-an{k}", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, 0.6, "power2.inOut", t + 0.25)
            prev_t = t + 0.4
            t_last = max(t_last, t + (0.85 if m.get("ativo") else 0.55))
        self._g_fecha(i, j, t_last + 0.2, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_antes_depois(self, i, fx):
        """Comparação antes/depois (before-after): dois painéis, um sobre o outro, ligados por um conector que se desenha.
        Use para REGRA ANTERIOR x REGRA ATUAL (ou duas situações), NUNCA para prometer resultado (regras de publicidade profissional)."""
        p, s = self.pal, self.F["safe"]
        a, d = fx["antes"], fx["depois"]
        la, ld = a.get("linhas", []), d.get("linhas", [])
        frases = [a.get("fala") or (la[0] if la else None), d.get("fala") or (ld[0] if ld else None)]
        j = self._g_janela(i, fx, frases, intervalo_padrao=1.8)
        textos = []
        for blk in (a, d):
            textos += [blk["fala"]] if "fala" in blk else list(blk.get("linhas", []))
        origem = self.conferir_texto(i, fx, textos)
        lw = (s["x1"] - s["x0"]) - 80
        il = float(fx.get("intervalo_linhas", 0.28))

        def painel(k, blk, tit_padrao, destaque):
            lin = "".join(f'<div id="fx{i}-p{k}l{m}" class="ad-l">{_esc(t)}</div>' for m, t in enumerate(blk.get("linhas", [])))
            return (f'<div id="fx{i}-p{k}" class="ad-p{" ad-pd" if destaque else ""}"><div class="ad-h">{_esc(blk.get("titulo", tit_padrao))}</div>{lin}</div>')

        corpo = (painel(0, a, "ANTES", False)
                 + f'<div class="ad-cx"><div id="fx{i}-cn" class="ad-cn"></div><div id="fx{i}-cv" class="ad-cv"></div></div>'
                 + painel(1, d, "DEPOIS", True))
        self.css.append(
            f".ad-p{{width:{lw}px;box-sizing:border-box;border:2px solid {_misturar(p['fundo'], p['texto'], 0.35)};border-radius:18px;padding:30px 40px 30px;background:{_misturar(p['fundo'], '#FFFFFF', 0.05)};opacity:0;}}"
            f".ad-pd{{border-color:{p['destaque']};background:{_misturar(p['fundo'], '#FFFFFF', 0.10)};}}"
            f".ad-h{{font-weight:650;font-size:{int(fx.get('titulo_tamanho', 30))}px;letter-spacing:0.16em;text-transform:uppercase;color:{p['apoio']};margin-bottom:{int(fx.get('titulo_espaco', 14))}px;text-align:{'center' if fx.get('titulo_centro') else 'left'};}}"
            f".ad-l{{font-weight:600;font-size:44px;line-height:1.3;color:{p['texto']};opacity:0;}}"
            f".ad-cx{{position:relative;width:4px;height:84px;}} .ad-cn{{position:absolute;left:0;top:0;width:4px;height:100%;border-radius:2px;background:{p['destaque']};transform-origin:50% 0;transform:scaleY(0);}}"
            f".ad-cv{{position:absolute;left:-12px;bottom:-2px;width:0;height:0;border-left:14px solid transparent;border-right:14px solid transparent;border-top:20px solid {p['destaque']};opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        t_a = max(j["ts"][0] - 0.05, j["ini"] + 0.3)
        t_d = max(j["ts"][1] - 0.05, t_a + 0.6 + 0.3 * max(1, len(la)))
        self._ft(f"#fx{i}-p0", {"opacity": 0, "y": 20}, {"opacity": 1, "y": 0}, 0.5, "power3.out", t_a)
        for m in range(len(la)):
            self._ft(f"#fx{i}-p0l{m}", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t_a + 0.35 + il * m)
        self._ft(f"#fx{i}-cn", {"scaleY": 0}, {"scaleY": 1}, 0.4, "power2.inOut", t_d - 0.55)
        self._ft(f"#fx{i}-cv", {"opacity": 0}, {"opacity": 1}, 0.25, "power2.out", t_d - 0.2)
        self._ft(f"#fx{i}-p1", {"opacity": 0, "y": 20}, {"opacity": 1, "y": 0}, 0.5, "power3.out", t_d)
        for m in range(len(ld)):
            self._ft(f"#fx{i}-p1l{m}", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t_d + 0.35 + il * m)
        self._g_fecha(i, j, t_d + 0.35 + il * max(0, len(ld) - 1) + 0.4, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_fluxo_etapas(self, i, fx):
        """Fluxo em etapas com conectores (step flow): cartões em coluna, um conector se desenha entre cada par e um pulso
        pequeno corre por ele até a próxima etapa, na ordem em que são ditas."""
        p, s = self.pal, self.F["safe"]
        et = [e if isinstance(e, dict) else {"texto": e} for e in fx["etapas"]]
        j = self._g_janela(i, fx, [e.get("fala") or e["texto"] for e in et], intervalo_padrao=1.0)
        origem = self.conferir_texto(i, fx, [e.get("fala") or e["texto"] for e in et] + [fx.get("titulo")])
        lw = (s["x1"] - s["x0"]) - 120
        n = len(et)
        cn = int(fx.get("conector", 64))
        partes = ""
        for k, e in enumerate(et):
            partes += (f'<div id="fx{i}-n{k}" class="fl-n"><span class="fl-b">{k + 1}</span><span class="fl-t">{_esc(e["texto"])}</span></div>')
            if k < n - 1:
                partes += (f'<div class="fl-cx" style="height:{cn}px"><div id="fx{i}-c{k}" class="fl-c"></div><div id="fx{i}-pl{k}" class="fl-pl"></div></div>')
        corpo = self._g_titulo_html(i, fx) + f'<div style="width:{lw}px;display:flex;flex-direction:column;align-items:center">{partes}</div>'
        self.css.append(
            f".fl-n{{width:100%;box-sizing:border-box;display:flex;align-items:center;gap:26px;padding:26px 34px;border-radius:18px;border:2px solid {p['destaque']};background:{_misturar(p['fundo'], '#FFFFFF', 0.08)};opacity:0;}}"
            f".fl-b{{flex:none;width:58px;height:58px;border-radius:50%;background:{p['destaque']};color:{p['fundo']};font-weight:700;font-size:34px;display:flex;align-items:center;justify-content:center;}}"
            f".fl-t{{font-weight:650;font-size:42px;line-height:1.2;color:{p['texto']};}}"
            f".fl-cx{{position:relative;width:4px;}} .fl-c{{position:absolute;left:0;top:0;width:4px;height:100%;border-radius:2px;background:{p['apoio']};transform-origin:50% 0;transform:scaleY(0);}}"
            f".fl-pl{{position:absolute;left:-5px;top:0;width:14px;height:14px;border-radius:50%;background:{p['texto']};opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        self._g_titulo(i, fx, j)
        t_last = 0
        for k in range(n):
            t = max(j["ts"][k] - 0.05, j["ini"] + 0.35)
            self._ft(f"#fx{i}-n{k}", {"opacity": 0, "y": 16}, {"opacity": 1, "y": 0}, 0.45, "power3.out", t)
            if k < n - 1:
                tc = t + 0.4
                self._ft(f"#fx{i}-c{k}", {"scaleY": 0}, {"scaleY": 1}, 0.45, "power2.inOut", tc)
                self.js.append(f'tl.fromTo("#fx{i}-pl{k}",{{opacity:0,y:0}},{{opacity:1,y:{cn - 14},duration:0.45,ease:"power2.inOut"}},{tc:.4f});')
                self.js.append(f'tl.to("#fx{i}-pl{k}",{{opacity:0,duration:0.2,ease:"power2.out"}},{tc + 0.45:.4f});')
                t_last = max(t_last, tc + 0.65)
            else:
                t_last = max(t_last, t + 0.5)
        self._g_fecha(i, j, t_last + 0.2, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_contador_valor(self, i, fx):
        """Contador de valor (value counter): o valor antigo aparece pequeno e é riscado; o número conta até o novo valor
        e assenta, com rótulo. Formato pt-BR (R$ 1.234,56)."""
        p, s = self.pal, self.F["safe"]
        fx.setdefault("_pos_padrao", "terco-superior")
        casas = int(fx.get("casas", 0))
        de, para = float(fx["de"]), float(fx["para"])
        pre, suf = fx.get("prefixo", ""), fx.get("sufixo", "")
        f_de = fx.get("fala_de") or _num_pt(de, casas)
        f_para = fx.get("fala_para") or _num_pt(para, casas)
        conta_em = float(fx.get("conta_em", 1.4))
        j = self._g_janela(i, fx, [f_de, f_para], ent_padrao=0.5, intervalo_padrao=conta_em)
        origem = self.conferir_texto(i, fx, [f_de, f_para, fx.get("rotulo")])
        sw = s["x1"] - s["x0"]
        txt_de = pre + _num_pt(de, casas) + suf
        tam = self._g_ajusta(pre + _num_pt(max(de, para), casas) + suf, int(fx.get("tamanho", 120)), 800, sw - 200)
        corpo = (f'<div id="fx{i}-de" class="cv-de"><span id="fx{i}-det">{_esc(txt_de)}</span><div id="fx{i}-rb" class="cv-rb"></div></div>'
                 f'<div id="fx{i}-n" class="cv-n" style="font-size:{tam}px">{_esc(txt_de)}</div>'
                 + (f'<div id="fx{i}-rot" class="cv-rot">{_esc(fx["rotulo"])}</div>' if fx.get("rotulo") else ""))
        self.css.append(
            f".cv-de{{position:relative;display:inline-block;font-weight:600;font-size:{round(tam * 0.38)}px;color:{p['apoio']};font-feature-settings:'tnum';opacity:0;margin-bottom:6px;}}"
            f".cv-rb{{position:absolute;left:-3%;right:-3%;top:54%;height:4px;border-radius:2px;background:{p['destaque']};transform-origin:0 50%;transform:scaleX(0);}}"
            f".cv-n{{font-weight:700;line-height:1.05;color:{p['texto']};font-feature-settings:'tnum';text-align:center;white-space:nowrap;}}"
            f".cv-rot{{font-weight:600;font-size:40px;color:{p['apoio']};margin-top:14px;text-align:center;opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        t_de = max(j["ts"][0] - 0.05, j["ini"] + j["ent"] * 0.5)
        dur = float(fx.get("contagem", 1.1))
        t_c = j["ts"][1] if j["sinc"] else j["ts"][0] + conta_em
        t_c0 = max(t_c - dur + (0.3 if j["sinc"] else 0), t_de + 0.5)
        self._ft(f"#fx{i}-de", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t_de)
        self._ft(f"#fx{i}-rb", {"scaleX": 0}, {"scaleX": 1}, 0.4, "power2.inOut", t_c0 - 0.1)
        self._ft(f"#fx{i}-det", {"opacity": 1}, {"opacity": 0.5}, 0.35, "power2.inOut", t_c0)
        self.js.append(f'(function(){{const el=document.getElementById("fx{i}-n");const o={{v:{de}}};const f={JS_FMT};'
                       f'tl.fromTo(o,{{v:{de}}},{{v:{para},duration:{dur},ease:"power2.out",'
                       f'onUpdate:()=>{{el.textContent={_js(pre)}+f(o.v,{casas})+{_js(suf)};}}}},{t_c0:.4f});}})();')
        if fx.get("rotulo"):
            self._ft(f"#fx{i}-rot", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t_c0 + dur * 0.6)
        self._g_fecha(i, j, t_c0 + dur + 0.4, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_checklist_cascata(self, i, fx):
        """Checklist em cascata (cascading checklist): cada item entra quando é dito; um anel se desenha ao redor e o visto
        se traça por dentro. Ordem de leitura."""
        p, s = self.pal, self.F["safe"]
        its = [e if isinstance(e, dict) else {"texto": e} for e in fx["itens"]]
        j = self._g_janela(i, fx, [e.get("fala") or e["texto"] for e in its], intervalo_padrao=0.7)
        origem = self.conferir_texto(i, fx, [e.get("fala") or e["texto"] for e in its] + [fx.get("titulo")])
        lw = (s["x1"] - s["x0"]) - 80
        tam = int(fx.get("tamanho", 46))
        linhas = ""
        for k, e in enumerate(its):
            linhas += (f'<div id="fx{i}-r{k}" class="ck-r"><svg class="ck-s" width="60" height="60" viewBox="0 0 60 60">'
                       f'<circle id="fx{i}-c{k}" cx="30" cy="30" r="26" fill="none" stroke="{p["destaque"]}" stroke-width="4" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" transform="rotate(-90 30 30)"/>'
                       f'<path id="fx{i}-v{k}" d="M18 31 L26 39 L42 21" fill="none" stroke="{p["texto"]}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>'
                       f'<span class="ck-t" style="font-size:{tam}px">{_esc(e["texto"])}</span></div>')
        corpo = self._g_titulo_html(i, fx) + f'<div style="width:{lw}px">{linhas}</div>'
        self.css.append(
            f".ck-r{{display:flex;align-items:center;gap:28px;margin:0 0 30px;opacity:0;}} .ck-s{{flex:none;}}"
            f".ck-t{{font-weight:650;line-height:1.22;color:{p['texto']};}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        self._g_titulo(i, fx, j)
        t_last = 0
        for k in range(len(its)):
            t = max(j["ts"][k] - 0.05, j["ini"] + 0.35)
            self._ft(f"#fx{i}-r{k}", {"opacity": 0, "y": 14}, {"opacity": 1, "y": 0}, 0.4, "power3.out", t)
            self._ft(f"#fx{i}-c{k}", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, 0.4, "power2.inOut", t + 0.1)
            self._ft(f"#fx{i}-v{k}", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, 0.3, "power2.out", t + 0.4)
            t_last = max(t_last, t + 0.7)
        self._g_fecha(i, j, t_last + 0.2, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_destaque_de_lei(self, i, fx):
        """Destaque de trecho de lei (statute highlight): o texto aparece em cascata de linhas num cartão de papel; o trecho
        citado recebe marca-texto e o resto esmaece. Cabeçalho = identificação do dispositivo. Texto exato da fala."""
        p, s = self.pal, self.F["safe"]
        linhas, dest = fx["linhas"], fx["destaque"]
        nd = dest.split()
        alvo_idx, pos = None, None
        for k, ln in enumerate(linhas):
            ws = ln.split()
            for m in range(len(ws) - len(nd) + 1):
                if [_norm(x) for x in ws[m:m + len(nd)]] == [_norm(x) for x in nd]:
                    alvo_idx, pos = k, m
                    break
            if alvo_idx is not None:
                break
        if alvo_idx is None:
            erro(f"efeito {i}: o destaque «{dest}» precisa estar inteiro dentro de uma das linhas")
        j = self._g_janela(i, fx, [fx.get("fala") or " ".join(linhas), dest], intervalo_padrao=2.2)
        origem = self.conferir_texto(i, fx, [fx["fala"]] if "fala" in fx else [" ".join(linhas), fx.get("cabecalho")])
        larg = int(fx.get("largura", (s["x1"] - s["x0"]) - 120))
        tam = int(fx.get("tamanho", 46))
        LH = round(tam * 1.42)
        papel = fx.get("papel", "#F4EEE2")
        corpo_l = ""
        for k, ln in enumerate(linhas):
            if k == alvo_idx:
                ws = ln.split()
                a_, b_, c_ = " ".join(ws[:pos]), " ".join(ws[pos:pos + len(nd)]), " ".join(ws[pos + len(nd):])
                corpo_l += (f'<div id="fx{i}-l{k}" class="dl-ln"><span class="dl-o">{_esc(a_)}</span> <span class="dl-hw"><span id="fx{i}-hl" class="dl-hl"></span>'
                            f'<span id="fx{i}-ht" class="dl-ht">{_esc(b_)}</span></span> <span class="dl-o">{_esc(c_)}</span></div>')
            else:
                corpo_l += f'<div id="fx{i}-l{k}" class="dl-ln"><span class="dl-o">{_esc(ln)}</span></div>'
        cab = fx.get("cabecalho")
        corpo = (f'<div id="fx{i}-pp" class="dl-pp">'
                 + (f'<div class="dl-cab"><span class="dl-pt"></span>{_esc(cab)}</div><div class="dl-reg"></div>' if cab else "")
                 + corpo_l + "</div>")
        self.css.append(
            f".dl-pp{{width:{larg}px;box-sizing:border-box;background:{papel};color:{p['fundo']};border-radius:26px;padding:40px 46px 38px;"
            f"box-shadow:0 28px 60px rgba(0,0,0,0.30),0 6px 16px rgba(0,0,0,0.16);opacity:0;}}"
            f".dl-cab{{display:flex;align-items:center;gap:12px;font-weight:650;font-size:{round(tam * 0.5)}px;letter-spacing:0.06em;text-transform:uppercase;opacity:0.72;}}"
            f".dl-pt{{width:10px;height:10px;border-radius:3px;background:{p['destaque']};}} .dl-reg{{height:2px;background:{p['fundo']};opacity:0.12;margin:18px 0 22px;}}"
            f".dl-ln{{font-weight:600;font-size:{tam}px;line-height:{LH}px;}} .dl-hw{{position:relative;display:inline-block;margin:0 0.06em;}}"
            f".dl-hl{{position:absolute;left:-0.1em;right:-0.1em;top:8%;bottom:4%;background:{p['destaque']};border-radius:8px;transform-origin:0 50%;transform:scaleX(0);z-index:0;}}"
            f".dl-ht{{position:relative;z-index:1;font-weight:700;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        t0 = max(j["ts"][0] - 0.05, j["ini"] + 0.3)
        self._ft(f"#fx{i}-pp", {"opacity": 0, "y": 40}, {"opacity": 1, "y": 0}, 0.55, "power3.out", t0)
        t_lin = t0 + 0.4 + 0.14 * len(linhas)
        for k in range(len(linhas)):
            self._ft(f"#fx{i}-l{k}", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.4, "power2.out", t0 + 0.4 + 0.14 * k)
        t_h = max(j["ts"][1] - 0.1, t_lin + 0.5) if j["sinc"] else t_lin + float(fx.get("destaca_em", 0.9))
        self._ft(f"#fx{i}-hl", {"scaleX": 0}, {"scaleX": 1}, 0.55, "power2.inOut", t_h)
        for k in range(len(linhas)):
            if k != alvo_idx:
                self.js.append(f'tl.to("#fx{i}-l{k}",{{opacity:0.38,duration:0.45,ease:"power2.inOut"}},{t_h + 0.1:.4f});')
        self.js.append(f'tl.to("#fx{i}-l{alvo_idx} .dl-o",{{opacity:0.38,duration:0.45,ease:"power2.inOut"}},{t_h + 0.1:.4f});')
        self._g_fecha(i, j, t_h + 0.7, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_anel_percentual(self, i, fx):
        """Anel de proporção (ring gauge): o anel se completa no sentido horário a partir das 12h enquanto o número conta no
        centro. Rótulo embaixo."""
        p, s = self.pal, self.F["safe"]
        valor = float(fx["valor"])
        casas = int(fx.get("casas", 0))
        fala = fx.get("fala") or _num_pt(valor, casas)
        j = self._g_janela(i, fx, [fala], ent_padrao=0.6)
        origem = self.conferir_texto(i, fx, [fala, fx.get("rotulo")])
        D = int(fx.get("diametro", 480))
        R, sw_ = D / 2 - 22, 30
        un = fx.get("unidade", "%")
        frac = max(0.0, min(1.0, valor / float(fx.get("max", 100))))
        corpo = (f'<div style="position:relative;width:{D}px;height:{D}px"><svg width="{D}" height="{D}" viewBox="0 0 {D} {D}">'
                 f'<circle id="fx{i}-tr" cx="{D / 2}" cy="{D / 2}" r="{R}" fill="none" stroke="{_misturar(p["fundo"], p["texto"], 0.16)}" stroke-width="{sw_}" opacity="0"/>'
                 f'<circle id="fx{i}-an" cx="{D / 2}" cy="{D / 2}" r="{R}" fill="none" stroke="{p["destaque"]}" stroke-width="{sw_}" pathLength="1" '
                 f'stroke-dasharray="1" stroke-dashoffset="1" transform="rotate(-90 {D / 2} {D / 2})"/></svg>'
                 f'<div id="fx{i}-n" class="an-n">{_esc(_num_pt(0, casas))}<span class="an-u">{_esc(un)}</span></div></div>'
                 + (f'<div id="fx{i}-rot" class="an-rot">{_esc(fx["rotulo"])}</div>' if fx.get("rotulo") else ""))
        self.css.append(
            f".an-n{{position:absolute;left:0;top:0;width:{D}px;height:{D}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:{round(D * 0.25)}px;"
            f"color:{p['texto']};font-feature-settings:'tnum';}} .an-u{{font-size:{round(D * 0.12)}px;font-weight:650;color:{p['apoio']};margin-left:6px;padding-top:{round(D * 0.04)}px;}}"
            f".an-rot{{font-weight:600;font-size:44px;line-height:1.2;color:{p['apoio']};margin-top:30px;text-align:center;max-width:{(s['x1'] - s['x0']) - 120}px;opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=True)
        dur = float(fx.get("contagem", 1.4))
        t_fim = j["te"][0] if j["sinc"] else j["ini"] + j["ent"] * 0.6 + dur
        t0 = max(t_fim - dur, j["ini"] + 0.2)
        self._ft(f"#fx{i}-tr", {"opacity": 0}, {"opacity": 1}, 0.4, "power2.out", j["ini"] + 0.1)
        self._ft(f"#fx{i}-an", {"strokeDashoffset": 1}, {"strokeDashoffset": 1 - frac}, dur, "power2.inOut", t0)
        self.js.append(f'(function(){{const el=document.getElementById("fx{i}-n");const o={{v:0}};const f={JS_FMT};'
                       f'tl.fromTo(o,{{v:0}},{{v:{valor},duration:{dur},ease:"power2.inOut",'
                       f'onUpdate:()=>{{el.innerHTML=f(o.v,{casas})+\'<span class="an-u">\'+{_js(un)}+\'</span>\';}}}},{t0:.4f});}})();')
        if fx.get("rotulo"):
            self._ft(f"#fx{i}-rot", {"opacity": 0, "y": 10}, {"opacity": 1, "y": 0}, 0.45, "power2.out", t0 + dur * 0.7)
        self._g_fecha(i, j, t0 + dur + 0.5, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    # ------------------------------------------------------------------ FECHAMENTOS
    def _g_fecho_texto(self, i, fx):
        t = fx["texto"]
        if fx.get("texto_aprovado"):
            return f"aprovado: {fx['texto_aprovado']}"
        if " ".join(_norm(w) for w in t.split()) in FECHOS_NEUTROS:
            return "fechamento neutro (lista FECHOS_NEUTROS)"
        erro(f"efeito {i}: fechamento só com frase neutra aprovada ('Vale guardar esse vídeo', 'Fica de olho nisso') "
             "ou 'texto_aprovado' com a autorização de quem aparece no vídeo. Sem promessa de resultado nem apelo comercial.")

    def fx_fecho_frase_regua(self, i, fx):
        """Fechamento com régua (rule sign-off): uma régua fina se desenha do centro e a frase neutra surge embaixo. Pequeno,
        em espaço livre."""
        p, s = self.pal, self.F["safe"]
        fx.setdefault("_pos_padrao", "terco-superior")
        j = self._g_janela(i, fx, [None], ent_padrao=0.5, manter_padrao=1.5)
        origem = self._g_fecho_texto(i, fx)
        tam = self._g_ajusta(fx["texto"], int(fx.get("tamanho", 52)), 650, (s["x1"] - s["x0"]) - 200)
        corpo = (f'<div id="fx{i}-rg" class="ff-rg"></div><div id="fx{i}-tx" class="ff-tx" style="font-size:{tam}px">{_esc(fx["texto"])}</div>')
        self.css.append(f".ff-rg{{height:3px;width:46%;border-radius:2px;background:{p['destaque']};margin-bottom:16px;transform-origin:50% 50%;}}"
                        f".ff-tx{{font-weight:650;color:{p['texto']};text-align:center;line-height:1.2;opacity:0;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False)
        t0 = j["ini"] + 0.1
        self._ft(f"#fx{i}-rg", {"scaleX": 0}, {"scaleX": 1}, 0.55, "power2.inOut", t0)
        self._ft(f"#fx{i}-tx", {"opacity": 0, "y": 12}, {"opacity": 1, "y": 0}, 0.5, "power3.out", t0 + 0.25)
        self._g_fecha(i, j, t0 + 0.8, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_fecho_ficha_tema(self, i, fx):
        """Fechamento com ficha de referência (reference tag): ficha de duas partes (ex.: «Tribunal | Caso 0000») que se revela da
        esquerda para a direita, para o espectador guardar o tema. Texto da fala."""
        p = self.pal
        fx.setdefault("_pos_padrao", "terco-superior")
        partes = fx["partes"]
        j = self._g_janela(i, fx, [fx.get("fala") or " ".join(partes)], ent_padrao=0.5, manter_padrao=1.5)
        origem = self.conferir_texto(i, fx, [fx.get("fala") or " ".join(partes)])
        tam = int(fx.get("tamanho", 46))
        corpo = (f'<div class="fh"><div id="fx{i}-a" class="fh-a" style="font-size:{tam}px">{_esc(partes[0])}</div><div id="fx{i}-dv" class="fh-dv"></div>'
                 f'<div class="fh-bm"><div id="fx{i}-b" class="fh-b" style="font-size:{tam}px">{_esc(" ".join(partes[1:]))}</div></div></div>')
        self.css.append(
            f".fh{{display:inline-flex;align-items:center;gap:26px;}}"
            f".fh-a{{font-weight:700;color:{p['destaque']};letter-spacing:0.04em;opacity:0;}}"
            f".fh-dv{{width:3px;height:{round(tam * 1.2)}px;border-radius:2px;background:{p['apoio']};transform-origin:50% 0;transform:scaleY(0);}}"
            f".fh-bm{{overflow:hidden;padding:0.04em 0.05em 0.14em;}} .fh-b{{font-weight:650;color:{p['texto']};white-space:nowrap;}}")
        recorte = self._g_cena(i, fx, j, corpo, recorte_padrao=False, larg=int(fx.get("largura", 700)))
        t0 = max(j["ts"][0] - 0.05, j["ini"] + 0.2) if j["sinc"] else j["ini"] + 0.2
        self._ft(f"#fx{i}-a", {"opacity": 0, "x": -16}, {"opacity": 1, "x": 0}, 0.45, "power3.out", t0)
        self._ft(f"#fx{i}-dv", {"scaleY": 0}, {"scaleY": 1}, 0.4, "power2.inOut", t0 + 0.25)
        self._ft(f"#fx{i}-b", {"xPercent": -105}, {"xPercent": 0}, 0.55, "power3.out", t0 + 0.4)
        self._g_fecha(i, j, t0 + 1.0, hard_cut=recorte)
        return j["ini"], j["fim"], origem

    def fx_fecho_tela_limpa(self, i, fx):
        """Fechamento em tela limpa (quiet end card): recorte em tela cheia com fundo neutro, uma frase neutra e uma régua
        fina, com push-in lento (1,03x). Corte seco de ida. Só no fim do vídeo."""
        p, s = self.pal, self.F["safe"]
        j = self._g_janela(i, fx, [None], ent_padrao=0.5, manter_padrao=1.5)
        origem = self._g_fecho_texto(i, fx)
        tam = self._g_ajusta(fx["texto"], int(fx.get("tamanho", 76)), 700, (s["x1"] - s["x0"]) - 140)
        corpo = (f'<div id="fx{i}-tx" class="ft-tx" style="font-size:{tam}px">{_esc(fx["texto"])}</div><div id="fx{i}-rg" class="ft-rg"></div>')
        self.css.append(f".ft-tx{{font-weight:700;color:{p['texto']};text-align:center;line-height:1.2;opacity:0;}}"
                        f".ft-rg{{height:3px;width:30%;border-radius:2px;background:{p['destaque']};margin-top:30px;transform-origin:50% 50%;}}")
        fx["recorte"] = True
        self._g_cena(i, fx, j, corpo, recorte_padrao=True, push=1.03)
        t0 = j["ini"] + 0.25
        self._ft(f"#fx{i}-tx", {"opacity": 0, "y": 16}, {"opacity": 1, "y": 0}, 0.6, "power3.out", t0)
        self._ft(f"#fx{i}-rg", {"scaleX": 0}, {"scaleX": 1}, 0.6, "power2.inOut", t0 + 0.4)
        self._g_fecha(i, j, t0 + 1.1, hard_cut=True)
        return j["ini"], j["fim"], origem


def quadros(projeto, tempos, saida_dir, sem_fundo=False):
    """PNGs com alfa de um projeto de motion em instantes dados (sem renderizar o vídeo). Roda sem rede, pelo Node local do
    hyperframes-run (puppeteer-core que já vem com ele). Devolve a lista de arquivos. Serve para olhar o gráfico e para medir
    o conteúdo contra a safe area (--sem-fundo esconde o fundo do recorte)."""
    import json
    import subprocess
    from .comum import KIT, FORMATOS, HF_DIR, NAVEGADOR, caminho
    proj = caminho(projeto)
    html = proj / "index.html"
    if not html.exists():
        erro(f"projeto sem index.html: {proj} (gere com kit.py motion --so-projeto)")
    F = FORMATOS[json.loads((proj / "spec.json").read_text(encoding="utf-8")).get("formato", "reels")]
    hf = HF_DIR
    saida = caminho(saida_dir)
    saida.mkdir(parents=True, exist_ok=True)
    env = {"PATH": f"{hf / 'node' / 'bin'}:/usr/bin:/bin", "HOME": str(hf / "home"), "HF_NODE_MODULES": str(hf / "node_modules"),
           "HYPERFRAMES_BROWSER_PATH": NAVEGADOR}
    cmd = ["unshare", "-rn", "sh", "-c", 'ip link set lo up && exec node "$@"', "sh", str(KIT / "motion" / "quadros.mjs"),
           str(html), str(F["w"]), str(F["h"]), str(saida), ",".join(f"{t:.3f}" for t in tempos)] + (["--sem-fundo"] if sem_fundo else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        erro("quadros: falhou")
    return sorted(saida.glob("t_*.png"))
