#!/usr/bin/env python3
"""Popula a coleção BRNomeExame (ValueSet) no OCL com todos os conceitos ativos
do HEAD das fontes BRNomeExameLOINC e BRNomeExameGAL, como no ValueSet
BRNomeExame-2.0 do REL-IG (include dos dois CodeSystems inteiros).

Uso (PowerShell, uma linha por vez):
    $env:OCL_TOKEN = "SEU_TOKEN"
    python popular_colecao_BRNomeExame.py --seco          # só mostra o que faria
    python popular_colecao_BRNomeExame.py                  # grava as referências
    python popular_colecao_BRNomeExame.py --corrigir-canonical   # também corrige o canonical

O token não é gravado nem impresso. A leitura (--seco) não precisa de token.
Autoria: Jussara Macedo Pinho Rötzsch.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br").rstrip("/")
TOKEN = os.environ.get("OCL_TOKEN", "").strip().strip('"').strip("<>")
ORG = "MS"
COLECAO = "BRNomeExame"
FONTES = ["BRNomeExameLOINC", "BRNomeExameGAL"]
CANONICAL_CERTO = "https://terminologia.saude.gov.br/fhir/ValueSet/BRNomeExame"
LOTE = 100


def chamar(metodo, caminho, corpo=None, auth=True):
    url = caminho if caminho.startswith("http") else API + caminho
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Accept", "application/json")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", "Token " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500], {}


def conceitos_head(fonte):
    """Lista os conceitos ativos do HEAD da fonte, página a página."""
    todos, pagina = [], 1
    while True:
        st, dados, _ = chamar("GET", f"/orgs/{ORG}/sources/{fonte}/concepts/?limit=500&page={pagina}", auth=False)
        if st != 200:
            sys.exit(f"Erro {st} ao ler {fonte}: {dados}")
        if not dados:
            break
        todos += [c for c in dados if not c.get("retired")]
        if len(dados) < 500:
            break
        pagina += 1
    return todos


def resumo_colecao():
    st, dados, _ = chamar("GET", f"/orgs/{ORG}/collections/{COLECAO}/?includeSummary=true", auth=False)
    if st != 200:
        sys.exit(f"Erro {st} ao ler a coleção: {dados}")
    return dados


def main():
    seco = "--seco" in sys.argv
    corrigir = "--corrigir-canonical" in sys.argv

    if not seco:
        if not TOKEN:
            sys.exit("Defina OCL_TOKEN antes (ou rode com --seco).")
        st, eu, _ = chamar("GET", "/user/")
        if st != 200:
            sys.exit(f"Token recusado ({st}).")
        print(f"Usuário: {eu.get('username')}")

    col = resumo_colecao()
    print(f"Coleção {COLECAO}: canonical {col.get('canonical_url')}; "
          f"conceitos ativos antes: {(col.get('summary') or {}).get('active_concepts')}")

    expressoes, problemas = [], []
    for fonte in FONTES:
        cs = conceitos_head(fonte)
        print(f"{fonte} (HEAD): {len(cs)} conceitos ativos")
        for c in cs:
            cid = c.get("id") or ""
            if "/" in cid or cid.lower().startswith("http") or not cid.strip():
                problemas.append((fonte, cid, c.get("display_name")))
                continue
            expressoes.append(f"/orgs/{ORG}/sources/{fonte}/concepts/{urllib.request.quote(cid, safe='')}/")

    for fonte, cid, nome in problemas:
        print(f"  ignorado (código inválido): {fonte} | {cid} | {nome}")
    print(f"Referências a incluir: {len(expressoes)}")

    if seco:
        print("Modo seco: nada foi gravado.")
        return

    if corrigir and col.get("canonical_url") != CANONICAL_CERTO:
        st, r, _ = chamar("PUT", f"/orgs/{ORG}/collections/{COLECAO}/", {"canonical_url": CANONICAL_CERTO})
        print(f"Canonical corrigido para {CANONICAL_CERTO}" if st in (200, 201) else f"Falha ao corrigir canonical ({st}): {r}")

    incluidas, recusadas = 0, []
    for i in range(0, len(expressoes), LOTE):
        lote = expressoes[i:i + LOTE]
        st, r, _ = chamar("PUT", f"/orgs/{ORG}/collections/{COLECAO}/references/",
                          {"data": {"expressions": lote}})
        if st not in (200, 201, 202):
            sys.exit(f"Erro {st} no lote {i // LOTE + 1}: {r}")
        for item in (r or []):
            if item.get("added"):
                incluidas += 1
            else:
                recusadas.append((item.get("expression"), item.get("message")))
        print(f"  lote {i // LOTE + 1}: {len(lote)} enviadas")

    print(f"Incluídas: {incluidas}; recusadas: {len(recusadas)}")
    for exp, msg in recusadas[:30]:
        print(f"  recusada: {exp} | {msg}")

    col = resumo_colecao()
    print(f"Conceitos ativos depois: {(col.get('summary') or {}).get('active_concepts')}")
    print("Confira no OCL e libere uma nova versão da coleção quando estiver de acordo.")


if __name__ == "__main__":
    main()
