import base64
import json
import time
import urllib.request
from uuid import uuid4
import pika

def management(path,body):
    token=base64.b64encode(b"fisi:fisi_dev").decode()
    request=urllib.request.Request("http://localhost:15672/api"+path,data=json.dumps(body).encode(),method="POST",headers={"authorization":"Basic "+token,"content-type":"application/json"})
    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response) if response.status!=204 else None

def main():
    management("/queues/%2F/cola_errores/get",{"count":100,"ackmode":"ack_requeue_false","encoding":"auto"})
    message_id,correlation=str(uuid4()),str(uuid4())
    event={"message_id":message_id,"event_type":"reserva.crear","event_version":1,"correlation_id":correlation,"causation_id":None,"id_orden":"ORD-2026-999999","timestamp":"2026-07-20T00:00:00Z","source":"test-dlq","attempt":0,"payload":{}}
    connection=pika.BlockingConnection(pika.ConnectionParameters("localhost",credentials=pika.PlainCredentials("fisi","fisi_dev")));channel=connection.channel();channel.basic_publish("fisi.ordenes.exchange","reserva.crear",json.dumps(event).encode(),pika.BasicProperties(delivery_mode=2));connection.close()
    deadline=time.time()+40;found=None
    while time.time()<deadline:
        messages=management("/queues/%2F/cola_errores/get",{"count":10,"ackmode":"ack_requeue_true","encoding":"auto"})
        for message in messages:
            payload=json.loads(message["payload"])
            if payload.get("message_id")==message_id:found=payload;break
        if found:break
        time.sleep(2)
    assert found and found["event_type"]=="error.tecnico" and found["attempt"]==4,found
    print(json.dumps(found,indent=2))

if __name__=="__main__":main()
