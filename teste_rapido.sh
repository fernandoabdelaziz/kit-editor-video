#!/usr/bin/env bash
# Teste rápido do kit-editor: gera um clipe sintético (ffmpeg testsrc2 + tom), uma transcrição falsa e roda
# compacta > rascunho > renderizar (prévia com legenda) > conferir > motion (só o projeto HTML, ou o render
# completo com --completo). Tudo vai para <raiz>/trabalho/_teste_kit_<data>/ e brutos/_teste_kit/. Não apaga nada.
#   KIT_RAIZ=/caminho/da/raiz bash teste_rapido.sh [--completo]
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETO=0; [ "${1:-}" = "--completo" ] && COMPLETO=1
KIT="python3 $REPO/kit.py"
RAIZ="$(python3 -c "import sys; sys.path.insert(0, '$REPO'); from kitlib.comum import RAIZ; print(RAIZ)")"
T="_teste_kit_$(date +%Y%m%d_%H%M%S)"
W="$RAIZ/trabalho/$T"
B="$RAIZ/brutos/_teste_kit"
echo "raiz: $RAIZ   tema de teste: $T"
mkdir -p "$W/transcricoes" "$B"

# 1) clipe sintético de 6 s, 1080x1920, com áudio (tom 220 Hz com pausas)
CLIPE="$B/clipe_${T}.mp4"
ffmpeg -v error -n -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=6" \
  -f lavfi -i "sine=frequency=220:sample_rate=48000:duration=6,volume='if(between(mod(t,1.5),1.2,1.5),0,0.3)':eval=frame" \
  -c:v libx264 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a aac -shortest "$CLIPE"

# 2) transcrição falsa (o formato que o transcrever_whisper.py grava)
python3 - "$CLIPE" "$W/transcricoes/clipe.json" <<'PY'
import json, sys
fonte, dest = sys.argv[1], sys.argv[2]
frase = "este é um teste rápido do kit de edição com legenda palavra por palavra e tudo local".split()
pal, t = [], 0.3
for w in frase:
    pal.append(dict(w=w, s=round(t, 3), e=round(t + 0.28, 3), p=0.99)); t += 0.34
json.dump(dict(fonte=fonte, sha256="teste", modelo="falso", idioma="pt", duracao=6.0, piso_ruido_db=-60,
               prompt="", segmentos=[dict(s=0.3, e=round(t, 3), texto=" ".join(frase))], palavras=pal, gaps=[]),
          open(dest, "w"), ensure_ascii=False, indent=1)
PY

cd "$RAIZ"
export KIT_RAIZ="$RAIZ"
echo; echo "== compacta";   $KIT compacta --tema "$T"
echo; echo "== rascunho";   $KIT rascunho --tema "$T" | tail -n 4
echo; echo "== renderizar (prévia, legenda caixa-d)"
$KIT renderizar "trabalho/$T/edl_rascunho.json" --formato reels --saida "trabalho/$T/teste_previa.mp4" --legenda caixa-d --previa
ls -la "$W"/teste_previa*.mp4
echo; echo "== conferir"; $KIT conferir "trabalho/$T/teste_previa.mp4" || echo "(o conferir apontou itens; com clipe sintético isso pode acontecer)"
cat > "$W/motion_spec.json" <<JSON
{"formato": "reels", "paleta": "verde-bege", "edl": "trabalho/$T/edl_rascunho.json",
 "efeitos": [{"efeito": "titulo-cinetico", "texto": "teste rápido do kit", "sincronizar": true, "posicao": "terco-superior"}]}
JSON
if [ "$COMPLETO" = 1 ]; then
  echo; echo "== motion (render completo HyperFrames + silhueta)"
  $KIT motion "trabalho/$T/motion_spec.json" --saida "trabalho/$T/motion_teste.mov" --base "trabalho/$T/teste_previa_sem-legenda.mp4"
  ls -la "$W"/motion_teste.mov
else
  echo; echo "== motion --so-projeto (HTML + lint do HyperFrames)"
  $KIT motion "trabalho/$T/motion_spec.json" --saida "trabalho/$T/motion_teste.mov" --so-projeto
fi
echo; echo "TESTE RÁPIDO OK: $W"
