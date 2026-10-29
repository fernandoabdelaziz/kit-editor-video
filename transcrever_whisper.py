"""Transcrição LOCAL com faster-whisper (roda só pelo .venv-whisper). Nada sai da máquina.

Uso (normalmente via kit.py transcrever):
  .venv-whisper/bin/python ferramentas/kit-editor/transcrever_whisper.py --saida-dir trabalho/<tema>/transcricoes \
      [--termos "nomes, siglas, termos técnicos"] [--modelo medium] fonte1.mov [fonte2.mov ...]

Saída por fonte: <saida-dir>/<nome>.json com palavras (w, s, e, p), segmentos, sha256 da fonte e
"gaps": trechos entre palavras com energia de voz (possível muleta que o whisper não escreveu).
Cache: se o JSON existe e o sha256 bate, não transcreve de novo. A fonte é só lida.
"""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kitlib.comum import MODELOS_WHISPER  # noqa: E402  (só stdlib)

MODELOS = str(MODELOS_WHISPER)
# Prompt com hesitações reais: induz o whisper a escrever muletas ("é...", "hum") em vez de limpá-las.
PROMPT_BASE = "Então, é... hum, a gente vai ver, né? Tipo, ééé, o imposto."


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def audio_16k(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def energia_gaps(x, palavras, dur):
    """Para cada intervalo sem palavra >= 0,25 s: fração de quadros de 10 ms com voz."""
    q = 160
    n = len(x) // q
    rms = np.sqrt(np.mean(x[: n * q].reshape(n, q) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    piso = float(np.percentile(db, 10))
    limiar = piso + 15
    marcos = [(0.0, palavras[0]["s"] if palavras else dur)]
    marcos += [(a["e"], b["s"]) for a, b in zip(palavras, palavras[1:])]
    if palavras:
        marcos.append((palavras[-1]["e"], dur))
    gaps = []
    for a, b in marcos:
        if b - a < 0.25:
            continue
        i0, i1 = int(a * 100), int(b * 100)
        seg = db[i0:i1]
        if len(seg) == 0:
            continue
        voz = float(np.mean(seg > limiar))
        gaps.append(dict(s=round(a, 3), e=round(b, 3), voz=round(voz, 2), pico_db=round(float(seg.max()), 1)))
    return gaps, round(piso, 1)


def ajustar_bordas(x, palavras):
    """O whisper estica bordas de palavra (sobretudo a 1ª de cada frase, que pode 'começar' em 0,00).
    Encolhe início/fim que caem em silêncio: limiar = piso + 10 dB, mantendo 40 ms de folga."""
    q = 160
    n = len(x) // q
    db = 20 * np.log10(np.sqrt(np.mean(x[: n * q].reshape(n, q) ** 2, axis=1) + 1e-12))
    lim = float(np.percentile(db, 10)) + 10
    for w in palavras:
        i0, i1 = int(w["s"] * 100), max(int(w["s"] * 100) + 1, int(w["e"] * 100))
        voz = np.nonzero(db[i0:i1] > lim)[0]
        if len(voz) == 0:
            continue
        ns = (i0 + voz[0]) / 100 - 0.04
        ne = (i0 + voz[-1] + 1) / 100 + 0.04
        if ns - w["s"] > 0.08:
            w["s0"], w["s"] = w["s"], round(ns, 3)
        if w["e"] - ne > 0.12:
            w["e0"], w["e"] = w["e"], round(ne, 3)
    return palavras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fontes", nargs="+")
    ap.add_argument("--saida-dir", required=True)
    ap.add_argument("--termos", default="", help="termos técnicos/nomes para o prompt (ex.: 'nomes próprios, siglas')")
    ap.add_argument("--modelo", default="medium")
    ap.add_argument("--idioma", default="pt")
    a = ap.parse_args()
    out_dir = Path(a.saida_dir)
    if "brutos" in out_dir.resolve().parts:
        sys.exit("recusado: saída em brutos/")
    out_dir.mkdir(parents=True, exist_ok=True)
    modelo = None
    for f in a.fontes:
        f = Path(f)
        dest = out_dir / (f.stem + ".json")
        h = sha256(f)
        if dest.exists():
            antigo = json.loads(dest.read_text())
            if antigo.get("sha256") == h:
                print(f"cache: {dest}")
                continue
            sys.exit(f"recusado: {dest} existe e é de outra versão da fonte; apague-o você mesmo se quiser refazer")
        if modelo is None:
            modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8", download_root=MODELOS)
        prompt = PROMPT_BASE + (" " + a.termos if a.termos else "")
        segs, inf = modelo.transcribe(str(f), language=a.idioma, word_timestamps=True, vad_filter=False,
                                      condition_on_previous_text=False, initial_prompt=prompt, beam_size=5)
        segmentos, palavras = [], []
        for s in segs:
            segmentos.append(dict(s=round(s.start, 3), e=round(s.end, 3), texto=s.text.strip()))
            for w in s.words:
                palavras.append(dict(w=w.word.strip(), s=round(w.start, 3), e=round(w.end, 3),
                                     p=round(w.probability, 3)))
        x = audio_16k(f)
        dur = len(x) / 16000
        palavras = ajustar_bordas(x, palavras)
        gaps, piso = energia_gaps(x, palavras, dur)
        json.dump(dict(fonte=str(f.resolve()), sha256=h, modelo=a.modelo, idioma=a.idioma, duracao=round(dur, 3),
                       piso_ruido_db=piso, prompt=prompt, segmentos=segmentos, palavras=palavras, gaps=gaps),
                  open(dest, "w"), ensure_ascii=False, indent=1)
        print(f"{dest}: {len(palavras)} palavras | {' '.join(s['texto'] for s in segmentos)}", flush=True)


if __name__ == "__main__":
    main()
