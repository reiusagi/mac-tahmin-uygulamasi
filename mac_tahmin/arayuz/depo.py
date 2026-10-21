"""Açılan sezonların önbelleği. Süren sezonun bir liginin dosyası arka planda değişince yalnızca o lig yeniden kurulur."""
import json
import logging
import re
import threading
from datetime import date
from pathlib import Path

from ..sezon import GECMIS, LIGLER, SON_SEZON, Sezon, ham_oku, lig, sadelestir
from ..sezon import lig as lig_bilgisi
from ..stadyum import stadyum_oku

logger = logging.getLogger(__name__)
ETIKET_TUPLE = '__tuple__'  # diskteki JSON'da tuple'ın işareti: {"__tuple__": [...]}


def onbellek_kodla(o):
    """Disk önbelleği için JSON'a yazılabilir kopya: tuple'lar {"__tuple__": [...]} olur (yüklenince yine tuple),
    sayısal kütüphane sayıları düz sayıya çevrilir. Desteklenmeyen tipte (küme, metin olmayan anahtar…) TypeError."""
    if isinstance(o, tuple):
        return {ETIKET_TUPLE: [onbellek_kodla(x) for x in o]}
    if isinstance(o, list):
        return [onbellek_kodla(x) for x in o]
    if isinstance(o, dict):
        if not all(isinstance(k, str) for k in o):
            raise TypeError('önbellekte sözlük anahtarları metin olmalı')
        return {k: onbellek_kodla(x) for k, x in o.items()}
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    if hasattr(o, 'item'):  # numpy sayıları
        return onbellek_kodla(o.item())
    raise TypeError(f'önbelleğe yazılamayan tip: {type(o).__name__}')


def onbellek_coz(o):
    """onbellek_kodla'nın tersi: {"__tuple__": [...]} yeniden tuple olur."""
    if isinstance(o, list):
        return [onbellek_coz(x) for x in o]
    if isinstance(o, dict):
        if len(o) == 1 and isinstance(o.get(ETIKET_TUPLE), list):
            return tuple(onbellek_coz(x) for x in o[ETIKET_TUPLE])
        return {k: onbellek_coz(x) for k, x in o.items()}
    return o


def dosya_adi(s):
    """Önbellek dosya adına girecek parça: harf, rakam, + _ - dışındakiler _ olur (yol gezintisi olmasın)."""
    return re.sub(r'[^A-Za-z0-9+_-]', '_', str(s))


class Depo:
    def __init__(self, veri_klasoru, guncelleyici):
        self.veri_klasoru = Path(veri_klasoru)
        self.g = guncelleyici
        self._sezonlar = {}
        self._kilit = threading.Lock()
        self._stad, self._stad_zaman = None, None
        self._degerler, self._deger_yenilenen = {}, set()  # lig piyasa değerleri: lig → (zaman, {oyuncu: €}); yenilenenler
        self._deger_kilit = threading.Lock()  # sezon kilidinden ayrı: değer yenileme sezon kurulurken çağrılsa da kilitlenmesin
        self._scout_kilitleri = {}  # (yaş, değer) -> kilit: bütün liglerin aday havuzu aynı anda bir kez hesaplanır
        self._gecmis_endeks = {}  # (lig, yıl) -> geçmiş sezonun oyuncu endeksleri (_gecmis_endeksler)
        # oyuncuların kariyer dizini (oyuncu kartı, önceki sezonlar) ilk kullanımda birkaç saniye sürer: arka planda hazırla
        threading.Thread(target=self._dizin_hazirla, daemon=True).start()

    def _dizin_hazirla(self):
        try:
            from ..sezon import _kariyer_dizini
            _kariyer_dizini(self.veri_klasoru)
        except Exception:
            logger.debug('kariyer dizini hazırlanamadı', exc_info=True)

    SEZON_TAZE_SAAT = 6  # süren sezon, dosyası değişmese de bu kadar saatte bir yeniden kurulur (kadro, değerler, roller)

    def _dosya_zamani(self, anahtar, yil):
        yol = self.veri_klasoru / f'{anahtar}-{yil}.json'
        return yol.stat().st_mtime if yol.exists() else None

    def guncel_mi(self, S):
        """Açık sezon hâlâ güncel mi: süren sezonun lig dosyası, sezon kurulduktan sonra değişmedi ve sezon
        SEZON_TAZE_SAAT'ten eski değil. Geçmiş sezonlar hep güncel."""
        if S.yil != SON_SEZON:
            return True
        import time
        return (getattr(S, '_dosya_zamani', None) == self._dosya_zamani(S.lig, S.yil)
                and time.time() - getattr(S, '_kurulus', 0) < self.SEZON_TAZE_SAAT * 3600)

    def sezon(self, anahtar, yil):
        """Sezonu önceki en çok GECMIS sezonla birlikte kurar (çok sezonlu eğitim için). S.raw: ham veri. Önbellek lig
        lig tutulur: süren sezon yalnızca kendi dosyası değişince (ya da SEZON_TAZE_SAAT geçince) yeniden kurulur;
        başka bir ligde maç bitince açık lig etkilenmez."""
        import time
        with self._kilit:
            S = self._sezonlar.get((anahtar, yil))
            if S is not None and not self.guncel_mi(S):
                S = None
            if S is None:
                S = self._kur(anahtar, yil)
                self._sezonlar[(anahtar, yil)] = S
            return S

    def _kur(self, anahtar, yil):
        """Sezonu kurar (önbelleğe koymadan; sezon() kilit altında çağırır)."""
        import time
        zaman = self._dosya_zamani(anahtar, yil)
        ilk = lig(anahtar)[3]
        onceki = []
        for y in range(yil - GECMIS, yil):
            if y >= ilk:
                try:
                    onceki.append(ham_oku(self.veri_klasoru, anahtar, y))
                except FileNotFoundError:
                    pass
        raw = ham_oku(self.veri_klasoru, anahtar, yil)
        S = Sezon(raw, anahtar, yil, onceki)
        S.raw, S.sim = raw, None
        S._dosya_zamani, S._kurulus = zaman, time.time()
        if yil == SON_SEZON:  # maç tahmininde kadro değeri düzeltmesi (yalnızca süren sezon; değerler bugünkü)
            self._kadro_degeri_ekle(S)
            self._guncel_kulup_ekle(S)
            self._hava_hakimi_ekle(S)
        return S

    def stadyumlar(self):
        yol = self.veri_klasoru / 'stadyumlar.json'
        zaman = yol.stat().st_mtime if yol.exists() else None
        if self._stad is None or zaman != self._stad_zaman:
            self._stad, self._stad_zaman = stadyum_oku(self.veri_klasoru), zaman
        return self._stad

    def ara(self, sorgu, adet=12):
        """Genel arama: süren sezondaki bütün liglerin takımları ve oyuncuları, Avrupa kupalarının takımları.
        Döner: [{'tur': 'takim'|'oyuncu', 'ad', 'ek', 'tid'|('lig', 'yil', 'id')}]; önce adı sorguyla başlayanlar."""
        q = sadelestir(sorgu.strip())
        if len(q) < 2:
            return []
        dizin = self._arama_dizini()
        bulunan = [x for x in dizin if q in x['anahtar']]
        bulunan.sort(key=lambda x: (not x['anahtar'].startswith(q) and not any(k.startswith(q) for k in x['anahtar'].split()),
                                    x['tur'] != 'takim', -x.get('dk', 0)))
        return bulunan[:adet]

    def _arama_dizini(self):
        if getattr(self, '_dizin_surum', None) == self.g.veri_surum and getattr(self, '_dizin', None) is not None:
            return self._dizin
        dizin, goruldu = [], set()
        stad = self.stadyumlar()['ligler']
        for l in LIGLER:
            raw, yil = None, None
            for y in (SON_SEZON, SON_SEZON - 1):
                try:
                    raw, yil = ham_oku(self.veri_klasoru, l[0], y), y
                    break
                except FileNotFoundError:
                    continue
            if raw is None:
                continue
            for t in raw['t']:
                tid = (stad.get(l[0]) or {}).get(t)
                if tid is not None and str(tid) not in goruldu:
                    goruldu.add(str(tid))
                    dizin.append({'tur': 'takim', 'ad': t, 'ek': l[1], 'tid': tid, 'anahtar': sadelestir(t)})
            for a in raw['p']:
                if len(a) > 14 and a[14] is not None and a[1]:
                    dizin.append({'tur': 'oyuncu', 'ad': a[0], 'ek': f'{a[1]} · {l[1]}', 'lig': l[0], 'yil': yil, 'id': a[14],
                                  'dk': a[4] or 0, 'anahtar': sadelestir(a[0])})
        try:  # Avrupa kupalarındaki diğer takımlar (uygulamanın liglerinde olmayanlar)
            from .. import avrupa
            v = avrupa.oku(self.veri_klasoru)
            if v:
                son = {r[0] for kid, _ in avrupa.KUPALAR for s in avrupa.sezonlar(v, kid)[:1]
                       for r in (avrupa.lig_asamasi(avrupa.sezon(v, kid, s)) or [])}
                for t in son:
                    if str(t) not in goruldu:
                        goruldu.add(str(t))
                        ad = v['takimlar'].get(str(t), str(t))
                        dizin.append({'tur': 'takim', 'ad': ad, 'ek': 'Avrupa kupaları', 'tid': t, 'anahtar': sadelestir(ad)})
        except Exception:
            logger.debug('Avrupa kupalarındaki takımlar dizine eklenemedi', exc_info=True)
        self._dizin, self._dizin_surum = dizin, self.g.veri_surum
        return dizin

    def karsilasmalar(self, lig, ad1, ad2, adet=10):
        """İki takımın bu ligdeki geçmiş karşılaşmaları (bütün sezonlar, yeniden eskiye): [(tarih, ev, dep, ev gol,
        dep gol, sezon)]. Biten sezonlar bir kez okunup bellekte tutulur; süren sezon her seferinde dosyadan."""
        if not hasattr(self, '_gecmis'):
            self._gecmis = {}
        if lig not in self._gecmis:
            maclar = []
            for y in range(lig_bilgisi(lig)[3], SON_SEZON):
                try:
                    raw = ham_oku(self.veri_klasoru, lig, y)
                except FileNotFoundError:
                    continue
                maclar += [(m[0], raw['t'][m[1]], raw['t'][m[2]], m[3], m[4], y) for m in raw['m']]
            self._gecmis[lig] = maclar
        try:
            raw = ham_oku(self.veri_klasoru, lig, SON_SEZON)
            guncel = [(m[0], raw['t'][m[1]], raw['t'][m[2]], m[3], m[4], SON_SEZON) for m in raw['m']]
        except FileNotFoundError:
            guncel = []
        hepsi = [m for m in self._gecmis[lig] + guncel if {m[1], m[2]} == {ad1, ad2}]
        return sorted(hepsi, key=lambda m: m[0], reverse=True)[:adet]

    DEGER_SAAT = 24  # piyasa değerleri bu kadar saatte bir yenilenir

    def lig_degerleri(self, lig, takimlar, ilerleme=None):
        """Ligdeki oyuncuların FotMob piyasa değeri: {FotMob oyuncu id: € değeri}. Her takımın sayfası okunur; sonuç
        bellekte ve diskte (ham/degerler/LİG.json) tutulur. Elde değer varsa hemen döner: DEGER_SAAT'ten eskiyse yenisi
        arka planda alınır (kullanıcı takım sayfalarının inmesini beklemez). Hiç yoksa (ilk açılış) indirilir."""
        import json
        import time
        eski = self._degerler.get(lig)
        if eski is None:
            yol = Path(self.g.ham) / 'degerler' / f'{dosya_adi(lig)}.json'
            if yol.exists():
                try:
                    eski = (yol.stat().st_mtime, {int(k): v for k, v in json.loads(yol.read_text(encoding='utf-8')).items()})
                    self._degerler[lig] = eski
                except (OSError, ValueError):
                    eski = None
        if eski is not None:
            if time.time() - eski[0] >= self.DEGER_SAAT * 3600:
                self._degerleri_arka_planda_yenile(lig, takimlar)
            return eski[1]
        out, _ = self._kadro_tara(lig, takimlar, ilerleme)
        self._degerler[lig] = (time.time(), out)
        return out

    def _degerleri_arka_planda_yenile(self, lig, takimlar):
        """Eskimiş piyasa değerlerini arka planda yeniler: ligler tek bir kuyrukta sırayla (birçok lig birden eskidiyse
        kaynağa aynı anda yüzlerce istek gitmesin), bir lig kuyrukta bir kez."""
        import queue
        with self._deger_kilit:
            if lig in self._deger_yenilenen:
                return
            self._deger_yenilenen.add(lig)
            if not hasattr(self, '_deger_kuyruk'):
                self._deger_kuyruk = queue.Queue()
                threading.Thread(target=self._deger_iscisi, daemon=True).start()
        self._deger_kuyruk.put((lig, list(takimlar)))

    def _deger_iscisi(self):
        import time
        while True:
            lig, takimlar = self._deger_kuyruk.get()
            try:
                out, _ = self._kadro_tara(lig, takimlar)
                if out:
                    self._degerler[lig] = (time.time(), out)
            except Exception:
                logger.warning('piyasa değerleri yenilenemedi: %s', lig, exc_info=True)
            finally:
                with self._deger_kilit:
                    self._deger_yenilenen.discard(lig)

    # ------------------------------------------------------------ scout aday havuzu (bütün ligler)
    SCOUT_HAVUZ_SAAT = 24  # lig dosyaları değişmese de bu kadar saatte bir yeniden hesaplanır (piyasa değerleri)
    SCOUT_SURUM = 2  # aday kaydının biçimi ya da hesabı değişirse artırılır: eski dosyalar yok sayılır

    def _scout_yolu(self, yas, deger):
        return Path(self.g.ham) / 'scout' / f'havuz-{dosya_adi(yas or "hepsi")}-{int(deger) if deger else "hepsi"}.json'

    def scout_havuzu_oku(self, yas, deger):
        """Diske yazılmış bütün liglerin aday havuzu: (adaylar, taze mi) ya da yoksa None. Taze: lig dosyalarının hiçbiri
        değişmemiş ve SCOUT_HAVUZ_SAAT dolmamış. Bayat havuz da döner (hemen gösterilir, arkada yenisi hesaplanır)."""
        import time
        yol = self._scout_yolu(yas, deger)
        try:  # eski .pkl dosyaları hiç açılmaz: yok sayılır, havuz yeniden hesaplanır
            v = onbellek_coz(json.loads(yol.read_text(encoding='utf-8')))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RecursionError):
            logger.warning('scout havuzu okunamadı, yeniden hesaplanacak: %s', yol.name, exc_info=True)
            return None
        if not isinstance(v, dict) or v.get('surum') != self.SCOUT_SURUM or not isinstance(v.get('adaylar'), list) \
                or not isinstance(v.get('zamanlar'), dict):
            return None
        zamanlar = {l[0]: self._dosya_zamani(l[0], SON_SEZON) for l in LIGLER}
        taze = v.get('zamanlar') == zamanlar and time.time() - v.get('zaman', 0) < self.SCOUT_HAVUZ_SAAT * 3600
        return v['adaylar'], taze

    def scout_havuzu_hesapla(self, yas, deger, ilerleme=None, durdur=None):
        """Bütün liglerin süren sezondaki scout adayları (oyuncu_tahmin.scout_adaylari; yaş ve piyasa değeri süzgeçleriyle),
        uyruk ve maçtan maça istikrarla; sonuç diske yazılır. ilerleme(metin): durum yazısı; durdur(): True dönerse
        yarıda bırakılır (None döner)."""
        with self._scout_kilitleri.setdefault((yas, deger), threading.Lock()):  # aynı havuz iki kez birden hesaplanmasın
            kayit = self.scout_havuzu_oku(yas, deger)
            if kayit and kayit[1]:  # beklerken başkası (ör. açılıştaki ön hazırlık) hesapladı
                return kayit[0]
            return self._scout_havuzu_hesapla(yas, deger, ilerleme, durdur)

    def _scout_yaz(self, yas, deger, zamanlar, adaylar):
        """Havuzu JSON olarak yazar (önce geçici dosyaya, sonra yerine taşınır). Yazılamazsa dosya bırakılmaz."""
        import time
        metin = json.dumps({'surum': self.SCOUT_SURUM, 'zaman': time.time(), 'zamanlar': zamanlar,
                            'adaylar': onbellek_kodla(adaylar)}, ensure_ascii=False, separators=(',', ':'))
        yol = self._scout_yolu(yas, deger)
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(f'.{threading.get_ident()}.tmp')
        try:
            gecici.write_text(metin, encoding='utf-8')
            gecici.replace(yol)
        finally:
            gecici.unlink(missing_ok=True)
        for eski in yol.parent.glob('*.pkl'):  # eski sürümün kullanılmayan önbellek dosyaları
            try:
                eski.unlink()
            except OSError:
                logger.debug('eski önbellek silinemedi: %s', eski.name, exc_info=True)

    def _scout_havuzu_hesapla(self, yas, deger, ilerleme, durdur):
        zamanlar = {l[0]: self._dosya_zamani(l[0], SON_SEZON) for l in LIGLER}
        adaylar = []
        for k, l in enumerate(LIGLER):
            lig = l[0]
            if durdur and durdur():
                return None
            if ilerleme:
                ilerleme(f'Hazırlanıyor… {l[1]} ({k + 1}/{len(LIGLER)})')
            try:
                S = self.sezon(lig, SON_SEZON)
            except Exception:
                logger.warning('sezon kurulamadı, scout havuzunda atlandı: %s', lig, exc_info=True)
                continue
            if not S.M:
                continue
            adaylar += self.lig_scout_adaylari(S, yas, deger, ilerleme)
        try:
            self._scout_yaz(yas, deger, zamanlar, adaylar)
        except (OSError, TypeError, ValueError):  # yazılamazsa sonuç yine döner; yalnızca bir sonraki açılışta önbellek olmaz
            logger.warning('scout havuzu diske yazılamadı', exc_info=True)
        return adaylar

    def lig_scout_adaylari(self, S, yas, deger, ilerleme=None):
        """Bir ligin scout adayları, uyruk (a['uyruk']: (ülke kodu, ülke adı) ya da None) ve istikrarla (a['istikrar'])."""
        from .. import lig_maclari, oyuncu_tahmin
        from ..sezon import YAS_GRUPLARI
        lig = S.lig
        self.endeks_harmanla(S)  # performans endeksi önceki sezonla harmanlanır (oyuncu_tahmin.endeks_harmanla)

        def deger_ilerleme(i, n):
            if ilerleme:
                ilerleme(f'Piyasa değerleri alınıyor… {lig_bilgisi(lig)[1]} {i}/{n} takım (bir kez, sonra 24 saat önbellekten)')
        degerler = self.lig_degerleri(lig, list(S.T), deger_ilerleme) or {}
        kadro = self.kadro_degerleri(lig, list(S.T), False)  # yoksa oyuncu değerleri toplamı
        # takımından ayrılmış oyuncular (güncel kadroda yok) _guncel_kulup_ekle ile işaretli; aday olmazlar
        uyruk_, _ = self.uyruklar(lig, list(S.T)) or ({}, {})
        yeni = oyuncu_tahmin.scout_adaylari(S, degerler, YAS_GRUPLARI.get(yas), deger or None, kadro) or []
        # maçtan maça istikrar: önceden indirilmiş maç sayfalarından (ağ isteği yok)
        ist = lig_maclari.istikrar(lig_maclari.oyuncu_satirlari(lig, self.g.ham, None, False) or [])
        for a in yeni:
            u = uyruk_.get(str(a['p'].get('fm_id')))
            a['uyruk'] = u if u and u[0] else None
            fm = a['p'].get('fm_id')
            a['istikrar'] = ist.get(int(fm)) if str(fm).isdigit() else None
        return yeni

    ENDEKS_SURUM = 1  # geçmiş sezon endekslerinin disk kaydı; hesap değişirse artırılır

    def _gecmis_endeksler(self, anahtar, yil):
        """Geçmiş bir sezonun oyuncu endeksleri (performans_endeksi'nin çekilmemiş hâli): {oyuncu id: [(takım, yüzdelik
        ortalaması, 90 dk sayısı)]}. Geçmiş sezon değişmez: ham/endeks/'e yazılır (lig dosyası değişince yenilenir) ve
        bellekte tutulur; hesaplamak için kurulan sezon önbelleğe alınmaz (yalnızca bunun için 18 sezon bellekte kalmasın)."""
        import json
        from .. import oyuncu_tahmin
        k = (anahtar, yil)
        if k in self._gecmis_endeks:
            return self._gecmis_endeks[k]
        zaman = self._dosya_zamani(anahtar, yil)
        yol = Path(self.g.ham) / 'endeks' / f'{anahtar}-{yil}.json'
        satirlar = None
        try:
            v = json.loads(yol.read_text(encoding='utf-8'))
            if v.get('zaman') == zaman and v.get('surum') == self.ENDEKS_SURUM:
                satirlar = v['oyuncular']
        except (OSError, ValueError, KeyError):
            logger.debug('endeks önbelleği okunamadı, yeniden hesaplanacak: %s', yol.name, exc_info=True)
        if satirlar is None and zaman is not None:
            with self._kilit:
                S2 = self._sezonlar.get(k) or self._kur(anahtar, yil)
            oyuncu_tahmin.performans_endeksi(S2)
            satirlar = [[q['id'], q['t'], *S2._endeks_ham[q['idx']]] for q in S2.PLY if q['idx'] in S2._endeks_ham]
            yol.parent.mkdir(parents=True, exist_ok=True)
            gecici = yol.with_suffix(f'.{threading.get_ident()}.tmp')
            gecici.write_text(json.dumps({'surum': self.ENDEKS_SURUM, 'zaman': zaman, 'oyuncular': satirlar},
                                         ensure_ascii=False), encoding='utf-8')
            gecici.replace(yol)
        harita = {}
        for pid, t, h, n in satirlar or []:
            harita.setdefault(pid, []).append((t, h, n))
        self._gecmis_endeks[k] = harita
        return harita

    def endeks_harmanla(self, S):
        """Scout endeksi (oyuncu_tahmin.endeks_harmanla): oyuncunun bir önceki sezonu (uygulamanın herhangi bir liginde;
        transfer olan FotMob id'siyle, sezon.kariyer gibi eşleşir) o sezon ligindeki mevkidaşlarına göre
        (_gecmis_endeksler: bir kez hesaplanıp diske yazılır). Sonuç sezonda bir kez hesaplanır (S._endeks_harman)."""
        from .. import oyuncu_tahmin
        from ..sezon import _kariyer_dizini
        if getattr(S, '_endeks_harman', None) is not None:
            return S._endeks_harman
        oyuncu_tahmin.performans_endeksi(S)
        dizin = _kariyer_dizini(self.veri_klasoru)
        onceki = {}
        for p in S.PLY:
            if p['idx'] not in S._endeks_ham:
                continue
            satirlar = {(r['anahtar'], r['yil'], r['takim']): r for r in dizin['kaynak'].get((S.src, p['id']), [])}
            for r in dizin['fm'].get(p.get('fm_id'), []) if p.get('fm_id') is not None else []:
                satirlar.setdefault((r['anahtar'], r['yil'], r['takim']), r)
            toplam_h = toplam_n = 0.0
            goruldu = set()
            for r in satirlar.values():
                if r['yil'] != S.yil - 1 or not r['min']:
                    continue
                try:
                    adaylar = self._gecmis_endeksler(r['anahtar'], r['yil']).get(r['id'], [])
                except Exception:
                    logger.debug('geçmiş sezon endeksi alınamadı: %s %s', r['anahtar'], r['yil'], exc_info=True)
                    continue
                x = next((a for a in adaylar if a[0] == r['takim']), None) or next(iter(adaylar), None)
                if x is None or (r['anahtar'], r['id'], x[0]) in goruldu:
                    continue
                goruldu.add((r['anahtar'], r['id'], x[0]))
                toplam_h += x[1] * x[2]
                toplam_n += x[2]
            if toplam_n:
                onceki[p['idx']] = (toplam_h / toplam_n, toplam_n)
        return oyuncu_tahmin.endeks_harmanla(S, onceki)

    def scout_on_hazirla(self, gecikme=180):
        """Uygulama açıldıktan biraz sonra (arayüz yüklenirken yük bindirmesin) varsayılan süzgeçlerin (23 yaş altı, her
        değer) aday havuzunu, yoksa ya da bayatsa arka planda hazırlar: Scout'ta takıma göre öneri hemen gelsin."""
        def is_():
            try:
                kayit = self.scout_havuzu_oku('U23', '')
                if kayit is None or not kayit[1]:
                    self.scout_havuzu_hesapla('U23', '')
            except Exception:
                logger.warning('scout havuzu ön hazırlığı başarısız', exc_info=True)
        t = threading.Timer(gecikme, is_)
        t.daemon = True
        t.start()

    def degerler_onbellek(self, lig):
        """lig_degerleri'nin ağ isteği yapmayan hâli: bellekte ya da diskte ne varsa (yaşına bakılmadan), yoksa {}."""
        import json
        eski = self._degerler.get(lig)
        if eski:
            return eski[1]
        yol = Path(self.g.ham) / 'degerler' / f'{dosya_adi(lig)}.json'
        if not yol.exists():
            return {}
        try:
            return {int(k): v for k, v in json.loads(yol.read_text(encoding='utf-8')).items()}
        except (OSError, ValueError):
            logger.debug('değer önbelleği okunamadı: %s', yol.name, exc_info=True)
            return {}

    def _kadro_tara(self, lig, takimlar, ilerleme=None):
        """Ligin takım sayfalarından oyuncu değerleri ({FotMob oyuncu id: €}) ve kadro değerleri ({takım adı: €});
        ikisi de ham/degerler/ altına yazılır."""
        import json
        from .. import takim
        oyuncu, kadro = {}, {}
        for k, ad in enumerate(takimlar):
            if ilerleme:
                ilerleme(k + 1, len(takimlar))
            tid = self.takim_kimligi(lig, ad)
            if tid is None:
                continue
            try:
                v = takim.takim_sayfasi(tid, self.g.ham)
            except Exception:
                logger.warning('takım sayfası alınamadı: %s', tid, exc_info=True)
                continue
            for o in v['kadro']:
                if o.get('deger'):
                    oyuncu[o['id']] = o['deger']
            kadro[ad] = sum(o.get('deger') or 0 for o in v['kadro'])
        klasor = Path(self.g.ham) / 'degerler'
        klasor.mkdir(parents=True, exist_ok=True)
        if oyuncu:
            (klasor / f'{dosya_adi(lig)}.json').write_text(json.dumps(oyuncu), encoding='utf-8')
        if sum(1 for v in kadro.values() if v) >= len(takimlar) // 2:
            (klasor / f'{dosya_adi(lig)}-kadro.json').write_text(json.dumps(kadro, ensure_ascii=False), encoding='utf-8')
        return oyuncu, kadro

    def uyruklar(self, lig, takimlar):
        """Önbellekteki takım sayfalarından (lig_degerleri onları indirir; ağ isteği yok): (oyuncuların uyruğu {FotMob
        oyuncu id (metin): (ülke kodu, ülke adı)}, güncel kadrolar {takım adı: {FotMob oyuncu id (metin)}}). Sayfası
        önbellekte olmayan takım kadrolarda yer almaz."""
        from .. import takim
        out, kadrolar = {}, {}
        for ad in takimlar:
            tid = self.takim_kimligi(lig, ad)
            if tid is not None:
                uy = takim.onbellekteki_uyruklar(tid, self.g.ham)[1]
                out.update(uy)
                if uy:
                    kadrolar[ad] = set(uy)
        return out, kadrolar

    KADRO_DIZINI_SN = 3600

    def kadro_dizini(self):
        """Bütün liglerin önbellekteki takım sayfalarından {FotMob oyuncu id (metin): uygulamadaki takım adı} (ağ isteği
        yok; bellekte bir saat)."""
        import time
        from .. import takim
        eski = getattr(self, '_kadro_dizini', None)
        if eski and time.time() - eski[0] < self.KADRO_DIZINI_SN:
            return eski[1]
        out = {}
        for takimlar in self.stadyumlar()['ligler'].values():
            for ad, tid in takimlar.items():
                for f in takim.onbellekteki_uyruklar(tid, self.g.ham)[1]:
                    out.setdefault(f, ad)
        self._kadro_dizini = (time.time(), out)
        return out

    def _guncel_kulup_ekle(self, S):
        """Süren sezonda takımının güncel FotMob kadrosunda olmayan (sezon içinde ayrılmış ya da kiralanmış) oyunculara
        p['ayrildi'] = [yeni kulüp (uygulamanın liglerindeyse, yoksa ''), None] yazar; böylece Scout, golcü listeleri, ilk
        11 ve tablolar onu eski takımında saymaz. Kadrolar önbellekteki takım sayfalarından; ligin takımlarının yarısından
        azının kadrosu biliniyorsa dokunulmaz."""
        _, kadrolar = self.uyruklar(S.lig, list(S.T))
        if len(kadrolar) < len(S.T) / 2:
            return
        dizin = None
        for p in S.PLY:
            takimlar = p['t'].split(' / ')  # sezon içinde ligde iki takımda oynadıysa ikisi de
            if (p.get('ayrildi') or p.get('fm_id') is None or takimlar[-1] not in kadrolar
                    or any(str(p['fm_id']) in kadrolar.get(t, ()) for t in takimlar)):
                continue
            if dizin is None:
                dizin = self.kadro_dizini()
            p['ayrildi'] = [dizin.get(str(p['fm_id']), ''), None]

    def takim_ulkesi(self, tid):
        """Takımın ülke kodu (FotMob, ör. 'TUR', 'ENG'): önbellekteki takım sayfasından, yoksa indirilir."""
        from .. import takim
        ulke = takim.onbellekteki_uyruklar(tid, self.g.ham)[0]
        if ulke is None:
            try:
                ulke = takim.takim_sayfasi(tid, self.g.ham)['ulke']
            except Exception:
                logger.warning('takımın ülkesi alınamadı: %s', tid, exc_info=True)
                return None
        return ulke

    SOZLESME_GUN = 30 # sözleşme bitiş tarihleri nadiren değişir: bu kadar gün önbellekte (ham/sozlesme.json)

    def sozlesmeler(self, fm_idler, ilerleme=None, indir=True):
        """{FotMob oyuncu id (metin): sözleşme bitişi 'YYYY-AA-GG' ya da None}. Önbellekte olmayanlar ya da eskiyenler oyuncu
        sayfasından alınır (oyuncu başına bir istek, aralarında kısa bekleme); ilerleme(sıra, toplam) bildirilir.
        indir=False: yalnızca önbellektekiler döner (bilinmeyenler sonuçta yer almaz)."""
        import json
        import time
        from .. import takim
        yol = Path(self.g.ham) / 'sozlesme.json'
        with self._kilit:
            if not hasattr(self, '_sozlesme'):
                self._sozlesme = json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else {}
        simdi = time.time()
        if not indir:
            return {str(f): self._sozlesme[str(f)][0] for f in fm_idler if f is not None and str(f) in self._sozlesme}
        eksik = [f for f in dict.fromkeys(str(x) for x in fm_idler if x is not None)
                 if simdi - (self._sozlesme.get(f) or [None, 0])[1] > self.SOZLESME_GUN * 86400]
        for k, f in enumerate(eksik):
            if ilerleme:
                ilerleme(k + 1, len(eksik))
            try:
                self._sozlesme[f] = [takim.sozlesme_bitisi(f, self.g.ham), simdi]
            except Exception:
                logger.warning('sözleşme bitişi alınamadı: %s', f, exc_info=True)
                continue
            time.sleep(0.2)  # kaynağa yük bindirmemek için
            if k % 20 == 19:  # yarıda kesilirse kazanılan kaybolmasın
                yol.write_text(json.dumps(self._sozlesme), encoding='utf-8')
        if eksik:
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(json.dumps(self._sozlesme), encoding='utf-8')
        # anahtarlar metin ('123'); yalnızca önbellekte kaydı olanlar (alınamayanlar sonuçta yer almaz)
        return {str(f): self._sozlesme[str(f)][0] for f in fm_idler if f is not None and str(f) in self._sozlesme}

    def sozlesmeler_tm(self, oyuncular, ilerleme=None, indir=True):
        """FotMob'da sözleşmesi olmayan oyuncular için Transfermarkt'tan yalnızca sözleşme bitişi (transfermarkt.py).
        oyuncular: [(FotMob id, ad, kulüp, yaş)]. Döner: {FotMob id (metin): {'bitis', 'kiralik', 'tm'}}."""
        from .. import transfermarkt
        return transfermarkt.sozlesmeler(self.g.ham, oyuncular, ilerleme, indir)

    KADRO_DEGERI_GUN = 7  # kadro değerleri yavaş değişir: maç tahmini için bu kadar gün önbellekte

    def kadro_degerleri(self, lig, takimlar, indir=True):
        """Takımların kadro değeri {takım adı: €} (maç tahmininde süren sezonun güç düzeltmesi). Önbellek eskiyse ya da
        yoksa indir=True ile takım sayfalarından hesaplanır (yaklaşık lig başına 20 istek), indir=False ise None."""
        import json
        import time
        yol = Path(self.g.ham) / 'degerler' / f'{dosya_adi(lig)}-kadro.json'
        if yol.exists() and time.time() - yol.stat().st_mtime < self.KADRO_DEGERI_GUN * 86400:
            return json.loads(yol.read_text(encoding='utf-8'))
        if not indir:
            return None
        _, kadro = self._kadro_tara(lig, takimlar)
        return kadro if sum(1 for v in kadro.values() if v) >= len(takimlar) // 2 else None

    def xg_maclari(self, S):
        """Sezonun xG'li maçları [(tarih, ev adı, dep adı, ev golü, dep golü, ev xG, dep xG, ev şutları, dep şutları)],
        tarih sırasıyla. Sezon verisinde maç xG'si varsa (büyük 5 lig) oradan; yoksa süren sezonda indirilmiş maç
        sayfalarından (ağ isteği yok). Şutlar (maçtaki şutların xG'leri; hak edilen puanın şut şut hesabı için) süren
        sezonda indirilmiş maç sayfalarından, yoksa None. Döner: (maçlar, kaynak: 'sezon' | 'mac' | None)."""
        from ..lig_maclari import takim_xg_maclari
        ad = {str(t): n for n, t in (self.stadyumlar()['ligler'].get(S.lig) or {}).items()}
        sayfalar = takim_xg_maclari(S.lig, self.g.ham) if S.yil == SON_SEZON else []
        if any(m.hx or m.ax for m in S.M):
            # sezon verisinin maçı ile FotMob maç sayfası: aynı ev / deplasman takımı, tarihleri en çok 2 gün farklı
            ids = {n: str(t) for n, t in (self.stadyumlar()['ligler'].get(S.lig) or {}).items()}
            cift = {}
            for m in sayfalar:
                cift.setdefault((str(m['ev_id']), str(m['dep_id'])), []).append(m)

            def sutlar(m):
                for x in cift.get((ids.get(S.T[m.h]), ids.get(S.T[m.a])), []):
                    if abs((date.fromisoformat(x['zaman'][:10]) - date.fromisoformat(m.d[:10])).days) <= 2:
                        return x['ev_sutlar'], x['dep_sutlar']
                return None, None
            return [(m.d, S.T[m.h], S.T[m.a], m.hg, m.ag, m.hx, m.ax, *sutlar(m)) for m in S.M if m.hx or m.ax], 'sezon'
        if S.yil != SON_SEZON:
            return [], None
        out = [(m['zaman'][:10], ad[str(m['ev_id'])], ad[str(m['dep_id'])], m['ev_gol'], m['dep_gol'], m['ev_xg'], m['dep_xg'],
                m['ev_sutlar'], m['dep_sutlar'])
               for m in sayfalar if str(m['ev_id']) in ad and str(m['dep_id']) in ad]
        return out, ('mac' if out else None)

    def _hava_hakimi_ekle(self, S):
        """'Hava hâkimi' özel rolü (sezon.HAVA_HAKIMI): sezon verisinde hava topu yok, maç maç veriden hesaplanır. Yalnızca
        önceden indirilmiş maçlar okunur (ağ isteği yok); maçları inmemiş ligde rol yok."""
        from ..lig_maclari import buyuk_mac_oyunculari, hava_hakimleri, oyuncu_satirlari
        from ..sezon import BUYUK_MAC, BUYUK_TAKIM_SAYISI, HAVA_HAKIMI, rol_esik
        try:
            satirlar = oyuncu_satirlari(S.lig, self.g.ham, indir=False)
        except Exception:
            logger.debug('maç verisi okunamadı, hava hâkimi rolü yok: %s', S.lig, exc_info=True)
            return
        ids = self.stadyumlar()['ligler'].get(S.lig) or {}
        buyukler = {ids[S.T[i]] for i in sorted(range(len(S.T)), key=lambda i: -S.elo[i])[:BUYUK_TAKIM_SAYISI] if S.T[i] in ids}
        for (ad, aciklama), sonuc, sira in ((HAVA_HAKIMI, hava_hakimleri(satirlar, rol_esik(S.min_esik)), 2),
                                            (BUYUK_MAC, buyuk_mac_oyunculari(satirlar, buyukler), 4)):
            uyeler = [p for p in S.PLY if p.get('fm_id') is not None and int(p['fm_id']) in sonuc and not p.get('ayrildi')]
            if not uyeler:
                continue
            for p in uyeler:
                p.setdefault('ozel', []).append(ad)
            S.ozel = (S.ozel or []) + [{'ad': ad, 'aciklama': aciklama,
                                        'oyuncular': sorted(uyeler, key=lambda p: -sonuc[int(p['fm_id'])][sira])}]

    def _kadro_degeri_ekle(self, S):
        """Süren sezona kadro değerlerini ekler: önbellekte varsa hemen, yoksa arka planda indirip ekler."""
        d = self.kadro_degerleri(S.lig, list(S.T), indir=False)
        if d:
            S.deger_ata(d)
            return

        def arka():
            try:
                d2 = self.kadro_degerleri(S.lig, list(S.T))
                if d2:
                    S.deger_ata(d2)
            except Exception:
                logger.debug('kadro değerleri arka planda alınamadı: %s', S.lig, exc_info=True)
        threading.Thread(target=arka, daemon=True).start()

    def oyuncu_kaydi(self, fm_id):
        """FotMob oyuncu id'si → uygulamadaki en yeni kaydı (lig, yıl, oyuncu id) ya da None (G.git ile kartı açılır)."""
        from ..sezon import _kariyer_dizini
        try:
            satirlar = _kariyer_dizini(self.veri_klasoru)['fm'].get(int(fm_id)) or []
        except (TypeError, ValueError):
            return None
        r = max(satirlar, key=lambda r: r['yil'], default=None)
        return (r['anahtar'], r['yil'], r['id']) if r else None

    def takim_kimligi(self, lig, ad):
        """Uygulamadaki takım adı → FotMob takım id (yoksa None)."""
        return (self.stadyumlar()['ligler'].get(lig) or {}).get(ad)

    def takim_ligi(self, fm_id):
        """FotMob takım id → (lig anahtarı, uygulamadaki takım adı); takım uygulamanın liglerinde değilse None.
        Birden çok ligde görünürse (ör. küme düşen) ilk bulunan."""
        for lig, takimlar in self.stadyumlar()['ligler'].items():
            for ad, t in takimlar.items():
                if str(t) == str(fm_id):
                    return lig, ad
        return None

    def mac_olasiliklari(self, maclar):
        """Canlı skor listesindeki (uygulamanın liglerindeki) başlamamış ve canlı maçların olasılıkları:
        {maç id: {'once': maç öncesi [ev, ber, dep], 'simdi': canlıysa kalan süre ve skora göre (modeller.canli_olasilik)
        ya da None, 'dk': okunan dakika}}. Liglerin sezonu gerekirse kurulur (ilk seferde lig başına ~0,5 sn)."""
        from ..modeller import canli_olasilik, dakika_oku
        out = {}
        ligler = {l[0] for l in LIGLER}
        for m in maclar:
            if m.get('lig') not in ligler or m.get('durum') not in ('canli', 'baslamadi'):
                continue
            ters = {str(v): ad for ad, v in (self.stadyumlar()['ligler'].get(m['lig']) or {}).items()}
            ev, dep = ters.get(str(m.get('evId'))), ters.get(str(m.get('depId')))
            try:
                S = self.sezon(m['lig'], SON_SEZON)
            except Exception:
                logger.debug('sezon kurulamadı: %s', m['lig'], exc_info=True)
                continue
            if ev not in S.T or dep not in S.T:
                continue
            h, a = S.T.index(ev), S.T.index(dep)
            kayit = {'once': S.olasilik(h, a), 'simdi': None, 'dk': None}
            if m['durum'] == 'canli':
                dk = dakika_oku(m.get('dakika'))
                if dk is not None:
                    lh, la = S.lambdalar(h, a)
                    kayit['simdi'] = canli_olasilik(lh, la, m.get('evGol') or 0, m.get('depGol') or 0, dk, once=kayit['once'])
                    kayit['dk'] = dk
            out[m['id']] = kayit
        return out

    def canli_mac(self, S, h, a):
        """Canlı skor verisinde (bugün ve önümüzdeki 4 gün) bu eşleşme varsa o maç: hakem ve maçın stadyumu."""
        c = self.g.canli
        if not c:
            return None
        ids = self.stadyumlar()['ligler'].get(S.lig) or {}
        hi, ai = ids.get(S.T[h]), ids.get(S.T[a])
        if hi is None or ai is None:
            return None
        for m in (c.get('maclar') or []) + (c.get('yakinda') or []):
            if m['lig'] == S.lig and m['evId'] == hi and m['depId'] == ai and m.get('durum', 'baslamadi') in ('baslamadi', 'canli'):
                return m
        return None

    def mac_konumu(self, m=None, ev_fm_id=None):
        """Maçın oynanacağı yerin [enlem, boylam]'ı: canlı skor verisindeki maçın stadyumu, yoksa ev sahibinin iç sahası
        (FotMob takım id'siyle); bilinmiyorsa None."""
        if (m or {}).get('konum'):
            return m['konum']
        tid = ev_fm_id if ev_fm_id is not None else (m or {}).get('evId')
        return (self.stadyumlar()['fotmob'].get(str(tid)) or {}).get('konum') if tid is not None else None

    def lig_mac_havasi(self, S, h, a):
        """Süren sezonun oynanmamış lig maçının maç saatindeki hava tahmini (hava.mac_havasi) ya da None. Saat canlı skor
        verisinden, yoksa ligin fikstüründen. Ağa çıkabilir: arka planda çağrılır."""
        from .. import hava, lig_maclari
        if S.yil != SON_SEZON:
            return None
        fm = self.canli_mac(S, h, a)
        ids = self.stadyumlar()['ligler'].get(S.lig) or {}
        eid, did = ids.get(S.T[h]), ids.get(S.T[a])
        bas = (fm or {}).get('baslangic')
        if not bas and eid is not None and did is not None:
            bas = next((m['zaman'] for m in lig_maclari.fikstur(S.lig, self.g.ham) if m['ev_id'] == str(eid)
                        and m['dep_id'] == str(did) and not m['bitti'] and not m['iptal']), None)
        return hava.mac_havasi(self.mac_konumu(fm, eid), bas, self.g.ham)
