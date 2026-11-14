
import numpy as np
import xarray as xr
from stats.trend_tests import trend_analizi

# Tekrarlanabilir rastgele veri
rng = np.random.default_rng(42)

# 25 yillik ornek
yillar = np.arange(2001, 2026)

# Bilinen trend: her yil -0.5
# On yilda -5 birim
gercek_egim = -5.0

gurultu = rng.normal(
    0, 0.25, len(yillar)
)

degerler = (
    50
    - 0.5 * (yillar - 2001)
    + gurultu
)

seri = xr.DataArray(
    degerler,
    dims=["yil"],
    coords={"yil": yillar}
)

# Kendi istatistik motorumuzu calistir
sonuc = trend_analizi(seri)

print("\n===== MOTOR DOGRULAMA =====")
print("Gercek egim:", gercek_egim)
print("Hesaplanan egim:", sonuc["egim_10yil"])
print("Alt guven siniri:", sonuc["ci_alt"])
print("Ust guven siniri:", sonuc["ci_ust"])

# Temel otomatik kontroller
assert sonuc["durum"] == "ok"
assert sonuc["n"] == 25
assert abs(
    sonuc["egim_10yil"] - gercek_egim
) < 1.0

assert sonuc["ci_alt"] <= sonuc["egim_10yil"]
assert sonuc["egim_10yil"] <= sonuc["ci_ust"]

assert sonuc["trend"] == "decreasing"
assert sonuc["p_mk"] < 0.05

print("\nTEST BASARILI!")
