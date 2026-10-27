#!/usr/bin/env python3
"""Exporta a coleção BRNomeExame do OCL para o guia de terminologia.

Lê os conceitos da versão liberada da coleção (padrão 2.1.2) e grava, em
input/resources:

- ValueSet-BRNomeExame.json: os exames LOINC enumerados com
  system http://loinc.org e o CodeSystem BRNomeExameGAL incluído inteiro,
  sem fixar versão no include;
- CodeSystem-BRNomeExameGAL.json: os conceitos do GAL, content = complete.

Só lê o OCL; não precisa de token. Códigos inválidos (ex.: código igual à URL
do OCL, DL-39) são ignorados e listados.

Uso (PowerShell, na raiz do repositório br.org.hl7.terminologia):
    python ocl\\BRNomeExame\\exportar_BRNomeExame_para_ig.py --seco
    python ocl\\BRNomeExame\\exportar_BRNomeExame_para_ig.py
    python ocl\\BRNomeExame\\exportar_BRNomeExame_para_ig.py 2.1.2

Autoria: Jussara Macedo Pinho Rötzsch.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br").rstrip("/")
COL = "/orgs/MS/collections/BRNomeExame"
FONTE_LOINC = "BRNomeExameLOINC"
FONTE_GAL = "BRNomeExameGAL"
LOINC = "http://loinc.org"
GAL = "https://terminologia.saude.gov.br/fhir/CodeSystem/BRNomeExameGAL"
RES = Path("input/resources")


def ler(caminho):
    req = urllib.request.Request(API + caminho, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"Erro {e.code} ao ler {caminho}: {e.read().decode('utf-8', 'replace')[:300]}")


def conceitos(versao):
    todos, pag = [], 1
    while True:
        d = ler(f"{COL}/{versao}/concepts/?limit=500&page={pag}&verbose=true")
        if not d:
            break
        todos += d
        if len(d) < 500:
            break
        pag += 1
    return [c for c in todos if not c.get("retired")]


def valido(cod):
    return bool(cod) and "/" not in cod and not cod.lower().startswith("http") and cod == cod.strip()


def main():
    seco = "--seco" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    versao = args[0] if args else "2.1.2"
    if not RES.is_dir():
        sys.exit("Rode na raiz do repositório br.org.hl7.terminologia (não achei input/resources).")

    cs = conceitos(versao)
    loinc, gal, ignorados = {}, {}, []
    for c in cs:
        cod, nome, fonte = c.get("id"), c.get("display_name"), c.get("source")
        if not valido(cod):
            ignorados.append((fonte, cod, nome))
        elif fonte == FONTE_LOINC:
            loinc[cod] = nome
        elif fonte == FONTE_GAL:
            gal[cod] = nome
        else:
            ignorados.append((fonte, cod, nome))
    print(f"Coleção BRNomeExame {versao}: {len(cs)} conceitos ativos")
    print(f"  LOINC: {len(loinc)}; GAL: {len(gal)}; ignorados: {len(ignorados)}")
    for f, c, n in ignorados:
        print(f"  ignorado: {f} | {c} | {n}")
    if seco:
        print("Modo seco: nada foi gravado.")
        return

    p_vs = RES / "ValueSet-BRNomeExame.json"
    vs = json.loads(p_vs.read_text(encoding="utf-8"))
    for k in ("text", "meta", "version", "expansion"):
        vs.pop(k, None)
    vs["description"] = (f"Exames de laboratório: LOINC (http://loinc.org) e códigos do GAL. "
                         f"Gerado da coleção BRNomeExame {versao} do OCL.")
    vs["compose"] = {"include": [
        {"system": LOINC,
         "concept": [{"code": k, "display": v} for k, v in sorted(loinc.items())]},
        {"system": GAL},
    ]}
    p_vs.write_text(json.dumps(vs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    p_cs = RES / "CodeSystem-BRNomeExameGAL.json"
    cs_gal = json.loads(p_cs.read_text(encoding="utf-8"))
    for k in ("text", "meta", "version"):
        cs_gal.pop(k, None)
    cs_gal["content"] = "complete"
    cs_gal["count"] = len(gal)
    cs_gal["concept"] = [{"code": k, "display": v} for k, v in sorted(gal.items())]
    p_cs.write_text(json.dumps(cs_gal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"Gravados {p_vs} ({len(loinc)} LOINC + GAL inteiro) e {p_cs} ({len(gal)} conceitos).")


if __name__ == "__main__":
    main()
