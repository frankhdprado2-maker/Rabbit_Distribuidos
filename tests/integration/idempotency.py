import json
import subprocess
import time
import urllib.request
from uuid import uuid4

import pika

BASE="http://localhost:8000"
ORDER={"cliente_id":"CLI-IDEMP","nombre_cliente":"Prueba Idempotencia","ruc_cliente":"20481234567","items":[{"codigo_articulo":"ART-001","cantidad":1}]}

def http(method,path,data=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data else None,method=method,headers={"content-type":"application/json"})
    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)

def sql(user,database,query):
    return subprocess.check_output(["docker","compose","exec","-T","postgres","psql","-U",user,"-d",database,"-tAc",query],text=True).strip()

def main():
    created=http("POST","/ordenes",ORDER)
    for _ in range(60):
        order=http("GET",f"/ordenes/{created['id_orden']}")
        if order["estado"]=="CONFIRMADA":break
        time.sleep(2)
    else:raise AssertionError(order)
    history=http("GET",f"/ordenes/{created['id_orden']}/historial")
    message_id=next(x["message_id"] for x in history if x["evento"]=="inventario.validar")
    before=(sql("inventario_user","db_inventario","SELECT cantidad_existente FROM articulos WHERE codigo_articulo='ART-001'"),
            sql("reserva_user","db_reserva",f"SELECT count(*) FROM reservas WHERE id_orden='{created['id_orden']}'"),
            sql("facturacion_user","db_facturacion",f"SELECT count(*) FROM facturas WHERE id_orden='{created['id_orden']}'"),
            sql("cxc_user","db_cxc",f"SELECT count(*) FROM cuentas_cobrar WHERE id_orden='{created['id_orden']}'"))
    assert before[1:]==("1","1","1"),before
    event={"message_id":message_id,"event_type":"inventario.validar","event_version":1,"correlation_id":created["correlation_id"],"causation_id":None,"id_orden":created["id_orden"],"timestamp":"2026-07-20T00:00:00Z","source":"test-idempotencia","attempt":0,"payload":{"cliente":{"cliente_id":ORDER["cliente_id"],"nombre_cliente":ORDER["nombre_cliente"],"ruc_cliente":ORDER["ruc_cliente"]},"items":ORDER["items"],"trace":[]}}
    connection=pika.BlockingConnection(pika.ConnectionParameters("localhost",credentials=pika.PlainCredentials("fisi","fisi_dev")))
    channel=connection.channel();channel.confirm_delivery()
    for _ in range(2):channel.basic_publish("fisi.ordenes.exchange","inventario.validar",json.dumps(event).encode(),pika.BasicProperties(delivery_mode=2,message_id=message_id,correlation_id=created["correlation_id"]))
    connection.close();time.sleep(4)
    after=(sql("inventario_user","db_inventario","SELECT cantidad_existente FROM articulos WHERE codigo_articulo='ART-001'"),
           sql("reserva_user","db_reserva",f"SELECT count(*) FROM reservas WHERE id_orden='{created['id_orden']}'"),
           sql("facturacion_user","db_facturacion",f"SELECT count(*) FROM facturas WHERE id_orden='{created['id_orden']}'"),
           sql("cxc_user","db_cxc",f"SELECT count(*) FROM cuentas_cobrar WHERE id_orden='{created['id_orden']}'"))
    assert before==after,(before,after)
    print(json.dumps({"order":created["id_orden"],"message_id":message_id,"before":before,"after":after}))

if __name__=="__main__":main()
