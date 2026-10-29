# hyperframes-run: HyperFrames local e isolado

O `install.sh` copia esta pasta para `<raiz>/ferramentas/hyperframes-run/` e instala ali:

| Item | Versão / origem |
| --- | --- |
| Node.js | v22.21.1 em `node/` (tarball oficial de nodejs.org, SHA-256 conferido com o SHASUMS256.txt). O Node do sistema não é tocado. |
| HyperFrames CLI | npm `hyperframes@0.8.185` fixo (`package.json` + `package-lock.json`), instalado com `npm ci --ignore-scripts` (nenhum script de instalação roda). |
| GSAP | `gsap@3.15.0` do npm, arquivos `dist/*.min.js` copiados para `vendor/gsap-3.15.0/` (licença: https://gsap.com/standard-license). |
| Chrome | o do sistema (`google-chrome` ou `chromium`; troque com `HYPERFRAMES_BROWSER_PATH`). |
| HOME do HyperFrames | `home/` (config e caches ficam aqui, não no seu HOME). |

## Uso
Sempre pelo wrapper `hf.sh` (o `kit.py motion` já chama):
- liga `HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`, `HYPERFRAMES_NO_UPDATE_CHECK=1`, `HYPERFRAMES_NO_AUTO_INSTALL=1`,
  `HYPERFRAMES_SKIP_SKILLS=1`, `HYPERFRAMES_NO_OPTIONAL_INSTALL=1`;
- tira do ambiente chaves de API (HEYGEN, ELEVENLABS, OPENROUTER, GEMINI, FIGMA...);
- roda dentro de `unshare -rn` (rede só com loopback): sem acesso à internet;
- bloqueia os comandos de nuvem, conta e instalação (cloud, lambda, publish, auth, upgrade, skills, add, tts...).

`rede-log.cjs` é uma instrumentação opcional (via `NODE_OPTIONS=--require`) que registra as conexões do processo Node; o
`kit.py motion` grava `rede.log` em cada projeto e informa quantas foram externas (o esperado é 0).

Se o seu sistema bloquear `unshare -rn` sem root (Ubuntu 24.04 com AppArmor, por exemplo), veja a seção "Problemas comuns"
no README.md da raiz do kit.
