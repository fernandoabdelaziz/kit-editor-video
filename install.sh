#!/usr/bin/env bash
# Instalação do kit-editor numa máquina Ubuntu/Debian nova. Pode rodar de novo quantas vezes quiser:
# o que já está instalado e conferido é pulado.
#
#   ./install.sh [--raiz DIR] [opções]
#
# Opções:
#   --raiz DIR          pasta de trabalho (brutos/, trabalho/, editados/, ferramentas/, .venv-*). Também: KIT_RAIZ=DIR.
#                       Padrão: se este repositório estiver em <algo>/ferramentas/kit-editor, usa <algo>; senão ~/videos.
#   --sem-sistema       não roda apt-get (use se os pacotes do sistema já estiverem instalados ou se não tiver sudo)
#   --sem-whisper       não cria o .venv-whisper (transcrição)
#   --sem-pessoa        não cria o .venv-pessoa nem baixa o modelo da silhueta
#   --sem-motion        não instala Node/HyperFrames/GSAP (motion graphics)
#   --com-ffmpeg-skill  também baixa o ffmpeg-skill (MIT) para o check.py opcional do `kit.py conferir`
#   --baixar-whisper    já baixa o modelo Whisper "medium" (~1,5 GB); senão ele baixa na 1ª transcrição
#   --simular           só mostra o que faria, sem mudar nada
#   --teste             no fim, roda o teste rápido (teste_rapido.sh)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_VER="22.21.1"
HF_VER="0.8.185"
GSAP_VER="3.15.0"
GSAP_SHA="92bb9a96476f983d212a2bc4f54c889039c1696dd4461d40a736860938570fbb"   # dist/gsap.min.js do gsap@3.15.0
FASTER_WHISPER_VER="1.2.1"
AV_VER="15.1.0"   # PyAV 19 quebra o faster-whisper 1.2.1 (open() sem metadata_errors)
MEDIAPIPE_VER="1.1.1"
SELFIE_URL="https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite"
SELFIE_SHA="191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b"
RNN_URL="https://raw.githubusercontent.com/GregorR/rnnoise-models/master/conjoined-burgers-2018-08-28/cb.rnnn"
RNN_SHA="f1357c4e5be9dee8467bead486dfced2d75b640c26ad0b594fa7f102322371d9"
FFS_URL="https://github.com/kajisho5/ffmpeg-skill.git"
FFS_COMMIT="5ebe34b0bbc11d7e87464b081e2b8c46c3316346"

RAIZ="${KIT_RAIZ:-}"; SISTEMA=1; WHISPER=1; PESSOA=1; MOTION=1; FFS=0; BAIXAR_WHISPER=0; SIMULAR=0; TESTE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --raiz) RAIZ="$2"; shift 2;;
    --sem-sistema) SISTEMA=0; shift;;
    --sem-whisper) WHISPER=0; shift;;
    --sem-pessoa) PESSOA=0; shift;;
    --sem-motion) MOTION=0; shift;;
    --com-ffmpeg-skill) FFS=1; shift;;
    --baixar-whisper) BAIXAR_WHISPER=1; shift;;
    --simular) SIMULAR=1; shift;;
    --teste) TESTE=1; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) echo "opção desconhecida: $1 (veja --help)" >&2; exit 2;;
  esac
done
if [ -z "$RAIZ" ]; then
  if [ "$(basename "$(dirname "$REPO")")" = "ferramentas" ]; then RAIZ="$(dirname "$(dirname "$REPO")")"; else RAIZ="$HOME/videos"; fi
fi
case "$RAIZ" in /*) ;; *) RAIZ="$PWD/$RAIZ";; esac
FERR="$RAIZ/ferramentas"
HFD="$FERR/hyperframes-run"

passo() { printf '\n== %s\n' "$*"; }
ok() { printf '   ok: %s\n' "$*"; }
faz() {  # executa (ou só mostra, com --simular)
  if [ "$SIMULAR" = 1 ]; then printf '   [simular] %s\n' "$*"; else "$@"; fi
}
sha_ok() { [ -f "$1" ] && [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ]; }
baixar() {  # baixar URL DESTINO SHA256
  local url="$1" dest="$2" sha="$3"
  if sha_ok "$dest" "$sha"; then ok "$(basename "$dest") já baixado e conferido"; return; fi
  faz mkdir -p "$(dirname "$dest")"
  faz curl -fsSL --retry 3 -o "$dest.part" "$url"
  if [ "$SIMULAR" = 1 ]; then return; fi
  if ! sha_ok "$dest.part" "$sha"; then rm -f "$dest.part"; echo "ERRO: sha256 de $url não confere" >&2; exit 1; fi
  mv "$dest.part" "$dest"; ok "$(basename "$dest") baixado, sha256 conferido"
}

echo "kit-editor: instalação"
echo "   repositório: $REPO"
echo "   raiz de trabalho: $RAIZ"
[ "$SIMULAR" = 1 ] && echo "   modo --simular: nada será alterado"

# 1) pacotes do sistema
if [ "$SISTEMA" = 1 ]; then
  passo "pacotes do sistema (apt-get)"
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  PKGS="ffmpeg python3 python3-venv python3-pip python3-numpy python3-pil fontconfig fonts-dejavu-core curl ca-certificates xz-utils iproute2 util-linux git"
  faz $SUDO apt-get update
  faz $SUDO apt-get install -y $PKGS
  if [ "$MOTION" = 1 ] && ! command -v google-chrome >/dev/null && ! command -v chromium >/dev/null; then
    . /etc/os-release 2>/dev/null || true
    if [ "${ID:-}" = "debian" ]; then
      faz $SUDO apt-get install -y chromium
    elif [ "$(dpkg --print-architecture 2>/dev/null)" = "amd64" ]; then
      # Ubuntu: o pacote chromium é snap; o .deb oficial do Google Chrome funciona melhor em modo headless
      faz curl -fsSL -o /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
      faz $SUDO apt-get install -y /tmp/google-chrome.deb
    else
      echo "   aviso: instale um Chrome/Chromium e exporte HYPERFRAMES_BROWSER_PATH=/caminho/do/navegador" >&2
    fi
  fi
else
  passo "pacotes do sistema: pulado (--sem-sistema)"
fi
for c in ffmpeg ffprobe python3 curl sha256sum; do
  command -v "$c" >/dev/null || { [ "$SIMULAR" = 1 ] && echo "   aviso: falta $c" || { echo "ERRO: falta o comando $c" >&2; exit 1; }; }
done
python3 -c 'import numpy, PIL' 2>/dev/null || echo "   aviso: o python3 do sistema precisa de numpy e Pillow (apt: python3-numpy python3-pil)" >&2

# 2) pastas
passo "pastas em $RAIZ"
faz mkdir -p "$RAIZ/brutos" "$RAIZ/trabalho" "$RAIZ/editados" "$FERR"
ok "brutos/ (só leitura para o kit), trabalho/, editados/, ferramentas/"
if [ "$REPO" != "$FERR/kit-editor" ]; then
  if [ -e "$FERR/kit-editor" ] && [ "$(readlink -f "$FERR/kit-editor")" != "$REPO" ]; then
    echo "   aviso: $FERR/kit-editor já existe e aponta para outro lugar; não mexi" >&2
  elif [ ! -e "$FERR/kit-editor" ]; then
    faz ln -s "$REPO" "$FERR/kit-editor"; ok "link $FERR/kit-editor -> $REPO"
  fi
fi
if [ "$SIMULAR" = 0 ]; then printf '%s\n' "$RAIZ" > "$REPO/raiz.txt"; fi
ok "raiz.txt grava a raiz para o kit.py (a variável KIT_RAIZ continua valendo por cima)"

# 3) fonte Inter (para o libass, que queima a legenda)
passo "fonte Inter"
FD="$HOME/.local/share/fonts"
if [ -f "$FD/Inter-Variable.ttf" ] && cmp -s "$FD/Inter-Variable.ttf" "$REPO/motion/fontes/Inter-Variable.ttf"; then ok "já instalada"
else faz mkdir -p "$FD"; faz cp "$REPO/motion/fontes/Inter-Variable.ttf" "$REPO/motion/fontes/OFL-inter.txt" "$FD/"; command -v fc-cache >/dev/null && faz fc-cache -f "$FD" >/dev/null; ok "copiada para $FD"; fi

# 4) transcrição: .venv-whisper com faster-whisper
if [ "$WHISPER" = 1 ]; then
  passo ".venv-whisper (faster-whisper $FASTER_WHISPER_VER)"
  V="$RAIZ/.venv-whisper"
  if [ -x "$V/bin/python" ] && "$V/bin/python" -c "import faster_whisper, av, sys; sys.exit(faster_whisper.__version__ != '$FASTER_WHISPER_VER' or av.__version__ != '$AV_VER')" 2>/dev/null; then ok "já instalado"
  else faz python3 -m venv "$V"; faz "$V/bin/python" -m pip install -q --upgrade pip; faz "$V/bin/python" -m pip install -q "faster-whisper==$FASTER_WHISPER_VER" "av==$AV_VER"; ok "instalado"; fi
  faz mkdir -p "$RAIZ/.modelos-whisper"
  if [ "$BAIXAR_WHISPER" = 1 ]; then
    faz "$V/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8', download_root='$RAIZ/.modelos-whisper')"
    ok "modelo medium em .modelos-whisper/"
  else ok "o modelo Whisper medium (~1,5 GB) baixa sozinho na 1ª transcrição, em .modelos-whisper/"; fi
fi

# 5) silhueta: .venv-pessoa com MediaPipe + modelo selfie_segmenter
if [ "$PESSOA" = 1 ]; then
  passo ".venv-pessoa (mediapipe $MEDIAPIPE_VER) e modelo selfie_segmenter"
  V="$RAIZ/.venv-pessoa"
  if [ -x "$V/bin/python" ] && "$V/bin/python" -c "import mediapipe, cv2, numpy" 2>/dev/null; then ok "já instalado"
  else faz python3 -m venv "$V"; faz "$V/bin/python" -m pip install -q --upgrade pip; faz "$V/bin/python" -m pip install -q "mediapipe==$MEDIAPIPE_VER" opencv-python-headless numpy; ok "instalado"; fi
  baixar "$SELFIE_URL" "$RAIZ/.modelos-pessoa/selfie_segmenter.tflite" "$SELFIE_SHA"
fi

# 6) áudio: modelo rnnoise do perfil "rua"
passo "modelo de ruído (rnnoise cb.rnnn, perfil de áudio 'rua')"
baixar "$RNN_URL" "$FERR/modelos-ruido/cb.rnnn" "$RNN_SHA"

# 7) motion: Node local + HyperFrames + GSAP
if [ "$MOTION" = 1 ]; then
  passo "hyperframes-run (Node $NODE_VER local, hyperframes@$HF_VER, gsap@$GSAP_VER)"
  faz mkdir -p "$HFD/home/.hyperframes" "$HFD/vendor/gsap-$GSAP_VER" "$HFD/npm-cache"
  for f in hf.sh package.json package-lock.json rede-log.cjs LEIA-ME.md; do
    if ! cmp -s "$REPO/hyperframes-run/$f" "$HFD/$f" 2>/dev/null; then faz cp "$REPO/hyperframes-run/$f" "$HFD/$f"; fi
  done
  faz chmod +x "$HFD/hf.sh"
  [ -f "$HFD/home/.hyperframes/config.json" ] || { [ "$SIMULAR" = 1 ] || printf '{\n  "telemetryEnabled": false\n}\n' > "$HFD/home/.hyperframes/config.json"; }
  case "$(uname -m)" in x86_64) NARCH=x64;; aarch64|arm64) NARCH=arm64;; *) echo "ERRO: arquitetura $(uname -m) sem Node oficial" >&2; exit 1;; esac
  if [ -x "$HFD/node/bin/node" ] && [ "$("$HFD/node/bin/node" --version)" = "v$NODE_VER" ]; then ok "Node v$NODE_VER já instalado"
  else
    TB="node-v$NODE_VER-linux-$NARCH.tar.xz"
    if [ "$SIMULAR" = 1 ]; then echo "   [simular] baixar $TB + SHASUMS256.txt, conferir sha256 e extrair em $HFD/node"
    else
      T="$(mktemp -d)"
      curl -fsSL --retry 3 -o "$T/SHASUMS256.txt" "https://nodejs.org/dist/v$NODE_VER/SHASUMS256.txt"
      curl -fsSL --retry 3 -o "$T/$TB" "https://nodejs.org/dist/v$NODE_VER/$TB"
      (cd "$T" && grep " $TB\$" SHASUMS256.txt | sha256sum -c --quiet -) || { echo "ERRO: sha256 do Node não confere" >&2; exit 1; }
      rm -rf "$HFD/node"; mkdir -p "$HFD/node"; tar -xJf "$T/$TB" -C "$HFD/node" --strip-components=1; rm -rf "$T"
      ok "Node v$NODE_VER em $HFD/node (sha256 conferido)"
    fi
  fi
  NPM_ENV=(env "PATH=$HFD/node/bin:$PATH" "HOME=$HFD/home" "npm_config_cache=$HFD/npm-cache" npm_config_update_notifier=false npm_config_fund=false npm_config_audit=false)
  if [ -f "$HFD/node_modules/hyperframes/package.json" ] && grep -q "\"version\": \"$HF_VER\"" "$HFD/node_modules/hyperframes/package.json"; then ok "hyperframes@$HF_VER já instalado"
  else
    if [ "$SIMULAR" = 1 ]; then echo "   [simular] (cd $HFD && npm ci --ignore-scripts)"
    else (cd "$HFD" && "${NPM_ENV[@]}" npm ci --ignore-scripts --no-audit --no-fund >/dev/null); ok "hyperframes@$HF_VER instalado (npm ci --ignore-scripts)"; fi
  fi
  GD="$HFD/vendor/gsap-$GSAP_VER"
  if sha_ok "$GD/gsap.min.js" "$GSAP_SHA" && [ -f "$GD/SplitText.min.js" ]; then ok "gsap@$GSAP_VER já no vendor"
  else
    if [ "$SIMULAR" = 1 ]; then echo "   [simular] npm pack gsap@$GSAP_VER, copiar dist/*.min.js para $GD"
    else
      T="$(mktemp -d)"
      (cd "$T" && "${NPM_ENV[@]}" npm pack --silent "gsap@$GSAP_VER" >/dev/null 2>&1 && tar -xzf "gsap-$GSAP_VER.tgz")
      for f in gsap CustomEase DrawSVGPlugin SplitText MotionPathPlugin MorphSVGPlugin Flip; do cp "$T/package/dist/$f.min.js" "$GD/"; done
      cp "$T/package/package.json" "$GD/"
      rm -rf "$T"
      sha_ok "$GD/gsap.min.js" "$GSAP_SHA" || { echo "ERRO: sha256 do gsap.min.js não confere" >&2; exit 1; }
      ok "gsap@$GSAP_VER em $GD (licença: https://gsap.com/standard-license)"
    fi
  fi
  if [ "$SIMULAR" = 0 ]; then
    if unshare -rn sh -c 'ip link set lo up' 2>/dev/null; then ok "isolamento de rede (unshare -rn) funciona"
    else echo "   aviso: 'unshare -rn' não funciona aqui (user namespaces bloqueados). Veja 'Problemas comuns' no README.md" >&2; fi
  fi
fi

# 8) opcional: ffmpeg-skill (check.py do kit.py conferir)
if [ "$FFS" = 1 ]; then
  passo "ffmpeg-skill (MIT, commit ${FFS_COMMIT:0:7}) para o check.py opcional"
  if [ -d "$FERR/ffmpeg-skill/.git" ]; then ok "já clonado"
  else faz git clone -q "$FFS_URL" "$FERR/ffmpeg-skill"; fi
  faz git -C "$FERR/ffmpeg-skill" -c advice.detachedHead=false checkout -q "$FFS_COMMIT"
  [ -x "$RAIZ/.venv-ffmpeg-skill/bin/python" ] || faz python3 -m venv "$RAIZ/.venv-ffmpeg-skill"
  ok "ffmpeg-skill em $FERR/ffmpeg-skill"
fi

passo "pronto"
echo "   teste rápido:   KIT_RAIZ=\"$RAIZ\" bash \"$REPO/teste_rapido.sh\""
echo "   uso:            cd \"$RAIZ\" && python3 ferramentas/kit-editor/kit.py --help"
if [ "$TESTE" = 1 ] && [ "$SIMULAR" = 0 ]; then KIT_RAIZ="$RAIZ" bash "$REPO/teste_rapido.sh"; fi
