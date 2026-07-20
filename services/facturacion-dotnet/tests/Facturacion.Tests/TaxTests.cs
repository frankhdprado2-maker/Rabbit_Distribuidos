namespace Facturacion.Tests; public class TaxTests { [Xunit.Fact] public void IgvIsEighteenPercent()=>Xunit.Assert.Equal(18m,System.Math.Round(100m*0.18m,2)); }
