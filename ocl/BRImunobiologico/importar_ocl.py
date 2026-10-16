"""Importa BRImunobiologico-mapeamentos.jsonl no OCL pela API e confere o resultado.

Uso (PowerShell):
    $env:OCL_TOKEN = "<token da API>"     # OCL: menu do usuário > API Token
    python importar_ocl.py                # importa e confere
    python importar_ocl.py --so-conferir  # só confere
    python importar_ocl.py --rest 225     # atualiza só o 225 pela API REST (teste)
    python importar_ocl.py --rest         # atualiza e retira todos os que têm id

O token fica só na variável de ambiente; o script não grava nem imprime o token.
"""
import json, os, pathlib, sys, time, urllib.request, urllib.error, uuid

API = os.environ.get("OCL_API", "https://oclapi2.ips.hsl.org.br")
LOTE = pathlib.Path(__file__).with_name("BRImunobiologico-mapeamentos.jsonl")
FONTE = "/orgs/MS/sources/BRImunobiologico/"


def chamar(metodo, caminho, corpo=None, tipo="application/json"):
    req = urllib.request.Request(API + caminho, data=corpo, method=metodo)
    tok = os.environ.get("OCL_TOKEN")
    if tok:
        req.add_header("Authorization", "Token " + tok)
    if corpo is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def importar():
    if not os.environ.get("OCL_TOKEN"):
        sys.exit("Defina OCL_TOKEN antes de importar.")
    st, quem = chamar("GET", "/user/")
    if st != 200:
        sys.exit(f"Token recusado ({st}).")
    print("Usuário:", quem.get("username"))
    limite = "----ocl" + uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{LOTE.name}\"\r\n"
             f"Content-Type: application/json\r\n\r\n").encode() + LOTE.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    st, r = chamar("POST", "/importers/bulk-import/?update_if_exists=true", corpo,
                   tipo=f"multipart/form-data; boundary={limite}")
    print("POST bulk-import:", st)
    if st not in (200, 201, 202):
        sys.exit(str(r)[:2000])
    tarefa = (r or {}).get("task") or (r or {}).get("id")
    print("Tarefa:", tarefa)
    for _ in range(120):
        time.sleep(5)
        st, r = chamar("GET", f"/importers/bulk-import/?task={tarefa}&result=summary")
        estado = r.get("state") if isinstance(r, dict) else None
        print(" ", st, estado or str(r)[:200])
        if st == 200 and estado not in ("PENDING", "STARTED", "RECEIVED", None):
            break
        if st == 200 and estado is None and r:
            break
    st, r = chamar("GET", f"/importers/bulk-import/?task={tarefa}&result=report")
    pathlib.Path(__file__).with_name("importacao-relatorio.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=1) if not isinstance(r, str) else r, encoding="utf-8")
    print("Relatório salvo em importacao-relatorio.json")


def conferir():
    st, ms = chamar("GET", FONTE + "mappings/?limit=1000&verbose=true&includeRetired=true")
    if st != 200:
        sys.exit(f"Falha ao ler os mapeamentos ({st}).")
    ativos = {}
    por_id = {m["id"]: m for m in ms}
    for m in ms:
        if not m.get("retired"):
            ativos.setdefault(m["from_concept_code"], []).append(m)
    erros = 0
    for linha in LOTE.read_text(encoding="utf-8").splitlines():
        l = json.loads(linha)
        if l.get("retired"):
            m = por_id.get(l["id"])
            ok = m is not None and m.get("retired")
            desc = f"retira {l['id']}"
        else:
            cod = l["from_concept_url"].rstrip("/").split("/")[-1]
            cand = [m for m in ativos.get(cod, []) if m.get("to_concept_code") == l["to_concept_code"]
                    and m.get("map_type") == l["map_type"] and "/SNOMED/sources/gps/" in (m.get("to_source_url") or "")]
            if "id" in l:
                cand = [m for m in cand if m["id"] == l["id"]]
            ok = len(cand) == 1
            desc = f"{cod} -> {l['to_concept_code']} {l['map_type']}" + (f" (id {l['id']})" if "id" in l else " (novo)")
        if not ok:
            erros += 1
            print("FALTA:", desc)
    # duplicados SNOMED ativos por conceito
    for cod, lst in sorted(ativos.items()):
        sct = [m for m in lst if "/SNOMED/" in (m.get("to_source_url") or "")]
        if len(sct) > 1:
            print("DUPLICADO:", cod, [(m["id"], m["to_concept_code"]) for m in sct])
            erros += 1
    print("Conferência:", "OK" if erros == 0 else f"{erros} problema(s)")


def rest(so=None):
    """Atualiza (PUT) e retira (DELETE) os mapeamentos com id, um a um.
    O bulk import desta instância não atualiza por id (49 'failed')."""
    if not os.environ.get("OCL_TOKEN"):
        sys.exit("Defina OCL_TOKEN.")
    for linha in LOTE.read_text(encoding="utf-8").splitlines():
        l = json.loads(linha)
        if "id" not in l or (so and l["id"] not in so):
            continue
        url = FONTE + f"mappings/{l['id']}/"
        if l.get("retired"):
            st, r = chamar("DELETE", url)
        else:
            corpo = {k: l[k] for k in ("map_type", "to_source_url", "to_concept_code", "to_concept_name")}
            corpo["update_comment"] = l.get("extras", {}).get("motivo", "revisão 16/10/2026")
            st, r = chamar("PUT", url, json.dumps(corpo).encode())
        print(l["id"], "DELETE" if l.get("retired") else "PUT", st, "" if st in (200, 204) else str(r)[:300])
    # 95: o mapeamento retirado 290 já tem o mesmo alvo; reativa em vez de criar
    if not so or "290" in so:
        st, r = chamar("PUT", FONTE + "mappings/290/", json.dumps({"retired": False, "update_comment": "reativado na revisão de 16/10/2026 (mesmo alvo do lote)"}).encode())
        print("290 reativar", st, "" if st == 200 else str(r)[:300])


if __name__ == "__main__":
    if "--rest" in sys.argv:
        i = sys.argv.index("--rest")
        so = [x for x in sys.argv[i + 1:] if not x.startswith("--")] or None
        rest(so)
    elif "--so-conferir" not in sys.argv:
        importar()
    conferir()
