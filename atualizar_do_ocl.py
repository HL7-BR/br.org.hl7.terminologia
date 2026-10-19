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


def buscar_cs(url):
    q = OCL + "/fhir/CodeSystem/?url=" + urllib.parse.quote(url, safe="")
    req = urllib.request.Request(q, headers={"Accept": "application/fhir+json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            b = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # rede
        return None, str(e)
    ents = b.get("entry") or []
    if not ents:
        return None, "não está no OCL"
    return ents[0]["resource"], None


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
    rel = {"arquivo": caminho.name, "url": local["url"], "versao_antes": local.get("version"),
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


def main():
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
