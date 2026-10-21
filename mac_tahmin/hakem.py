"""Maç detayları (FotMob): hakem ve hakemin istatistikleri, maçın oynanacağı stadyum.

Hakemler genelde maçtan 2-4 gün önce atanır; atanmamışsa alan boş gelir. Detaylar diske
önbelleğe alınır: hakemi belli olan maç bir daha istenmez, olmayan en çok 3 saatte bir yeniden sorulur.
"""
import json
import logging
import time
from pathlib import Path

from .veri import BEKLEME, fotmob_url, json_getir, kimlik

logger = logging.getLogger(__name__)

HAKEMSIZ_YENILE_SN = 3 * 3600


def _hakem(ref):
    if not ref or not ref.get('text'):
        return None
    st = {s.get('type'): s for s in ref.get('stats') or []}
    sari = st.get('yellowCards') or {}
    return {
        'ad': ref['text'], 'ulke': ref.get('country') or '',
        'mac': (st.get('matches') or {}).get('value'),
        'sariOrt': sari.get('value'), 'sariLigOrt': sari.get('average'),
        'kirmizi': (st.get('redCards') or {}).get('value'),
        'penalti': (st.get('penalties') or {}).get('value'),
        'faulOrt': (st.get('fouls') or {}).get('value'),
    }


def mac_detay(mac_id, ham):
    """{hakem: {...} | None, stadyum: {ad, sehir, kapasite, konum ([enlem, boylam])} | None}; ağ hatasında önbellekteki
    ya da boş sonuç."""
    mac_id = kimlik(mac_id)  # dosya adına ve adrese girer
    yol = Path(ham) / 'mac' / f'{mac_id}.json'
    if yol.exists():
        eski = json.loads(yol.read_text(encoding='utf-8'))
        if eski.get('hakem') or time.time() - yol.stat().st_mtime < HAKEMSIZ_YENILE_SN:
            return eski
    else:
        eski = {'hakem': None, 'stadyum': None}
    try:
        j = json_getir(fotmob_url('matchDetails', matchId=mac_id))
        time.sleep(BEKLEME)
    except Exception:
        logger.debug('maç detayı alınamadı: %s', mac_id, exc_info=True)
        return eski
    info = ((j.get('content') or {}).get('matchFacts') or {}).get('infoBox') or {}
    s = info.get('Stadium') or {}
    yeni = {'hakem': _hakem(info.get('Referee')),
            'stadyum': {'ad': s['name'], 'sehir': s.get('city') or '', 'kapasite': s.get('capacity'),
                        'konum': [s['lat'], s['long']] if s.get('lat') is not None and s.get('long') is not None else None}
            if s.get('name') else None}
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(yeni, ensure_ascii=False), encoding='utf-8')
    return yeni
