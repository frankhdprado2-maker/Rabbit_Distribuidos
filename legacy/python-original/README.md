# FISI Tiendas Utiles - Gestion de Ordenes con RabbitMQ

Aplicacion de laboratorio para simular la cadena de valor de una gestion de ordenes de compra usando **FastAPI**, **RabbitMQ**, **Pika** y **SQLite**.

RabbitMQ funciona como bus de mensajes entre modulos independientes. Los modulos de negocio no se llaman entre si por HTTP; se comunican publicando y consumiendo eventos.

## Tabla de contenido

- [Arquitectura](#arquitectura)
- [Modulos implementados](#modulos-implementados)
- [Tecnologias usadas](#tecnologias-usadas)
- [Requisitos previos](#requisitos-previos)
- [Instalacion paso a paso](#instalacion-paso-a-paso)
- [Ejecucion paso a paso](#ejecucion-paso-a-paso)
- [Como probar el sistema](#como-probar-el-sistema)
- [Endpoints disponibles](#endpoints-disponibles)
- [Colas y routing keys](#colas-y-routing-keys)
- [Solucion de problemas](#solucion-de-problemas)
- [Pendientes](#pendientes)

## Arquitectura

Flujo principal:

```text
Cliente / Operador
-> API Procesamiento de Ordenes
-> RabbitMQ
-> Inventario
-> Reserva
-> Facturacion
-> Cuentas por Cobrar
-> RabbitMQ
-> Procesamiento de Ordenes recibe confirmacion final
```

El sistema inicia con una orden recibida por la API. Luego, cada modulo toma una parte del proceso:

1. La API registra la orden.
2. Inventario valida productos y stock.
3. Reserva descuenta el stock.
4. Facturacion genera la factura.
5. Cuentas por Cobrar genera la cuenta pendiente.
6. Procesamiento de Ordenes recibe la respuesta final y actualiza el estado de la orden.

## Modulos implementados

- **Procesamiento de Ordenes**: API FastAPI, registro y consulta de ordenes, consumidor de respuesta final.
- **Inventario**: valida articulos, estado activo y stock disponible.
- **Reserva**: descuenta stock y evita reservas duplicadas.
- **Facturacion**: genera factura con formato `F001-000001` y evita facturas duplicadas.
- **Cuentas por Cobrar**: crea cuenta pendiente con fecha de cobro a 30 dias y evita duplicados.

## Tecnologias usadas

- Python 3.11
- FastAPI
- Uvicorn
- Pika
- SQLite
- RabbitMQ
- Docker Compose
- python-dotenv
- Pydantic

## Requisitos previos

Antes de ejecutar el proyecto, instala o verifica lo siguiente:

1. **Python 3.11 o superior**

   Verificar version:

   ```powershell
   python --version
   ```

2. **Docker Desktop**

   Se usa para levantar RabbitMQ con Docker Compose.

   Verificar version:

   ```powershell
   docker --version
   docker compose version
   ```

3. **Git**

   Solo es necesario si vas a clonar el repositorio desde GitHub.

   ```powershell
   git --version
   ```

## Instalacion paso a paso

### 1. Clonar el repositorio

Si todavia no tienes el proyecto en tu computadora, clonalo desde GitHub:

```powershell
git clone https://github.com/frankhdprado2-maker/Rabbit_Distribuidos.git
```

Entrar a la carpeta del proyecto:

```powershell
cd Rabbit_Distribuidos
```

Si ya tienes el proyecto abierto localmente, solo entra a su carpeta:

```powershell
cd C:\Users\Frankie\Desktop\Rbbit
```

### 2. Crear entorno virtual

```powershell
python -m venv .venv
```

### 3. Activar entorno virtual

En Windows con PowerShell:

```powershell
.\.venv\Scripts\activate
```

Cuando este activo, veras `(.venv)` al inicio de la terminal.

Si PowerShell bloquea la activacion, ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\activate
```

### 4. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 5. Configurar variables de entorno

El proyecto incluye un archivo de ejemplo llamado `.env.example`.

Puedes copiarlo a `.env`:

```powershell
Copy-Item .env.example .env
```

Por defecto, estos valores funcionan para ejecucion local:

```env
APP_ENV=development
SQLITE_DB_PATH=data/fisi_ordenes.db

RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VHOST=/

RABBITMQ_EXCHANGE=fisi.ordenes.exchange
RABBITMQ_DLX=fisi.ordenes.dlx
```

Si no creas `.env`, la aplicacion tambien usa esos mismos valores por defecto.

## Ejecucion paso a paso

Para ejecutar todo el sistema se necesitan varias terminales abiertas, porque cada consumidor de RabbitMQ queda escuchando mensajes de forma permanente.

### Paso 1. Levantar RabbitMQ

Desde la carpeta del proyecto:

```powershell
docker compose up -d
```

Verificar que el contenedor este corriendo:

```powershell
docker ps
```

Debe aparecer un contenedor llamado:

```text
fisi-rabbitmq
```

Tambien puedes abrir el panel web de RabbitMQ:

```text
http://localhost:15672
```

Credenciales:

```text
Usuario: guest
Contrasena: guest
```

### Paso 2. Inicializar la base de datos

En una terminal con el entorno virtual activado:

```powershell
python scripts/init_db.py
```

Resultado esperado:

```text
Base de datos inicializada en ...\data\fisi_ordenes.db
```

Este comando crea las tablas necesarias en SQLite.

### Paso 3. Cargar datos de prueba

```powershell
python scripts/seed_data.py
```

Resultado esperado:

```text
Datos de prueba cargados correctamente.
```

Este comando carga productos de ejemplo:

| Codigo | Producto | Stock inicial |
| --- | --- | --- |
| `ART-001` | Cuaderno A4 | 50 |
| `ART-002` | Lapicero azul | 100 |
| `ART-003` | Folder manila | 80 |
| `ART-004` | Plumon negro | 20 |
| `ART-005` | Resaltador | 5 |

### Paso 4. Ejecutar la API

Abre una terminal y ejecuta:

```powershell
uvicorn src.procesamiento_ordenes.main:app --reload --port 8080
```

La API queda disponible en:

```text
http://localhost:8080
```

Swagger queda disponible en:

```text
http://localhost:8080/docs
```

Puedes verificar que la API esta viva con:

```powershell
curl.exe http://localhost:8080/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "service": "procesamiento_ordenes"
}
```

### Paso 5. Ejecutar consumidor de respuesta final

Abre otra terminal, activa el entorno virtual y ejecuta:

```powershell
.\.venv\Scripts\activate
python -m src.procesamiento_ordenes.response_consumer
```

Este consumidor escucha las respuestas finales de RabbitMQ y actualiza la orden como `CONFIRMADA`, `RECHAZADA` o `ERROR`.

### Paso 6. Ejecutar consumidor de inventario

Abre otra terminal:

```powershell
.\.venv\Scripts\activate
python -m src.inventario.worker
```

Este modulo valida si los articulos existen, estan activos y tienen stock suficiente.

### Paso 7. Ejecutar consumidor de reserva

Abre otra terminal:

```powershell
.\.venv\Scripts\activate
python -m src.reserva.worker
```

Este modulo descuenta el stock y registra la reserva.

### Paso 8. Ejecutar consumidor de facturacion

Abre otra terminal:

```powershell
.\.venv\Scripts\activate
python -m src.facturacion.worker
```

Este modulo genera la factura de la orden.

### Paso 9. Ejecutar consumidor de cuentas por cobrar

Abre otra terminal:

```powershell
.\.venv\Scripts\activate
python -m src.cuentas_cobrar.worker
```

Este modulo genera la cuenta por cobrar asociada a la factura.

### Resumen de terminales necesarias

Para ver todo funcionando, normalmente tendras estas terminales abiertas:

| Terminal | Comando |
| --- | --- |
| 1 | `docker compose up -d` |
| 2 | `uvicorn src.procesamiento_ordenes.main:app --reload --port 8080` |
| 3 | `python -m src.procesamiento_ordenes.response_consumer` |
| 4 | `python -m src.inventario.worker` |
| 5 | `python -m src.reserva.worker` |
| 6 | `python -m src.facturacion.worker` |
| 7 | `python -m src.cuentas_cobrar.worker` |

El comando de Docker no necesita quedarse abierto porque se ejecuta con `-d`.

## Como probar el sistema

Puedes probar desde Swagger o desde PowerShell.

### Opcion A. Probar desde Swagger

1. Abre:

   ```text
   http://localhost:8080/docs
   ```

2. Ejecuta `GET /productos` para confirmar que los productos fueron cargados.

3. Ejecuta `POST /ordenes` con el JSON de prueba.

4. Copia el `id_orden` que devuelve la API.

5. Consulta la orden con `GET /ordenes/{id_orden}`.

6. Consulta el historial con `GET /ordenes/{id_orden}/historial`.

### Opcion B. Probar desde PowerShell

#### 1. Ver productos

```powershell
curl.exe http://localhost:8080/productos
```

#### 2. Crear una orden exitosa

```powershell
$body = @{
  cliente_id = "CLI-001"
  nombre_cliente = "Juan Perez"
  ruc_cliente = "10456789123"
  items = @(
    @{
      codigo_articulo = "ART-001"
      cantidad = 2
    },
    @{
      codigo_articulo = "ART-002"
      cantidad = 5
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://localhost:8080/ordenes" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Respuesta esperada similar:

```json
{
  "id_orden": "ORD-2026-000001",
  "correlation_id": "...",
  "estado": "VALIDANDO_STOCK"
}
```

La orden se crea inicialmente como `VALIDANDO_STOCK` porque el procesamiento completo ocurre por eventos asincronos.

#### 3. Consultar la orden

Espera unos segundos para que los consumidores procesen los mensajes y consulta:

```powershell
curl.exe http://localhost:8080/ordenes/ORD-2026-000001
```

Resultado esperado:

```text
estado: CONFIRMADA
```

#### 4. Consultar historial

```powershell
curl.exe http://localhost:8080/ordenes/ORD-2026-000001/historial
```

En el historial deberias ver eventos como:

- `orden.creada`
- `inventario.validado`
- `reserva.creada`
- `factura.generada`
- `cuenta.creada`
- `orden.confirmada`

### Prueba de rechazo por stock insuficiente

Crea una orden solicitando mas stock del disponible para `ART-005`, que solo tiene 5 unidades:

```powershell
$body = @{
  cliente_id = "CLI-002"
  nombre_cliente = "Maria Lopez"
  ruc_cliente = "20456789123"
  items = @(
    @{
      codigo_articulo = "ART-005"
      cantidad = 99
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://localhost:8080/ordenes" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Luego consulta la orden:

```powershell
curl.exe http://localhost:8080/ordenes/ORD-2026-000002
```

Resultado esperado:

```text
estado: RECHAZADA
```

El motivo debe indicar stock insuficiente.

## Endpoints disponibles

| Metodo | Endpoint | Descripcion |
| --- | --- | --- |
| `GET` | `/health` | Verifica que la API este activa |
| `GET` | `/productos` | Lista productos cargados en inventario |
| `POST` | `/ordenes` | Registra una nueva orden |
| `GET` | `/ordenes/{id_orden}` | Consulta una orden por ID |
| `GET` | `/ordenes/{id_orden}/historial` | Consulta el historial de eventos de una orden |

## Flujo de eventos

1. `POST /ordenes` registra la orden y publica `inventario.validar`.
2. Inventario publica `reserva.crear` si hay stock o `orden.error` si hay rechazo de negocio.
3. Reserva descuenta stock y publica `factura.generar`.
4. Facturacion genera factura y publica `cuenta.crear`.
5. Cuentas por Cobrar genera cuenta y publica `orden.confirmar`.
6. Procesamiento de Ordenes consume `orden.confirmar` u `orden.error` desde `cola_respuesta`.

## Colas y routing keys

| Routing key | Cola | Proposito |
| --- | --- | --- |
| `inventario.validar` | `cola_inventario` | Validar productos y stock |
| `reserva.crear` | `cola_reserva` | Reservar productos |
| `factura.generar` | `cola_facturacion` | Generar factura |
| `cuenta.crear` | `cola_cxc` | Crear cuenta por cobrar |
| `orden.confirmar` | `cola_respuesta` | Confirmar orden |
| `orden.error` | `cola_respuesta` | Rechazar o marcar error |
| `error.tecnico` | `cola_errores` | Recibir mensajes enviados al DLX |

Exchange principal:

```text
fisi.ordenes.exchange
```

Tipo:

```text
direct
```

Exchange de errores:

```text
fisi.ordenes.dlx
```

Tipo:

```text
direct
```

## Estados de orden

| Estado | Significado |
| --- | --- |
| `PENDIENTE` | Estado base antes del procesamiento |
| `VALIDANDO_STOCK` | Orden enviada al modulo de inventario |
| `RESERVADA` | Stock reservado correctamente |
| `FACTURADA` | Factura generada |
| `CUENTA_CREADA` | Cuenta por cobrar creada |
| `CONFIRMADA` | Flujo completado correctamente |
| `RECHAZADA` | Orden rechazada por una regla de negocio |
| `ERROR` | Error tecnico durante el procesamiento |

## Estructura del proyecto

```text
.
|-- data/
|-- docs/
|-- scripts/
|   |-- init_db.py
|   `-- seed_data.py
|-- src/
|   |-- cuentas_cobrar/
|   |-- facturacion/
|   |-- inventario/
|   |-- procesamiento_ordenes/
|   |-- reserva/
|   `-- shared/
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
```

## Detener el sistema

Para detener la API y los consumidores, presiona `Ctrl + C` en cada terminal.

Para detener RabbitMQ:

```powershell
docker compose down
```

Si quieres borrar tambien el volumen de RabbitMQ:

```powershell
docker compose down -v
```

Si quieres reiniciar la base de datos SQLite desde cero, elimina los archivos dentro de `data/` y vuelve a ejecutar:

```powershell
python scripts/init_db.py
python scripts/seed_data.py
```

## Solucion de problemas

### Error: no se puede activar el entorno virtual

Ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\activate
```

### Error: `ModuleNotFoundError`

Verifica que estas en la carpeta raiz del proyecto y que instalaste las dependencias:

```powershell
pip install -r requirements.txt
```

### Error: RabbitMQ no conecta

Verifica que Docker este abierto y que el contenedor exista:

```powershell
docker ps
```

Si no aparece `fisi-rabbitmq`, levantalo:

```powershell
docker compose up -d
```

### La orden se queda en `VALIDANDO_STOCK`

Significa que la API publico el mensaje, pero algun consumidor no esta ejecutandose.

Verifica que esten activos:

```powershell
python -m src.procesamiento_ordenes.response_consumer
python -m src.inventario.worker
python -m src.reserva.worker
python -m src.facturacion.worker
python -m src.cuentas_cobrar.worker
```

Cada comando debe estar corriendo en una terminal diferente.

### Puerto 8080 ocupado

Puedes usar otro puerto:

```powershell
uvicorn src.procesamiento_ordenes.main:app --reload --port 8081
```

Luego abre:

```text
http://localhost:8081/docs
```

### Puerto 15672 ocupado

Ese puerto pertenece al panel web de RabbitMQ. Puedes cambiarlo en `docker-compose.yml`:

```yaml
ports:
  - "5672:5672"
  - "15673:15672"
```

Luego ejecuta:

```powershell
docker compose up -d
```

Y abre:

```text
http://localhost:15673
```

## Documentacion adicional

Las pruebas manuales completas tambien estan en:

```text
docs/pruebas_manual.md
```

## Pendientes

- Reprocesamiento supervisado desde una interfaz o endpoint administrativo.
- Reintentos con backoff y limites por tipo de error.
- Pruebas automatizadas de integracion con RabbitMQ.
- Separacion de bases por modulo para una distribucion mas realista.
- Metricas y trazas centralizadas.
