package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	amqp "github.com/rabbitmq/amqp091-go"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

const (
	service  = "cuentas-cobrar"
	exchange = "fisi.ordenes.exchange"
	dlx      = "fisi.ordenes.dlx"
	queue    = "cola_cxc"
)

type Cliente struct {
	ClienteID string `json:"cliente_id"`
	Nombre    string `json:"nombre_cliente"`
	RUC       string `json:"ruc_cliente"`
}
type Item struct {
	Codigo   string  `json:"codigo_articulo"`
	Nombre   string  `json:"nombre_articulo"`
	Cantidad int     `json:"cantidad"`
	Precio   float64 `json:"precio_unitario"`
}
type Stage struct {
	Estado      string  `json:"estado"`
	Evento      string  `json:"evento"`
	MessageID   string  `json:"message_id"`
	CausationID *string `json:"causation_id"`
	Descripcion string  `json:"descripcion"`
}
type Payload struct {
	Cliente       Cliente `json:"cliente"`
	Items         []Item  `json:"items"`
	ReservaID     string  `json:"reserva_id"`
	NumeroFactura string  `json:"numero_factura"`
	Subtotal      float64 `json:"subtotal"`
	IGV           float64 `json:"igv"`
	Total         float64 `json:"total"`
	Trace         []Stage `json:"trace"`
}
type Envelope struct {
	MessageID     string  `json:"message_id"`
	EventType     string  `json:"event_type"`
	EventVersion  int     `json:"event_version"`
	CorrelationID string  `json:"correlation_id"`
	CausationID   *string `json:"causation_id"`
	IDOrden       string  `json:"id_orden"`
	Timestamp     string  `json:"timestamp"`
	Source        string  `json:"source"`
	Attempt       int     `json:"attempt"`
	Payload       Payload `json:"payload"`
}
type ConfirmPayload struct {
	ReservaID     string  `json:"reserva_id"`
	NumeroFactura string  `json:"numero_factura"`
	CuentaID      string  `json:"cuenta_cobrar_id"`
	Subtotal      float64 `json:"subtotal"`
	IGV           float64 `json:"igv"`
	Total         float64 `json:"total"`
	Trace         []Stage `json:"trace"`
}
type ConfirmEnvelope struct {
	MessageID     string         `json:"message_id"`
	EventType     string         `json:"event_type"`
	EventVersion  int            `json:"event_version"`
	CorrelationID string         `json:"correlation_id"`
	CausationID   string         `json:"causation_id"`
	IDOrden       string         `json:"id_orden"`
	Timestamp     string         `json:"timestamp"`
	Source        string         `json:"source"`
	Attempt       int            `json:"attempt"`
	Payload       ConfirmPayload `json:"payload"`
}
type App struct {
	db         *pgxpool.Pool
	maxRetries int
	retryDelay time.Duration
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}
func main() {
	ctx := context.Background()
	db, err := pgxpool.New(ctx, env("DATABASE_URL", "postgresql://cxc_user:cxc_dev@postgres:5432/db_cxc"))
	must(err)
	app := &App{db: db, maxRetries: atoi(env("MAX_RETRIES", "3")), retryDelay: time.Duration(atoi(env("RETRY_DELAY_MS", "5000"))) * time.Millisecond}
	must(app.init(ctx))
	go func() {
		http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
			if app.db.Ping(r.Context()) != nil {
				w.WriteHeader(503)
				return
			}
			w.Header().Set("content-type", "application/json")
			fmt.Fprint(w, `{"status":"ok","service":"cuentas-cobrar","language":"go"}`)
		})
		_ = http.ListenAndServe(":8084", nil)
	}()
	app.consume(ctx)
}
func must(e error) {
	if e != nil {
		log.Fatal(e)
	}
}
func atoi(s string) int { n, _ := strconv.Atoi(s); return n }
func now() string       { return time.Now().UTC().Format(time.RFC3339Nano) }
func (a *App) init(ctx context.Context) error {
	deadline := time.Now().Add(90 * time.Second)
	for {
		_, err := a.db.Exec(ctx, `CREATE TABLE IF NOT EXISTS cuentas_cobrar(id_cuenta TEXT PRIMARY KEY,numero_factura TEXT NOT NULL UNIQUE,id_orden TEXT NOT NULL UNIQUE,cliente_id TEXT NOT NULL,nombre_cliente TEXT NOT NULL,ruc_cliente TEXT NOT NULL,total_cobrar NUMERIC(14,2) NOT NULL,fecha_vencimiento DATE NOT NULL,estado TEXT NOT NULL);CREATE TABLE IF NOT EXISTS mensajes_procesados(message_id UUID PRIMARY KEY,id_orden TEXT NOT NULL,procesado_en TIMESTAMPTZ DEFAULT NOW())`)
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return err
		}
		time.Sleep(2 * time.Second)
	}
}
func (a *App) consume(ctx context.Context) {
	delay := time.Second
	for {
		err := a.session(ctx)
		log.Printf(`{"timestamp":%q,"level":"ERROR","service":"%s","language":"go","action":"reconexion","result":%q}`, now(), service, err.Error())
		time.Sleep(delay)
		if delay < 30*time.Second {
			delay *= 2
		}
	}
}
func (a *App) session(ctx context.Context) error {
	url := fmt.Sprintf("amqp://%s:%s@%s:5672/", env("RABBITMQ_USER", "fisi"), env("RABBITMQ_PASSWORD", "fisi_dev"), env("RABBITMQ_HOST", "rabbitmq"))
	conn, err := amqp.DialConfig(url, amqp.Config{Heartbeat: 30 * time.Second, Dial: amqp.DefaultDial(30 * time.Second)})
	if err != nil {
		return err
	}
	defer conn.Close()
	ch, err := conn.Channel()
	if err != nil {
		return err
	}
	defer ch.Close()
	if err = ch.Qos(1, 0, false); err != nil {
		return err
	}
	if err = ch.Confirm(false); err != nil {
		return err
	}
	confirms := ch.NotifyPublish(make(chan amqp.Confirmation, 1))
	deliveries, err := ch.Consume(queue, "", false, false, false, false, nil)
	if err != nil {
		return err
	}
	logJSON(nil, "consumidor_iniciado", "success", 0)
	for d := range deliveries {
		start := time.Now()
		var e Envelope
		dec := json.NewDecoder(bytes.NewReader(d.Body))
		dec.DisallowUnknownFields()
		err = dec.Decode(&e)
		if err == nil {
			err = validate(e, d.RoutingKey)
		}
		if err != nil {
			_ = d.Nack(false, false)
			continue
		}
		result, procErr := a.process(ctx, ch, confirms, e)
		if procErr != nil {
			_ = a.retry(ctx, ch, confirms, d, e, procErr)
			_ = d.Ack(false)
			continue
		}
		_ = d.Ack(false)
		action := "cuenta_creada"
		if result == "duplicate" {
			action = "mensaje_ignorado_idempotencia"
		}
		logJSON(&e, action, result, time.Since(start).Milliseconds())
	}
	return errors.New("canal cerrado")
}
func validate(e Envelope, key string) error {
	if e.EventType != "cuenta.crear" || e.EventType != key || e.EventVersion != 1 || e.Attempt < 0 || e.MessageID == "" || e.CorrelationID == "" || e.IDOrden == "" || e.Payload.NumeroFactura == "" || e.Payload.ReservaID == "" || len(e.Payload.Items) == 0 {
		return errors.New("contrato cuenta.crear invalido")
	}
	for _, i := range e.Payload.Items {
		if i.Codigo == "" || i.Cantidad < 1 {
			return errors.New("item invalido")
		}
	}
	return nil
}
func (a *App) process(ctx context.Context, ch *amqp.Channel, confirms <-chan amqp.Confirmation, e Envelope) (string, error) {
	tx, err := a.db.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)
	var exists bool
	if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM mensajes_procesados WHERE message_id=$1)", e.MessageID).Scan(&exists); err != nil {
		return "", err
	}
	if exists {
		return "duplicate", nil
	}
	var id string
	err = tx.QueryRow(ctx, "SELECT id_cuenta FROM cuentas_cobrar WHERE numero_factura=$1", e.Payload.NumeroFactura).Scan(&id)
	if err != nil {
		id = fmt.Sprintf("CXC-%d", time.Now().UTC().UnixNano())
		_, err = tx.Exec(ctx, "INSERT INTO cuentas_cobrar VALUES($1,$2,$3,$4,$5,$6,$7,CURRENT_DATE+30,'PENDIENTE')", id, e.Payload.NumeroFactura, e.IDOrden, e.Payload.Cliente.ClienteID, e.Payload.Cliente.Nombre, e.Payload.Cliente.RUC, e.Payload.Total)
		if err != nil {
			return "", err
		}
	}
	cause := e.CausationID
	e.Payload.Trace = append(e.Payload.Trace, Stage{"CUENTA_CREADA", "cuenta.crear", e.MessageID, cause, "Cuenta por cobrar creada/reutilizada: " + id + "."})
	out := ConfirmEnvelope{newID(), "orden.confirmar", 1, e.CorrelationID, e.MessageID, e.IDOrden, now(), service, 0, ConfirmPayload{e.Payload.ReservaID, e.Payload.NumeroFactura, id, e.Payload.Subtotal, e.Payload.IGV, e.Payload.Total, e.Payload.Trace}}
	if err = publish(ctx, ch, confirms, exchange, "orden.confirmar", out, e.CorrelationID, out.MessageID); err != nil {
		return "", err
	}
	if _, err = tx.Exec(ctx, "INSERT INTO mensajes_procesados VALUES($1,$2,NOW())", e.MessageID, e.IDOrden); err != nil {
		return "", err
	}
	if err = tx.Commit(ctx); err != nil {
		return "", err
	}
	return "orden.confirmar", nil
}
func publish(ctx context.Context, ch *amqp.Channel, confirms <-chan amqp.Confirmation, ex, key string, v any, corr, msg string) error {
	body, err := json.Marshal(v)
	if err != nil {
		return err
	}
	if err = ch.PublishWithContext(ctx, ex, key, true, false, amqp.Publishing{ContentType: "application/json", ContentEncoding: "utf-8", DeliveryMode: amqp.Persistent, MessageId: msg, CorrelationId: corr, Timestamp: time.Now().UTC(), Body: body}); err != nil {
		return err
	}
	select {
	case c := <-confirms:
		if !c.Ack {
			return errors.New("publisher nack")
		}
		return nil
	case <-time.After(10 * time.Second):
		return errors.New("publisher confirm timeout")
	}
}
func (a *App) retry(ctx context.Context, ch *amqp.Channel, confirms <-chan amqp.Confirmation, d amqp.Delivery, e Envelope, reason error) error {
	e.Attempt++
	e.Timestamp = now()
	e.Source = service
	if e.Attempt > a.maxRetries {
		e.EventType = "error.tecnico"
		return publish(ctx, ch, confirms, dlx, "error.tecnico", e, e.CorrelationID, e.MessageID)
	}
	time.Sleep(a.retryDelay)
	return publish(ctx, ch, confirms, exchange, d.RoutingKey, e, e.CorrelationID, e.MessageID)
}
func newID() string {
	return fmt.Sprintf("%08x-%04x-4%03x-8%03x-%012x", time.Now().UnixNano()&0xffffffff, time.Now().UnixNano()&0xffff, time.Now().UnixNano()&0xfff, time.Now().UnixNano()&0xfff, time.Now().UnixNano()&0xffffffffffff)
}
func logJSON(e *Envelope, action, result string, ms int64) {
	m := map[string]any{"timestamp": now(), "level": "INFO", "service": service, "language": "go", "action": action, "result": result, "duration_ms": ms}
	if e != nil {
		m["event_type"] = e.EventType
		m["message_id"] = e.MessageID
		m["correlation_id"] = e.CorrelationID
		m["causation_id"] = e.CausationID
		m["id_orden"] = e.IDOrden
		m["attempt"] = e.Attempt
	}
	b, _ := json.Marshal(m)
	log.Print(string(b))
}
