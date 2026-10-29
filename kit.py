#!/usr/bin/env python3
"""kit-editor — kit de edição de vídeos falados (Reels, LinkedIn, paisagem). Ponto de entrada único (stdlib +
ffmpeg; a transcrição roda no .venv-whisper). Rode da raiz de trabalho (a pasta com brutos/, trabalho/, editados/;
defina outra com a variável KIT_RAIZ):

  python3 ferramentas/kit-editor/kit.py <comando> ...

Comandos (fluxo completo em ferramentas/kit-editor/KIT.md):
  presets | paletas                     lista a biblioteca de legendas (e a de aberturas/gráficos) e as paletas
  biblioteca [--md]                     aberturas, gráficos animados e fechamentos (17 efeitos do motion)
  motion-quadros PROJETO --t 1,2 --saida-dir D [--sem-fundo]   PNGs com alfa de um projeto de motion, sem renderizar
  projeto   --tema T                    cria trabalho/T/projeto.md (memória do vídeo) a partir do modelo
  transcrever --tema T [--termos ".."] fonte.mov ...     whisper local + transcricao_compacta.md
  compacta  --tema T                    refaz a transcrição compacta a partir dos JSON
  rascunho  --tema T [--pausa 0.35]     EDL automática (tira pausas/muletas/repetições) + plano em texto
  plano     EDL                         mostra o plano de corte para aprovação
  aprovar   EDL --como "texto do OK" [--por NOME]   registra a aprovação na EDL
  renderizar EDL --formato reels|linkedin|paisagem --saida X.mp4 --legenda PRESET [--paleta P] [--previa]
            [--titulos arquivo.ass] [--y 0.78] [--grupos legenda_grupos.json]
  legendas  EDL --formato F --legenda PRESET [--paleta P] --saida-base trabalho/T/legenda_x
  conferir  VIDEO.mp4                   autochecagem (cortes, áudio, safe area, loudness) + PNGs
  mostruario --video BASE.mp4 --edl EDL --saida-dir DIR [--t 4.2] [--presets a,b,..] [--paleta P] [--mp4]
  efeitos                               lista os efeitos de motion (HyperFrames local)
  motion    SPEC.json --saida trabalho/T/motion_x.mov [--so-projeto] [--base VIDEO_SEM_OVERLAY]
                                        gera o overlay com alfa (ProRes 4444); com --base confere que nada cobre o apresentador
  sobrepor  VIDEO.mp4 --overlays a.mov [b.mov] --saida trabalho/T/x.mp4   aplica overlays num vídeo pronto (prévia/teste)
  (renderizar ... --overlays a.mov  aplica overlays na renderização final, abaixo de títulos e legenda)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kitlib.comum import RAIZ, KIT, VENV_WHISPER, caminho, saida_segura, ler_json, erro, info, BRUTOS  # noqa: E402
from kitlib import compacta, edl as E, legendas, video, conferir as C  # noqa: E402


def pasta_tema(tema):
    p = RAIZ / "trabalho" / tema
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_presets(a):
    pals = legendas.carregar_paletas()
    for n in legendas.listar_presets():
        pr = json.loads((legendas.PASTA / "presets" / f"{n}.json").read_text())
        print(f"{n:22s} [{pr.get('paleta_padrao')}]  {pr['aparencia']}\n{'':22s} origem: {pr['origem']}")
    print()
    cmd_biblioteca(argparse.Namespace(md=False, cabecalho=True))


def cmd_biblioteca(a):
    """Aberturas, gráficos animados e fechamentos (kit.py motion). --md imprime a tabela em Markdown."""
    from kitlib import motion
    ops = motion.biblioteca()
    if getattr(a, "md", False):
        print("| # | Nome (pt / en) | Grupo | Serve para | Quando usar | Duração e easing | Como se comporta | Parâmetros | Encaixe |")
        print("|---|---|---|---|---|---|---|---|---|")
        for n, o in enumerate(ops, 1):
            cel = [str(n), f"**{o['pt']}** / {o['en']}<br>`{o['id']}`", o['grupo'], o['serve'], o['quando'], f"{o['duracao']}. Easing: {o['easing']}",
                   o['comportamento'], ', '.join(o['parametros']), f"{o['momento']} (recorte padrão: {'sim' if o['recorte'] else 'não'})"]
            print("| " + " | ".join(c.replace("|", "\\|") for c in cel) + " |")
        return
    print("ABERTURAS, GRÁFICOS ANIMADOS E FECHAMENTOS (motion; HyperFrames local; uso: kit.py motion SPEC.json, campo \"efeito\"):")
    for g, rot in (("abertura", "aberturas (hook)"), ("grafico", "gráficos animados"), ("fechamento", "fechamentos discretos")):
        print(f"  {rot}:")
        for o in ops:
            if o["grupo"] == g:
                print(f"    {o['id']:22s} {o['pt']} / {o['en']}  [{'recorte' if o['recorte'] else 'espaço livre'}]\n{'':27s}{o['serve']}")
    print("  tabela completa: kit.py biblioteca --md; exemplo com as 17: motion/exemplos/biblioteca_aberturas_graficos.json")


def cmd_paletas(a):
    for k, v in legendas.carregar_paletas().items():
        if not k.startswith("_"):
            print(f"{k:15s} {v['nome']}  texto {v['texto']} · caixa {v['caixa']} · destaque {v['destaque']}")


def cmd_projeto(a):
    dest = pasta_tema(a.tema) / "projeto.md"
    if dest.exists():
        info(f"já existe: {dest}"); return
    dest.write_text((KIT / "modelos" / "projeto.md").read_text().replace("{TEMA}", a.tema), encoding="utf-8")
    info(f"criado: {dest}")


def _ids(fontes):
    return {Path(f).stem: str(caminho(f)) for f in fontes}


def cmd_transcrever(a):
    out = pasta_tema(a.tema) / "transcricoes" if not a.saida_dir else caminho(a.saida_dir)
    cmd = [str(VENV_WHISPER), str(KIT / "transcrever_whisper.py"), "--saida-dir", str(out), "--modelo", a.modelo]
    if a.termos:
        cmd += ["--termos", a.termos]
    r = subprocess.run(cmd + [str(caminho(f)) for f in a.fontes])
    if r.returncode:
        erro("transcrição falhou")
    a.dir = str(out)
    cmd_compacta(a)


def cmd_compacta(a):
    d = caminho(a.dir) if getattr(a, "dir", None) else pasta_tema(a.tema) / "transcricoes"
    trs = [(p.stem, ler_json(p)) for p in sorted(d.glob("*.json"))]
    dest = d.parent / "transcricao_compacta.md"
    compacta.gerar(trs, dest)
    info(f"transcrição compacta: {dest}")


def cmd_rascunho(a):
    d = caminho(a.dir) if a.dir else pasta_tema(a.tema) / "transcricoes"
    trs = {p.stem: str(p) for p in sorted(d.glob("*.json"))}
    fontes = {k: ler_json(v)["fonte"] for k, v in trs.items()}
    ordem = a.ordem.split(",") if a.ordem else list(trs)
    edl = E.rascunho({k: fontes[k] for k in ordem}, {k: trs[k] for k in ordem}, pausa_max=a.pausa,
                     remover_talvez=a.tirar_talvez)
    edl["tema"] = a.tema
    dest = caminho(a.saida) if a.saida else d.parent / "edl_rascunho.json"
    saida_segura(dest).write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(E.plano_texto(edl))
    info(f"\nEDL: {dest}  (rascunho — mostre o plano a quem aparece no vídeo e só renderize para editados/ depois do OK)")


def cmd_plano(a):
    print(E.plano_texto(ler_json(a.edl)))


def cmd_aprovar(a):
    p = caminho(a.edl).resolve()
    if BRUTOS in p.parents or (RAIZ / "editados") in p.parents:
        erro("EDL deve ficar em trabalho/")
    edl = ler_json(p)
    from datetime import datetime
    edl["aprovacao"] = dict(por=a.por, quando=datetime.now().strftime("%Y-%m-%d %H:%M"), como=a.como)
    p.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    info(f"aprovação registrada em {p}")


def cmd_renderizar(a):
    video.renderizar(a.edl, a.formato, a.saida, a.legenda, paleta=a.paleta, previa=a.previa,
                     ass_extra=a.titulos, y_legenda=a.y, grupos_json=a.grupos, overlays=a.overlays,
                     y_janelas=[tuple(float(v) for v in j.split(':')) for j in (a.y_janela or [])])


def cmd_legendas(a):
    edl = ler_json(a.edl)
    _, tot = E.offsets(edl)
    base = saida_segura(Path(str(caminho(a.saida_base)) + ".ass"))
    r = legendas.gerar(E.palavras_saida(edl), a.legenda, a.formato, str(base)[:-4], paleta=a.paleta, y=a.y,
                       duracao=tot, grupos_fixos=[g["palavras"] for g in ler_json(a.grupos)["grupos"]] if a.grupos else None)
    for g in r["grupos"]:
        print(f"{g['ini']:6.2f}-{g['fim']:6.2f} | {g['texto']}")


def cmd_conferir(a):
    ok = C.conferir(caminho(a.video), a.manifesto)
    sys.exit(0 if ok else 1)


def cmd_efeitos(a):
    from kitlib import motion
    for k, v in motion.EFEITOS.items():
        print(f"{k:22s} {v}")


def cmd_motion(a):
    from kitlib import motion
    motion.gerar(a.spec, a.saida, so_projeto=a.so_projeto, base=a.base, motor=a.motor)


def cmd_motion_quadros(a):
    from kitlib import motion, motion_graficos  # motion primeiro (registra os efeitos)
    ts = [float(x) for x in a.t.split(",")]
    for f in motion_graficos.quadros(a.projeto, ts, a.saida_dir, sem_fundo=a.sem_fundo):
        print(f)


def cmd_sobrepor(a):
    from kitlib import motion
    motion.sobrepor(a.video, a.overlays, a.saida)


def cmd_mostruario(a):
    from kitlib import mostruario
    mostruario.gerar(a)


def main():
    ap = argparse.ArgumentParser(description="kit-editor", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("presets").set_defaults(f=cmd_presets)
    p = sp.add_parser("biblioteca"); p.add_argument("--md", action="store_true", help="tabela em Markdown"); p.set_defaults(f=cmd_biblioteca)
    sp.add_parser("paletas").set_defaults(f=cmd_paletas)
    p = sp.add_parser("projeto"); p.add_argument("--tema", required=True); p.set_defaults(f=cmd_projeto)
    p = sp.add_parser("transcrever"); p.add_argument("fontes", nargs="+"); p.add_argument("--tema", required=True)
    p.add_argument("--termos", default=""); p.add_argument("--modelo", default="medium"); p.add_argument("--saida-dir")
    p.set_defaults(f=cmd_transcrever)
    p = sp.add_parser("compacta"); p.add_argument("--tema"); p.add_argument("--dir"); p.set_defaults(f=cmd_compacta)
    p = sp.add_parser("rascunho"); p.add_argument("--tema", required=True); p.add_argument("--dir")
    p.add_argument("--pausa", type=float, default=0.35); p.add_argument("--ordem", help="ids das fontes, separados por vírgula")
    p.add_argument("--tirar-talvez", action="store_true", help="também tira 'né'/'tipo' marcados como talvez")
    p.add_argument("--saida"); p.set_defaults(f=cmd_rascunho)
    p = sp.add_parser("plano"); p.add_argument("edl"); p.set_defaults(f=cmd_plano)
    p = sp.add_parser("aprovar"); p.add_argument("edl"); p.add_argument("--como", required=True)
    p.add_argument("--por", default="apresentador", help="quem aprovou (padrão: apresentador)"); p.set_defaults(f=cmd_aprovar)
    p = sp.add_parser("renderizar"); p.add_argument("edl"); p.add_argument("--formato", required=True, choices=["reels", "linkedin", "paisagem"])
    p.add_argument("--saida", required=True); p.add_argument("--legenda", required=True, help="preset da biblioteca (kit.py presets)")
    p.add_argument("--paleta"); p.add_argument("--previa", action="store_true"); p.add_argument("--titulos", action="append")
    p.add_argument("--y", type=float, help="base da legenda (fração da altura)"); p.add_argument("--grupos")
    p.add_argument("--y-janela", action="append", help="ini:fim:y (s, s, fração) legenda em outra altura nessa janela")
    p.add_argument("--overlays", nargs="+", help="overlays .mov com alfa gerados por kit.py motion")
    p.set_defaults(f=cmd_renderizar)
    sp.add_parser("efeitos").set_defaults(f=cmd_efeitos)
    p = sp.add_parser("motion"); p.add_argument("spec"); p.add_argument("--saida", required=True)
    p.add_argument("--so-projeto", action="store_true", help="só gera o projeto HTML (sem renderizar)")
    p.add_argument("--motor", choices=["hyperframes"], default=None, help="motor de render (só hyperframes)")
    p.add_argument("--base", help="vídeo da EDL SEM overlays (ex.: prévia _sem-legenda) para conferir a silhueta do apresentador")
    p.set_defaults(f=cmd_motion)
    p = sp.add_parser("motion-quadros"); p.add_argument("projeto", help="pasta <saida>_projeto gerada por motion --so-projeto")
    p.add_argument("--t", required=True, help="instantes (s), separados por vírgula"); p.add_argument("--saida-dir", required=True)
    p.add_argument("--sem-fundo", action="store_true", help="esconde o fundo do recorte (para medir o conteúdo)")
    p.set_defaults(f=cmd_motion_quadros)
    p = sp.add_parser("sobrepor"); p.add_argument("video"); p.add_argument("--overlays", nargs="+", required=True)
    p.add_argument("--saida", required=True); p.set_defaults(f=cmd_sobrepor)
    p = sp.add_parser("legendas"); p.add_argument("edl"); p.add_argument("--formato", required=True)
    p.add_argument("--legenda", required=True); p.add_argument("--paleta"); p.add_argument("--saida-base", required=True)
    p.add_argument("--y", type=float); p.add_argument("--grupos"); p.set_defaults(f=cmd_legendas)
    p = sp.add_parser("conferir"); p.add_argument("video"); p.add_argument("--manifesto"); p.set_defaults(f=cmd_conferir)
    p = sp.add_parser("mostruario"); p.add_argument("--video", required=True); p.add_argument("--edl", required=True)
    p.add_argument("--formato", default="reels"); p.add_argument("--saida-dir", required=True); p.add_argument("--t", type=float)
    p.add_argument("--presets"); p.add_argument("--paleta"); p.add_argument("--mp4", action="store_true")
    p.add_argument("--nome", default="mostruario_legendas")
    p.set_defaults(f=cmd_mostruario)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
