import json
import time
import urllib.error
import urllib.request

BASE="http://localhost:8000"
SUCCESS={"cliente_id":"CLI-001","nombre_cliente":"María López","ruc_cliente":"20481234567","items":[{"codigo_articulo":"ART-001","cantidad":2},{"codigo_articulo":"ART-002","cantidad":5}]}
REJECT={"cliente_id":"CLI-002","nombre_cliente":"María López","ruc_cliente":"20481234567","items":[{"codigo_articulo":"ART-005","cantidad":99}]}

def request(method,path,data=None):
    body=json.dumps(data,ensure_ascii=False).encode() if data else None
    req=urllib.request.Request(BASE+path,data=body,method=method,headers={"content-type":"application/json"})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def wait_state(order_id,expected,timeout=120):
    deadline=time.time()+timeout
    while time.time()<deadline:
        order=request("GET",f"/ordenes/{order_id}")
        if order["estado"]==expected:return order
        if order["estado"] in {"RECHAZADA","ERROR"} and order["estado"]!=expected:raise AssertionError(order)
        time.sleep(2)
    raise AssertionError(f"timeout esperando {expected}: {order}")

def main():
    created=request("POST","/ordenes",SUCCESS);assert created["estado"]=="PENDIENTE"
    confirmed=wait_state(created["id_orden"],"CONFIRMADA")
    assert confirmed["reserva_id"] and confirmed["numero_factura"] and confirmed["cuenta_cobrar_id"]
    history=request("GET",f"/ordenes/{created['id_orden']}/historial")
    states={h["estado"] for h in history};assert {"PENDIENTE","VALIDANDO_STOCK","RESERVADA","FACTURADA","CUENTA_CREADA","CONFIRMADA"}<=states
    assert {str(h["correlation_id"]) for h in history}=={created["correlation_id"]}
    rejected=request("POST","/ordenes",REJECT);order=wait_state(rejected["id_orden"],"RECHAZADA")
    assert order["motivo_error"] and not order["reserva_id"] and not order["numero_factura"] and not order["cuenta_cobrar_id"]
    print(json.dumps({"success":confirmed,"rejected":order},ensure_ascii=False,indent=2,default=str))

if __name__=="__main__":main()
