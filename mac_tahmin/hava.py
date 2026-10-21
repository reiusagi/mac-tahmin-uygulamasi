"""Maç saatinin hava tahmini (Open-Meteo: ücretsiz, anahtarsız; veriler CC BY 4.0). Yalnızca bilgi olarak gösterilir:
karne düzeninde ölçüldü (GELISTIRME.md), yağmur golü biraz artırıyor ama modele katılınca tahminler anlamlı ölçüde
iyileşmedi. Stadyumun konumu FotMob'dan (maç detayı ya da ev sahibinin iç sahası).

Bir konumun saatlik tahmini ham/hava/'ya yazılır ve SURE_SN'de bir yenilenir; aynı stadyumdaki bütün maçlar onu kullanır."""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .veri import json_getir

logger = logging.getLogger(__name__)

TAHMIN_GUN = 7  # maçtan bu kadar gün öncesine kadar gösterilir (daha ilerisi için yağış tahmini güvenilmez)
SURE_SN = 3 * 3600  # bir konumun tahmini bu kadar saniyede bir yenilenir
MAC_SAAT = 2  # başlangıçtan sonraki bu kadar saat (maçın süresi)
SIDDETLI_YAGIS = 2.0  # mm: karne ölçümündeki "şiddetli yağış" eşiği (maç gününde bu maçlarda ~%5 daha çok gol)
URL = ('https://api.open-meteo.com/v1/forecast?latitude={:.3f}&longitude={:.3f}&hourly=temperature_2m,precipitation,'
       'precipitation_probability,wind_speed_10m,weather_code&timezone=GMT&forecast_days=8')
KOD = {0: 'açık', 1: 'çoğunlukla açık', 2: 'parçalı bulutlu', 3: 'kapalı', 45: 'sisli', 48: 'kırağılı sis',
       51: 'hafif çisenti', 53: 'çisenti', 55: 'yoğun çisenti', 56: 'dondurucu çisenti', 57: 'dondurucu çisenti',
       61: 'hafif yağmur', 63: 'yağmur', 65: 'şiddetli yağmur', 66: 'dondurucu yağmur', 67: 'dondurucu yağmur',
       71: 'hafif kar', 73: 'kar', 75: 'yoğun kar', 77: 'kar taneleri', 80: 'hafif sağanak', 81: 'sağanak',
       82: 'şiddetli sağanak', 85: 'kar sağanağı', 86: 'yoğun kar sağanağı', 95: 'gök gürültülü fırtına',
       96: 'dolulu fırtına', 99: 'dolulu fırtına'}

_bellek = {}  # konum anahtarı -> (alındığı an, saatlik veri)
_kilit = threading.Lock()


def _zaman(bas):
    if isinstance(bas, datetime):
        return bas if bas.tzinfo else bas.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(bas).replace('Z', '+00:00'))
    except ValueError:
        return None


def _saatlik(lat, lon, ham):
    """Konumun saatlik tahmini (bellekte, sonra diskte; eskiyse yeniden indirilir). Ağ hatasında eldeki eski veri."""
    anahtar = f'{lat:.2f}_{lon:.2f}'
    with _kilit:  # aynı konum için iki sayfa aynı anda indirmesin
        v = _bellek.get(anahtar)
        if v and time.time() - v[0] < SURE_SN:
            return v[1]
        yol = Path(ham) / 'hava' / f'{anahtar}.json'
        if not v and yol.exists():
            try:
                v = (yol.stat().st_mtime, json.loads(yol.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                v = None
            if v and time.time() - v[0] < SURE_SN:
                _bellek[anahtar] = v
                return v[1]
        try:
            j = json_getir(URL.format(lat, lon)).get('hourly') or {}
        except Exception:
            logger.debug('hava tahmini alınamadı: %s', anahtar, exc_info=True)
            return v[1] if v else None
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(f'.{threading.get_ident()}.tmp')
        gecici.write_text(json.dumps(j), encoding='utf-8')
        gecici.replace(yol)
        _bellek[anahtar] = (time.time(), j)
        return j


def mac_havasi(konum, baslangic, ham):
    """Maç süresince (başlangıçtan MAC_SAAT saat) beklenen hava: {'sicaklik' °C, 'yagis' mm (toplam), 'olasilik' %
    (en yüksek), 'ruzgar' km/sa (ortalama), 'durum' (en kötü saatin tanımı)}. Maç TAHMIN_GUN'den uzaksa, bittiyse ya da
    konum / saat bilinmiyorsa None."""
    bas = _zaman(baslangic)
    if not konum or not bas:
        return None
    simdi = datetime.now(timezone.utc)
    if bas - simdi > timedelta(days=TAHMIN_GUN) or bas + timedelta(hours=MAC_SAAT) < simdi:
        return None
    h = _saatlik(float(konum[0]), float(konum[1]), ham)
    if not h:
        return None
    ilk = bas.replace(minute=0, second=0, microsecond=0)
    son = bas + timedelta(hours=MAC_SAAT)
    satir = [k for k, t in enumerate(h.get('time') or [])
             if ilk <= datetime.fromisoformat(t).replace(tzinfo=timezone.utc) < son]
    if not satir:
        return None

    def degerler(ad):
        return [x for x in (h.get(ad) or [None] * len(h['time']))[satir[0]:satir[-1] + 1] if x is not None]
    sic, yag, ola, ruz, kod = (degerler(a) for a in ('temperature_2m', 'precipitation', 'precipitation_probability',
                                                      'wind_speed_10m', 'weather_code'))
    if not sic:
        return None
    return {'sicaklik': sum(sic) / len(sic), 'yagis': sum(yag), 'olasilik': max(ola) if ola else None,
            'ruzgar': sum(ruz) / len(ruz) if ruz else None, 'durum': KOD.get(int(max(kod))) if kod else None}
