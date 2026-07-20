package pe.edu.fisi.inventario;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.node.*;
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;

@SpringBootApplication
public class Application {
    static final String EXCHANGE="fisi.ordenes.exchange", DLX="fisi.ordenes.dlx", SERVICE="inventario";
    public static void main(String[] args) { SpringApplication.run(Application.class, args); }
    @Bean ObjectMapper objectMapper() { return JsonMapper.builder().findAndAddModules().enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES).build(); }
    @Bean ApplicationRunner init(JdbcTemplate db) { return args -> {
        db.execute("CREATE TABLE IF NOT EXISTS articulos(codigo_articulo TEXT PRIMARY KEY,nombre_articulo TEXT NOT NULL,precio_unitario NUMERIC(14,2) NOT NULL,cantidad_existente INT NOT NULL,activo BOOLEAN NOT NULL)");
        db.execute("CREATE TABLE IF NOT EXISTS movimientos_inventario(id BIGSERIAL PRIMARY KEY,id_orden TEXT NOT NULL,codigo_articulo TEXT NOT NULL,cantidad INT NOT NULL,tipo TEXT NOT NULL,fecha TIMESTAMPTZ DEFAULT NOW(),UNIQUE(id_orden,codigo_articulo,tipo))");
        db.execute("CREATE TABLE IF NOT EXISTS mensajes_procesados(message_id UUID PRIMARY KEY,id_orden TEXT NOT NULL,procesado_en TIMESTAMPTZ DEFAULT NOW())");
        db.update("INSERT INTO articulos VALUES('ART-001','Laptop FISI',1500.00,100,true),('ART-002','Mouse ergonomico',50.00,50,true),('ART-005','Monitor con stock bajo',800.00,2,true) ON CONFLICT(codigo_articulo) DO NOTHING");
    }; }

    @JsonIgnoreProperties(ignoreUnknown=false)
    public record Envelope(UUID message_id, String event_type, int event_version, UUID correlation_id,
        UUID causation_id, String id_orden, Instant timestamp, String source, int attempt, ObjectNode payload) {}

    @Bean InventoryConsumer consumer(ObjectMapper mapper, JdbcTemplate db, RabbitTemplate rabbit, TransactionTemplate tx) {
        return new InventoryConsumer(mapper, db, rabbit, tx);
    }

    static class InventoryConsumer {
        final ObjectMapper mapper; final JdbcTemplate db; final RabbitTemplate rabbit; final TransactionTemplate tx;
        final int maxRetries=Integer.parseInt(System.getenv().getOrDefault("MAX_RETRIES","3"));
        InventoryConsumer(ObjectMapper m, JdbcTemplate d, RabbitTemplate r, TransactionTemplate t){mapper=m;db=d;rabbit=r;tx=t;}

        @RabbitListener(queues="cola_inventario")
        public void receive(Message message, Channel channel) throws Exception {
            long started=System.nanoTime(); JsonNode raw=null;
            try {
                raw=mapper.readTree(new String(message.getBody(), StandardCharsets.UTF_8));
                Envelope event=mapper.treeToValue(raw, Envelope.class); validate(event, message.getMessageProperties().getReceivedRoutingKey());
                String result=tx.execute(status -> process(event));
                channel.basicAck(message.getMessageProperties().getDeliveryTag(),false);
                log(event,"stock_validado",result,(System.nanoTime()-started)/1_000_000);
            } catch (Exception ex) {
                if(raw==null){ channel.basicNack(message.getMessageProperties().getDeliveryTag(),false,false); return; }
                retry(raw.deepCopy(), message.getMessageProperties(), ex.getMessage());
                channel.basicAck(message.getMessageProperties().getDeliveryTag(),false);
            }
        }

        void validate(Envelope e,String key){
            if(!Set.of("inventario.validar","reserva.liberar").contains(e.event_type()) || !e.event_type().equals(key) || e.event_version()!=1 || e.attempt()<0) throw new IllegalArgumentException("envelope invalido");
            JsonNode p=e.payload(); if(!p.hasNonNull("cliente") || !p.has("items") || !p.get("items").isArray() || p.get("items").isEmpty()) throw new IllegalArgumentException("payload invalido");
            if("inventario.validar".equals(e.event_type())) { Set<String> allowed=Set.of("cliente","items","trace"); p.fieldNames().forEachRemaining(k->{if(!allowed.contains(k))throw new IllegalArgumentException("propiedad desconocida: "+k);}); }
        }

        String process(Envelope event){
            if(Boolean.TRUE.equals(db.query("SELECT EXISTS(SELECT 1 FROM mensajes_procesados WHERE message_id=?)", rs->{rs.next();return rs.getBoolean(1);}, event.message_id()))) return "duplicate";
            if("reserva.liberar".equals(event.event_type())) return release(event);
            ArrayNode enriched=mapper.createArrayNode(), errors=mapper.createArrayNode();
            for(JsonNode item:event.payload().withArray("items")){
                String code=item.path("codigo_articulo").asText(); int qty=item.path("cantidad").asInt();
                if(code.isBlank()||qty<1) throw new IllegalArgumentException("item invalido");
                List<Map<String,Object>> rows=db.queryForList("SELECT nombre_articulo,precio_unitario,cantidad_existente,activo FROM articulos WHERE codigo_articulo=? FOR UPDATE",code);
                if(rows.isEmpty()){ errors.add(error(code,"PRODUCTO_NO_EXISTE",0,qty)); continue; }
                Map<String,Object> row=rows.getFirst();
                if(!(Boolean)row.get("activo")){ errors.add(error(code,"PRODUCTO_INACTIVO",(Integer)row.get("cantidad_existente"),qty)); continue; }
                int stock=(Integer)row.get("cantidad_existente"); if(stock<qty){ errors.add(error(code,"STOCK_INSUFICIENTE",stock,qty)); continue; }
                ObjectNode out=mapper.createObjectNode(); out.put("codigo_articulo",code);out.put("cantidad",qty);
                out.put("nombre_articulo",String.valueOf(row.get("nombre_articulo")));out.put("precio_unitario",Double.parseDouble(String.valueOf(row.get("precio_unitario"))));enriched.add(out);
            }
            ObjectNode payload=event.payload().deepCopy(); String nextType;
            if(!errors.isEmpty()){
                payload.removeAll();payload.put("error_type","BUSINESS");payload.put("error_code","STOCK_INVALIDO");payload.put("message","Producto inexistente, inactivo o stock insuficiente.");payload.set("details",errors);payload.put("retryable",false);payload.set("trace",trace(event,"VALIDANDO_STOCK","inventario.validar","Inventario rechazo la orden."));nextType="orden.error";
            } else {
                for(JsonNode item:enriched){String code=item.path("codigo_articulo").asText();int qty=item.path("cantidad").asInt();db.update("UPDATE articulos SET cantidad_existente=cantidad_existente-? WHERE codigo_articulo=?",qty,code);db.update("INSERT INTO movimientos_inventario(id_orden,codigo_articulo,cantidad,tipo) VALUES(?,?,?,'RESERVA') ON CONFLICT DO NOTHING",event.id_orden(),code,qty);}
                payload.set("items",enriched);payload.set("trace",trace(event,"VALIDANDO_STOCK","inventario.validar","Stock validado y descontado una sola vez."));nextType="reserva.crear";
            }
            ObjectNode next=next(event,nextType,payload); publish(nextType,next); db.update("INSERT INTO mensajes_procesados(message_id,id_orden) VALUES(?,?)",event.message_id(),event.id_orden()); return nextType;
        }

        String release(Envelope event){
            for(JsonNode item:event.payload().withArray("items")){
                String code=item.path("codigo_articulo").asText(); int qty=item.path("cantidad").asInt();
                Integer reserved=db.queryForObject("SELECT count(*) FROM movimientos_inventario WHERE id_orden=? AND codigo_articulo=? AND tipo='RESERVA'",Integer.class,event.id_orden(),code);
                if(reserved!=null && reserved>0){int inserted=db.update("INSERT INTO movimientos_inventario(id_orden,codigo_articulo,cantidad,tipo) VALUES(?,?,?,'LIBERACION') ON CONFLICT DO NOTHING",event.id_orden(),code,qty);if(inserted==1)db.update("UPDATE articulos SET cantidad_existente=cantidad_existente+? WHERE codigo_articulo=?",qty,code);}
            }
            db.update("INSERT INTO mensajes_procesados(message_id,id_orden) VALUES(?,?)",event.message_id(),event.id_orden()); return "stock_liberado";
        }

        ObjectNode error(String code,String reason,int stock,int qty){ObjectNode n=mapper.createObjectNode();n.put("codigo_articulo",code);n.put("motivo",reason);n.put("stock_actual",stock);n.put("cantidad_solicitada",qty);return n;}
        ArrayNode trace(Envelope e,String state,String type,String description){ArrayNode a=e.payload().has("trace")?(ArrayNode)e.payload().get("trace").deepCopy():mapper.createArrayNode();ObjectNode n=mapper.createObjectNode();n.put("estado",state);n.put("evento",type);n.put("message_id",e.message_id().toString());if(e.causation_id()!=null)n.put("causation_id",e.causation_id().toString());else n.putNull("causation_id");n.put("descripcion",description);a.add(n);return a;}
        ObjectNode next(Envelope e,String type,ObjectNode payload){ObjectNode n=mapper.createObjectNode();n.put("message_id",UUID.randomUUID().toString());n.put("event_type",type);n.put("event_version",1);n.put("correlation_id",e.correlation_id().toString());n.put("causation_id",e.message_id().toString());n.put("id_orden",e.id_orden());n.put("timestamp",Instant.now().toString());n.put("source",SERVICE);n.put("attempt",0);n.set("payload",payload);return n;}
        void publish(String key,ObjectNode event){rabbit.convertAndSend(EXCHANGE,key,event.toString(),m->{m.getMessageProperties().setContentType("application/json");m.getMessageProperties().setDeliveryMode(org.springframework.amqp.core.MessageDeliveryMode.PERSISTENT);m.getMessageProperties().setMessageId(event.path("message_id").asText());m.getMessageProperties().setCorrelationId(event.path("correlation_id").asText());return m;});}
        void retry(JsonNode raw,MessageProperties props,String reason){ObjectNode n=(ObjectNode)raw;int attempt=n.path("attempt").asInt()+1;n.put("attempt",attempt);n.put("timestamp",Instant.now().toString());if(attempt>maxRetries){n.put("event_type","error.tecnico");rabbit.convertAndSend(DLX,"error.tecnico",n.toString());}else{try{Thread.sleep(Long.parseLong(System.getenv().getOrDefault("RETRY_DELAY_MS","5000")));}catch(InterruptedException e){Thread.currentThread().interrupt();}publish(props.getReceivedRoutingKey(),n);} }
        void log(Envelope e,String action,String result,long ms){System.out.println("{\"timestamp\":\""+Instant.now()+"\",\"level\":\"INFO\",\"service\":\"inventario\",\"language\":\"java\",\"event_type\":\""+e.event_type()+"\",\"message_id\":\""+e.message_id()+"\",\"correlation_id\":\""+e.correlation_id()+"\",\"causation_id\":\""+e.causation_id()+"\",\"id_orden\":\""+e.id_orden()+"\",\"attempt\":"+e.attempt()+",\"action\":\""+action+"\",\"result\":\""+result+"\",\"duration_ms\":"+ms+"}");}
    }
}
