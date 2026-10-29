#!/usr/bin/env bash
# Wrapper do HyperFrames local (npm hyperframes@0.8.185, versão fixa no package-lock.json).
# Telemetria, update check, auto-update e auto-instalação de skills DESLIGADOS. HOME isolado.
# Sem rede por padrão (unshare -rn, só loopback). HF_REDE=1 desliga o isolamento (ex.: o sistema não permite
# user namespaces sem root); use só se souber o que está fazendo.
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$AQUI/node/bin:$PATH"
export HOME="$AQUI/home" XDG_STATE_HOME="$AQUI/home/.local/state" XDG_CONFIG_HOME="$AQUI/home/.config" XDG_CACHE_HOME="$AQUI/home/.cache"
export npm_config_cache="$AQUI/npm-cache" npm_config_update_notifier=false
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_NO_UPDATE_CHECK=1 HYPERFRAMES_NO_AUTO_INSTALL=1 HYPERFRAMES_SKIP_SKILLS=1 HYPERFRAMES_NO_OPTIONAL_INSTALL=1
if [ -z "${HYPERFRAMES_BROWSER_PATH:-}" ]; then
  for c in /usr/bin/google-chrome /usr/bin/google-chrome-stable /usr/bin/chromium /usr/bin/chromium-browser; do
    if [ -x "$c" ]; then HYPERFRAMES_BROWSER_PATH="$c"; break; fi
  done
fi
export HYPERFRAMES_BROWSER_PATH="${HYPERFRAMES_BROWSER_PATH:-/usr/bin/google-chrome}"
unset HEYGEN_API_KEY HYPERFRAMES_API_KEY ELEVENLABS_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY GOOGLE_API_KEY FIGMA_TOKEN
case "${1:-}" in
  cloud|lambda|cloudrun|publish|auth|usage|feedback|events|upgrade|skills|add|catalog|tts|media-use|capture|figma|catch-up|init)
    echo "hf.sh: o comando '$1' está bloqueado no kit-editor (nuvem/conta/rede/instalação)." >&2; exit 2;;
esac
CLI="$AQUI/node_modules/hyperframes/bin/hyperframes.mjs"
if [ "${HF_REDE:-0}" = "1" ]; then exec node "$CLI" "$@"; fi
exec unshare -rn sh -c 'ip link set lo up && exec node "$0" "$@"' "$CLI" "$@"
