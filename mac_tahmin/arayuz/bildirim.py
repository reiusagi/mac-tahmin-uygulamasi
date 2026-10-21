"""Favori takım bildirimleri: canlı skor verisi her yenilendiğinde (dakikada bir) favori takımların maçlarında başlama,
gol ve maç sonu aranır. Bildirim hem uygulamanın içinde (açık sayfalarda, sayfa.py okur) hem Windows bildirimi olarak
gösterilir. Sesi: varsayılan kısık hakem düdüğü (SES); Takımlarım'da genel ses ve takıma özel ses seçilir, kendi ses
dosyası eklenebilir (SES_KLASORU). Favoriler ve ayarlar app.storage.general'da: 'favoriler' [{id, ad}], 'bildirim'
(açık/kapalı), 'ses' ({'genel', 'takimlar'})."""
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from nicegui import app

logger = logging.getLogger(__name__)
_onceki = {}  # maç id -> (durum, ev gol, dep gol)
kuyruk = []  # (sıra no, zaman, başlık, metin); açık sayfalar son gördükleri sıradan sonrakileri gösterir
_sira = 0
_kilit = threading.Lock()
HAM = None  # ham veri klasörü (arayüz açılışta atar); ilk 11 bildirimi için
ILK11_DK = 90  # favori takımın maçına bu kadar dakika kala kesin ilk 11 aranır
ILK11_ARALIK_SN = 240  # aynı maçın sayfasına en sık bu aralıkla bakılır
_ilk11 = {}  # maç id -> son bakılan an; bildirildiyse True
DEPO = None  # veri deposu (arayüz açılışta atar); maç öncesi özet için
OZET_DK = 60  # favori takımın maçına bu kadar dakika kala maç öncesi özet bir kez gönderilir
_ozet = set()  # özeti gönderilen (ya da hazırlanan) maç id'leri


def favori_idler():
    try:
        return {str(f['id']) for f in app.storage.general.get('favoriler', [])}
    except Exception:
        logger.debug('favoriler okunamadı', exc_info=True)
        return set()


def favoriler():
    return list(app.storage.general.get('favoriler', []))


def favori_mi(tid):
    return str(tid) in favori_idler()


def favori_degistir(tid, ad):
    """Takımı favorilere ekler ya da çıkarır; yeni durumu (True: favori) döner."""
    liste = favoriler()
    if favori_mi(tid):
        app.storage.general['favoriler'] = [f for f in liste if str(f['id']) != str(tid)]
        return False
    app.storage.general['favoriler'] = liste + [{'id': tid, 'ad': ad}]
    return True


def acik_mi():
    try:
        return app.storage.general.get('bildirim', True)
    except Exception:
        logger.debug('bildirim ayarı okunamadı', exc_info=True)
        return True


def _ilk11_kontrol(m, fav):
    """Favori takımın maçı yaklaştıysa (ILK11_DK) kesin ilk 11 açıklandı mı diye maç sayfasına bakar; açıklandıysa bir
    kez bildirir (favori takımın ilk 11'i)."""
    from datetime import datetime, timezone
    from ..mac_ozeti import ayrinti
    if HAM is None or _ilk11.get(m['id']) is True or m.get('durum') != 'baslamadi' or not m.get('baslangic'):
        return
    try:
        bas = datetime.fromisoformat(m['baslangic'].replace('Z', '+00:00'))
    except ValueError:
        return
    kalan = (bas - datetime.now(timezone.utc)).total_seconds() / 60
    if kalan > ILK11_DK or kalan < -5 or time.time() - (_ilk11.get(m['id']) or 0) < ILK11_ARALIK_SN:
        return
    _ilk11[m['id']] = time.time()
    try:
        k = ayrinti(m['id'], HAM).get('kadro') or {}
    except Exception:
        logger.debug('maç ayrıntısı alınamadı: %s', m['id'], exc_info=True)
        return
    if k.get('tur') != 'standard':  # henüz açıklanmadı (tahmini ya da önceki maçın kadrosu)
        return
    _ilk11[m['id']] = True
    taraf = 'ev' if str(m.get('evId')) in fav else 'dep'
    adlar = [p['ad'].split(' ')[-1] for p in (k.get(taraf) or {}).get('ilk11') or []]
    takim = m['ev'] if taraf == 'ev' else m['dep']
    gonder(f'İlk 11 açıklandı: {m["ev"]} – {m["dep"]}',
           f'{takim}: ' + ', '.join(adlar) + f' · başlama {bas.astimezone():%H:%M} · tahmin kesin kadroya göre güncellendi',
           takim=m.get('evId') if taraf == 'ev' else m.get('depId'))


def _ilk11_adlari(S, i, taraf, k, tid):
    """Bir takımın ilk 11'i: (adlar, kaynak). Açıklanmış kesin kadro > FotMob'un tahmini > uygulamanın tahmini (tahmin
    sekmesindeki sırayla aynı)."""
    from .. import takim
    fk = (k or {}).get(taraf) or {}
    if k and k.get('tur') in ('standard', 'predicted') and len(fk.get('ilk11') or []) == 11:
        return [p['ad'] for p in fk['ilk11']], 'kesin' if k['tur'] == 'standard' else 'FotMob tahmini'
    if tid is None:
        return [], ''
    try:
        v = takim.takim_sayfasi(tid, HAM)
    except Exception:
        logger.debug('takım sayfası alınamadı: %s', tid, exc_info=True)
        return [], ''
    adaylar, _, mac = takim.ilk11_adaylari(S, S.T[i], v['kadro'])
    dizilis = (v.get('son_ilk11') or {}).get('dizilis') or '4-2-3-1'
    return [p['ad'] for p in takim.en_cok_oynayan(adaylar, dizilis, mac)], 'uygulamanın tahmini'


def ozet_metni(m):
    """Favori takımın maçı için maç öncesi özet: (başlık, metin) ya da None (maç uygulamanın liglerinde değilse).
    Hepsi hesaplanmış veridir: modelin sonuç olasılıkları, beklenen goller ve en olası skor (sezon.Sezon.tahmin), ilk
    11'ler (_ilk11_adlari) ve ilk 11'deki oyunculardan gol atma olasılığı en yüksek olanlar (Sezon.golculer)."""
    from .. import takim
    from ..mac_ozeti import ayrinti
    from ..oyuncu_tahmin import onceki_sezonlar
    from ..sezon import SON_SEZON
    from .ortak import fmt, yuzde
    if DEPO is None or not m.get('lig'):
        return None
    ters = {str(v): ad for ad, v in (DEPO.stadyumlar()['ligler'].get(m['lig']) or {}).items()}
    ev, dep = ters.get(str(m.get('evId'))), ters.get(str(m.get('depId')))
    S = DEPO.sezon(m['lig'], SON_SEZON)
    if not ev or not dep or ev not in S.T or dep not in S.T:
        return None
    h, a = S.T.index(ev), S.T.index(dep)
    t = S.tahmin(h, a)
    try:
        k = ayrinti(m['id'], HAM).get('kadro') or {}
    except Exception:
        logger.debug('maç ayrıntısı alınamadı: %s', m['id'], exc_info=True)
        k = {}
    onceki = onceki_sezonlar(S, DEPO.veri_klasoru, 'gol')
    ilk11, golcu = [], []
    for i, taraf, lam, tid in ((h, 'ev', t['lh'], m.get('evId')), (a, 'dep', t['la'], m.get('depId'))):
        adlar, kaynak = _ilk11_adlari(S, i, taraf, k, tid)
        if adlar:
            ilk11.append(f'{S.T[i]} ({kaynak}): ' + ', '.join(ad.split(' ')[-1] for ad in adlar))
        liste = [{'id': None, 'ad': ad} for ad in adlar]
        for p, pr in S.golculer(i, lam, adet=None, onceki=onceki):
            if not liste or takim.kadrodaki(p['n'], liste):  # ilk 11 bilinmiyorsa süzülmez
                golcu.append((pr, p['n']))
    skor = max(t['hucreler'], key=lambda c: c[2])
    golcu = sorted(golcu, reverse=True)[:3]
    metin = (f'Tahmin: {ev} {yuzde(t["p"][0])} · beraberlik {yuzde(t["p"][1])} · {dep} {yuzde(t["p"][2])}. '
             f'Beklenen gol {fmt(t["lh"], 1)} – {fmt(t["la"], 1)}, en olası skor {skor[0]} – {skor[1]}.'
             + (' Gol atar: ' + ', '.join(f'{n} {yuzde(pr)}' for pr, n in golcu) + '.' if golcu else '')
             + (' İlk 11 · ' + ' · '.join(ilk11) if ilk11 else ''))
    try:
        bas = datetime.fromisoformat(m['baslangic'].replace('Z', '+00:00')).astimezone()
        zaman = f' · {bas:%H:%M}'
    except (KeyError, AttributeError, ValueError):
        zaman = ''
    return f'Maç öncesi: {ev} – {dep}{zaman}', metin


def _ozet_kontrol(m):
    """Favori takımın maçına OZET_DK kala maç öncesi özeti bir kez gönderir (hazırlığı ayrı iş parçacığında)."""
    if DEPO is None or m['id'] in _ozet or m.get('durum') != 'baslamadi' or not m.get('baslangic'):
        return
    try:
        bas = datetime.fromisoformat(m['baslangic'].replace('Z', '+00:00'))
    except ValueError:
        return
    kalan = (bas - datetime.now(timezone.utc)).total_seconds() / 60
    if not 0 < kalan <= OZET_DK:
        return
    _ozet.add(m['id'])

    takim = _favori_takim(m)

    def hazirla():
        try:
            ozet = ozet_metni(m)
        except Exception:
            logger.warning('maç öncesi özet hazırlanamadı: %s', m.get('id'), exc_info=True)
            return
        if ozet:
            gonder(*ozet, takim=takim)
    threading.Thread(target=hazirla, daemon=True).start()


def _favori_takim(m, fav=None):
    """Maçtaki favori takımın FotMob id'si (ikisi de favoriyse ev sahibi): takıma özel bildirim sesi için."""
    fav = favori_idler() if fav is None else fav
    return next((t for t in (m.get('evId'), m.get('depId')) if str(t) in fav), None)


def kontrol(canli):
    """Guncelleyici her yeni canlı skor verisinde çağırır."""
    fav = favori_idler()
    if fav and acik_mi():
        for m in (canli.get('maclar') or []) + (canli.get('yakinda') or []):
            if {str(m.get('evId')), str(m.get('depId'))} & fav:
                _ozet_kontrol(m)
                _ilk11_kontrol(m, fav)
    from . import takip
    for m in canli.get('maclar') or []:
        simdi = (m.get('durum'), m.get('evGol'), m.get('depGol'))
        once = _onceki.get(m['id'])
        _onceki[m['id']] = simdi
        # takip edilen oyuncunun takımının maçı bitti: gol / asist için maç sayfasına bakılacak (takip.py)
        if once is not None and once[0] == 'canli' and simdi[0] == 'bitti' and \
                {str(m.get('evId')), str(m.get('depId'))} & takip.takim_idleri():
            takip.mac_bitti(m)
        if once is None or not fav or not ({str(m.get('evId')), str(m.get('depId'))} & fav) or not acik_mi():
            continue
        skor = f'{m["ev"]} {m.get("evGol") or 0} – {m.get("depGol") or 0} {m["dep"]}'
        takim = _favori_takim(m, fav)
        if once[0] == 'baslamadi' and simdi[0] == 'canli':
            gonder('Maç başladı', f'{m["ev"]} – {m["dep"]} · {m.get("baslik") or ""}', takim=takim)
        elif simdi[0] in ('canli', 'bitti') and (simdi[1], simdi[2]) != (once[1], once[2]) and once[0] != 'baslamadi':
            gol_atan = m['ev'] if (simdi[1] or 0) > (once[1] or 0) else m['dep'] if (simdi[2] or 0) > (once[2] or 0) else None
            if gol_atan:
                gonder(f'GOL! {gol_atan}', f'{skor} ({m.get("dakika") or ""})', takim=takim)
        if once[0] == 'canli' and simdi[0] == 'bitti':
            gonder('Maç sonu', skor, takim=takim)


def gonder(baslik, metin, takim=None):
    """Bildirim: uygulamanın içinde (açık sayfalar kuyruktan okur) ve Windows bildirimi. takim: bildirim bir favori takımın
    maçıyla ilgiliyse FotMob id'si (o takıma ayrı ses seçildiyse o çalar; ses_secimi)."""
    global _sira
    with _kilit:
        _sira += 1
        kuyruk.append((_sira, time.time(), baslik, metin))
        del kuyruk[:-50]
    threading.Thread(target=_windows, args=(baslik, metin, ses_secimi(takim)), daemon=True).start()


# ---------------------------------------------------------------- bildirim sesi
# Windows bildirimi (paketlenmemiş uygulamada) yalnızca sistemin hazır seslerini çalabilir: bildirimin kendi sesi
# kapatılır ve hakem düdüğü (kullanıcının verdiği ses efekti, proje kökünde bildirim.mp3) Windows'un MCI arayüzüyle
# (winmm; MP3 çalar, ses düzeyi ayarlanır, pencere mesaj döngüsü gerekmez) kısık sesle çalınır. Windows Media Player
# bileşeni (WMPlayer.OCX) mesaj döngüsü olmadan hiç başlamadığı için kullanılmaz.
SES = None  # varsayılan bildirim sesinin (hakem düdüğü) dosyası (arayüz açılışta atar)
SES_KLASORU = None  # kullanıcının eklediği ses dosyalarının klasörü (arayüz açılışta atar)
SES_DUZEYI = 25  # 0-100: kısık
SES_EN_UZUN_SN = 6  # ses en çok bu kadar çalınır
SES_UZANTI = ('.mp3', '.wav')
SES_EN_BUYUK = 5 * 1024 * 1024  # eklenen ses dosyası en çok 5 MB
SES_EN_COK_DOSYA = 20  # SES_KLASORU'nda en çok bu kadar ses dosyası
SES_TOPLAM_EN_BUYUK = 50 * 1024 * 1024  # SES_KLASORU'ndaki dosyaların toplamı en çok 50 MB
# hazır seçenekler; bunların dışındakiler SES_KLASORU'ndaki dosyaların adı. Ayar app.storage.general['ses']:
# {'genel': seçim, 'takimlar': {FotMob takım id: seçim ya da 'genel'}}
SESLER = {'duduk': 'Hakem düdüğü (kısık)', 'sistem': 'Windows bildirim sesi', 'sessiz': 'Sessiz'}
_ses_sira = 0


def ses_var():
    return sys.platform == 'win32' and SES is not None and SES.exists()


def ses_ayarlari():
    try:
        return dict(app.storage.general.get('ses') or {})
    except Exception:
        logger.debug('ses ayarları okunamadı', exc_info=True)
        return {}


def ozel_sesler():
    """Kullanıcının eklediği ses dosyaları {dosya adı: yol}."""
    if SES_KLASORU is None or not SES_KLASORU.exists():
        return {}
    return {f.name: f for f in sorted(SES_KLASORU.iterdir()) if f.is_file() and f.suffix.lower() in SES_UZANTI}


def ses_secenekleri():
    """{seçim: ad}: hazır sesler ve eklenen dosyalar."""
    return {**SESLER, **{ad: f'{f.stem} (eklenen)' for ad, f in ozel_sesler().items()}}


def ses_secimi(takim=None):
    """Bildirimde çalınacak ses: takıma ayrı ses seçildiyse o, değilse genel ses (varsayılan hakem düdüğü). Eklenen dosya
    silinmişse hakem düdüğü."""
    a = ses_ayarlari()
    s = (a.get('takimlar') or {}).get(str(takim)) if takim is not None else None
    if not s or s == 'genel':
        s = a.get('genel') or 'duduk'
    return s if s in SESLER or s in ozel_sesler() else 'duduk'


def ses_dosyasi(secim):
    """Seçimin çalınacak dosyası; Windows sesi ya da sessizde None."""
    if secim == 'duduk':
        return SES if ses_var() else None
    return ozel_sesler().get(secim)


def ses_ayarla(secim, takim=None):
    """Genel sesi (takim None) ya da bir takımın sesini ('genel': genel sesi kullanır) kaydeder. Arayüzden çağrılır."""
    a = ses_ayarlari()
    if takim is None:
        a['genel'] = secim
    else:
        t = dict(a.get('takimlar') or {})
        if secim == 'genel':
            t.pop(str(takim), None)
        else:
            t[str(takim)] = secim
        a['takimlar'] = t
    app.storage.general['ses'] = a


def ses_icerigi_gecerli_mi(uzanti, icerik):
    """İçerik, uzantının söylediği türde mi (dosyanın ilk baytlarından): MP3 → 'ID3' etiketi ya da MPEG çerçeve
    başlığı, WAV → 'RIFF' ... 'WAVE'. Adını değiştirilmiş başka bir dosya (ör. .exe, .html) geçmez."""
    uzanti = (uzanti or '').lower()
    if uzanti == '.mp3':
        if icerik[:3] == b'ID3':
            return True
        # çerçeve başlığı: 11 bitlik eşleme (0xFFE), sürüm 01 (ayrılmış) ve katman 00 (ayrılmış) olamaz
        return len(icerik) >= 4 and icerik[0] == 0xFF and icerik[1] & 0xE0 == 0xE0 and (icerik[1] >> 3) & 3 != 1 \
            and (icerik[1] >> 1) & 3 != 0
    if uzanti == '.wav':
        return len(icerik) >= 12 and icerik[:4] == b'RIFF' and icerik[8:12] == b'WAVE'
    return False


def ses_ekle(ad, icerik):
    """Kullanıcının seçtiği ses dosyasını SES_KLASORU'na kaydeder; kayıtlı adı döner (aynı ad varsa sonuna sayı eklenir).
    İçerik gerçekten MP3 / WAV olmalı; klasörde en çok SES_EN_COK_DOSYA dosya ve SES_TOPLAM_EN_BUYUK bayt olabilir."""
    from pathlib import Path
    yol = Path(ad)
    if yol.suffix.lower() not in SES_UZANTI:
        raise ValueError('Yalnızca MP3 ya da WAV dosyası eklenebilir.')
    if len(icerik) > SES_EN_BUYUK:
        raise ValueError('Ses dosyası en çok 5 MB olabilir.')
    if not ses_icerigi_gecerli_mi(yol.suffix, icerik):
        raise ValueError('Dosya geçerli bir MP3 ya da WAV sesi değil.')
    var = list(ozel_sesler().values())
    if len(var) >= SES_EN_COK_DOSYA:
        raise ValueError(f'En çok {SES_EN_COK_DOSYA} ses eklenebilir; önce eskilerinden birini klasörden sil.')
    if sum(f.stat().st_size for f in var) + len(icerik) > SES_TOPLAM_EN_BUYUK:
        raise ValueError(f'Eklenen seslerin toplamı en çok {SES_TOPLAM_EN_BUYUK // (1024 * 1024)} MB olabilir.')
    kok = ''.join(c for c in yol.stem if c.isalnum() or c in ' -_').strip()[:60] or 'ses'
    SES_KLASORU.mkdir(parents=True, exist_ok=True)
    hedef, n = SES_KLASORU / f'{kok}{yol.suffix.lower()}', 1
    while hedef.exists():
        n += 1
        hedef = SES_KLASORU / f'{kok} {n}{yol.suffix.lower()}'
    hedef.write_bytes(icerik)
    return hedef.name


def sesi_dinle(secim):
    """Ayarlarda "Dinle": seçilen sesi çalar (Windows sesi için sistemin bildirim sesi)."""
    if sys.platform != 'win32' or secim == 'sessiz':
        return
    if secim == 'sistem':
        import winsound
        threading.Thread(target=winsound.PlaySound, args=('SystemNotification', winsound.SND_ALIAS), daemon=True).start()
        return
    threading.Thread(target=_sesi_cal, args=(ses_dosyasi(secim),), daemon=True).start()


def _sesi_cal(dosya=None):
    """Bildirim sesini çalar (bitene kadar, en çok SES_EN_UZUN_SN). Hata olursa sessizce geçilir."""
    global _ses_sira
    dosya = dosya or (SES if ses_var() else None)
    if sys.platform != 'win32' or dosya is None or not dosya.exists():
        return
    import ctypes
    with _kilit:
        _ses_sira += 1
        ad = f'bildirim{_ses_sira}'  # aynı anda iki bildirim gelirse karışmasın
    mci = ctypes.windll.winmm.mciSendStringW
    tur = 'waveaudio' if dosya.suffix.lower() == '.wav' else 'mpegvideo'
    try:
        if mci(f'open "{dosya}" type {tur} alias {ad}', None, 0, None):
            return
        mci(f'setaudio {ad} volume to {SES_DUZEYI * 10}', None, 0, None)  # MCI ses düzeyi 0-1000
        mci(f'play {ad}', None, 0, None)
        durum = ctypes.create_unicode_buffer(32)
        for _ in range(SES_EN_UZUN_SN * 10):
            time.sleep(0.1)
            mci(f'status {ad} mode', durum, 32, None)
            if durum.value != 'playing':
                break
    finally:
        mci(f'close {ad}', None, 0, None)


UYGULAMA_KIMLIGI = 'MacTahminLaboratuvari.Uygulama'
POWERSHELL_KIMLIGI = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
_kimlik = {'id': POWERSHELL_KIMLIGI}


def kaydet(simge):
    """Uygulamayı Windows'a bildirim gönderen bir uygulama olarak tanıtır (kullanıcının kendi kayıt alanında,
    HKCU\\Software\\Classes\\AppUserModelId): bildirimlerde PowerShell yerine uygulamanın adı ve logosu görünür.
    Yapılamazsa bildirimler PowerShell adıyla gönderilmeye devam eder."""
    if sys.platform != 'win32':
        return
    if simge and simge.exists():
        _kimlik['logo'] = simge
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f'Software\\Classes\\AppUserModelId\\{UYGULAMA_KIMLIGI}') as k:
            winreg.SetValueEx(k, 'DisplayName', 0, winreg.REG_SZ, 'Maç Tahmin Laboratuvarı')
            if simge and simge.exists():
                winreg.SetValueEx(k, 'IconUri', 0, winreg.REG_SZ, str(simge))
                _kimlik['logo'] = simge
            winreg.SetValueEx(k, 'IconBackgroundColor', 0, winreg.REG_SZ, 'FF1C5B3E')
        _kimlik['id'] = UYGULAMA_KIMLIGI
    except Exception:
        logger.debug('uygulama Windows kaydına eklenemedi', exc_info=True)


# Başlat menüsündeki kısayola uygulama kimliği yazar (System.AppUserModel.ID): Windows bildirimin üst satırındaki küçük
# simgeyi ve adı bu kısayoldan alır. PowerShell içinde küçük bir C# parçasıyla (ek paket gerekmez).
_KISAYOL_BETIGI = r'''
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {
  [PreserveSig] int GetCount(out uint c); [PreserveSig] int GetAt(uint i, out PropertyKey k);
  [PreserveSig] int GetValue(ref PropertyKey k, out PropVariant v); [PreserveSig] int SetValue(ref PropertyKey k, ref PropVariant v);
  [PreserveSig] int Commit(); }
[StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PropertyKey { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit)] public struct PropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }
public static class Kisayol {
  [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
  static extern void SHGetPropertyStoreFromParsingName(string yol, IntPtr bos, int bayrak, ref Guid iid,
    [MarshalAs(UnmanagedType.Interface)] out IPropertyStore ps);
  public static int Ayarla(string yol, string kimlik) {
    Guid g = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"); IPropertyStore s;
    SHGetPropertyStoreFromParsingName(yol, IntPtr.Zero, 2, ref g, out s);
    PropertyKey k = new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    PropVariant v = new PropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(kimlik) };
    int r = s.SetValue(ref k, ref v); if (r == 0) r = s.Commit(); Marshal.ReleaseComObject(s); return r; } }
"@
$sonuc = @()
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter *.lnk | ForEach-Object {
  $hedef = (New-Object -ComObject WScript.Shell).CreateShortcut($_.FullName).TargetPath
  if ($hedef -like '*MacTahmin.exe') { $sonuc += $_.Name + ':' + [Kisayol]::Ayarla($_.FullName, 'KIMLIK') } }
$sonuc -join ';'
'''


def kisayola_kimlik_ver():
    """Başlat menüsündeki MacTahmin kısayollarına uygulama kimliğini yazar. Döner: PowerShell çıktısı ('ad:0' başarı)."""
    if sys.platform != 'win32':
        return ''
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                            _KISAYOL_BETIGI.replace('KIMLIK', UYGULAMA_KIMLIGI)], timeout=60, capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return (r.stdout or b'').decode('utf-8', 'replace').strip() + (r.stderr or b'').decode('utf-8', 'replace').strip()[:300]
    except (OSError, subprocess.SubprocessError) as ex:
        logger.warning('kısayola kimlik verilemedi', exc_info=True)
        return str(ex)


def _windows(baslik, metin, secim='duduk'):
    """Windows bildirimi (PowerShell ile; ek paket gerekmez). Başka sistemde ya da hata olursa sessizce geçilir.
    secim (ses_secimi): ses dosyası çalınacaksa bildirimin kendi sesi kapalı, dosya ardından çalınır (_sesi_cal);
    'sistem': Windows'un bildirim sesi; 'sessiz': ses yok."""
    if sys.platform != 'win32':
        return
    from xml.sax.saxutils import escape, quoteattr
    dosya = ses_dosyasi(secim) if secim not in ('sistem', 'sessiz') else None
    sessiz = secim == 'sessiz' or dosya is not None
    # logo bildirimin içinde (appLogoOverride): kayıttaki logo yolunu (IconUri) her Windows sürümü kullanmıyor
    logo = _kimlik.get('logo')
    resim = (f'<image placement="appLogoOverride" src={quoteattr(logo.as_uri())}/>' if logo and logo.exists() else '')
    xml = (f'<toast><visual><binding template="ToastGeneric"><text>{escape(str(baslik))}</text>'
           f'<text>{escape(str(metin))}</text>{resim}</binding></visual>'
           + ('<audio silent="true"/>' if sessiz else '') + '</toast>')
    betik = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('{xml.replace(chr(39), chr(39) * 2)}');"
        "$n = [Windows.UI.Notifications.ToastNotification]::new($x);"
        # kayıtlı bir uygulama kimliği gerekir (kayıtsız kimlikle Windows bildirimi göstermez): kaydet() başarılıysa
        # uygulamanınki (adı ve logosuyla), değilse PowerShell'inki
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_kimlik['id']}').Show($n)")
    try:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', betik], timeout=20,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), capture_output=True)
    except (OSError, subprocess.SubprocessError):
        logger.debug('Windows bildirimi gösterilemedi', exc_info=True)
    if dosya is not None:
        try:
            _sesi_cal(dosya)  # bildirim ekrana geldikten sonra
        except Exception:
            logger.debug('bildirim sesi çalınamadı', exc_info=True)
