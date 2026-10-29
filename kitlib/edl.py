"""EDL (lista de cortes) em JSON, ideia do edl.json do video-use reescrita para o nosso fluxo.

{
 "versao": 1, "tema": "meu-video",
 "fontes":       {"bloco1": "brutos/....mov"},
 "transcricoes": {"bloco1": "trabalho/<tema>/transcricoes/....json"},
 "segmentos": [ {"fonte": "bloco1", "in": 0.70, "out": 3.12, "nota": "gancho",
                 "transicao": "corte" | {"tipo": "dissolve", "dur": 0.25}} ],
 "zooms": [ {"de": 2.0, "ate": 4.2, "escala": 1.08, "rampa": 0.25, "nota": "punch zoom em 'prazo'"} ],   (tempo da SAÍDA)
           opcional: "rampa_entrada"/"rampa_saida" separadas (0 = degrau seco, p/ punch-in de jump cut; >1 s = push-in
           lento). Zooms se somam (escala-1). Punch que começa num corte: "de" = início do trecho - 0,01;
           "ate" = fim do trecho - 0,001 (não vaza para o trecho seguinte).
 "enquadramento": {"bloco1": {"foco_x": 0.5, "foco_y": 0.35}},
 "ruido": {"fonte": "bloco3", "de": 0.6, "ate": 1.9},        (perfil de ruído; opcional)
 "removidos": [...],                                           (informativo: o que o rascunho tirou e por quê)
 "aprovacao": null | {"por": "apresentador", "quando": "2026-10-22 14:30", "como": "mensagem 'pode renderizar'"}
}
"""
import math
from .comum import FPS, caminho, ler_json, erro
from . import compacta

PAD_IN, PAD_OUT, PAD_FIM = 0.06, 0.10, 0.30


def q(t):
    """Prende o tempo na grade de quadros (áudio e vídeo com a mesma duração, sem deriva no concat)."""
    return round(t * FPS) / FPS


def trans_dur(seg):
    t = seg.get("transicao", "corte")
    return q(float(t.get("dur", 0.25))) if isinstance(t, dict) and t.get("tipo") == "dissolve" else 0.0


def offsets(edl):
    """Início de cada segmento na saída (dissolves sobrepõem) e duração total."""
    off, t = [], 0.0
    for i, s in enumerate(edl["segmentos"]):
        d = trans_dur(s) if i else 0.0
        t -= d
        off.append(t)
        t += q(s["out"]) - q(s["in"])
    return off, t


def palavras_saida(edl):
    """Palavras das transcrições levadas para a linha do tempo da saída (seg = índice do segmento)."""
    off, _ = offsets(edl)
    trs = {f: ler_json(p) for f, p in edl["transcricoes"].items()}
    # correções de transcrição só no texto exibido: {"fonte": "bloco4", "i": 21, "texto": "contratado"};
    # texto "" funde a palavra na seguinte (a seguinte passa a começar onde ela começava)
    corr = {(c["fonte"], c["i"]): c["texto"] for c in edl.get("correcoes", [])}
    out = []
    for i, s in enumerate(edl["segmentos"]):
        a, b = q(s["in"]), q(s["out"])
        PW = trs[s["fonte"]]["palavras"]
        for wi, w in enumerate(PW):
            texto = corr.get((s["fonte"], wi), w["w"])
            if texto == "":
                continue
            if wi and corr.get((s["fonte"], wi - 1)) == "":
                w = dict(w, s=PW[wi - 1]["s"])
            meio = (w["s"] + w["e"]) / 2
            if a <= meio < b:
                ns = max(w["s"], a) - a + off[i]
                ne = min(w["e"], b) - a + off[i]
                out.append(dict(w=texto, s=round(ns, 3), e=round(ne, 3), seg=i, seg_fim=round(off[i] + b - a, 3)))
    return out


def rascunho(fontes, transcricoes, pausa_max=0.35, remover_talvez=False):
    """EDL automática: corta pausas > pausa_max, muletas, repetições e falsos começos.
    Nada é renderizado; o resultado é um RASCUNHO para quem aparece no vídeo aprovar."""
    segs, removidos = [], []
    for fid in fontes:
        tr = ler_json(transcricoes[fid])
        P = tr["palavras"]
        al = compacta.marcar(P)
        tira = {}
        for a in al:
            if a["tipo"] in ("muleta",) or (remover_talvez and a["tipo"] == "muleta?"):
                tira[a["i"]] = a["tipo"]
            elif a["tipo"] == "repeticao":
                tira[a["i"]] = "repetição"
            elif a["tipo"] == "falso-comeco":
                tira[a["i"]] = "falso começo"
            elif a["tipo"] == "retomada":
                j = a["i"]
                while j < len(P) and P[j]["e"] <= a["e"] + 1e-6:
                    tira.setdefault(j, "retomada"); j += 1
        for i, mot in sorted(tira.items()):
            removidos.append(dict(fonte=fid, s=P[i]["s"], e=P[i]["e"], texto=P[i]["w"], motivo=mot))
        corridas, cur = [], []
        for i, w in enumerate(P):
            if i in tira:
                if cur: corridas.append(cur); cur = []
                continue
            if cur and w["s"] - P[cur[-1]]["e"] > pausa_max:
                removidos.append(dict(fonte=fid, s=P[cur[-1]]["e"], e=w["s"], texto="",
                                      motivo=f"pausa {w['s'] - P[cur[-1]]['e']:.2f} s"))
                corridas.append(cur); cur = []
            cur.append(i)
        if cur: corridas.append(cur)
        for c in corridas:
            a = P[c[0]]["s"] - PAD_IN
            b = P[c[-1]]["e"] + PAD_OUT
            if c[0] > 0: a = max(a, P[c[0] - 1]["e"] + 0.01)
            if c[-1] + 1 < len(P): b = min(b, P[c[-1] + 1]["s"] - 0.01)
            a, b = max(0.0, a), min(tr["duracao"], b)
            texto = " ".join(P[i]["w"] for i in c)
            if segs and segs[-1]["fonte"] == fid and a - segs[-1]["out"] < 0.12:
                segs[-1]["out"] = round(b, 3); segs[-1]["nota"] += " " + texto
            else:
                segs.append(dict(fonte=fid, **{"in": round(a, 3), "out": round(b, 3)}, nota=texto, transicao="corte"))
    if segs:
        segs[-1]["out"] = round(min(ler_json(transcricoes[segs[-1]["fonte"]])["duracao"], segs[-1]["out"] + PAD_FIM), 3)
    return dict(versao=1, fontes=fontes, transcricoes=transcricoes, segmentos=segs, zooms=[], enquadramento={},
                removidos=removidos, aprovacao=None)


def plano_texto(edl):
    """Resumo em português para mostrar a quem aparece no vídeo ANTES de renderizar."""
    off, tot = offsets(edl)
    bruto = sum(ler_json(p)["duracao"] for p in edl["transcricoes"].values())
    L = [f"Plano de corte: {len(edl['segmentos'])} trechos, {tot:.1f} s na saída (bruto somado: {bruto:.1f} s).", ""]
    for i, s in enumerate(edl["segmentos"]):
        tr = "" if i == 0 else (" [dissolve %.2f s]" % trans_dur(s) if trans_dur(s) else " [corte seco]")
        L.append(f"{i+1:2d}. {off[i]:6.2f}s  {s['fonte']} {s['in']:.2f}-{s['out']:.2f}{tr}  “{s.get('nota', '').strip()}”")
    for z in edl.get("zooms", []):
        L.append(f"    zoom {z['escala']:.2f}x de {z['de']:.2f} a {z['ate']:.2f} s ({z.get('nota', '')})")
    if edl.get("removidos"):
        L += ["", "Removido:"]
        for r in edl["removidos"]:
            L.append(f"  - {r['fonte']} {r['s']:.2f}-{r['e']:.2f}  {r['motivo']}" + (f": “{r['texto']}”" if r["texto"] else ""))
    L += ["", "Aprovado: " + (f"sim ({edl['aprovacao']})" if edl.get("aprovacao") else "NÃO — aguardando aprovação")]
    return "\n".join(L)


def validar(edl):
    if not edl.get("segmentos"):
        erro("EDL sem segmentos")
    for f, p in edl["fontes"].items():
        if not caminho(p).exists():
            erro(f"fonte {f} não encontrada: {p}")
    for i, s in enumerate(edl["segmentos"]):
        if s["fonte"] not in edl["fontes"]:
            erro(f"segmento {i+1}: fonte {s['fonte']} não declarada")
        if q(s["out"]) - q(s["in"]) < 2 / FPS:
            erro(f"segmento {i+1}: curto demais")
        if i and trans_dur(s) >= min(q(s["out"]) - q(s["in"]), q(edl["segmentos"][i-1]["out"]) - q(edl["segmentos"][i-1]["in"])):
            erro(f"segmento {i+1}: dissolve maior que o trecho")
