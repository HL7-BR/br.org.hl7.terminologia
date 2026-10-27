"""Cria no OCL (org HL7) o CodeSystem v2-0443 (Provider role) e o ValueSet
immunization-function do FHIR R4, a partir dos JSON oficiais desta pasta.

    https://hl7.org/fhir/R4/v2/0443/index.html            -> v2-0443.cs.json
    http://hl7.org/fhir/ValueSet/immunization-function    -> valueset-immunization-function.json

Segue o que o OCL já tem na org HL7: tabela v2 como fonte (Dictionary,
versão SemVer liberada, como a v2-0203 2.9.0) e ValueSet como coleção
(Value Set, com a versão do FHIR liberada, como a immunization-status 4.0.1).

Uso (PowerShell, na pasta do script):
    python importar_ocl.py --seco         # mostra o plano e confere o que já existe (sem token)
    $env:OCL_TOKEN = "<token da API>"     # OCL: menu do usuário > API Token
    python importar_ocl.py                # cria fonte, conceitos, coleção, referências e versões
    python importar_ocl.py --so-conferir  # só confere

O token fica só na variável de ambiente; o script não grava nem imprime o token.
Autoria: Jussara Macedo Pinho Rötzsch.
"""
import json, os, pathlib, sys, urllib.request, urllib.error

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br")
AQUI = pathlib.Path(__file__).parent
CS = json.loads((AQUI / "v2-0443.cs.json").read_text(encoding="utf-8"))
VS = json.loads((AQUI / "valueset-immunization-function.json").read_text(encoding="utf-8"))

FONTE = "/orgs/HL7/sources/v2-0443/"
COLECAO = "/orgs/HL7/collections/immunization-function/"
VERSAO_FONTE = "2.9.0"          # CodeSystem 2.9, em SemVer como as outras v2 do OCL
VERSAO_COLECAO = VS["version"]  # 4.0.1


def chamar(metodo, caminho, corpo=None):
    req = urllib.request.Request(API + caminho, method=metodo,
                                 data=None if corpo is None else json.dumps(corpo).encode())
    tok = os.environ.get("OCL_TOKEN")
    if tok:
        req.add_header("Authorization", "Token " + tok)
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def fonte():
    return {"id": "v2-0443", "short_code": "v2-0443", "name": CS["name"], "full_name": CS["title"],
            "source_type": "Dictionary", "canonical_url": CS["url"], "default_locale": "en",
            "supported_locales": "en", "description": CS["description"], "public_access": "View",
            "case_sensitive": True, "version_needed": True}


def conceitos():
    return [{"id": c["code"], "concept_class": "Misc", "datatype": "Text",
             "names": [{"name": c["display"].strip(), "locale": "en", "locale_preferred": True,
                        "name_type": "Fully Specified"}]} for c in CS["concept"]]


def colecao():
    return {"id": "immunization-function", "short_code": "immunization-function", "name": VS["name"],
            "full_name": VS["title"], "collection_type": "Value Set", "canonical_url": VS["url"],
            "default_locale": "en", "supported_locales": "en", "description": VS["description"],
            "public_access": "View", "autoexpand_head": True}


def expressoes():
    inc = VS["compose"]["include"]
    assert len(inc) == 1 and inc[0]["system"] == CS["url"]
    return [FONTE + f"concepts/{c['code']}/" for c in inc[0]["concept"]]


def existe(caminho):
    st, _ = chamar("GET", caminho)
    return st == 200


def plano():
    print(f"API: {API}")
    print(f"Fonte {FONTE} ({CS['title']}): {'JÁ EXISTE' if existe(FONTE) else 'nova'}")
    print(f"  {len(CS['concept'])} conceitos: " + ", ".join(c["code"] for c in CS["concept"]))
    print(f"  versão {VERSAO_FONTE} liberada")
    print(f"Coleção {COLECAO} ({VS['title']}): {'JÁ EXISTE' if existe(COLECAO) else 'nova'}")
    print("  referências: " + ", ".join(expressoes()))
    print(f"  versão {VERSAO_COLECAO} liberada")


def ok(rotulo, st, r, esperado=(200, 201)):
    print(f"{rotulo}: {st}", "" if st in esperado else str(r)[:400])
    if st not in esperado:
        sys.exit("Parado no primeiro erro.")


def importar():
    if not os.environ.get("OCL_TOKEN"):
        sys.exit("Defina OCL_TOKEN.")
    st, quem = chamar("GET", "/user/")
    if st != 200:
        sys.exit(f"Token recusado ({st}).")
    print("Usuário:", quem.get("username"))
    if existe(FONTE) or existe(COLECAO):
        sys.exit("Fonte ou coleção já existe; nada foi feito. Rode --so-conferir.")
    ok("POST fonte", *chamar("POST", "/orgs/HL7/sources/", fonte()))
    for c in conceitos():
        ok(f"POST conceito {c['id']}", *chamar("POST", FONTE + "concepts/", c))
    ok(f"POST versão {VERSAO_FONTE}", *chamar("POST", FONTE + "versions/", {
        "id": VERSAO_FONTE, "released": True,
        "description": f"HL7 v2 table 0443 (Provider role), CodeSystem {CS['version']} do FHIR R4"}))
    ok("POST coleção", *chamar("POST", "/orgs/HL7/collections/", colecao()))
    ok("PUT referências", *chamar("PUT", COLECAO + "references/?cascade=none",
                                    {"data": {"expressions": expressoes()}}))
    ok(f"POST versão {VERSAO_COLECAO}", *chamar("POST", COLECAO + "versions/", {
        "id": VERSAO_COLECAO, "released": True, "description": f"{VS['title']} do FHIR R4 ({VERSAO_COLECAO})"}))


def conferir():
    erros = 0
    st, cs = chamar("GET", FONTE + "concepts/?limit=100")
    codigos = {c["id"]: c["display_name"] for c in cs} if st == 200 else {}
    for c in CS["concept"]:
        if codigos.get(c["code"]) != c["display"].strip():
            erros += 1
            print("FALTA conceito:", c["code"], c["display"].strip(), "| OCL:", codigos.get(c["code"]))
    st, vs = chamar("GET", f"/orgs/HL7/sources/v2-0443/versions/")
    if st != 200 or not any(v["id"] == VERSAO_FONTE and v.get("released") for v in vs):
        erros += 1
        print(f"FALTA versão liberada {VERSAO_FONTE} da fonte")
    st, refs = chamar("GET", COLECAO + "references/?limit=100")
    tem = {r["expression"] for r in refs} if st == 200 else set()
    for e in expressoes():
        if e not in tem:
            erros += 1
            print("FALTA referência:", e)
    st, vs = chamar("GET", COLECAO + "versions/")
    if st != 200 or not any(v["id"] == VERSAO_COLECAO and v.get("released") for v in vs):
        erros += 1
        print(f"FALTA versão liberada {VERSAO_COLECAO} da coleção")
    for caminho in (f"/fhir/CodeSystem/?url={CS['url']}", f"/fhir/ValueSet/?url={VS['url']}"):
        st, b = chamar("GET", caminho)
        n = b.get("total") if isinstance(b, dict) else None
        print(f"FHIR {caminho}: {st}, total {n}")
    print("Conferência:", "OK" if erros == 0 else f"{erros} problema(s)")


if __name__ == "__main__":
    if "--seco" in sys.argv:
        plano()
    elif "--so-conferir" in sys.argv:
        conferir()
    else:
        importar()
        conferir()
