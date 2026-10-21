"""Maç Tahmin Laboratuvarı'nın arayüzü: tamamen Python ile (NiceGUI) yazılmıştır.

Tarayıcıda: python -m mac_tahmin sunucu   ·   Kendi penceresinde: python -m mac_tahmin uygulama
Veriler arka planda kendini günceller: canlı skorlar dakikada bir, süren sezonun sonuçları ve oyuncuları 6 saatte bir.
"""
import os
from pathlib import Path


def calistir(veri_klasoru, ham, *, pencere=False, port=8080, tarayici_ac=True, canli_aralik=60, veri_saat=6,
             depolama=None, yaz=print, host='127.0.0.1'):
    """Uygulamayı açar ve kapanana kadar bekler. pencere=True: kendi penceresinde (Edge WebView2), değilse tarayıcıda.
    host: dinlenen adres; varsayılan yalnızca bu bilgisayar (parolası yok). Dışa açık bir adreste MAC_TAHMIN_ANAHTAR
    ortam değişkeni varsa her istek bu anahtarı ister (erisim.py)."""
    if depolama:  # son seçilen lig, sezon ve sekme burada saklanır
        os.environ.setdefault('NICEGUI_STORAGE_PATH', str(depolama))
    from nicegui import app, ui

    from ..guncelleme import Guncelleyici
    from . import bildirim
    from .depo import Depo
    from .erisim import ANAHTAR_ORTAM, AnahtarKorumasi, YerelHostKorumasi, gunlukte_anahtari_gizle, loopback_mi
    from .ortak import UYGULAMA
    from .sayfa import sayfa

    anahtar = os.environ.get(ANAHTAR_ORTAM)
    gunlukte_anahtari_gizle()
    if anahtar and not loopback_mi(host):
        app.add_middleware(AnahtarKorumasi, anahtar=anahtar)
    if loopback_mi(host):  # pywebview de 127.0.0.1 / localhost açar; başka Host adı DNS yeniden bağlamadır
        app.add_middleware(YerelHostKorumasi)
    g = Guncelleyici(veri_klasoru, ham, canli_aralik, veri_saat, yaz)
    bildirim.HAM = ham  # ilk 11 bildirimi maç sayfasına bakar
    g.dinleyiciler.append(bildirim.kontrol)  # favori takımların maçlarında ilk 11, başlama, gol ve maç sonu bildirimi
    g.baslat()
    depo = Depo(veri_klasoru, g)
    depo.scout_on_hazirla()  # Scout'ta takıma göre öneri hemen gelsin: bütün liglerin aday havuzu arka planda

    def _zararsiz_kopmalari_gec():
        """Windows'ta pencere / sekme kapanınca asyncio "ConnectionResetError" izini yazar; zararsızdır ama günlükte
        hata gibi durur. Yalnızca bu tür geçilir, diğer hatalar eskisi gibi yazılır."""
        import asyncio
        dongu = asyncio.get_running_loop()

        def isleyici(d, baglam):
            if isinstance(baglam.get('exception'), ConnectionResetError):
                return
            d.default_exception_handler(baglam)
        dongu.set_exception_handler(isleyici)
    app.on_startup(_zararsiz_kopmalari_gec)
    bildirim.DEPO = depo  # maç öncesi özet modeli ve kadroları kullanır
    from . import takip
    takip.baslat()  # takip edilen oyuncular: gol / asist, değer ve sözleşme bildirimleri
    kok = Path(__file__).resolve().parent.parent.parent
    bildirim.kaydet(kok / 'uygulama.png')  # Windows bildirimlerinde uygulamanın adı ve logosu
    bildirim.SES = kok / 'bildirim.mp3'  # varsayılan bildirim sesi: kısık hakem düdüğü
    bildirim.SES_KLASORU = Path(ham).parent / 'sesler'  # kullanıcının eklediği sesler (Takımlarım → Bildirim sesi)
    if pencere:  # masaüstü uygulaması: Başlat menüsü kısayoluna kimlik (bildirimin üst satırındaki simge); arka planda
        import threading
        threading.Thread(target=bildirim.kisayola_kimlik_ver, daemon=True).start()
    yazi = kok / 'vendor'
    if (yazi / 'fonts.css').exists():  # yazı tipleri yerel kopyadan (internetsiz açılış için)
        app.add_static_files('/vendor', yazi)
        ui.add_head_html('<link rel="stylesheet" href="/vendor/fonts.css">', shared=True)
    # pencere ve görev çubuğu .ico'yu (her boyut ayrı çizilmiş), tarayıcı sekmesi her boyutta keskin .svg'yi kullanır
    simge = kok / ('uygulama.ico' if pencere or not (kok / 'uygulama.svg').exists() else 'uygulama.svg')
    ui.run(lambda: sayfa(depo), title=UYGULAMA, host=host, port=port, reload=False, show=tarayici_ac and not pencere,
           native=pencere, window_size=(1320, 900) if pencere else None, language='tr',
           favicon=simge if simge.exists() else None, show_welcome_message=False)
