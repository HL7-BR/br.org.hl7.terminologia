#!/usr/bin/env python3
"""Refaz as referências da coleção BRNomeExame que ficaram sem conceito.

As referências foram gravadas quando a última versão liberada da fonte
BRNomeExameLOINC era a 2.0 (160 conceitos). As que apontam para códigos que só
existiam no HEAD ficaram resolvidas com 0 conceitos, e o OCL não as reavalia ao
criar versão da coleção. Este script remove essas referências e as inclui de
novo, agora que a fonte tem versão liberada com os 449 conceitos. Depois, se
for informado um número, cria a versão da coleção.

Uso (PowerShell, uma linha por vez, na pasta do script):
    $env:OCL_TOKEN = "SEU_TOKEN"
    python reavaliar_referencias_BRNomeExame.py --seco
    python reavaliar_referencias_BRNomeExame.py
    python reavaliar_referencias_BRNomeExame.py 2.1.2      # refaz e cria a versão 2.1.2 da coleção

Autoria: Jussara Macedo Pinho Rötzsch.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br").rstrip("/")
TOKEN = os.environ.get("OCL_TOKEN", "").strip().strip('"').strip("<>")
COL = "/orgs/MS/collections/BRNomeExame"
LOTE = 100


def chamar(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(API + caminho, data=dados, method=metodo)
    req.add_header("Accept", "application/json")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", "Token " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:800]


def resumo(caminho):
    st, d = chamar("GET", caminho + "?includeSummary=true")
    return (d.get("summary") or {}) if st == 200 and isinstance(d, dict) else {}


def referencias():
    todas, pag = [], 1
    while True:
        st, d = chamar("GET", f"{COL}/HEAD/references/?limit=500&page={pag}&verbose=true")
        if st != 200:
            sys.exit(f"Erro {st} ao ler as referências: {d}")
        if not d:
            break
        todas += d
        if len(d) < 500:
            break
        pag += 1
    return todas


def main():
    seco = "--seco" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    versao = args[0] if args else None
    if not seco:
        if not TOKEN:
            sys.exit("Defina OCL_TOKEN antes (ou rode com --seco).")
        st, eu = chamar("GET", "/user/")
        if st != 200:
            sys.exit(f"Token recusado ({st}).")
        print(f"Usuário: {eu.get('username')}")

    print(f"Coleção HEAD antes: {resumo(COL + '/HEAD/')}")
    refs = referencias()
    vazias = [r["expression"] for r in refs if not r.get("concepts")]
    print(f"Referências: {len(refs)}; sem conceito: {len(vazias)}")
    for e in vazias[:5]:
        print(f"  ex.: {e}")
    if seco:
        print("Modo seco: nada foi gravado.")
        return

    if vazias:
        for i in range(0, len(vazias), LOTE):
            lote = vazias[i:i + LOTE]
            st, r = chamar("DELETE", f"{COL}/references/", {"expressions": lote})
            if st not in (200, 202, 204):
                sys.exit(f"Erro {st} ao remover o lote {i // LOTE + 1}: {r}")
        print(f"Removidas: {len(vazias)}")
        incluidas, sem = 0, []
        for i in range(0, len(vazias), LOTE):
            lote = vazias[i:i + LOTE]
            st, r = chamar("PUT", f"{COL}/references/", {"data": {"expressions": lote}})
            if st not in (200, 201, 202):
                sys.exit(f"Erro {st} ao incluir o lote {i // LOTE + 1}: {r}")
            for item in (r or []):
                if item.get("added"):
                    incluidas += 1
                else:
                    sem.append((item.get("expression"), item.get("message")))
        print(f"Incluídas de novo: {incluidas}; recusadas: {len(sem)}")
        for e, m in sem[:20]:
            print(f"  recusada: {e} | {m}")

    refs = referencias()
    print(f"Referências ainda sem conceito: {sum(1 for r in refs if not r.get('concepts'))}")
    time.sleep(5)
    print(f"Coleção HEAD depois: {resumo(COL + '/HEAD/')}")

    if versao:
        st, r = chamar("POST", f"{COL}/versions/",
                       {"id": versao, "description": f"Versão {versao}: exames LOINC e GAL do REL", "released": True})
        print(f"Criar versão {versao} da coleção: {st}")
        if st not in (200, 201, 202):
            sys.exit(f"Falhou: {r}")
        for _ in range(30):
            time.sleep(10)
            s = resumo(f"{COL}/{versao}/")
            print(f"  {versao}: {s.get('active_concepts')} conceitos")
            if (s.get("active_concepts") or 0) >= len(refs):
                break


if __name__ == "__main__":
    main()
