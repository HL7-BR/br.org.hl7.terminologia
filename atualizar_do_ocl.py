#!/usr/bin/env python3
"""Atualiza os CodeSystems e ValueSets de input/resources a partir do OCL.

O pacote de terminologia saía com os CodeSystems vazios (content = not-present,
version = HEAD) e os ValueSets com include.version = HEAD, exportados do OCL e
nunca atualizados. Este script busca, na API FHIR do OCL, a última versão
liberada de cada CodeSystem e reescreve o arquivo local.

Uso (na raiz do repositório):
    python atualizar_do_ocl.py                     # todos os CodeSystems
    python atualizar_do_ocl.py --ids BRImunobiologico,BRDose
    python atualizar_do_ocl.py --max 20000         # limite de conceitos para content = complete
    python atualizar_do_ocl.py --vs-todos          # ValueSet com o mesmo id do CodeSystem passa a incluir o CodeSystem inteiro
    python atualizar_do_ocl.py --seco              # só mostra o que mudaria
    python atualizar_do_ocl.py --usar-head         # fonte sem versão liberada: lê o HEAD (version = HEAD)
    python atualizar_do_ocl.py --liberar 2026-10-19  # cria e libera essa versão nas fontes sem versão liberada (precisa de OCL_TOKEN)
    python atualizar_do_ocl.py --corrigir-urls [--seco]  # acerta a canonical_url das fontes do MS no OCL (precisa de OCL_TOKEN)

Regras:
- CodeSystem: mantém os metadados locais; troca version pela versão liberada no
  OCL; com até --max conceitos (padrão 10000), content = complete e os
  conceitos (code, display, inactive); acima disso, content = not-present.
  As propriedades internas do OCL (conceptclass, datatype) não entram, e
  inactive vai como boolean (o OCL declara Coding).
- ValueSet: retira include.version = HEAD. Com --vs-todos, o ValueSet de mesmo
  id do CodeSystem deixa de enumerar conceitos (a lista do OCL está
  desatualizada) e inclui o CodeSystem inteiro.
- Relatório em ocl-atualizacao.json.
"""
import json, pathlib, sys, urllib.parse, urllib.request, urllib.error

OCL = "https://oclapi2.ips.hsl.org.br"
RES = pathlib.Path("input/resources")
INACTIVE = {"code": "inactive", "uri": "http://hl7.org/fhir/concept-properties#inactive",
            "description": "Conceito inativo (retirado no OCL).", "type": "boolean"}


def arg(nome, padrao=None):
    return sys.argv[sys.argv.index(nome) + 1] if nome in sys.argv else padrao


def _get(caminho):
    req = urllib.request.Request(OCL + caminho, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r), r.headers


_FONTES = None


def fontes():
    """canonical_url -> URL da fonte no OCL (todas as organizações)."""
    global _FONTES
    if _FONTES is None:
        # limite acima de 500 o OCL ignora (devolve 25); pagina pelo cabeçalho next
        lista, pagina = [], 1
        while True:
            lote, h = _get(f"/sources/?limit=500&page={pagina}&verbose=true")
            lista += lote
            if not h.get("next") or not lote:
                break
            pagina += 1
        _FONTES = {"_por_id": {}}
        for f in lista:
            can = (f.get("canonical_url") or "").rstrip("/")
            if can:
                _FONTES.setdefault(can, f["url"])
            if f.get("owner") == "MS":
                _FONTES["_por_id"].setdefault(_norm(f.get("short_code") or f.get("id") or ""), (f["url"], can))
    return _FONTES


def _norm(i):
    return i.lower().replace("_", "-")


def buscar_cs(url):
    """Lê a última versão liberada da fonte pela API REST do OCL (a busca FHIR
    por url falha para várias fontes e a leitura FHIR corta em 1000 conceitos)."""
    try:
        fonte, aviso = fontes().get(url.rstrip("/")), None
        if not fonte:
            achado = fontes()["_por_id"].get(_norm(url.rstrip("/").split("/")[-1]))
            if not achado:
                return None, "não está no OCL"
            fonte, can = achado
            aviso = f"achado pelo id em {fonte}; canonical_url no OCL diverge: {can or '(vazia)'}"
        versoes, _h = _get(fonte + "versions/?limit=500")
        liberadas = [v for v in versoes if v.get("released") and v.get("id") != "HEAD"]
        if not liberadas:
            if "--usar-head" not in sys.argv:
                return None, "sem versão liberada no OCL (use --usar-head para ler o HEAD)"
            ver, caminho = "HEAD", fonte
        else:
            ver = liberadas[0]["id"]
            caminho = fonte + urllib.parse.quote(ver) + "/"
        conceitos, pagina = [], 1
        while True:
            lote, h = _get(caminho + f"concepts/?limit=1000&page={pagina}&includeRetired=true")
            conceitos += lote
            if not h.get("next") or not lote:
                break
            pagina += 1
        cs = {"version": ver, "aviso": aviso, "concept": [
            {"code": c["id"], "display": c.get("display_name"),
             "property": [{"code": "inactive", "valueBoolean": True}] if c.get("retired") else []}
            for c in conceitos]}
        return cs, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # rede
        return None, str(e)


def limpar_conceito(c):
    novo = {"code": c["code"]}
    if c.get("display"):
        novo["display"] = c["display"]
    inativo = any(p.get("code") == "inactive" and (p.get("valueBoolean") is True or
                  p.get("valueString") in ("true", True) or get_code(p) == "true")
                  for p in c.get("property", []))
    if inativo:
        novo["property"] = [{"code": "inactive", "valueBoolean": True}]
    return novo, inativo


def get_code(p):
    v = p.get("valueCoding") or {}
    return v.get("code")


def atualizar_cs(caminho, maximo, seco):
    local = json.loads(caminho.read_text(encoding="utf-8"))
    ocl, erro = buscar_cs(local["url"])
    if erro:
        return {"arquivo": caminho.name, "erro": erro}
    conceitos = [limpar_conceito(c) for c in ocl.get("concept", [])]
    n = len(conceitos)
    novo = {k: v for k, v in local.items() if k not in ("version", "content", "count", "concept", "property")}
    novo["version"] = ocl.get("version")
    novo["count"] = n
    if n and n <= maximo:
        novo["content"] = "complete"
        if any(i for _c, i in conceitos):
            novo["property"] = [INACTIVE]
        novo["concept"] = [c for c, _i in conceitos]
    else:
        novo["content"] = "not-present"
    # ordem: concept por último
    if "concept" in novo:
        novo["concept"] = novo.pop("concept")
    rel = {"arquivo": caminho.name, "url": local["url"], **({"aviso": ocl["aviso"]} if ocl.get("aviso") else {}),
           "versao_antes": local.get("version"),
           "versao_ocl": ocl.get("version"), "conceitos": n, "content": novo["content"],
           "inativos": sum(1 for _c, i in conceitos if i)}
    if not seco:
        caminho.write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rel


def atualizar_vs(caminho, cs_por_url, vs_todos, seco):
    vs = json.loads(caminho.read_text(encoding="utf-8"))
    mudou, notas = False, []
    for inc in vs.get("compose", {}).get("include", []):
        if inc.get("version") == "HEAD":
            del inc["version"]
            mudou = True
        cs = cs_por_url.get(inc.get("system"))
        if cs and inc.get("concept"):
            codigos = {c["code"]: c for c in cs.get("concept", [])}
            if codigos:
                falta = [c["code"] for c in inc["concept"] if c["code"] not in codigos]
                inat = [c["code"] for c in inc["concept"] if any(p.get("code") == "inactive" for p in codigos.get(c["code"], {}).get("property", []))]
                fora = [k for k, c in codigos.items() if k not in {x["code"] for x in inc["concept"]} and not c.get("property")]
                if falta: notas.append(f"{len(falta)} códigos fora do CodeSystem: {falta[:10]}")
                if inat: notas.append(f"{len(inat)} códigos inativos: {inat[:10]}")
                if fora: notas.append(f"{len(fora)} conceitos ativos do CodeSystem fora do ValueSet: {fora[:10]}")
        if vs_todos and cs and cs.get("id") == vs.get("id") and inc.get("concept"):
            inc.pop("concept")
            mudou = True
            notas.append("passa a incluir o CodeSystem inteiro")
    if mudou and not seco:
        caminho.write_text(json.dumps(vs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"arquivo": caminho.name, "mudou": mudou, "notas": notas} if (mudou or notas) else None


def liberar(versao):
    """Cria e libera a versão `versao` nas fontes sem versão liberada (lidas do último relatório)."""
    import os
    tok = os.environ.get("OCL_TOKEN")
    if not tok:
        sys.exit("Defina OCL_TOKEN.")
    rel = json.loads(pathlib.Path("ocl-atualizacao.json").read_text(encoding="utf-8"))
    alvos = [r for r in rel["codesystems"] if "sem versão liberada" in r.get("erro", "")]
    print(len(alvos), "fontes sem versão liberada")
    for r in alvos:
        local = json.loads((RES / r["arquivo"]).read_text(encoding="utf-8"))
        url = local["url"].rstrip("/")
        fonte = fontes().get(url) or (fontes()["_por_id"].get(_norm(url.split("/")[-1])) or (None,))[0]
        if not fonte:
            print(r["arquivo"], "fonte não encontrada")
            continue
        corpo = json.dumps({"id": versao, "released": True,
                            "description": "Versão liberada para o pacote de terminologia"}).encode()
        req = urllib.request.Request(OCL + fonte + "versions/", data=corpo, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": "Token " + tok})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                print(fonte, versao, resp.status)
        except urllib.error.HTTPError as e:
            print(fonte, versao, e.code, e.read().decode("utf-8", "replace")[:200])


def corrigir_urls(seco):
    """Acerta a canonical_url das fontes do MS no OCL para a URL do CodeSystem deste repositório."""
    import os
    tok = os.environ.get("OCL_TOKEN")
    if not tok and not seco:
        sys.exit("Defina OCL_TOKEN.")
    n = 0
    for f in sorted(RES.glob("CodeSystem-*.json")):
        url = json.loads(f.read_text(encoding="utf-8"))["url"].rstrip("/")
        if fontes().get(url):
            continue
        achado = fontes()["_por_id"].get(_norm(url.split("/")[-1]))
        if not achado:
            continue
        fonte, can = achado
        n += 1
        print(f"{fonte}: {can or '(vazia)'} -> {url}")
        if seco:
            continue
        req = urllib.request.Request(OCL + fonte, data=json.dumps({"canonical_url": url}).encode(), method="PUT",
                                     headers={"Content-Type": "application/json", "Authorization": "Token " + tok})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                print("   ", resp.status)
        except urllib.error.HTTPError as e:
            print("   ", e.code, e.read().decode("utf-8", "replace")[:200])
    print(n, "fontes com canonical_url divergente" + (" (simulação)" if seco else " corrigidas"))


def main():
    if "--corrigir-urls" in sys.argv:
        corrigir_urls("--seco" in sys.argv)
        return
    if "--liberar" in sys.argv:
        liberar(arg("--liberar"))
        return
    seco = "--seco" in sys.argv
    maximo = int(arg("--max", "10000"))
    ids = arg("--ids")
    ids = set(ids.split(",")) if ids else None
    rel = {"codesystems": [], "valuesets": []}
    cs_por_url = {}
    for f in sorted(RES.glob("CodeSystem-*.json")):
        cid = f.stem.split("-", 1)[1]
        if ids and cid not in ids:
            continue
        r = atualizar_cs(f, maximo, seco)
        rel["codesystems"].append(r)
        print(r)
        if "erro" not in r:
            cs_por_url[r["url"]] = json.loads(f.read_text(encoding="utf-8")) if not seco else {}
    for f in sorted(RES.glob("ValueSet-*.json")):
        if ids and f.stem.split("-", 1)[1] not in ids:
            continue
        r = atualizar_vs(f, cs_por_url, "--vs-todos" in sys.argv, seco)
        if r:
            rel["valuesets"].append(r)
            print(r)
    pathlib.Path("ocl-atualizacao.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in rel["codesystems"] if "erro" not in r)
    print(f"\nCodeSystems atualizados: {ok} de {len(rel['codesystems'])}; ValueSets alterados: "
          f"{sum(1 for r in rel['valuesets'] if r['mudou'])}. Relatório em ocl-atualizacao.json"
          + (" (simulação: nada gravado)" if seco else ""))


if __name__ == "__main__":
    main()
