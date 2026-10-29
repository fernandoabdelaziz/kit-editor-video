"""Utilidades comuns: caminhos, travas de segurança, ffprobe, execução de ffmpeg."""
import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent


def _achar_raiz():
    """Pasta de trabalho (raiz) com brutos/, trabalho/, editados/, ferramentas/ e os .venv-*.
    Ordem: variável KIT_RAIZ > arquivo raiz.txt ao lado do kit.py (gravado pelo install.sh) >
    duas pastas acima do kit, se ele estiver em <raiz>/ferramentas/kit-editor."""
    if os.environ.get("KIT_RAIZ"):
        return Path(os.environ["KIT_RAIZ"]).expanduser().resolve()
    arq = KIT / "raiz.txt"
    if arq.exists() and arq.read_text(encoding="utf-8").strip():
        return Path(arq.read_text(encoding="utf-8").strip()).expanduser().resolve()
    if KIT.parent.name == "ferramentas":
        return KIT.parent.parent
    return Path.cwd().resolve()


def _achar_navegador():
    if os.environ.get("HYPERFRAMES_BROWSER_PATH"):
        return os.environ["HYPERFRAMES_BROWSER_PATH"]
    for c in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if Path(c).exists():
            return c
    return "/usr/bin/google-chrome"


RAIZ = _achar_raiz()
BRUTOS = RAIZ / "brutos"
FERRAMENTAS = RAIZ / "ferramentas"
VENV_WHISPER = RAIZ / ".venv-whisper" / "bin" / "python"
MODELOS_WHISPER = RAIZ / ".modelos-whisper"
VENV_PESSOA = RAIZ / ".venv-pessoa" / "bin" / "python"
MODELO_PESSOA = RAIZ / ".modelos-pessoa" / "selfie_segmenter.tflite"
MODELO_RUIDO = FERRAMENTAS / "modelos-ruido" / "cb.rnnn"
HF_DIR = FERRAMENTAS / "hyperframes-run"
# Opcional: check.py do ffmpeg-skill (MIT) usado pelo `kit.py conferir`; sem ele, o item é pulado.
CHECK_PY = FERRAMENTAS / "ffmpeg-skill" / "scripts" / "check.py"
PY_SKILL = RAIZ / ".venv-ffmpeg-skill" / "bin" / "python"
NAVEGADOR = _achar_navegador()

# Onde o kit pode escrever. brutos/ nunca.
PERMITIDAS = [RAIZ / "trabalho", RAIZ / "editados", Path("/tmp")]

# Formatos de saída e safe areas (px). "legenda_y" = base da legenda (fração da altura).
FORMATOS = {
    "reels":    dict(w=1080, h=1920, safe=dict(x0=60, x1=1020, y0=250, y1=1600)),
    "linkedin": dict(w=1080, h=1350, safe=dict(x0=60, x1=1020, y0=60, y1=1290)),
    "paisagem": dict(w=1920, h=1080, safe=dict(x0=96, x1=1824, y0=54, y1=1026)),
}
FPS = 30
BT709 = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
# Tone mapping HDR padrão (HLG/PQ -> bt709, hable), seguido de saturação 0,92.
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,eq=saturation=0.92")
HDR_TRC = {"arib-std-b67", "smpte2084"}


def erro(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(2)


def info(msg):
    print(msg, flush=True)


def caminho(p):
    p = Path(p)
    return p if p.is_absolute() else (RAIZ / p)


def saida_segura(p, sobrescrever_trabalho=False):
    """Confere se dá para escrever em p: nunca em brutos/, só em pastas permitidas,
    nunca sobrescreve em editados/ (e, por padrão, em lugar nenhum)."""
    p = caminho(p).resolve()
    if p == BRUTOS or BRUTOS in p.parents:
        erro(f"recusado: {p} fica em brutos/ (só leitura)")
    if not any(p == d or d in p.parents for d in PERMITIDAS):
        erro(f"recusado: {p} fora de trabalho/, editados/ ou /tmp")
    if p.exists():
        if (RAIZ / "editados") in p.parents or not sobrescrever_trabalho:
            erro(f"recusado: {p} já existe (o kit não sobrescreve; use outro nome/versão)")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run(cmd, quieto=True, capturar=False):
    if not quieto:
        info("+ " + " ".join(str(c) for c in cmd)[:200])
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:], file=sys.stderr)
        erro(f"comando falhou: {' '.join(str(c) for c in cmd)[:200]}")
    return r if capturar else None


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        erro(f"ffprobe falhou em {path}")
    return json.loads(r.stdout)


def video_info(path):
    d = ffprobe(path)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = int(v["width"]), int(v["height"])
    if rot % 180:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    return dict(w=w, h=h, rot=rot, hdr=v.get("color_transfer") in HDR_TRC, trc=v.get("color_transfer"),
                fps=float(num) / float(den or 1), dur=float(d["format"]["duration"]),
                tem_audio=any(s["codec_type"] == "audio" for s in d["streams"]), pix_fmt=v.get("pix_fmt"))


def ler_json(p):
    return json.loads(Path(caminho(p)).read_text(encoding="utf-8"))


def gravar_json(p, obj, sobrescrever=False):
    p = saida_segura(p, sobrescrever_trabalho=sobrescrever)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def sha256(path, limite=None):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ass_cor(h):
    """#RRGGBB -> &HBBGGRR& (ASS)."""
    r, g, b = hex_rgb(h)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def ass_alfa(opacidade):
    """opacidade 0..1 -> &HAA& (ASS: 00 opaco, FF transparente)."""
    return f"&H{round(255 * (1 - max(0.0, min(1.0, opacidade)))):02X}&"


def ts_ass(t):
    t = max(t, 0)
    cs = int(round(t * 100))
    h, r = divmod(cs, 360000)
    m, r = divmod(r, 6000)
    s, cs = divmod(r, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ts_srt(t):
    ms = int(round(max(t, 0) * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def esc_filtro(p):
    """Escapa caminho para usar dentro de um filtro (ass=...)."""
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
