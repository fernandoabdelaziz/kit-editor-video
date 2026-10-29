# kit-editor

Kit de linha de comando para editar vídeos falados, como Reels, posts de LinkedIn e vídeos na horizontal. Ele foi
pensado para profissionais que gravam falando para a câmera e querem um resultado sóbrio. Tudo roda no seu computador:
nenhum vídeo vai para a nuvem e nenhuma chave paga é necessária.

## O que o kit faz

1. **Transcreve** a fala, palavra por palavra, com o Whisper rodando local.
2. **Propõe o corte**: tira pausas longas, muletas ("é...", "hum"), repetições e falsos começos. Antes de renderizar, mostra
   o plano em texto para alguém aprovar.
3. **Renderiza** nos formatos `reels` (1080x1920), `linkedin` (1080x1350) e `paisagem` (1920x1080). Trata a voz e ajusta o
   volume para -14 LUFS, o padrão das redes. Queima a legenda palavra por palavra, com 16 estilos prontos e 10 paletas.
4. **Anima textos** (motion graphics) com o HyperFrames local: nome na tela, número contando, frase datilografada, listas,
   gráficos, 17 aberturas e fechamentos. Um detector de silhueta (MediaPipe) confere que nenhum gráfico cobre a pessoa
   no vídeo.
5. **Confere o resultado** antes da entrega: duração, cor, volume, estalos nos cortes, legenda dentro da área segura. Também
   gera imagens de cada corte para você olhar.

O kit tem algumas travas de segurança. Ele nunca escreve em `brutos/` (os arquivos originais) e nunca sobrescreve um
arquivo. Para gravar em `editados/`, a EDL precisa estar aprovada.

O passo a passo completo de cada vídeo está no [`KIT.md`](KIT.md). As origens das ideias e as licenças estão no [`NOTICE.md`](NOTICE.md).

## Como as pastas ficam

O kit trabalha dentro de uma **raiz** (por padrão `~/videos`):

```
~/videos/                      <- raiz (troque com --raiz no install.sh ou com a variável KIT_RAIZ)
├── brutos/                    vídeos originais (o kit só lê)
├── trabalho/<tema>/           transcrições, EDL, prévias, projetos de motion
├── editados/                  entregas finais
├── .venv-whisper/             Python com faster-whisper (transcrição)
├── .modelos-whisper/          modelo Whisper (baixa na 1ª transcrição)
├── .venv-pessoa/              Python com MediaPipe (silhueta)
├── .modelos-pessoa/           selfie_segmenter.tflite
├── .venv-ffmpeg-skill/        (opcional) Python do check.py do ffmpeg-skill
└── ferramentas/
    ├── kit-editor/            este repositório (ou um link para ele)
    ├── hyperframes-run/       Node 22 local + HyperFrames + GSAP (motion)
    ├── modelos-ruido/cb.rnnn  modelo de ruído do perfil de áudio "rua"
    └── ffmpeg-skill/          (opcional)
```

O kit encontra a raiz nesta ordem:
1. a variável `KIT_RAIZ`;
2. o arquivo `raiz.txt` ao lado do `kit.py`, que o `install.sh` grava;
3. duas pastas acima do kit, se ele estiver em `<raiz>/ferramentas/kit-editor`.

O navegador usado pelo motion é o `google-chrome` ou o `chromium` do sistema. Para usar outro, defina `HYPERFRAMES_BROWSER_PATH`.

## Instalação (Ubuntu ou Debian, máquina nova)

### Jeito rápido

```bash
mkdir -p ~/videos/ferramentas && cd ~/videos/ferramentas
git clone https://github.com/fernandoabdelaziz/kit-editor-video.git kit-editor
cd kit-editor
./install.sh --teste
```

O `install.sh` pode rodar de novo sem problema: o que já está instalado e conferido é pulado. Opções úteis:
- `--raiz DIR`: escolhe outra raiz.
- `--sem-sistema`: não chama `apt-get` (para quem não tem sudo).
- `--sem-whisper`, `--sem-pessoa`, `--sem-motion`: pulam uma parte.
- `--com-ffmpeg-skill`: instala também o check extra do `conferir`.
- `--baixar-whisper`: já baixa o modelo de ~1,5 GB.
- `--simular`: mostra o que faria, sem mudar nada.

### Passo a passo (o que o `install.sh` faz)

1. **Pacotes do sistema:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y ffmpeg python3 python3-venv python3-pip python3-numpy python3-pil \
        fontconfig fonts-dejavu-core curl ca-certificates xz-utils iproute2 util-linux git
   ```
   O ffmpeg precisa ter `libass`, `arnndn` e `zscale`, como o ffmpeg do Debian e do Ubuntu. O `python3` do sistema
   precisa de `numpy` e `Pillow`.
   O motion também precisa de um navegador:
   - no Debian: `sudo apt-get install -y chromium`;
   - no Ubuntu: o [.deb do Google Chrome](https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb) com `sudo apt-get install -y ./google-chrome-stable_current_amd64.deb`. O `chromium` do Ubuntu é um snap e costuma falhar no modo sem tela.
2. **Pastas:** `mkdir -p ~/videos/{brutos,trabalho,editados,ferramentas}`. O kit fica em `~/videos/ferramentas/kit-editor`.
3. **Fonte Inter** (a legenda usa essa fonte):
   ```bash
   mkdir -p ~/.local/share/fonts && cp motion/fontes/Inter-Variable.ttf ~/.local/share/fonts/ && fc-cache -f
   ```
4. **Transcrição:**
   ```bash
   python3 -m venv ~/videos/.venv-whisper
   ~/videos/.venv-whisper/bin/pip install faster-whisper==1.2.1 av==15.1.0   # o PyAV 19 quebra o faster-whisper 1.2.1
   ```
   O modelo `medium` baixa sozinho para `~/videos/.modelos-whisper/` na primeira transcrição.
5. **Silhueta:**
   ```bash
   python3 -m venv ~/videos/.venv-pessoa
   ~/videos/.venv-pessoa/bin/pip install mediapipe==1.1.1 opencv-python-headless numpy
   mkdir -p ~/videos/.modelos-pessoa
   curl -fL -o ~/videos/.modelos-pessoa/selfie_segmenter.tflite \
     https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite
   echo "191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b  $HOME/videos/.modelos-pessoa/selfie_segmenter.tflite" | sha256sum -c
   ```
6. **Modelo de ruído** (perfil de áudio `rua`, para gravação sem microfone):
   ```bash
   mkdir -p ~/videos/ferramentas/modelos-ruido
   curl -fL -o ~/videos/ferramentas/modelos-ruido/cb.rnnn \
     https://raw.githubusercontent.com/GregorR/rnnoise-models/master/conjoined-burgers-2018-08-28/cb.rnnn
   echo "f1357c4e5be9dee8467bead486dfced2d75b640c26ad0b594fa7f102322371d9  $HOME/videos/ferramentas/modelos-ruido/cb.rnnn" | sha256sum -c
   ```
7. **Motion (HyperFrames):** copie a pasta `hyperframes-run/` deste repositório para `~/videos/ferramentas/hyperframes-run/`.
   Lá dentro:
   - instale o Node.js v22.21.1 em `node/`, com o tarball oficial `node-v22.21.1-linux-x64.tar.xz` de nodejs.org,
     conferido com o `SHASUMS256.txt` e extraído com `--strip-components=1`;
   - rode `PATH=$PWD/node/bin:$PATH HOME=$PWD/home npm ci --ignore-scripts` (instala o `hyperframes@0.8.185` do `package-lock.json`);
   - rode `npm pack gsap@3.15.0` e copie de `package/dist/` para `vendor/gsap-3.15.0/` os arquivos `gsap.min.js`,
     `CustomEase.min.js`, `DrawSVGPlugin.min.js`, `SplitText.min.js`, `MotionPathPlugin.min.js`, `MorphSVGPlugin.min.js` e `Flip.min.js`;
   - grave `home/.hyperframes/config.json` com `{"telemetryEnabled": false}`.
8. **Opcional, ffmpeg-skill:**
   ```bash
   git clone https://github.com/kajisho5/ffmpeg-skill ~/videos/ferramentas/ffmpeg-skill
   git -C ~/videos/ferramentas/ffmpeg-skill checkout 5ebe34b
   python3 -m venv ~/videos/.venv-ffmpeg-skill
   ```
   Sem ele, o `kit.py conferir` só pula esse item.

### Teste rápido

```bash
KIT_RAIZ=~/videos bash ~/videos/ferramentas/kit-editor/teste_rapido.sh             # ~1 min
KIT_RAIZ=~/videos bash ~/videos/ferramentas/kit-editor/teste_rapido.sh --completo  # inclui o render do motion
```

O teste gera um clipe sintético e uma transcrição falsa. Depois roda transcrição compacta, corte, prévia com legenda,
conferência e motion. Os arquivos ficam em `trabalho/_teste_kit_<data>/`. Com som de teste, é normal o `conferir` apontar
itens de áudio.

## Uso no dia a dia

```bash
cd ~/videos
python3 ferramentas/kit-editor/kit.py --help
python3 ferramentas/kit-editor/kit.py projeto --tema meu-video
python3 ferramentas/kit-editor/kit.py transcrever --tema meu-video brutos/gravacao.mov
python3 ferramentas/kit-editor/kit.py rascunho --tema meu-video
python3 ferramentas/kit-editor/kit.py plano trabalho/meu-video/edl_rascunho.json
python3 ferramentas/kit-editor/kit.py aprovar trabalho/meu-video/edl_rascunho.json --como "pode renderizar" --por "Ana"
python3 ferramentas/kit-editor/kit.py renderizar trabalho/meu-video/edl_rascunho.json --formato reels \
        --saida editados/2026-01-01_meu-video_reels.mp4 --legenda caixa-d --paleta verde-bege
python3 ferramentas/kit-editor/kit.py conferir editados/2026-01-01_meu-video_reels.mp4
```

`kit.py presets`, `kit.py paletas`, `kit.py efeitos` e `kit.py biblioteca` listam os estilos disponíveis.

## Problemas comuns

- **"unshare: unshare failed: Operation not permitted"** ao renderizar o motion: o sistema bloqueia user namespaces sem
  root. O kit usa esse recurso para rodar o HyperFrames sem acesso à internet. No Ubuntu 23.10 ou mais novo, a trava é do
  AppArmor (`kernel.apparmor_restrict_unprivileged_userns=1`). Você pode liberar com
  `sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0`. Outra saída é rodar sem o isolamento, com `HF_REDE=1`
  antes do comando. Nesse caso o HyperFrames continua com telemetria e atualizações desligadas, mas sem a garantia de rede
  bloqueada.
- **Legenda com fonte errada:** confira se `fc-list | grep -i inter` mostra a Inter.
- **`falta o ambiente da silhueta`:** rode o `install.sh` sem `--sem-pessoa`.

## Licença

Código sob a licença MIT (`LICENSE`). A fonte Inter segue a SIL Open Font License 1.1. Ferramentas externas (HyperFrames,
GSAP, MediaPipe, faster-whisper, Node.js, ffmpeg) são baixadas da fonte original e seguem as próprias licenças, listadas no `NOTICE.md`.
