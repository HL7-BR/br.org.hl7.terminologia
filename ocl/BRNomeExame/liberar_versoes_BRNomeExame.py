#!/usr/bin/env python3
"""Libera uma versão da fonte BRNomeExameLOINC a partir do HEAD e, em seguida,
uma versão da coleção BRNomeExame, para que as referências "latest" passem a
resolver os 449 conceitos do HEAD (e não os 160 da versão 2.0).

Uso (PowerShell, uma linha por vez, na pasta do script):
    $env:OCL_TOKEN = "SEU_TOKEN"
    python liberar_versoes_BRNomeExame.py 2.1.0

O número da versão é o primeiro argumento (SemVer) e vale para a fonte e a coleção.
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
ORG = "MS"
FONTE = "BRNomeExameLOINC"
COLECAO = "BRNomeExame"


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


def esperar(caminho, chave, alvo, rotulo):
    for _ in range(60):
        n = resumo(caminho).get(chave)
        print(f"  {rotulo}: {n}")
        if n is not None and n >= alvo:
            return n
        time.sleep(10)
    return resumo(caminho).get(chave)


def main():
    if len(sys.argv) < 2:
        sys.exit("Informe a versão: python liberar_versoes_BRNomeExame.py 2.1.0")
    versao = sys.argv[1]
    if not TOKEN:
        sys.exit("Defina OCL_TOKEN antes.")
    st, eu = chamar("GET", "/user/")
    if st != 200:
        sys.exit(f"Token recusado ({st}).")
    print(f"Usuário: {eu.get('username')}")

    alvo = resumo(f"/orgs/{ORG}/sources/{FONTE}/HEAD/").get("active_concepts") or 0
    print(f"{FONTE} HEAD: {alvo} conceitos ativos")

    # 1. Versão da fonte a partir do HEAD
    st, r = chamar("POST", f"/orgs/{ORG}/sources/{FONTE}/versions/",
                   {"id": versao, "description": f"Versão {versao} a partir do HEAD ({alvo} conceitos)",
                    "released": True})
    print(f"Criar versão {versao} da fonte: {st}")
    if st not in (200, 201, 202):
        sys.exit(f"Falhou: {r}")
    n = esperar(f"/orgs/{ORG}/sources/{FONTE}/{versao}/", "active_concepts", alvo, f"{FONTE} {versao}")
    if (n or 0) < alvo:
        sys.exit("A versão da fonte não terminou de processar. Rode de novo daqui a alguns minutos só a parte da coleção.")

    # 2. Versão da coleção (recalcula a expansão)
    refs = resumo(f"/orgs/{ORG}/collections/{COLECAO}/HEAD/").get("active_references") or 0
    st, r = chamar("POST", f"/orgs/{ORG}/collections/{COLECAO}/versions/",
                   {"id": versao, "description": f"Versão {versao}: exames LOINC e GAL do REL ({refs} referências)",
                    "released": True})
    print(f"Criar versão {versao} da coleção: {st}")
    if st not in (200, 201, 202):
        sys.exit(f"Falhou: {r}")
    n = esperar(f"/orgs/{ORG}/collections/{COLECAO}/{versao}/", "active_concepts", refs, f"{COLECAO} {versao}")
    print(f"Coleção {COLECAO} {versao}: {n} conceitos ativos (esperado {refs}).")


if __name__ == "__main__":
    main()
