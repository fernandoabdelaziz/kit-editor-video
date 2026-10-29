# NOTICE: origem das ideias e do código do kit-editor

O código do kit-editor é próprio e sai sob a licença MIT (arquivo `LICENSE`). Abaixo estão as fontes de ideias e de
valores adaptados, com a licença de cada uma. Nenhum código foi copiado de repositório sem licença.

## Adaptado de projetos MIT (com atribuição)

- **ffmpeg-skill**, © 2026 kajisho5, licença MIT (https://github.com/kajisho5/ffmpeg-skill, commit 5ebe34b).
  - Presets `ffs-varredura`, `ffs-palavra-ativa` e `ffs-faixa`. Reproduzem os modos do `scripts/caption.py`: `--karaoke` com varredura `\kf`, `--animate pop` (tags `\fad(80,120)\fscx60…\t(…110)\t(…100)`), `--karaoke-style word` (ativa 112%, futuras `#B4B4B4`, destaque `#FFD200`) e `--box`.
  - Regra de "não fechar a linha em artigo/preposição", inspirada no `--wrap phrase`.
  - O `scripts/check.py` é chamado tal como está (só lê o arquivo) dentro do `kit.py conferir`, se estiver instalado. Ele não vem neste repositório; o `install.sh` baixa o projeto original (opcional).
- **video-use**, © 2026 Browser Use, licença MIT (https://github.com/browser-use/video-use, commit 43cfc56).
  - Ideias reescritas, sem cópia de código:
    - transcrição compacta em frases com `[início-fim]` (takes_packed)
    - EDL em JSON
    - trechos extraídos um a um, fades de áudio de 30 ms em cada corte, legenda queimada por último
    - tempos de palavra levados para a linha do tempo da saída
    - autochecagem do vídeo renderizado em cada corte (tira de quadros + forma de onda)
    - memória `project.md`
    - aprovação do plano antes de renderizar
  - Presets `vu-caixa-alta` (estilo bold-overlay do `helpers/render.py`: 2 palavras, MAIÚSCULAS, contorno 2, MarginV 90/288) e `vu-frase` (estilo "natural-sentence" descrito no SKILL.md).
- **claude-video-skills**, © 2026 Tamil Iniyan, licença MIT (https://github.com/imtamiliniyan/claude-video-skills). Presets `cvs-shorts` e `cvs-cartao` e paleta `azul-eletrico`, a partir dos valores de `.claude/skills/video-edit/remotion/src/templates/Captions.tsx`:
  - até 3 palavras em MAIÚSCULAS, Space Grotesk 800, sombra pesada em 3 camadas
  - palavra viva acesa na cor de destaque `#2563EB`
  - entrada fade + subida de 14 px + desfoque que some, em 0,18 s
  - cartão `rgba(15,18,26,.78)`
- **claude-code-video-editing** (vyn-store/"KVK", https://github.com/vyn-store/claude-code-video-editing), licença MIT declarada no README ("MIT. Take it, use it, fork it"). Preset `kvk-pilula` e paleta `vidro-amarelo`, a partir de `KaraokeSubtitle.tsx` e `MOTION_PHILOSOPHY.md`:
  - pílula `rgba(8,10,14,.82)` com borda branca de 12% e raio 16
  - palavra ativa numa caixa amarela de raio 10 com texto escuro
  - palavras já ditas a 62%
- **video-alchemy**, © 2026 Bootoshi, licença MIT (https://github.com/kingbootoshi/video-alchemy). Preset `alchemy-paginas` e paleta `laranja`, a partir de `remotion-template/src/Main.tsx`:
  - páginas de 1.400 ms
  - peso 800, sombra pesada
  - palavra ativa `#FF9F1C` até a próxima
  - o conceito de "páginas" de legenda vem do `@remotion/captions`; aqui ele foi reimplementado em Python, sem código do Remotion.
- **ai-motion-library** (versão documental), © 2026 Douglas Januário, licença MIT (https://github.com/apenasdouglas/ai-motion-library).
  - Presets `doc-revelar` (word reveal + fade in), `doc-sublinhado` (highlight com sublinhado crescendo da esquerda, 0,4 s) e a mecânica de revelar usada no `revelar-chave`.
  - Vocabulário de motion do `KIT.md`.
- **awesome-opus5-5-videos** (© 2026 yihui-dev, https://github.com/yihui-dev/awesome-opus5-5-videos) e **ai-design-skills** (© 2026 Elaya, https://github.com/elayadesign/ai-design-skills, design-to-motion), licença MIT: ideias da biblioteca de 17 aberturas, gráficos e fechamentos (`kitlib/motion_graficos.py`), reescritas do zero; lidos só como texto.
- **gsap-skills** (greensock), licença MIT: guia oficial do GSAP, lido e resumido no `KIT.md`.

## Ferramentas usadas, mas não incluídas neste repositório

O `install.sh` baixa cada uma da fonte original. Nada disso é redistribuído aqui.

- **HyperFrames** (HeyGen, Apache-2.0), npm `hyperframes@0.8.185`. O kit só gera HTML e chama o CLI pelo `hyperframes-run/hf.sh`; `kitlib/motion.py` é código próprio.
- **GSAP 3.15.0** (Webflow/GreenSock), "Standard no-charge license" (https://gsap.com/standard-license). Uso comercial gratuito permitido; não é licença open source. Baixado do npm pelo `install.sh` (não vem no repositório).
- **Node.js** v22.21.1 (MIT), tarball oficial de nodejs.org.
- **faster-whisper** (SYSTRAN, MIT) e o modelo Whisper `medium` convertido (`Systran/faster-whisper-medium`, MIT), baixado na primeira transcrição.
- **MediaPipe** (Google, Apache-2.0), pacote `mediapipe` 1.1.1 no `.venv-pessoa`, e o modelo público `selfie_segmenter.tflite` (float16, versão 1, `storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/`, sha256 `191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b`, Apache-2.0 conforme o model card). Roda só local.
- **rnnoise-models** (GregorR), modelo `cb.rnnn` (conjoined-burgers), usado pelo filtro `arnndn` do ffmpeg no perfil de áudio "rua". O README do repositório declara que os modelos não são obra criativa e não estão sujeitos a direito autoral. sha256 `f1357c4e5be9dee8467bead486dfced2d75b640c26ad0b594fa7f102322371d9`.
- **ffmpeg** (LGPL/GPL, conforme a compilação da sua distribuição), usado como programa externo.

## Incluído neste repositório com licença própria

- **Inter** (Rasmus Andersson, SIL Open Font License 1.1): `motion/fontes/Inter-Variable.ttf`, licença em `motion/fontes/OFL-inter.txt`.

## Próprio do kit

- Presets `caixa-d`, `caixa-caminha`, `marca-texto-b`, `caixa-marinho` e `revelar-chave`.
- Paletas `verde-bege`, `classico`, `moderno`, `dourado`, `marinho` e `preto-branco`.
- Cadeia de voz (`kitlib/audio_voz.py`), tone mapping HDR, verificação de silhueta (`kitlib/pessoa.py`, `pessoa_seg.py`) e o resto do `kitlib/`.

## Texto da licença MIT (vale para os itens MIT acima)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright
notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.
