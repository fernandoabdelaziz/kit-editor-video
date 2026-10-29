"""Cadeia de voz padrão do kit, como módulo.
É padrão técnico do kit (não é escolha de estilo). Ordem:
 highpass 80 Hz > afftdn nr 12 com perfil de ruído aprendido num silêncio do bruto > expansor suave (agate)
 > EQ -3 dB em 300 Hz e +4 dB em 4 kHz > de-esser leve > compressor 3:1 > loudnorm 2 passadas (-14 LUFS, TP -1,5)."""
import json
import subprocess

from .comum import MODELO_RUIDO, run, erro, info

CADEIA = ",".join([
    "highpass=f=80:p=2",
    "afftdn@dn=nr=12:nf=-50:tn=0",
    "agate=threshold=0.008:ratio=2:range=0.4:attack=5:release=180:knee=4",
    "equalizer=f=300:t=q:w=1.0:g=-3",
    "equalizer=f=4000:t=q:w=0.9:g=4",
    "deesser=i=0.25:m=0.5:f=0.5",
    "acompressor=threshold=0.08:ratio=3:attack=5:release=80:knee=3:makeup=1",
])
ALVO_I, ALVO_TP, ALVO_LRA = -14, -1.5, 11

# Perfil "rua": gravação sem microfone externo, com ruído ambiente forte (avenida, janela aberta).
# Rede neural rnnoise (modelo cb, dados em texto)
# + afftdn leve contra chiado + gate suave. Sem concat de perfil de ruído.
MODELO_RUA = str(MODELO_RUIDO)  # <raiz>/ferramentas/modelos-ruido/cb.rnnn (baixado pelo install.sh)
CADEIA_RUA = ",".join([
    f"arnndn=m={MODELO_RUA}",
    "afftdn=nr=10:nf=-45:tn=1:tr=1",
    "lowpass=f=11000",
    "highpass=f=90",
    "agate=threshold=0.01:ratio=2:attack=20:release=300:range=0.15:knee=4",
    "equalizer=f=3200:t=q:w=1:g=2",
    "acompressor=threshold=0.1:ratio=2.5",
])
PERFIL = "padrao"


def _filtro(dur_ruido, extra):
    if PERFIL == "rua":
        return f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,{CADEIA_RUA}{extra}"
    pre = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    if dur_ruido:
        return (f"[0:a]{pre}[r];[1:a]{pre}[m];[r][m]concat=n=2:v=0:a=1,"
                f"asendcmd=c='0.05 afftdn@dn sample_noise start; {dur_ruido - 0.05:.2f} afftdn@dn sample_noise stop',"
                f"{CADEIA},atrim=start={dur_ruido},asetpts=PTS-STARTPTS{extra}")
    return f"[0:a]{pre},{CADEIA}{extra}"


def tratar(wav_editado, saida_wav, ruido=None, perfil="padrao"):
    global PERFIL
    PERFIL = perfil
    if perfil == "rua":
        ruido = None
    """wav_editado: áudio montado SEM tratamento. ruido: (arquivo, de, ate) de um silêncio do bruto ou None."""
    if ruido:
        arq, a, b = ruido
        entradas = ["-ss", f"{a}", "-to", f"{b}", "-i", str(arq), "-i", str(wav_editado)]
        dr = b - a
    else:
        entradas = ["-i", str(wav_editado)]
        dr = 0
        if perfil != "rua":
            info("aviso: sem perfil de ruído (nenhum silêncio ≥ 0,8 s achado); afftdn usa o modelo padrão")
    r = subprocess.run(["ffmpeg", "-hide_banner", *entradas, "-filter_complex",
                        _filtro(dr, f",loudnorm=I={ALVO_I}:TP={ALVO_TP}:LRA={ALVO_LRA}:print_format=json"),
                        "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:]); erro("loudnorm passada 1 falhou")
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I={ALVO_I}:TP={ALVO_TP}:LRA={ALVO_LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          f"linear=true:print_format=json")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-n", *entradas, "-filter_complex",
                        _filtro(dr, f",{ln},aresample=48000"), "-c:a", "pcm_s16le", str(saida_wav)],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:]); erro("loudnorm passada 2 falhou")
    m2 = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    return dict(antes_I=float(m["input_i"]), antes_TP=float(m["input_tp"]), depois_I=float(m2["output_i"]),
                depois_TP=float(m2["output_tp"]), tipo=m2["normalization_type"])


def achar_silencio(transcricoes, fontes, minimo=0.8):
    """Procura o maior intervalo sem palavra e sem voz (gaps do transcrever) para usar como perfil de ruído."""
    melhor = None
    for fid, tr in transcricoes.items():
        for g in tr.get("gaps", []):
            if g["voz"] <= 0.1 and g["e"] - g["s"] >= minimo:
                a, b = g["s"] + 0.1, min(g["e"] - 0.1, g["s"] + 1.6)
                if b - a >= 0.5 and (melhor is None or b - a > melhor[2] - melhor[1]):
                    melhor = (fontes[fid], round(a, 2), round(b, 2))
    return melhor
