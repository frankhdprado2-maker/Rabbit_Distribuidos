package contract

import "testing"

func TestExchange(t *testing.T) {
	if Exchange != "fisi.ordenes.exchange" {
		t.Fatal("exchange modificado")
	}
}
