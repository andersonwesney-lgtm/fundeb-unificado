"""Linha de comando.

  python -m fundeb_core coletar     # baixa IBGE e os arquivos publicados do painel SIOPE para brutos/
  python -m fundeb_core gerar       # monta site/ a partir de brutos/
  python -m fundeb_core servir      # abre site/ em http://localhost:8000
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
from pathlib import Path

from .coleta import ErroColeta, coletar_tudo
from .entes import ErroCadastro
from .gerar import RAIZ, gerar


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fundeb_core")
    p.add_argument("comando", choices=["coletar", "gerar", "servir"])
    p.add_argument("--brutos", default=str(RAIZ / "brutos"))
    p.add_argument("--saida", default=str(RAIZ / "site"))
    p.add_argument("--reserva", help="pasta com os brutos da última execução bem-sucedida (usada só se uma fonte falhar)")
    a = p.parse_args(argv)
    try:
        if a.comando == "coletar":
            config = json.loads((RAIZ / "config" / "sistemas.json").read_text(encoding="utf-8"))
            res = Path(a.reserva) if a.reserva and Path(a.reserva).is_dir() else None
            for m in coletar_tudo(config, Path(a.brutos), res):
                aviso = f"  [CÓPIA DE RESERVA coletada em {m['coletado_em']}: {m['motivo_reserva']}]" if m.get("reserva") else ""
                print(f"{m['nome']}: {m['bytes']} bytes, SHA-256 {m['sha256']}{aviso}")
        elif a.comando == "gerar":
            m = gerar(Path(a.brutos), Path(a.saida))
            print(f"site gerado: {m['entes']['total']} entes {m['entes']['por_tipo']}; entes.json SHA-256 {m['entes']['sha256']}")
        else:
            h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=a.saida)
            print("http://localhost:8000")
            http.server.ThreadingHTTPServer(("127.0.0.1", 8000), h).serve_forever()
    except (ErroColeta, ErroCadastro) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    return 0
