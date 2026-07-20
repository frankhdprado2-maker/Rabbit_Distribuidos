import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).parents[2]

def test_example_envelope_and_payload():
    envelope = json.loads((ROOT / "contracts/ejemplos/inventario.validar.json").read_text(encoding="utf-8"))
    envelope_schema = json.loads((ROOT / "contracts/event-envelope.schema.json").read_text(encoding="utf-8"))
    payload_schema = json.loads((ROOT / "contracts/inventario-validar.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(envelope_schema, format_checker=jsonschema.FormatChecker()).validate(envelope)
    jsonschema.Draft202012Validator(payload_schema).validate(envelope["payload"])

def test_official_topology_names():
    definitions = json.loads((ROOT / "infrastructure/rabbitmq/definitions.json").read_text(encoding="utf-8"))
    assert {q["name"] for q in definitions["queues"]} == {"cola_inventario","cola_reserva","cola_facturacion","cola_cxc","cola_respuesta","cola_errores"}
