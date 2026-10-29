"""Transcrição compacta (ideia do takes_packed.md do video-use, reescrita): frases com [início-fim],
mais alertas em pt-BR: muletas, repetições/falsos começos, pausas longas, palavras de baixa confiança
e "voz sem palavra" (energia de voz num intervalo sem palavra: muleta que o whisper não escreveu)."""
import re
import unicodedata
from pathlib import Path

MULETAS_FORTES = {"éé", "ééé", "eh", "ehh", "ã", "ãh", "ah", "ahn", "hum", "humm", "hm", "hmm", "uhm", "um,", "é..."}
MULETAS_ISOLADAS = {"é", "eh"}   # só são muleta se isoladas por pausa ou alongadas
MULETAS_TALVEZ = {"tipo", "né", "e", "então", "assim", "tá"}   # palavras reais: só sinaliza, o rascunho não corta
PAUSA_FRASE = 0.5
PAUSA_LONGA = 0.6


def norm(w):
    w = w.lower().strip()
    w = re.sub(r"[\"“”'’.,;:!?…()\[\]]", "", w)
    return w


def sem_acento(w):
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")


def marcar(palavras):
    """Devolve lista de alertas: dict(i, tipo, s, e, txt). i = índice da palavra (ou None para gaps)."""
    al = []
    n = len(palavras)
    for i, w in enumerate(palavras):
        t = norm(w["w"])
        gap_antes = w["s"] - palavras[i - 1]["e"] if i else 9
        gap_depois = palavras[i + 1]["s"] - w["e"] if i + 1 < n else 9
        dur = w["e"] - w["s"]
        if t in MULETAS_FORTES or re.fullmatch(r"(é|e)\1+|h+u*m+|ã+h*|a+h+", t or "-"):
            al.append(dict(i=i, tipo="muleta", s=w["s"], e=w["e"], txt=w["w"]))
        elif t in MULETAS_ISOLADAS and (min(gap_antes, gap_depois) >= 0.3 or dur >= 0.45 or w["w"].endswith("...")):
            al.append(dict(i=i, tipo="muleta", s=w["s"], e=w["e"], txt=w["w"]))
        elif t in MULETAS_TALVEZ and (gap_depois >= 0.25 or dur >= 0.45 or (i + 1 < n and norm(palavras[i + 1]["w"]) == t)):
            al.append(dict(i=i, tipo="muleta?", s=w["s"], e=w["e"], txt=w["w"]))
        if i + 1 < n:
            t2 = norm(palavras[i + 1]["w"])
            if t and t == t2:
                al.append(dict(i=i, tipo="repeticao", s=w["s"], e=w["e"], txt=f"{w['w']} {palavras[i+1]['w']}"))
            elif len(t) >= 3 and len(t2) > len(t) and sem_acento(t2).startswith(sem_acento(t).rstrip("-")):
                al.append(dict(i=i, tipo="falso-comeco", s=w["s"], e=w["e"], txt=f"{w['w']} → {palavras[i+1]['w']}"))
        # retomada: mesmo bigrama de novo logo à frente ("o juiz o juiz decidiu")
        if i + 3 < n:
            bg = (t, norm(palavras[i + 1]["w"]))
            for j in range(i + 2, min(i + 7, n - 1)):
                if (norm(palavras[j]["w"]), norm(palavras[j + 1]["w"])) == bg and all(bg):
                    al.append(dict(i=i, tipo="retomada", s=w["s"], e=palavras[j - 1]["e"],
                                   txt=" ".join(p["w"] for p in palavras[i:j + 2])))
                    break
        if w.get("p", 1) < 0.4:
            al.append(dict(i=i, tipo="baixa-confianca", s=w["s"], e=w["e"], txt=f"{w['w']} (p={w['p']:.2f})"))
        if i + 1 < n and gap_depois >= PAUSA_LONGA:
            al.append(dict(i=None, tipo="pausa", s=w["e"], e=palavras[i + 1]["s"], txt=f"{gap_depois:.2f} s"))
    return al


def frases(palavras, limiar=PAUSA_FRASE):
    out, cur = [], []
    for i, w in enumerate(palavras):
        if cur and w["s"] - palavras[cur[-1]]["e"] >= limiar:
            out.append(cur); cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def gerar(transcricoes, destino):
    """transcricoes: lista de (id_fonte, dict do JSON). Escreve o .md compacto e devolve {id: alertas}."""
    L = ["# Transcrição compacta", "",
         "Frases quebradas em pausas ≥ 0,5 s. Tempos em segundos da FONTE (use-os na EDL).",
         "Marcas: ⟦muleta⟧, ⟦muleta?⟧ (talvez), ⟦rep⟧ repetição, ⟦falso⟧ falso começo, `?` baixa confiança,",
         "⟨pausa X s⟩, ⟨voz sem palavra⟩ = som de voz sem texto (provável \"é...\" que o whisper omitiu).", ""]
    todos = {}
    for fid, tr in transcricoes:
        P = tr["palavras"]
        al = marcar(P)
        todos[fid] = al
        por_i = {}
        for a in al:
            if a["i"] is not None:
                por_i.setdefault(a["i"], []).append(a["tipo"])
        gaps_voz = [g for g in tr.get("gaps", []) if g["voz"] >= 0.3 and g["e"] - g["s"] >= 0.25]
        L.append(f"## {fid}  ({tr['duracao']:.1f} s, {len(P)} palavras) — `{tr['fonte']}`")
        for fr in frases(P):
            toks = []
            for i in fr:
                w = P[i]["w"]
                tipos = por_i.get(i, [])
                if "muleta" in tipos: w = f"⟦{w}⟧"
                elif "muleta?" in tipos: w = f"⟦{w}?⟧"
                elif "repeticao" in tipos: w = f"⟦rep:{w}⟧"
                elif "falso-comeco" in tipos: w = f"⟦falso:{w}⟧"
                if "baixa-confianca" in tipos: w += "?"
                toks.append(w)
                if i + 1 < len(P) and i + 1 in fr:
                    g = P[i + 1]["s"] - P[i]["e"]
                    if g >= 0.3:
                        voz = any(gv["s"] >= P[i]["e"] - 0.05 and gv["e"] <= P[i + 1]["s"] + 0.05 for gv in gaps_voz)
                        toks.append(f"⟨{g:.2f}s{' voz sem palavra' if voz else ''}⟩")
            L.append(f"  [{P[fr[0]]['s']:06.2f}-{P[fr[-1]]['e']:06.2f}] {' '.join(toks)}")
            if fr[-1] + 1 < len(P):
                g = P[fr[-1] + 1]["s"] - P[fr[-1]]["e"]
                voz = any(gv["s"] >= P[fr[-1]]["e"] - 0.05 and gv["e"] <= P[fr[-1] + 1]["s"] + 0.05 for gv in gaps_voz)
                L.append(f"    ⟨pausa {g:.2f} s{' · voz sem palavra' if voz else ''}⟩")
        if al:
            L.append("  Alertas:")
            for a in al:
                L.append(f"   - {a['s']:6.2f}-{a['e']:6.2f}  {a['tipo']}: {a['txt']}")
        L.append("")
    Path(destino).write_text("\n".join(L), encoding="utf-8")
    return todos
