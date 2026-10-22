"""Masaüstü uygulamasını paketler: python masaustu_paketle.py

1. vendor/: yazı tipleri yerel kopya olarak indirilir (bir kez); uygulama internetsiz de açılır, yalnızca canlı skor
   ve veri güncellemesi için internet gerekir.
2. uygulama.ico: uygulama simgesi çizilir.
3. PyInstaller ile dist/MacTahmin/MacTahmin.exe üretilir (arayüz, veriler ve Python dahil; Python kurulu olmayan
   bilgisayarda da çalışır). NiceGUI'nin kendi dosyaları da pakete eklenir (nicegui-pack'in yaptığı gibi).
"""
import re
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent
VENDOR = KOK / 'vendor'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
FONTLAR = ('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700'
           '&family=Barlow:wght@400;500;600;700&display=swap')


def indir(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
        return r.read()


def yerel_kaynaklar():
    (VENDOR / 'fonts').mkdir(parents=True, exist_ok=True)
    if not (VENDOR / 'fonts.css').exists():
        css = indir(FONTLAR).decode('utf-8')
        adresler = sorted(set(re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+)\)', css)))
        for i, adres in enumerate(adresler):
            ad = f'f{i:02d}.woff2'
            (VENDOR / 'fonts' / ad).write_bytes(indir(adres))
            css = css.replace(adres, f'fonts/{ad}')
        (VENDOR / 'fonts.css').write_text(css, encoding='utf-8')
        print(f'{len(adresler)} yazı tipi dosyası indirildi')


SAHA, CIZGI = (28, 91, 62, 255), (255, 255, 255, 255)
BOYUTLAR = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _saha(s):
    """s×s piksellik simge: yeşil saha, orta çizgi, orta yuvarlak, ceza sahaları. Küçük boyutlar küçültülerek değil
    doğrudan kendi piksel ızgarasında, kenar yumuşatmasız çizilir; böylece görev çubuğunda ve sekmede bulanık görünmez.
    Büyük boyutlar 4 kat büyük çizilip küçültülür (yuvarlak düzgün olsun)."""
    from PIL import Image, ImageDraw
    k = 4 if s >= 64 else 1
    S = s * k
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, round(s / 20)) * k                        # çizgi kalınlığı
    yuk = round(s * 0.80) // 2 * 2 * k                   # saha yüksekliği (çift sayı: ortalansın)
    y0, y1 = (S - yuk) // 2, (S + yuk) // 2 - 1
    x0, x1 = 0, S - 1
    d.rounded_rectangle([x0, y0, x1, y1], radius=max(1, round(s * 0.12)) * k, fill=SAHA)
    orta = S // 2 - w // 2
    d.rectangle([orta, y0, orta + w - 1, y1], fill=CIZGI)  # orta çizgi boydan boya
    r = max(2, round(s * 0.15)) * k
    cx, cy = S // 2, (y0 + y1 + 1) // 2
    d.ellipse([cx - r, cy - r, cx + r - 1, cy + r - 1], outline=CIZGI, width=w)
    kg, ky = max(2, round(s * 0.15)) * k, max(3, round(s * 0.20)) * k   # ceza sahası genişliği, yarı yüksekliği
    for sol in (True, False):  # ceza sahaları kenara bitişik: dış kenarları tuvalin dışında kalır
        xa, xb = (x0 - w, x0 + kg) if sol else (x1 - kg, x1 + w)
        d.rectangle([xa, cy - ky, xb, cy + ky - 1], outline=CIZGI, width=w)
    return img.resize((s, s), Image.LANCZOS) if k > 1 else img


def simge(zorla=False):
    """uygulama.ico (pencere, görev çubuğu, .exe), uygulama.svg (tarayıcı sekmesi) ve uygulama.png (Windows bildirimleri)."""
    if not (KOK / 'uygulama.png').exists() or zorla:
        _saha(256).save(KOK / 'uygulama.png')
    if (KOK / 'uygulama.ico').exists() and (KOK / 'uygulama.svg').exists() and not zorla:
        return
    kareler = [_saha(s) for s in BOYUTLAR]
    kareler[-1].save(KOK / 'uygulama.ico', sizes=[(s, s) for s in BOYUTLAR], append_images=kareler[:-1])
    (KOK / 'uygulama.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect x="0" y="6" width="64" height="52" rx="8" fill="#1c5b3e"/>'
        '<g fill="none" stroke="#fff" stroke-width="3">'
        '<path d="M32 10v44"/><circle cx="32" cy="32" r="9"/>'
        '<path d="M4 19h10v26H4M60 19H50v26h10"/></g></svg>', encoding='utf-8')
    print('simge çizildi')


# başlangıç önbelleği: yeni bir bilgisayarda ilk açılışta binlerce sayfanın kaynaklardan tek tek (aralarda bekleyerek)
# inmesini beklememek için paketle gelen hazır sayfalar; uygulama yalnızca eksik olanları kopyalar (masaustu.hazirla)
# biten maçlar, takım sayfaları, piyasa değerleri, scout havuzu, geçmiş sezonların oyuncu endeksleri (Depo._gecmis_endeksler)
BASLANGIC_KLASOR = ('mac_tam', 'takim', 'degerler', 'scout', 'endeks')
BASLANGIC_DOSYA = ('sozlesme.json', 'transfermarkt.json')  # sözleşme bitiş tarihleri (Transfermarkt'tan yalnızca tarih)


def baslangic_onbellegi():
    """build/ham_baslangic: BASLANGIC_KLASOR ve BASLANGIC_DOSYA ile süren sezonun FotMob lig dosyaları (haftalık fikstür).
    Kaynak proje klasöründeki ham/ ile masaüstü uygulamasının kendi önbelleği (%LOCALAPPDATA%\\MacTahmin\\ham); ikisinde de
    olan dosyanın yenisi alınır."""
    import os
    import shutil
    import time
    from mac_tahmin.guncelleme import ESKIME_GUN
    from mac_tahmin.sezon import FOTMOB_ID, SON_SEZON
    kaynaklar = [KOK / 'ham', Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'MacTahmin' / 'ham']
    hedef = KOK / 'build' / 'ham_baslangic'
    shutil.rmtree(hedef, ignore_errors=True)
    secilen = {}  # göreli yol -> kaynak dosya
    simdi = time.time()

    def taze(f, kl):  # uygulamanın önbellek temizliği (guncelleme.ESKIME_GUN) hemen silecek kadar eski olmasın
        return kl not in ESKIME_GUN or simdi - f.stat().st_mtime < (ESKIME_GUN[kl] - 1) * 86400
    for k in kaynaklar:
        if not k.exists():
            continue
        dosyalar = [f for kl in BASLANGIC_KLASOR for f in (k / kl).glob('*') if f.suffix == '.json' and taze(f, kl)]
        dosyalar += [k / ad for ad in BASLANGIC_DOSYA] + [k / f'fm-{i}-{SON_SEZON}.json' for i in FOTMOB_ID.values()]
        for f in dosyalar:
            if f.is_file():
                g = f.relative_to(k)
                if g not in secilen or f.stat().st_mtime > secilen[g].stat().st_mtime:
                    secilen[g] = f
    hedef.mkdir(parents=True, exist_ok=True)  # ham/ yoksa (GitHub Actions) önbellek boş kalır, sürüm dosyası yine yazılır
    for g, f in secilen.items():
        (hedef / g).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, hedef / g)
    (hedef / 'surum.txt').write_text(str(int(time.time())), encoding='utf-8')
    print(f'başlangıç önbelleği: {len(secilen)} dosya, {sum(f.stat().st_size for f in secilen.values()) / 1e6:.0f} MB')
    return hedef


def paketle():
    import nicegui
    import PyInstaller.__main__
    ayrac = ';'
    veri = [(Path(nicegui.__file__).parent, 'nicegui'), (KOK / 'd', 'd'), (VENDOR, 'vendor'), (KOK / 'uygulama.ico', '.'),
            (KOK / 'uygulama.svg', '.'), (KOK / 'uygulama.png', '.'), (KOK / 'bildirim.mp3', '.'),  # bildirim sesi
            (baslangic_onbellegi(), 'ham_baslangic')]
    if (KOK / 'ham' / 'dogum.json').exists():
        veri.append((KOK / 'ham' / 'dogum.json', '.'))
    PyInstaller.__main__.run([
        str(KOK / 'MacTahmin.pyw'), '--name', 'MacTahmin', '--windowed', '--noconfirm', '--clean',
        '--icon', str(KOK / 'uygulama.ico'),
        *[x for kaynak, hedef in veri for x in ('--add-data', f'{kaynak}{ayrac}{hedef}')],
        '--distpath', str(KOK / 'dist'), '--workpath', str(KOK / 'build'), '--specpath', str(KOK / 'build'),
    ])
    print(f'hazır: {KOK / "dist" / "MacTahmin" / "MacTahmin.exe"}')


if __name__ == '__main__':
    yerel_kaynaklar()
    simge()
    paketle()
