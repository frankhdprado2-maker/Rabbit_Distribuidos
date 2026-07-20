import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from app.main import OrdenIn

def test_valid_order():
    order = OrdenIn(cliente_id="CLI-1", nombre_cliente="Maria", ruc_cliente="20481234567",
                    items=[{"codigo_articulo":"ART-001", "cantidad":2}])
    assert order.items[0].cantidad == 2
