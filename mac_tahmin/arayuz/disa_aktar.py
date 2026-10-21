"""Tabloları dışa aktarma: Excel'in doğrudan açtığı CSV (Türkçe Excel'e göre: ayraç ';', ondalık virgül, Türkçe harfler
bozulmasın diye BOM'lu UTF-8). Dosya İndirilenler\\MacTahmin klasörüne yazılır (masaüstü penceresinde tarayıcı
indirmesine güvenilmez) ve klasör, dosya seçili olarak açılır.

Bir sekmeye eklemek: dugme('Excel\\'e aktar', lambda: (dosya adı, başlıklar, satırlar)) — satırlar liste listesi;
sayılar sayı olarak verilir (biçimi burada), None boş hücre olur."""
import csv
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from nicegui import ui

logger = logging.getLogger(__name__)
# Excel bu karakterlerle başlayan hücreyi formül sayar: metne başa kesme işareti konur (sayı gibi duran "+12" hariç)
FORMUL_BASLANGICI = ('=', '+', '-', '@', '\t', '\r')
_SAYI_GIBI = re.compile(r'[+-]?[0-9]+(?:[.,][0-9]+)*%?')


def klasor():
    indirilen = Path.home() / 'Downloads'
    return (indirilen if indirilen.exists() else Path.home()) / 'MacTahmin'


def _hucre(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return "'" + v if v.startswith(FORMUL_BASLANGICI) and not _SAYI_GIBI.fullmatch(v) else v
    if isinstance(v, bool):
        return 'evet' if v else 'hayır'
    if isinstance(v, float):  # bilimsel gösterim olmadan, en çok 3 ondalık, ondalık virgül
        return (f'{v:.3f}'.rstrip('0').rstrip('.') or '0').replace('.', ',')
    return v


def kaydet(ad, basliklar, satirlar):
    """CSV'yi yazar; yolu döner. Dosya adı: ad + tarih saat (aynı adla üst üste yazılmaz)."""
    temiz = re.sub(r'[\\/:*?"<>|]+', ' ', ad).strip() or 'tablo'
    yol = klasor() / f'{temiz} {datetime.now():%Y-%m-%d %H-%M-%S}.csv'
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow([_hucre(b) for b in basliklar])
        w.writerows([_hucre(v) for v in s] for s in satirlar)
    return yol


def _goster(yol):
    """Dosyayı Gezgin'de seçili gösterir (yalnızca Windows; MACTAHMIN_GEZGIN=0 ortam değişkeniyle kapanır, ör. denemede)."""
    if sys.platform == 'win32' and os.environ.get('MACTAHMIN_GEZGIN') != '0':
        try:
            subprocess.Popen(['explorer', '/select,', str(yol)])
        except OSError:
            logger.debug('Gezgin açılamadı', exc_info=True)


def dugme(etiket, uret, ipucu='Tabloyu Excel\'in açtığı bir dosya (CSV) olarak İndirilenler\\MacTahmin klasörüne kaydeder'):
    """Dışa aktarma düğmesi. uret() -> (dosya adı, başlıklar, satırlar); satır yoksa uyarı verir."""
    def tikla():
        try:
            ad, basliklar, satirlar = uret()
        except Exception:
            logger.exception('Tablo dışa aktarmaya hazırlanamadı')
            ui.notify('Tablo dışa aktarılamadı. Ayrıntı uygulama günlüğünde.', type='negative')
            return
        if not satirlar:
            ui.notify('Aktarılacak satır yok.')
            return
        try:
            yol = kaydet(ad, basliklar, satirlar)
        except Exception:
            logger.exception('CSV dosyası yazılamadı')
            ui.notify('Dosya yazılamadı. İndirilenler klasörüne yazma izni ya da boş yer olmayabilir.', type='negative')
            return
        ui.notify(f'{len(satirlar)} satır kaydedildi: {yol}', type='positive', timeout=8000)
        _goster(yol)
    return ui.button(etiket, icon='file_download', on_click=tikla).props('flat dense no-caps').tooltip(ipucu)
