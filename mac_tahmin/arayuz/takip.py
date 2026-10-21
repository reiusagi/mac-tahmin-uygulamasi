"""Oyuncu takip listesi: oyuncu kartındaki "Takip et" ile eklenir, Takımlarım sekmesinde listelenir. Takip edilen
oyuncu için bildirim (bildirim.gonder; "Bildirimler" anahtarı açıksa):
- gol ya da asist: oyuncunun takımının maçı bitince (canlı skordan, bildirim.kontrol haber verir) TAKIP_BEKLE_SN sonra
  maç sayfasına bakılır;
- sözleşmesi son SOZLESME_AY aya girdiğinde (bir kez);
- piyasa değeri en az DEGER_ESIK oranında değişince.
Liste app.storage.general['takip']'te: [{'fm_id', 'ad', 'lig', 'yil', 'id'}] (yalnızca arayüzden yazılır). Arka planın
durumu (oyuncunun güncel takımı, son bilinen değeri, bildirilenler) ham/takip_durum.json'da: arka plan iş parçacıkları
uygulama deposuna yazmasın diye ayrı dosya."""
import json
import logging
import threading
import time
from datetime import date
from pathlib import Path

from nicegui import app

from ..bicim import para as _para
from . import bildirim

logger = logging.getLogger(__name__)

TAKIP_BEKLE_SN = 600  # maç bitince olaylar (gol, asist) kesinleşsin diye bekleme
DEGER_ESIK = 0.10
SOZLESME_AY = 6
KONTROL_SAAT = 3  # değer, sözleşme ve takım bilgisi bu kadar saatte bir denetlenir
_kilit = threading.Lock()
_takimlar = set()  # takip edilen oyuncuların güncel takımlarının FotMob id'leri (metin)


# ---------------------------------------------------------------- liste (arayüz)
def liste():
    try:
        return list(app.storage.general.get('takip', []))
    except Exception:
        logger.debug('takip listesi okunamadı', exc_info=True)
        return []


def takipte_mi(fm_id):
    return any(str(t['fm_id']) == str(fm_id) for t in liste())


def degistir(p, lig, yil):
    """Oyuncuyu takibe alır ya da çıkarır (FotMob kaydı olan oyuncular); yeni durumu döner (True: takipte)."""
    L = liste()
    if takipte_mi(p['fm_id']):
        app.storage.general['takip'] = [t for t in L if str(t['fm_id']) != str(p['fm_id'])]
        return False
    app.storage.general['takip'] = L + [{'fm_id': str(p['fm_id']), 'ad': p['n'], 'lig': lig, 'yil': yil, 'id': p['id']}]
    threading.Thread(target=_takimlari_guncelle, daemon=True).start()
    return True


# ---------------------------------------------------------------- arka plan durumu
def _durum_yolu():
    return Path(bildirim.HAM) / 'takip_durum.json' if bildirim.HAM else None


def _durum_oku():
    yol = _durum_yolu()
    try:
        return json.loads(yol.read_text(encoding='utf-8')) if yol and yol.exists() else {}
    except (OSError, ValueError):
        logger.debug('takip durumu okunamadı', exc_info=True)
        return {}


def _durum_yaz(d):
    yol = _durum_yolu()
    if not yol:
        return
    gecici = yol.with_suffix('.tmp')
    gecici.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    gecici.replace(yol)


def guncel_takim(fm_id):
    """Oyuncunun güncel takımı: (lig anahtarı, takım adı, FotMob takım id) ya da None (önbellekteki kadrolardan)."""
    D = bildirim.DEPO
    if D is None:
        return None
    ad = D.kadro_dizini().get(str(fm_id))
    for lig, takimlar in D.stadyumlar()['ligler'].items():
        if ad in takimlar:
            return lig, ad, takimlar[ad]
    return None


def _takimlari_guncelle():
    global _takimlar
    yeni = set()
    for t in liste():
        g = guncel_takim(t['fm_id'])
        if g:
            yeni.add(str(g[2]))
    _takimlar = yeni


def takim_idleri():
    return _takimlar


# ---------------------------------------------------------------- maç sonu: gol / asist
def mac_bitti(m):
    """bildirim.kontrol çağırır: takip edilen bir oyuncunun takımının maçı bitti."""
    threading.Timer(TAKIP_BEKLE_SN, _mac_sonu, args=(m,)).start()


def _mac_sonu(m):
    from ..mac_ozeti import ayrinti
    try:
        a = ayrinti(m['id'], bildirim.HAM)
    except Exception:
        logger.debug('maç sayfası alınamadı: %s', m['id'], exc_info=True)
        return
    olay = {str(p.get('id')): p.get('olaylar') or {} for taraf in ('ev', 'dep') for grup in ('ilk11', 'yedek')
            for p in ((a.get('kadro') or {}).get(taraf) or {}).get(grup, [])}
    skor = f'{m["ev"]} {m.get("evGol") or 0} – {m.get("depGol") or 0} {m["dep"]}'
    with _kilit:
        d = _durum_oku()
        for t in liste():
            pid = str(t['fm_id'])
            o = (a.get('oyuncular') or {}).get(pid)
            kayit = d.setdefault(pid, {})
            if not o or not o.get('dk') or m['id'] in kayit.get('maclar', []):
                continue
            kayit['maclar'] = (kayit.get('maclar', []) + [m['id']])[-30:]
            gol, asist = olay.get(pid, {}).get('gol', 0), olay.get(pid, {}).get('asist', 0)
            if (gol or asist) and bildirim.acik_mi():
                parca = [x for x in (f'{gol} gol' if gol else '', f'{asist} asist' if asist else '') if x]
                puan = f' · puan {o["puan"]:.1f}'.replace('.', ',') if o.get('puan') else ''
                bildirim.gonder(f'Takip: {t["ad"]}', f'{", ".join(parca)}{puan} · {skor}')
        _durum_yaz(d)


# ---------------------------------------------------------------- değer ve sözleşme
def _ay_farki(tarih):
    b, g = date.fromisoformat(tarih[:10]), date.today()
    return (b.year - g.year) * 12 + b.month - g.month


def periyodik_kontrol():
    """Takip edilenlerin güncel takımı, piyasa değeri ve sözleşmesi; değişiklik varsa bildirim."""
    D = bildirim.DEPO
    L = liste()
    if D is None or not L:
        return
    _takimlari_guncelle()
    try:
        sozlesme = D.sozlesmeler([t['fm_id'] for t in L])  # 30 gün önbellek; yalnızca takip edilenler
    except Exception:
        logger.warning('sözleşmeler alınamadı', exc_info=True)
        sozlesme = {}
    with _kilit:
        d = _durum_oku()
        for t in L:
            pid = str(t['fm_id'])
            kayit = d.setdefault(pid, {})
            g = guncel_takim(pid)
            deger = D.degerler_onbellek(g[0]).get(int(pid)) if g and pid.isdigit() else None
            eski = kayit.get('deger')
            if deger and eski and abs(deger - eski) / eski >= DEGER_ESIK and bildirim.acik_mi():
                yon = 'yükseldi' if deger > eski else 'düştü'
                bildirim.gonder(f'Takip: {t["ad"]}', f'Piyasa değeri {yon}: {_para(eski)} → {_para(deger)}')
            if deger:
                kayit['deger'] = deger
            bitis = sozlesme.get(pid)
            if bitis and 0 <= _ay_farki(bitis) <= SOZLESME_AY and kayit.get('sozlesme_bildirildi') != bitis:
                kayit['sozlesme_bildirildi'] = bitis
                if bildirim.acik_mi():
                    bildirim.gonder(f'Takip: {t["ad"]}', f'Sözleşmesi {bitis[5:7]}.{bitis[:4]} tarihinde bitiyor '
                                                         f'({_ay_farki(bitis)} ay kaldı): bedelsiz ya da ucuza alınabilir.')
        _durum_yaz(d)


def _dongu():
    time.sleep(120)  # açılışta önce veri ve arayüz otursun
    while True:
        try:
            periyodik_kontrol()
        except Exception:
            logger.warning('takip denetimi başarısız', exc_info=True)
        time.sleep(KONTROL_SAAT * 3600)


def baslat():
    threading.Thread(target=_takimlari_guncelle, daemon=True).start()
    threading.Thread(target=_dongu, daemon=True).start()
