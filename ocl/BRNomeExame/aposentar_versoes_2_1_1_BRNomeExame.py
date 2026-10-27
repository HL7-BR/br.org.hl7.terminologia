#!/usr/bin/env python3
"""Aposenta as versões 2.1.1 criadas por engano no OCL:

- coleção MS/BRNomeExame 2.0 (definição antiga, sem conceitos);
- coleção MS/BRNomeExame 2.1.1 (207 conceitos; a correta é a 2.1.2);
- fonte MS/BRNomeExameLOINC 2.1.1 (duplicata da 2.1.0).

Antes de gravar, confere que a coleção 2.1.2 existe, está liberada e tem
conceitos; sem isso, não aposenta nada.

Uso (PowerShell, uma linha por vez, na pasta do script):
    python aposentar_versoes_2_1_1_BRNomeExame.py --seco
    $env:OCL_TOKEN = "SEU_TOKEN"
    python aposentar_versoes_2_1_1_BRNomeExame.py

O token não é gravado nem impresso.
Autoria: Jussara Macedo Pinho Rötzsch.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br").rstrip("/")
TOKEN = os.environ.get("OCL_TOKEN", "").strip().strip('"').strip("<>")
ALVOS = [
    "/orgs/MS/collections/BRNomeExame/2.0/",
    "/orgs/MS/collections/BRNomeExame/2.1.1/",
    "/orgs/MS/sources/BRNomeExameLOINC/2.1.1/",
]
BOA = "/orgs/MS/collections/BRNomeExame/2.1.2/"


def chamar(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(API + caminho, data=dados, method=metodo)
    req.add_header("Accept", "application/json")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", "Token " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def contar(caminho):
    """Conta os conceitos pela listagem (o resumo da versão pode vir zerado)."""
    total, pag = 0, 1
    while True:
        st, d = chamar("GET", f"{caminho}concepts/?limit=500&page={pag}")
        if st != 200 or not d:
            break
        total += sum(1 for c in d if not c.get("retired"))
        if len(d) < 500:
            break
        pag += 1
    return total


def estado(caminho):
    st, d = chamar("GET", caminho)
    if st != 200 or not isinstance(d, dict):
        return None
    return {"released": d.get("released"), "retired": d.get("retired"),
            "conceitos": contar(caminho)}


def main():
    seco = "--seco" in sys.argv
    boa = estado(BOA)
    print(f"Coleção BRNomeExame 2.1.2: {boa}")
    if not boa or not boa["released"] or not boa["conceitos"]:
        sys.exit("A 2.1.2 não está liberada ou está vazia; nada foi aposentado.")

    for alvo in ALVOS:
        print(f"{alvo}: {estado(alvo)}")
    if seco:
        print("Modo seco: nada foi gravado.")
        return
    if not TOKEN:
        sys.exit("Defina OCL_TOKEN antes (ou rode com --seco).")
    st, eu = chamar("GET", "/user/")
    if st != 200:
        sys.exit(f"Token recusado ({st}).")
    print(f"Usuário: {eu.get('username')}")

    for alvo in ALVOS:
        e = estado(alvo)
        if e is None:
            print(f"{alvo}: não encontrada; pulando.")
            continue
        if e["retired"]:
            print(f"{alvo}: já aposentada.")
            continue
        st, r = chamar("PUT", alvo, {"retired": True, "released": False})
        print(f"{alvo}: {'aposentada' if st in (200, 202, 204) else f'falhou ({st}): {r}'}")
        print(f"  agora: {estado(alvo)}")


if __name__ == "__main__":
    main()
