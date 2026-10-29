# kit-editor: roteiro de edição

Este é o fluxo principal para cada vídeo novo. Ele junta ideias do ffmpeg-skill, as ideias de método do video-use (reescritas, sem nuvem) e os padrões próprios do kit. Tudo roda local: ffmpeg + Python stdlib, transcrição com faster-whisper no `.venv-whisper` e silhueta com MediaPipe no `.venv-pessoa`. Não usa chave paga nem nuvem. A instalação está no `README.md`.

Rode tudo da raiz de trabalho (a pasta com `brutos/`, `trabalho/`, `editados/`; troque com a variável `KIT_RAIZ`):

    python3 ferramentas/kit-editor/kit.py <comando> --help

**Hierarquia:** as instruções de quem aparece no vídeo > este KIT.md > defaults do kit.

## Regras que o kit já aplica (e você não pode contornar)

- `brutos/` é só leitura. O kit recusa qualquer saída lá, só escreve em `trabalho/`, `editados/` ou `/tmp`, e **nunca sobrescreve** (use um nome ou versão nova).
- **Portão de aprovação:** `renderizar` para `editados/` só roda se a EDL tiver `aprovacao`, registrada com `kit.py aprovar` depois do OK explícito de quem aparece no vídeo. Prévias vão para `trabalho/` com `--previa`.
- Toda entrega sai em dupla: `<nome>.mp4` (com legenda) e `<nome>_sem-legenda.mp4` (o texto de tela continua). Também sai um `.srt`.
- Padrões técnicos fixos:
  - Tone mapping HDR (HLG/PQ → bt709, com `eq=saturation=0.92`).
  - 30 fps, cor marcada como bt709, H.264 CRF 18 e AAC 192k.
  - Fades de áudio de 30 ms em cada corte.
  - Cadeia de voz padrão (`kitlib/audio_voz.py`; perfil `rua` para gravação sem microfone, com ruído forte), com loudnorm em 2 passadas: -14 LUFS e TP -1,5, que fecha ≤ -1 dBTP.
  - Legenda queimada **por último**, depois dos títulos.
- **Nada sobre o apresentador (regra permanente).** Nenhum overlay (ficha, etiqueta, lower third,
  cartão, título de motion) pode cobrir qualquer parte da pessoa no vídeo: rosto, cabeça, corpo, braços, mãos.
  - Elementos pequenos (fichas, etiquetas, lower third) só em espaço livre: fundo, mesa, ao lado da pessoa.
  - Cartão grande (documento, datilografado) nunca vai sobre ela. Use um **recorte** (cutaway): fundo neutro da paleta em
    tela cheia com o cartão centrado, `"recorte": true` no `cartao-documento`, enquanto a voz continua (sensação de L-cut),
    com corte seco de ida e de volta. A outra saída é encolher o cartão até caber no espaço livre.
  - Conferência automática: `kitlib/pessoa.py` segmenta a silhueta da pessoa quadro a quadro no vídeo-base sem overlays. Usa
    MediaPipe `selfie_segmenter` local, no `.venv-pessoa` da raiz, com o modelo em `.modelos-pessoa/` (sha256
    `191ac952…658b`). Por padrão fica com a maior mancha, fecha buracos e dilata 28 px de margem. Depois cruza a silhueta
    com o alfa de cada overlay, a cada 4 quadros e nas bordas de entrada e saída. Se passar de 96 px de interseção, o
    overlay é **reprovado**. Quadro com overlay cobrindo ≥ 98% da tela conta como recorte e passa.
    - `kit.py motion … --base VIDEO_SEM_OVERLAY` confere já na geração. Sem `--base`, só avisa.
    - `kit.py renderizar --overlays` sempre confere e **recusa** a entrega se houver colisão. O PNG de diagnóstico fica em
      `<saida>_tmp/silhueta/`.
    - `kit.py conferir` refaz a conferência ("overlay fora do apresentador") e salva o PNG da silhueta na pasta da conferência.
  - O reflexo da pessoa numa mesa brilhante conta como parte dela quando encosta no corpo. Por isso o espaço livre
    típico é o fundo acima da cabeça (fichas e etiqueta de nome no topo). Se o punch-in subir demais a cabeça, use
    `enquadramento.<fonte>.foco_y_zoom` menor (ex.: 0,25) ou encurte o elemento.

## Passo a passo por vídeo

1. **Inventário e memória.** `kit.py projeto --tema T` cria `trabalho/T/projeto.md`. Se já existir, leia e resuma a última sessão numa frase. Rode `ffprobe` nos brutos (duração, HDR, rotação).
2. **Transcrever local:**

       kit.py transcrever --tema T --termos "nomes próprios, siglas, termos técnicos" brutos/<arquivos>.mov

   - Gera `trabalho/T/transcricoes/*.json`, com palavra a palavra e confiança, em cache por sha256.
   - Gera também `trabalho/T/transcricao_compacta.md`: frases com `[início-fim]` e alertas.
     - ⟦muleta⟧, ⟦…?⟧ (talvez), ⟦rep⟧, ⟦falso⟧
     - `?` = baixa confiança
     - ⟨pausa⟩ e ⟨voz sem palavra⟩ (provável "é…" que o whisper omitiu)
   - **Leia a compacta, não o JSON.**
   - Corrija erros de transcrição na EDL (`correcoes`), nunca inventando fala.
3. **Propor o corte:**
   - `kit.py rascunho --tema T [--ordem b1,b2,...] [--pausa 0.35]` gera `trabalho/T/edl_rascunho.json`. Ele corta pausas acima do limite, muletas fortes, repetições, falsos começos e retomadas. "Talvez" (né, tipo, e, assim…) só é sinalizado; `--tirar-talvez` corta também.
   - Ajuste a EDL com critério:
     - ordem e escolha de takes
     - nunca cortar ressalva técnica
     - hook nos 3-4 primeiros segundos
     - `zooms` e `transicao` (dissolve)
     - `enquadramento` por fonte (`foco_x`, `foco_y`)
     - `ruido` (silêncio do bruto para o perfil de ruído; se faltar, o kit procura um sozinho)
     - `correcoes`
   - Mostre a quem aparece no vídeo `kit.py plano <edl>` em português simples (trechos, o que sai e por quê, duração) **e espere**.
4. **Escolher o visual (se a pessoa não disse):**
   - Pergunte qual **legenda** (preset) e qual **paleta**.
   - Para ajudar, gere o mostruário do vídeo atual com `kit.py mostruario` (quadro inteiro, faixa da legenda a 50% e, com `--mp4`, um trecho em vídeo).
   - Registre a escolha no `projeto.md`. Não presuma um estilo para vídeo novo sem confirmar.
5. **Aprovação:** quando a pessoa aprovar o plano, rode `kit.py aprovar <edl> --como "<frase dela>" [--por "<nome>"]`.
6. **Render:**

       kit.py renderizar <edl> --formato reels|linkedin|paisagem --saida editados/AAAA-MM-DD_T_reels_1080x1920.mp4 \
              --legenda <preset> --paleta <paleta> [--titulos trabalho/T/titulos_9x16.ass] [--y 0.78]

   - Para iterar, use antes `--previa` com saída em `trabalho/T/`.
   - Para ajustar só a legenda, use `kit.py legendas ...`. Para fixar os grupos à mão, edite `legenda_<preset>_grupos.json` e passe `--grupos`.
7. **Autochecagem (antes de mostrar):** `kit.py conferir <video.mp4>` gera `<video>_conferir/relatorio.md`. Ele confere:
   - duração, resolução, fps, cor, codec, áudio
   - loudness (-14 ±1) e true peak (≤ -1)
   - quadro preto ou congelado
   - estalo em cada corte
   - legenda dentro da safe area
   - `check.py` do ffmpeg-skill (opcional; pulado se não estiver instalado)

   E gera os PNGs:
   - tira de quadros + forma de onda em cada corte
   - início e fim
   - 3 quadros inteiros

   **Abra 2-3 PNGs e olhe.** Você não ouve: reporte os números. Se falhar, corrija, renderize de novo e confira de novo, até 3 vezes. Depois disso, conte a quem pediu o vídeo o que sobrou.
8. **Entregar e registrar:**
   - Entregue a versão com legenda e a `_sem-legenda` e registre a entrega.
   - Acrescente a sessão em `trabalho/T/projeto.md`: decisões, EDL aprovada, versões, pendências.
   - Na entrega, nomeie cada efeito usado em português e em inglês.

## Biblioteca de legendas (`legendas/`)

A legenda e a paleta são **escolhas por vídeo**. Cada preset é um JSON em `legendas/presets/` com estes campos:
- fonte, tamanho, contorno, sombras
- caixa alta, pontuação
- regra de agrupamento
- destaque: `caixa` | `marca-texto` | `cor` | `sweep` | `revelar` | `sublinhado` | `nenhum`
- fundo do grupo, entrada e saída
- posição
- `paleta_padrao`

As cores se referem a papéis da paleta (`@texto`, `@caixa`…), então qualquer preset aceita qualquer paleta (`--paleta`). Para ver tudo: `kit.py presets` e `kit.py paletas`.

| preset | origem | visual em uma linha |
|---|---|---|
| `caixa-d` | próprio (variação D) | caixa arredondada atrás da palavra falada, deslizando 0,1 s; palavra-chave sozinha |
| `caixa-caminha` | próprio (variação A) | caixa dourada translúcida que caminha; palavra grifada em marinho |
| `marca-texto-b` | próprio (variação B) | marca-texto dourado que cresce e acumula da esquerda |
| `caixa-marinho` | próprio (variação C) | caixa marinho com contorno claro atrás da palavra |
| `ffs-varredura` | ffmpeg-skill | karaokê clássico: o amarelo varre a frase; entrada pop |
| `ffs-palavra-ativa` | ffmpeg-skill | palavra ativa amarela 12% maior; futuras em cinza |
| `ffs-faixa` | ffmpeg-skill | frase branca em faixa preta 50%, fade (legenda de TV) |
| `vu-caixa-alta` | video-use | 2 palavras em MAIÚSCULAS, branco com contorno grosso |
| `vu-frase` | video-use | frase natural de 4 a 7 palavras, sem destaque (documentário) |
| `cvs-shorts` | claude-video-skills | até 3 palavras em MAIÚSCULAS, sombra pesada, palavra viva acesa, entra subindo e ganhando foco |
| `cvs-cartao` | claude-video-skills | frase num cartão escuro translúcido; palavra viva acesa |
| `kvk-pilula` | claude-code-video-editing | pílula escura com borda; palavra ativa em caixa amarela; já ditas apagadas |
| `alchemy-paginas` | video-alchemy | blocos de ~1,4 s, sombra pesada, palavra mais recente em laranja |
| `doc-revelar` | ai-motion-library documental | cada palavra surge em fade no instante em que é dita (sóbrio) |
| `doc-sublinhado` | ai-motion-library documental | frase estática; sublinhado cresce sob a palavra dita (sóbrio) |
| `revelar-chave` | próprio (motor do doc-revelar) | palavras brancas surgem quando ditas; a palavra-chave ganha caixa da paleta |

Paletas: `verde-bege` (verde #1E3A2F / bege #E8DCC4 / #C9B895, o padrão), `classico`, `moderno`, `dourado`, `marinho`, `preto-branco`, `amarelo-tiktok`, `laranja`, `azul-eletrico`, `vidro-amarelo`.

Regras de legenda que valem para qualquer preset:
- Texto só com o que a pessoa fala.
- Grupo não atravessa corte.
- Grupo não termina em artigo ou preposição.
- Grupo largo demais é dividido.
- A base sobe sozinha se sair da safe area.
- Antes de entregar, confira no `_grupos.json` as palavras corrigidas e a separação dos grupos.

## Vocabulário de motion (pt / en) e quando usar

Referência: ai-motion-library, versão documental (MIT, ver NOTICE.md). Perfil sóbrio:
- no máximo 2 efeitos por elemento
- o efeito entra na palavra que ilustra
- saída com ~70% do tempo da entrada
- ease in-out ou ease-out, nunca linear
- **evitar** bounce, elastic, pop in e emoji (os presets com pop, `ffs-varredura`, só se a pessoa pedir)

| pt | en | quando | no kit |
|---|---|---|---|
| Corte seco | hard cut | padrão entre trechos | `"transicao": "corte"` |
| Dissolve curto | cross dissolve | troca de bloco ou assunto, 0,2-0,3 s | `"transicao": {"tipo": "dissolve", "dur": 0.25}` |
| Zoom sutil | punch zoom | ênfase na palavra mais forte (hook, número, decisão), 1,05-1,10x | `"zooms": [{"de","ate","escala","rampa"}]` |
| Palavra por palavra | word reveal | legenda sóbria, gancho | preset `doc-revelar` |
| Grifar | highlight | marcar termo-chave enquanto é dito | `caixa-d`, `marca-texto-b`, `doc-sublinhado` |
| Surgir | fade in | títulos de tela (0,4 s) | títulos .ass / entrada `fade` |
| Deslizar | slide in | entrada de título (40 px, ease-out) | entrada `slide` |
| Nome na tela | lower third | identificação no começo do vídeo | `kit.py motion` efeito `lower-third` |
| Título cinético | kinetic title | frase-chave palavra a palavra | `kit.py motion` efeito `titulo-cinetico` |
| Do borrado ao nítido | blur in | subtítulo, data | entrada `blur` / `subir-desfocar` |
| Contagem | count-up | número que importa (valor, prazo) | `kit.py motion` efeito `count-up` (só com dado falado) |
| Máquina de escrever + grifo | typewriter + highlight | citar trecho de decisão ou lei | `kit.py motion` efeito `typewriter-highlight` (texto exato da fala) |
| Cascata | stagger | listas e tópicos, 0,06-0,1 s entre itens | `kit.py motion` efeito `stagger-topicos` |
| Revelar por máscara | mask reveal | ano ou data | `kit.py motion` efeito `mask-reveal` |

## Motion graphics com HyperFrames local (`kit.py motion`)

Para texto animado sobre a imagem (lower third, número contando, frase datilografada, máscara, tópicos, título palavra a palavra).
Renderiza com o HyperFrames **instalado localmente** em `<raiz>/ferramentas/hyperframes-run/` (o `install.sh` monta) (npm 0.8.185 fixo, Node 22 local, Chrome do
sistema, GSAP e fonte Inter locais), com telemetria, checagem de update e auto-update desligados, chaves de API removidas e **sem
rede** (`unshare -n`). Nada vai para a HeyGen; não há render na nuvem.

1. `python3 ferramentas/kit-editor/kit.py efeitos` lista os efeitos:

| Efeito | Visual | Sincronia |
| --- | --- | --- |
| `lower-third` | cartão com barrinha de apoio, nome + cargo; slide 36 px + fade, linhas sobem de máscara | `inicio`/`duracao` |
| `count-up` | número conta até o valor dito (ex.: 19), resto da frase entra por máscara | número chega ao valor no fim da palavra falada |
| `typewriter-highlight` | frase datilografada; uma palavra ganha marca-texto (cor `destaque`) | cada palavra é datilografada quando é dita |
| `mask-reveal` | frase revelada por cortina da esquerda para a direita | do início ao fim da frase falada |
| `stagger-topicos` | tópicos com marcador entrando em sequência (fade + sobe 24 px) | cada tópico quando começa a ser dito |
| `titulo-cinetico` | título palavra a palavra (sobe 30 px e desfoca 6 px → 0) | cada palavra quando é dita |
| `chips-topo` | fichas de tópico (pílulas claras, sombra suave) no topo, acumulando; o grupo fica sempre centrado e desliza quando entra a próxima | cada ficha quando a palavra é dita (`itens`: str ou `{"texto","depois_de"}`), `fim` |
| `cartao-documento` | cartão claro tipo documento, sombra suave, sobe 70 px; cabeçalho pequeno opcional (`cabecalho`, partes separadas por " · ", também da fala); `linhas` explícitas fazem o cartão crescer linha a linha (nunca meio vazio); `recorte: true` = cutaway em tela cheia com corte seco | cada palavra datilografada quando é dita; marca-texto no `destaque` |

`lower-third` aceita `"uma_linha": true` + `"alinhar": "centro"`: vira uma etiqueta compacta "Nome · Cargo" que cabe no fundo
acima da cabeça. Zooms na EDL aceitam `rampa_entrada`/`rampa_saida` separadas: 0 é punch-in seco (jump cut) e > 1 s é push-in lento.

2. Escreva a spec (modelos em `motion/exemplos/`). Campos: `formato`, `paleta` (qualquer de `legendas/paletas.json`), `edl`
   (tempos das palavras), `efeitos[]` com `efeito`, `texto` (ou `itens`), `sincronizar: true` (ou a frase), `inicio`/`duracao`,
   `entrada` (s, padrão 0,5), `saida` (padrão 70% da entrada), `manter` (padrão 0,7 s após a última palavra),
   `posicao` (`terco-superior` | `centro` | `terco-inferior` | `{"x","y"}`), `alinhar`, `tamanho`, `ease` (padrão `power2.inOut`).
3. `python3 ferramentas/kit-editor/kit.py motion SPEC.json --saida trabalho/<tema>/motion_<nome>_v1.mov` gera:
   `<nome>_projeto/` (index.html, GSAP e fonte locais, `render.log`, `rede.log`), o overlay `.mov` (ProRes 4444 com alfa, 30 fps)
   e `.motion.json` (tempos de cada efeito, área ocupada a cada 0,25 s vs. safe area, conexões de rede; esperado "externas: 0").
   `--so-projeto` só gera o HTML (para olhar/ajustar antes de renderizar).
4. Prévia num vídeo pronto: `kit.py sobrepor VIDEO.mp4 --overlays X.mov --saida trabalho/<tema>/..._previa.mp4` (copia o áudio).
5. Entrega: `kit.py renderizar EDL ... --overlays X.mov [Y.mov]`. Ordem das camadas: vídeo → overlays → títulos `.ass` → legenda.
   O overlay entra também na `_sem-legenda` (é texto de tela).

Travas: o texto precisa estar na fala (confere contra a EDL); nome/cargo ou outro texto fora da fala só com
`"texto_aprovado": "<motivo>"`. Saídas só em `trabalho/`/`editados/`, sem sobrescrever. O `hf.sh` bloqueia `cloud`, `lambda`,
`cloudrun`, `publish`, `auth`, `usage`, `feedback`, `events`, `upgrade`, `skills`, `add`, `catalog`, `tts`, `media-use`, `capture`,
`figma`, `catch-up`, `init`. Tempo: ~50 s para 21,6 s de overlay 1080x1920 (render por screenshot, GPU por software).

## Biblioteca de aberturas e gráficos animados (17 opções)

Catálogo em `motion/biblioteca.json` (nome pt/en, serve, quando, duração e easing, comportamento, parâmetros, encaixe); implementação em `kitlib/motion_graficos.py` (`GraficosMixin`, acoplado ao `_Montador` por um bloco no fim de `kitlib/motion.py`; importar `motion` antes de `motion_graficos`).

- `kit.py presets` lista as legendas e a biblioteca; `kit.py biblioteca [--md]` só a biblioteca.
- Uso: campo `"efeito": "<id>"` no spec de `kit.py motion`. Exemplo com as 17: `motion/exemplos/biblioteca_aberturas_graficos.json`. Tabela completa: `kit.py biblioteca --md`.
- Ids: `palavra-revelada`, `numero-rolando`, `pergunta-resolve`, `titulo-reguas`, `afirmacao-corrigida` (aberturas); `barras-crescendo`, `linha-desenhando`, `linha-do-tempo-prazos`, `antes-depois`, `fluxo-etapas`, `contador-valor`, `checklist-cascata`, `destaque-de-lei`, `anel-percentual` (gráficos); `fecho-frase-regua`, `fecho-ficha-tema`, `fecho-tela-limpa` (fechamentos).
- Gráficos grandes: `recorte: true` por padrão (tela cheia, fundo neutro, push-in 1,03x, saída em corte seco; passa na verificação de silhueta). Pequenos: cartão da paleta no terço superior (`recorte: false`).
- `"exemplo": true` põe o selo "EXEMPLO · dados fictícios" e marca `exemplo` no `.motion.json`; `video.py renderizar` recusa overlay de exemplo em `editados/`.
- Fechamentos só da lista neutra ou com `texto_aprovado`. Easings só `power2.out`, `power2.inOut`, `power3.out`, `sine.inOut` (sem overshoot). A animação termina antes da saída (conferido pelo kit).
- `kit.py motion-quadros PROJETO_HTML --t T1,T2 --saida-dir DIR [--sem-fundo]` gera PNGs com transparência (Chrome headless, sem rede) sem renderizar o vídeo; `--sem-fundo` esconde o fundo do recorte para medir o conteúdo contra a safe area.

## Formatos e safe areas (px)

| formato | tamanho | área útil para legenda e texto |
|---|---|---|
| `reels` | 1080x1920 | x 60-1020, y 250-1600 (embaixo fica a interface do Instagram) |
| `linkedin` | 1080x1350 | x 60-1020, y 60-1290 |
| `paisagem` | 1920x1080 | x 96-1824, y 54-1026 (fonte vertical: imagem inteira sobre fundo desfocado) |

## Tom e regras de publicidade

O kit nasceu para vídeos de profissional liberal, com tom sóbrio. Se a sua profissão tem regras de publicidade (conselho
de classe, órgão regulador), anote-as no `projeto.md` e siga-as. O padrão do kit:

- Sem promessa de resultado e sem apelo comercial na tela.
- Fechamentos neutros ("Vale guardar esse vídeo", "Fica de olho nisso").
- Nunca cortar ressalvas técnicas. Não inventar fala, dado ou informação técnica.
- Sem música nem imagem de terceiros sem confirmação (a música costuma entrar na própria rede social).

## Formato da EDL

Veja o docstring de `kitlib/edl.py`.
- Tempos de `segmentos` em segundos **da fonte**. Tempos de `zooms` em segundos **da saída**.
- `correcoes`: `{"fonte": "bloco4", "i": 21, "texto": "contratado"}`, onde `i` é o índice da palavra no JSON da transcrição. Com `texto: ""`, a palavra é fundida na seguinte.

## Arquivos do kit

- `kit.py`: entrada única.
- `transcrever_whisper.py`: transcrição local (`.venv-whisper`, modelo em `.modelos-whisper/`).
- `kitlib/comum.py`: travas e utilidades.
- `kitlib/compacta.py`, `kitlib/edl.py`, `kitlib/video.py`, `kitlib/audio_voz.py`.
- `kitlib/legendas.py` (motor) e `kitlib/medir.py` (medida pelo libass).
- `kitlib/conferir.py`, `kitlib/mostruario.py`.
- `kitlib/motion.py` (efeitos de motion via HyperFrames local), `kitlib/motion_graficos.py` + `motion/biblioteca.json` + `motion/quadros.mjs` (biblioteca de aberturas e gráficos), `motion/exemplos/*.json`, `motion/fontes/Inter-Variable.ttf` (OFL).
- `hyperframes-run/` (wrapper `hf.sh`, versões fixas do HyperFrames; o `install.sh` copia para `<raiz>/ferramentas/`).
- `install.sh`, `README.md`, `LICENSE`.
- `kitlib/pessoa.py` + `pessoa_seg.py` (silhueta do apresentador x overlays; `.venv-pessoa`: mediapipe 1.1.1 + opencv-python-headless).
- `legendas/`, `modelos/projeto.md`, `NOTICE.md`.

## Doutrina de movimento (resumo em português, 2026-10-28)

Fontes lidas (nada instalado): skills `motion-doctrine`, `cut-the-curve` e `captions-overlay` do repositório heygen-com/hyperframes (licença Apache 2.0) e dicas `silence-detection`, `color-correction` e `light-leaks` do remotion-dev/skills. Resumo próprio, adaptado ao tom sóbrio. Não usar `media-use` (voz sintética, chaves de API, rede) nem `slideshow` (apresentação ao vivo, não gera MP4).

1. Continuidade no corte (vector law): a cena que sai e a que entra se movem no mesmo eixo e no mesmo sentido, com velocidade parecida. Nunca alternar sentidos em cortes seguidos (ping-pong parece erro). Escolher UM sentido dominante por vídeo (esquerda, neutro = "próximo ponto"); subir = conclusão/revelação; zoom para dentro = aprofundar o mesmo raciocínio.
2. Sem balanço parado: nada de pulsar/flutuar à toa (o `pulse` só para chamar atenção a algo já na tela). Entre a entrada e a saída, a tela deve ganhar informação em sincronia com a fala (staged reveals): cada item entra na palavra que o ilustra.
3. Movimento causal: um efeito começa no quadro da causa (ex.: o número termina de contar e o destaque acende no mesmo quadro), nunca "um pouco depois". Elementos maiores reagem mais devagar.
4. Imobilidade antes do clímax: segurar um instante antes do dado principal, para ele pesar.
5. Entrada em cascata (waterfall entry): palavras/itens entram em ordem de leitura com intervalo curto (já é o stagger do kit). Deslocamento de grupo na tela sem corte: ease in-out, sem retorno.
6. Legenda é sobreposição (overlay), nunca uma faixa reservada: não empurrar o conteúdo para cima para abrir espaço. Três papéis: drop (cortar vícios e hesitações), rail (legenda palavra a palavra, o padrão) e embed (uma palavra grande atrás do sujeito, raro, no máximo uma por trecho). Padrão do kit: rail sempre; embed só se pedirem.
7. Silêncio adaptativo (ffmpeg): medir com `loudnorm=print_format=json`, usar `input_thresh` como `noise` em `silencedetect=noise=<thresh>dB:d=0.5` para achar pausas a cortar.
8. Correção de cor: ajustes primários (exposição, temperatura, tinta, sombras/realces, contraste, saturação) numa passada só; LUT .cube só se aprovado.
9. Light leak (vazamento de luz): existe, mas fica fora do padrão sóbrio, só se pedirem.

## GSAP: guia oficial resumido (2026-10-28, fonte: greensock/gsap-skills, MIT)

Plugins disponíveis no projeto de motion (`assets/`, copiados por `kitlib/motion.py`; carregar com `<script src="assets/NOME.min.js">` depois do `gsap.min.js` e `gsap.registerPlugin(...)`): `DrawSVGPlugin`, `SplitText`, `MotionPathPlugin`, `MorphSVGPlugin`, `Flip`, `CustomEase`. Ainda não usados em nenhum efeito da biblioteca; testar num render curto antes de adotar.

- **draw-on (traço se desenhando):** `gsap.fromTo(path, {drawSVG:"0% 0%"}, {drawSVG:"0% 100%", duration:1.5})`. O elemento precisa ter `stroke` e `stroke-width`; só afeta traço, não preenchimento; preferir `<path>` de um segmento só.
- **word reveal / typewriter por unidade:** `SplitText.create(el, {type:"words"})` e `gsap.from(split.words, {opacity:0, y:20, stagger:0.06})`. Dividir só o que anima; esperar a fonte carregar (`document.fonts.ready`) ou usar `autoSplit` com `onSplit`; com chars usar `smartWrap:true` e `font-kerning:none`; não funciona em `<text>` SVG.
- **mask reveal por linha/palavra:** `SplitText` com `mask:"lines"` ou `"words"`.
- **morph:** `MorphSVGPlugin` converte uma forma em outra mesmo com número de pontos diferente; `circle`/`rect` precisam de `convertToPath`.
- **trajeto:** `MotionPathPlugin` move um elemento ao longo de um caminho SVG (rota, seta que percorre o gráfico).
- **Flip:** anima a mudança de posição/tamanho de um elemento entre dois layouts (card que vira outro).
- **Boas práticas oficiais:** usar `x`, `y`, `scale`, `rotation` em vez de `top/left/width/height`; `autoAlpha` em vez de `opacity` para entrar e sair; timelines com parâmetro de posição em vez de `delay` encadeado; guardar o retorno do tween; em vários `from()` na mesma propriedade usar `immediateRender:false` nos seguintes; só eases documentadas (`power1` a `power4`, `back`, `expo`, `sine`; `ease:"none"` só em ticker).
- **Ease do tom sóbrio:** `power2.out` ou `power3.inOut` na maioria; `back.out` e `elastic` só se pedirem.

## Tipografia (padrão do kit)

Fonte: **Inter** em tudo (legenda e textos animados). Peso máximo **700 (Bold)**; nunca 800 ou 900 (extra-negrito), que ficou feio no teste dos plugins GSAP. Títulos 700, textos de apoio 500 a 600. Sem espaçamento largo entre letras (`letter-spacing` só levemente positivo, até 0,04 em caixa-alta curta).
