"""Ülke parametresi: veri katmanının hangi ülke için çalıştığını tek yerden yönetir.

Ayarlar ``data/ulkeler.yaml``'dadır. Varsayılan ülke ``turkiye``; hiçbir şey seçilmezse bütün modüller
eskisi gibi Türkiye için çalışır (kutu, yollar, maske aynı).

    from data.ulkeler import ulke_baglami
    with ulke_baglami("yunanistan"):          # bu blokta fetch / harmonize / grid / domain_mask Yunanistan için
        ...

Aktif ülke modül düzeyinde tutulur (iş parçacıkları da görür); bağlam bitince eski değere döner.
Komutlar ``--ulke`` seçeneğiyle bu bağlamı açar (``data.build``, ``data.export``, ``data.make_boundaries``).
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import yaml

ULKELER_PATH = Path(__file__).resolve().parent / "ulkeler.yaml"
VARSAYILAN = "turkiye"
_aktif = VARSAYILAN


@lru_cache(maxsize=1)
def _kayitlar() -> dict[str, dict]:
    raw = yaml.safe_load(ULKELER_PATH.read_text(encoding="utf-8"))
    out = {}
    for k, v in raw.items():
        v = dict(v)
        v["anahtar"] = k
        for alan in ("ic_kutu", "yayin_kutusu"):
            if v.get(alan) is not None:
                v[alan] = tuple(float(x) for x in v[alan])
        v.setdefault("ek_uyarilar", {})
        out[k] = v
    return out


def ulke_listesi() -> list[str]:
    """Tanımlı ülke anahtarları."""
    return list(_kayitlar())


def ulke(anahtar: str | None = None) -> dict:
    """Ülke kaydı (``None`` → aktif ülke). Bilinmeyen anahtar → KeyError (seçenekler listelenir)."""
    k = anahtar or _aktif
    try:
        return _kayitlar()[k]
    except KeyError:
        raise KeyError(f"Bilinmeyen ülke: {k!r}. Tanımlı: {ulke_listesi()} (data/ulkeler.yaml)") from None


def aktif() -> str:
    """Aktif ülkenin anahtarı."""
    return _aktif


@contextmanager
def ulke_baglami(anahtar: str | None):
    """Blok boyunca aktif ülkeyi değiştirir (``None`` → değiştirmez)."""
    global _aktif
    if anahtar is None:
        yield ulke()
        return
    ulke(anahtar)                     # bilinmeyen ülke hemen hata versin
    eski, _aktif = _aktif, anahtar
    try:
        yield ulke()
    finally:
        _aktif = eski


def ic_kutu(anahtar: str | None = None) -> tuple[float, float, float, float]:
    """İşleme kutusu (batı, güney, doğu, kuzey)."""
    return ulke(anahtar)["ic_kutu"]


def yayin_kutusu(anahtar: str | None = None) -> tuple[float, float, float, float]:
    """L1 yayın kutusu; ayarda yoksa hata (önce ``python -m data.make_boundaries --ulke``)."""
    u = ulke(anahtar)
    if u.get("yayin_kutusu") is None:
        raise ValueError(f"{u['anahtar']}: yayin_kutusu ulkeler.yaml'da tanımlı değil "
                         f"(python -m data.make_boundaries --ulke {u['anahtar']} hesaplar)")
    return u["yayin_kutusu"]


def yayin_kutusu_hesapla(sinir: tuple[float, float, float, float], res: float = 0.25) -> tuple[float, ...]:
    """Ülke sınırının dış kutusunu ``res`` ızgarasına dışa doğru yuvarlar (hücre kenarları kutuya oturur)."""
    w, s, e, n = sinir
    yuv = lambda v, f: round(f(round(v / res, 9)) * res, 6)  # noqa: E731 (kayan nokta payı)
    return (yuv(w, math.floor), yuv(s, math.floor), yuv(e, math.ceil), yuv(n, math.ceil))


def varsayilan_mi(anahtar: str | None = None) -> bool:
    """Ülke varsayılan (Türkiye) mi? Türkiye dosyalarının biçimi geriye dönük olarak değişmez."""
    return (anahtar or _aktif) == VARSAYILAN


def ulke_yazimi(anahtar: str | None = None) -> str:
    """İşlem notlarında kullanılan ad (ör. "Türkiye")."""
    return ulke(anahtar)["ad"]
