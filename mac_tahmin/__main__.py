"""Komut satırı: python -m mac_tahmin <komut> ...

  veri         Understat ve FotMob verisini indirip d/ klasörüne yazar
  tablo        Puan durumu (xG ve Elo ile)
  tahmin       İki takım arasındaki maçın olasılıkları, skorlar ve gol atabilecek oyuncular
  degerlendir  Modellerin sezonun son %30'undaki başarısı
  oyuncu       Oyuncu kartı: özet, mevkidaşlarına göre yüzdelikler, ayrıntılar ve sezon geçmişi
  oyuncular    Oyuncu listesi; --mevki (ör. LB, AM, RW ya da D) ve --yas (U18, U21, U23, 24-29, 30+) süzgeçleri
  benzer       Bir oyuncuya istatistik profili en çok benzeyen oyuncular (--tum: bütün liglerde)
  roller       Oyuncu rolleri: istatistik profiline göre kümeleme (k-means)
  canli        Altı ligin bugünkü maçları, canlı skorlarla; ekran kendini yeniler
  simulasyon   Süren sezonun kalan maçlarını 10.000 kez oynatır: beklenen puan, şampiyonluk ve küme düşme olasılıkları
  uygulama     Uygulamayı kendi penceresinde açar (veriler kendini günceller)
  sunucu       Uygulamayı tarayıcıda açar (veriler kendini günceller)
  stadyum      Takımların iç saha stadyumlarını indirir
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
# veri klasörleri, komut hangi klasörden çalıştırılırsa çalıştırılsın proje klasöründe aranır
PROJE = Path(__file__).resolve().parent.parent

from . import veri
from .bicim import fmt, yuzde
from .modeller import js_round
from .sezon import (GECMIS, LIGLER, POS, SON_SEZON, Sezon, benzer_esik, benzer_oyuncular, ham_oku, kariyer, lig,
                    mevki_adi, sezon_etiketi, yas_metni, DETAY, YAS_GRUPLARI)
from .sezon import sadelestir as sadelestir_metin
from .stadyum import stadyum_bul, stadyum_oku, stadyumlar_indir


def hakem_metni(h):
    parca = [h['ad'] + (f' ({h["ulke"]})' if h.get('ulke') else '')]
    if h.get('mac'):
        parca.append(f'{h["mac"]} maç')
    if h.get('sariOrt') is not None:
        parca.append(f'maç başına {fmt(h["sariOrt"])} sarı kart')
    if h.get('kirmizi') is not None:
        parca.append(f'{h["kirmizi"]} kırmızı')
    if h.get('penalti') is not None:
        parca.append(f'{h["penalti"]} penaltı')
    return ' · '.join(parca)


def yaklasan_mac(stads, lig_anahtar, ev, dep, gun_sayisi=7):
    """İki takımın önümüzdeki günlerdeki maçını FotMob'da arar; hakem ve stadyumla döner. Ağ yoksa None."""
    from datetime import datetime, timedelta
    from .canli import gunun_maclari
    from .hakem import mac_detay
    ids = stads['ligler'].get(lig_anahtar) or {}
    ev_id, dep_id = ids.get(ev), ids.get(dep)
    if ev_id is None or dep_id is None:
        return None
    for i in range(gun_sayisi):
        gun = datetime.now() + timedelta(days=i)
        try:
            maclar = gunun_maclari(gun.strftime('%Y%m%d'))
        except Exception:
            logger.debug('günün maçları alınamadı: %s', gun, exc_info=True)
            return None
        for m in maclar:
            if m['evId'] == ev_id and m['depId'] == dep_id and m['durum'] == 'baslamadi':
                d = mac_detay(m['id'], PROJE / 'ham')
                std = d.get('stadyum') or {}
                return {'gun': gun.strftime('%d.%m.%Y') + ' ' + m['saat'], 'hakem': d.get('hakem'),
                        'stadyum': std.get('ad'), 'sehir': std.get('sehir')}
    return None


def stadyum_metni(std):
    kap = ' · ' + f'{std["kapasite"]:,}'.replace(',', '.') + ' kişilik' if std.get('kapasite') else ''
    return std['ad'] + (f' · {std["sehir"]}' if std.get('sehir') else '') + kap


def sezon_ac(a):
    """Sezonu, çok sezonlu eğitim için önceki en çok GECMIS sezonla birlikte açar (eskiden yeniye)."""
    ilk = lig(a.lig)[3]
    onceki = []
    for y in range(a.sezon - GECMIS, a.sezon):
        if y >= ilk:
            try:
                onceki.append(ham_oku(a.veri, a.lig, y))
            except FileNotFoundError:
                pass
    return Sezon(ham_oku(a.veri, a.lig, a.sezon), a.lig, a.sezon, onceki)


def baslik(s):
    l = lig(s.lig)
    print(f'{l[1]} {sezon_etiketi(s.yil, s.lig)}' + (' · sezon sürüyor' if s.U else ''))
    print()


def cmd_oyuncular(a):
    s = sezon_ac(a)
    baslik(s)
    m = (a.mevki or '').upper()
    if m and m not in DETAY and m not in POS:
        sys.exit('Mevki: ' + ', '.join(f'{k} ({v[1]})' for k, v in DETAY.items())
                 + ' ya da ana mevki ' + ', '.join(f'{k} ({v})' for k, v in POS.items() if k in 'DMWFG'))
    alt_y, ust_y = YAS_GRUPLARI[a.yas] if a.yas else (None, None)
    ply = [p for p in s.PLY if (not m or (p.get('detay') == m and DETAY[m][0] == p['pos'] if m in DETAY else p['pos'] == m))
           and (not a.yas or (p['yas'] is not None and alt_y <= p['yas'] <= ust_y))]
    ply.sort(key=lambda p: -(p[a.sirala] if p.get(a.sirala) is not None else -1e9))
    print(f'{"#":>3}  {"Oyuncu":<26}{"Takım":<22}{"Mevki":<18}{"Yaş":>4}{"Dk":>6}{"Gol":>5}{"Ast":>5}{"xG":>6}{"xA":>6}')
    for n, p in enumerate(ply[:a.adet], 1):
        yas = '' if p['yas'] is None else p['yas']
        print(f'{n:>3}  {p["n"][:25]:<26}{p["t"][:21]:<22}{mevki_adi(p)[:17]:<18}{yas:>4}{p["min"]:>6}{p["g"]:>5}'
              f'{p["a"]:>5}{fmt(p["xg"], 1):>6}{fmt(p["xa"], 1):>6}')
    bilinmeyen = sum(p['yas'] is None for p in s.PLY)
    print(f'\n{len(ply)} oyuncu.' + (' Yaş süren sezonda bugüne, geçmiş sezonlarda sezonun ortasına göredir;'
                                    f' {bilinmeyen} oyuncunun doğum tarihi bilinmiyor.' if a.yas and bilinmeyen else ''))


def cmd_veri(a):
    from . import avrupa, milli
    hata = veri.indir(a.ligler or None, a.sezonlar or None, a.veri, a.ham, a.yenile)
    if not a.ligler:  # milli turnuvalar ve Avrupa kupaları (süren sezonlar 6 saatten eskiyse yeniden)
        hata += milli.indir(a.ham, a.veri, yenile_guncel=True, yaz=print)
        hata += avrupa.indir(a.ham, a.veri, yenile_guncel=True, yaz=print)
    if hata:
        sys.exit(1)


def cmd_tablo(a):
    s = sezon_ac(a)
    baslik(s)
    elo = {r['i']: r['elo'] for r in s.reyting}
    print(f'{"#":>2}  {"Takım":<26}{"O":>3}{"G":>4}{"B":>4}{"M":>4}{"AG":>5}{"YG":>5}{"AV":>5}{"xG":>7}{"xGA":>7}{"Elo":>7}{"P":>5}')
    for n, r in enumerate(s.tablo, 1):
        xg = (fmt(r['xG'], 1), fmt(r['xGA'], 1)) if s.xg_var else ('–', '–')
        print(f'{n:>2}  {r["name"][:25]:<26}{r["O"]:>3}{r["G"]:>4}{r["B"]:>4}{r["M"]:>4}{r["AG"]:>5}{r["YG"]:>5}'
              f'{r["AV"]:>+5}{xg[0]:>7}{xg[1]:>7}{round(elo[r["i"]]):>7}{r["P"]:>5}')
    print(f'\n{len(s.M)} maç oynandı' + (f', {len(s.U)} maç kaldı' if s.U else '') + '. Puan silme cezaları dahil değildir.'
          + (f' Hükmen ya da iptal {s.skip} maç sayılmadı.' if s.skip else ''))


def cmd_tahmin(a):
    s = sezon_ac(a)
    h, d = s.takim_bul(a.ev), s.takim_bul(a.deplasman)
    if h == d:
        sys.exit('Ev sahibi ve deplasman aynı takım olamaz.')
    baslik(s)
    t = s.tahmin(h, d)
    print(f'{s.T[h]} – {s.T[d]}')
    stads = stadyum_oku(a.veri)
    std = stadyum_bul(stads, a.lig, s.T[h])
    yaklasan = yaklasan_mac(stads, a.lig, s.T[h], s.T[d]) if s.yil == SON_SEZON else None
    if yaklasan:
        std = yaklasan.get('stadyum') and {'ad': yaklasan['stadyum'], 'sehir': yaklasan.get('sehir')} or std
        print(f'  Maç: {yaklasan["gun"]}')
    if std:
        print(f'  {stadyum_metni(std)}')
    if yaklasan:
        print('  Hakem: ' + (hakem_metni(yaklasan['hakem']) if yaklasan.get('hakem') else 'henüz atanmadı'))
    print(f'  Ev kazanır {yuzde(t["p"][0])} · Beraberlik {yuzde(t["p"][1])} · Deplasman kazanır {yuzde(t["p"][2])}')
    print(f'  Beklenen gol: {fmt(t["lh"])} – {fmt(t["la"])}')
    oynanan = [m for m in s.M if m.h == h and m.a == d]
    if oynanan:
        m = oynanan[-1]
        print(f'  Bu sezon oynandı: {s.T[h]} {m.hg}–{m.ag} {s.T[d]} ({m.d[8:]}.{m.d[5:7]}.{m.d[:4]})')
    print('\nEn olası skorlar')
    for i, j, p in t['skorlar']:
        print(f'  {i} – {j}  {fmt(p * 100, 1)}%')
    for takim, liste in ((s.T[h], t['golcu_ev']), (s.T[d], t['golcu_dep'])):
        print(f'\nKim gol atar? {takim} (90 dk oynarsa)')
        if not liste:
            print('  Yeterli dakika almış oyuncu yok.')
        for p, pr in liste:
            print(f'  {yuzde(pr):>5}  {p["n"]}  ({p["g"]} gol, {p["a"]} asist, {fmt(p["xg"], 1)} xG)')


def cmd_degerlendir(a):
    s = sezon_ac(a)
    ev = s.degerlendir()
    if not ev:
        sys.exit(f'Model karşılaştırması için sezonda en az 120 maç oynanmış olmalı (şu an {len(s.M)}).')
    baslik(s)
    print(f'Test: bu sezonun son {ev["n_test"]} maçı. Tek sezon: yalnızca bu sezonun ilk {ev["n_egitim"]} maçıyla eğitim.')
    if ev['n_onceki']:
        print(f'Önceki sezonlarla: buna önceki {ev["n_onceki"]} sezonun {ev["n_gecmis"]} maçı eklendi, Elo ve takım güçleri'
              ' sezondan sezona taşındı' + (', maç xG değerleri de özellik olarak kullanıldı.' if ev['xg'] else '.'))
    print('Log-loss: düşük olan iyi.\n')
    son = lambda r: r['cok'] or r['tek']
    en_iyi = min(son(r)['log_loss'] for r in ev['sonuclar'])
    print(f'  {"Model":<28}{"Doğruluk":>10}{"Tek sezon":>11}' + (f'{"Önceki sezonlarla":>19}{"Fark":>8}' if ev['n_onceki'] else ''))
    for r in ev['sonuclar']:
        isaret = ' ←' if son(r)['log_loss'] == en_iyi else ''
        satir = f'  {r["model"]:<28}{yuzde(son(r)["dogruluk"]):>10}{fmt(r["tek"]["log_loss"], 3):>11}'
        if r['cok']:
            fark = r['cok']['log_loss'] - r['tek']['log_loss']
            satir += f'{fmt(r["cok"]["log_loss"], 3):>19}{("+" if fark > 0 else "") + fmt(fark, 3):>8}'
        print(satir + isaret)
    print('\nRandom Forest: hangi bilgi önemli?')
    for o in ev['onem']:
        print(f'  {o["f"]:<16}{fmt(o["v"])}  ' + '█' * round(o['v'] * 50))


def cmd_simulasyon(a):
    s = sezon_ac(a)
    if not s.U:
        sys.exit('Bu sezonda oynanacak maç kalmadı; simülasyon yalnızca süren sezonlarda anlamlı.')
    baslik(s)
    t0 = time.time()
    sonuc = s.simulasyon(a.n)
    n = len(s.T)
    alt = 3 if n >= 16 else 2
    yer = {r['i']: k + 1 for k, r in enumerate(s.tablo)}
    ys = lambda p: '>99%' if p >= 0.995 else '<1%' if 0 < p < 0.005 else '–' if p == 0 else f'{js_round(p * 100)}%'
    print(f'Kalan {len(s.U)} maç {a.n} kez oynatıldı ({time.time() - t0:.0f} sn). Takım güçleri bu sezonun'
          + (f' ve önceki {s.n_onceki} sezonun' if s.n_onceki else '') + ' sonuçlarından.\n')
    print(f'{"#":>3}  {"Takım":<26}{"P":>4}{"Beklenen P":>12}{"Şampiyon":>10}{"İlk 4":>8}{f"Son {alt}":>8}')
    for r in sonuc:
        d = r['dist']
        print(f'{yer[r["i"]]:>3}  {r["name"][:25]:<26}{r["P"]:>4}{fmt(r["exp"], 1):>12}{ys(d[0]):>10}'
              f'{ys(sum(d[:4])):>8}{ys(sum(d[n - alt:])):>8}')
    print('\nPuan silme cezaları, hükmen maçlar ve ligin play-off ya da ikiye ayrılma kuralları hesaba katılmaz.')


def cmd_roller(a):
    s = sezon_ac(a)
    R = s.roller
    if not R:
        sys.exit('Bu sezonda roller için yeterli oyuncu yok.')
    baslik(s)
    print(f'En az {R["esik"]} dakika oynayan {R["n"]} saha oyuncusu, 90 dakika başına istatistik profillerine göre '
          f'{len(R["roller"])} kümeye ayrıldı (k-means).'
          + (f' Bu sezon için kaynakta {", ".join(f"{a} yerine {b.lower()}" for a, b in R["yedek"])} kullanıldı'
             f' ({" ve ".join(a for a, _ in R["yedek"])} verisi yok).' if R.get('yedek') else '') + '\n')
    for r in R['roller']:
        one = ', '.join(f'{ad} {"↑" if yuksek else "↓"}' for ad, yuksek in r['one'])
        print(f'{r["ad"]} ({r["n"]} oyuncu)' + (f'  [{one}]' if one else ''))
        print(f'  {r["aciklama"]}')
        print(f'  {"En çok oynayanlar" if r["sure"] else "En iyiler"}: {", ".join(p["n"] for p in r["en_iyi"])}\n')
    if a.rol:
        q = sadelestir_metin(a.rol)
        uyan = [p for p in s.PLY if p.get('rol') and q in sadelestir_metin(p['rol'])]
        if not uyan:
            sys.exit(f'"{a.rol}" adında rol yok.')
        print(f'{uyan[0]["rol"]} rolündeki oyuncular (dakikaya göre):')
        for p in sorted(uyan, key=lambda p: -p['min']):
            print(f'  {p["n"]:<28}{p["t"][:22]:<23}{p["min"]:>5} dk  {p["g"]:>3} gol {p["a"]:>3} asist')


def cmd_benzer(a):
    s = sezon_ac(a)
    bulunan = s.oyuncu_bul(a.ad)
    if not bulunan:
        sys.exit(f'"{a.ad}" adında oyuncu bulunamadı.')
    p = bulunan[0]
    r = benzer_oyuncular(s, p, a.veri, a.tum)
    if r.get('kaleci'):
        sys.exit('Bu ligin veri kaynağı kaleciler için ayrıntılı istatistik vermediği için karşılaştırma yapılamıyor.')
    if r.get('yok'):
        sys.exit(f'{p["n"]} için karşılaştırma yapılacak yeterli veri yok (en az {benzer_esik(s)} dakika gerekir).')
    baslik(s)
    print(f'{p["n"]} ({p["t"]}) için en benzer oyuncular' + (' (tüm ligler)' if a.tum else '') + '\n')
    for q, lig_anahtar, b in r['sonuc']:
        yer = f' · {lig(lig_anahtar)[1]} ({lig(lig_anahtar)[2]})' if lig_anahtar != s.lig else ''
        print(f'  {js_round(b * 100):>3}%  {q["n"]}  ({q["t"]} · {mevki_adi(q)}{yer} · {q["g"]} gol, {q["a"]} asist)')
    print(f'\nBenzerlik; {", ".join(t[1] for t in r["tanimlar"])} değerlerinin (90 dk başına) en az {r["esik"]} dakika'
          f' oynayan {r["n"]} oyuncu arasındaki konumuna göre; hem oyun tarzı hem üretim düzeyi benzer olmalı.')


def cmd_oyuncu(a):
    s = sezon_ac(a)
    bulunan = s.oyuncu_bul(a.ad)
    if not bulunan:
        sys.exit(f'"{a.ad}" adında oyuncu bulunamadı.')
    baslik(s)
    if len(bulunan) > 1:
        print('Birden çok oyuncu eşleşti, en çok süre alan gösteriliyor. Diğerleri: '
              + ', '.join(p['n'] for p in bulunan[1:6]) + '\n')
    k = s.oyuncu_karti(bulunan[0])
    p = k['oyuncu']
    print(p['n'])
    mevki = mevki_adi(p)
    if p.get('pos_tahmin') == 'coklu':
        mevki += f' ({" ve ".join(POS[x].lower() for x in p["adaylar"])} oynadı; ana mevki istatistiklere göre)'
    elif p.get('pos_tahmin'):
        mevki += ' (istatistiklere göre tahmini)'
    yas = yas_metni(p.get('yas'), s.yil)
    print('  ' + ' · '.join(x for x in (p['t'], mevki, yas, f'Rol: {p["rol"]}' if p.get('rol') else '', p['cc']) if x))
    ozet = f'  {p["mp"]} maç · {p["min"]} dk · {p["g"]} gol · {p["a"]} asist · {fmt(p["xg"], 1)} xG · {fmt(p["xa"], 1)} xA'
    print(ozet + (f' · FotMob puanı {fmt(k["puan"])}' if k['puan'] is not None else ''))
    if k['yuzdelik']:
        print(f'\nMevkidaşlarına göre (90 dk başına; yüzdelik dilim, {k["es_sayisi"]} oyuncu arasında)')
        for etiket, v, pc in k['yuzdelik']:
            print(f'  {etiket:<16}{fmt(v):>7}  {"█" * round(pc / 5):<20} {pc}')
        if k['az_sure']:
            print('  Bu oyuncu az süre aldığı için oranlar yanıltıcı olabilir.')
    print('\nAyrıntılar')
    for ad, v in k['detay']:
        if v is None:
            v = '–'
        elif ad == 'Takım gollerindeki payı':
            v = yuzde(v)
        elif isinstance(v, float):
            v = ('+' if ad == 'Gol − xG' and v > 0 else '') + fmt(v, 1 if abs(v) >= 10 or ad == 'Gol − xG' else 2)
        print(f'  {ad:<28}{v}')
    if p['id'] is not None:
        print('\nSezon sezon (aynı veri kaynağındaki ligler)')
        for r in kariyer(a.veri, s.src, p['id'], p.get('fm_id')):
            print(f'  {sezon_etiketi(r["yil"], r["anahtar"]):<7}  {r["lig"]:<17}{r["takim"][:24]:<25}{r["mp"]:>3} maç {r["min"]:>5} dk'
                  f'{r["g"]:>4} gol {fmt(r["xg"], 1):>5} xG{r["a"]:>4} asist {fmt(r["xa"], 1):>5} xA')


def canli_yazdir(v):
    ad = {l[0]: l[1] for l in LIGLER}
    t = v['tarih']
    simdi = datetime.now().strftime('%H:%M:%S')
    canli_sayi = sum(1 for m in v['maclar'] if m['durum'] == 'canli')
    print(f'Canlı skorlar · {t[6:]}.{t[4:6]}.{t[:4]} · {simdi} itibarıyla · {canli_sayi} maç oynanıyor\n')
    if not v['maclar']:
        print('Bu tarihte takip edilen liglerde ve milli turnuvalarda maç yok.')
        return
    lig_simdi = None
    for m in v['maclar']:
        if m['lig'] != lig_simdi:
            lig_simdi = m['lig']
            print(('\n' if lig_simdi != v['maclar'][0]['lig'] else '') + (m.get('baslik') or ad.get(lig_simdi, lig_simdi)))
        if m['durum'] == 'canli':
            durum, skor = f'● {m["dakika"]}', f'{m["evGol"]} – {m["depGol"]}'
        elif m['durum'] == 'bitti':
            durum, skor = 'Bitti', f'{m["evGol"]} – {m["depGol"]}'
        elif m['durum'] == 'iptal':
            durum, skor = 'İptal', '–'
        else:
            durum, skor = m['saat'], '–'
        stad = f'  · {m["stadyum"]}' if m.get('stadyum') else ''
        print(f'  {durum:<8}{m["ev"][:24]:>24}  {skor:^7}  {m["dep"][:24]:<24}{stad}')
        if m.get('hakem'):
            print(f'{"":>10}Hakem: {hakem_metni(m["hakem"])}')


def cmd_canli(a):
    from .canli import canli_skorlar
    if a.json:
        v = canli_skorlar(a.tarih, stadyumlar=stadyum_oku(a.veri), ham=PROJE / 'ham', yakin_gun=4)
        Path(a.json).write_text(json.dumps(v, ensure_ascii=False), encoding='utf-8')
        hakemli = sum(1 for m in v['maclar'] + v['yakinda'] if m.get('hakem'))
        print(f'{len(v["maclar"])} maç ve önümüzdeki 4 günden {len(v["yakinda"])} maç yazıldı ({hakemli} maçın hakemi belli): {a.json}')
        return
    while True:
        try:
            v = canli_skorlar(a.tarih, stadyumlar=stadyum_oku(a.veri), ham=PROJE / 'ham')
            hata = None
        except Exception as e:  # ağ hatasında ekranı bozmadan bir sonraki turda tekrar dene
            v, hata = None, e
        if not a.bir_kez:
            os.system('cls' if os.name == 'nt' else 'clear')
        if v:
            canli_yazdir(v)
        else:
            print(f'Skorlar alınamadı ({hata}). {a.aralik} saniye sonra tekrar denenecek.')
        if a.bir_kez:
            return
        print(f'\n{a.aralik} saniyede bir yenilenir. Çıkmak için Ctrl+C.')
        try:
            time.sleep(a.aralik)
        except KeyboardInterrupt:
            return


def cmd_sunucu(a):
    """Uygulamayı (NiceGUI arayüzü) açar: 'sunucu' tarayıcıda, 'uygulama' kendi penceresinde. Canlı skorlar ve süren
    sezonun verisi arka planda kendini yeniler."""
    from .arayuz import calistir
    from .arayuz.erisim import ANAHTAR_ORTAM, adres_uyarisi, loopback_mi

    adres = 'localhost' if loopback_mi(a.host) else a.host
    print(('Uygulama kendi penceresinde açılıyor.' if a.pencere else f'Uygulama açık: http://{adres}:{a.port}/')
          + f'\nCanlı skorlar {a.aralik} saniyede bir'
          + (f', süren sezonun verisi {a.veri_saat:g} saatte bir' if a.veri_saat > 0 else '')
          + ' yenilenir. Kapatmak için ' + ('pencereyi kapat.' if a.pencere else 'Ctrl+C.'))
    uyari = adres_uyarisi(a.host, bool(os.environ.get(ANAHTAR_ORTAM)))
    if uyari:
        print('\n' + uyari)
    calistir(a.veri, PROJE / 'ham', pencere=a.pencere, port=a.port, tarayici_ac=not a.tarayici_acma,
             canli_aralik=a.aralik, veri_saat=a.veri_saat, depolama=PROJE / '.nicegui', host=a.host)


def main(argv=None):
    # Windows'ta çıktı dosyaya yönlendirilince Türkçe karakterler bozulmasın
    try:
        # line_buffering: sunucu mesajları IDE konsolunda ve dosyaya yönlendirmede hemen görünsün
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except AttributeError:
        pass
    ana = argparse.ArgumentParser(prog='python -m mac_tahmin', description='Maç Tahmin Laboratuvarı, komut satırı sürümü.')
    ana.add_argument('--veri', default=str(PROJE / 'd'), help='lig-sezon JSON dosyalarının klasörü (varsayılan: proje klasöründeki d)')
    alt = ana.add_subparsers(dest='komut', required=True)
    ligler = [l[0] for l in LIGLER]

    p = alt.add_parser('veri', help='verileri indir ve dönüştür')
    p.add_argument('--ligler', nargs='*', choices=ligler, help='yalnızca bu ligler')
    p.add_argument('--sezonlar', nargs='*', type=int, help='yalnızca bu sezonlar (başlangıç yılı, ör. 2025)')
    p.add_argument('--ham', default=str(PROJE / 'ham'), help='ham yanıtların önbellek klasörü')
    p.add_argument('--yenile', action='store_true', help='önbelleği yok say, yeniden indir')
    p.set_defaults(f=cmd_veri)

    def lig_sezon(p):
        p.add_argument('lig', choices=ligler)
        p.add_argument('sezon', type=int, help='sezonun başlangıç yılı, ör. 2025 = 2025/26')

    p = alt.add_parser('tablo', help='puan durumu'); lig_sezon(p); p.set_defaults(f=cmd_tablo)
    p = alt.add_parser('tahmin', help='maç tahmini'); lig_sezon(p)
    p.add_argument('ev'); p.add_argument('deplasman'); p.set_defaults(f=cmd_tahmin)
    p = alt.add_parser('degerlendir', help='model karşılaştırması'); lig_sezon(p); p.set_defaults(f=cmd_degerlendir)
    p = alt.add_parser('simulasyon', help='süren sezonun sonunu simüle et'); lig_sezon(p)
    p.add_argument('--n', type=int, default=10000, help='simülasyon sayısı (varsayılan: 10000)')
    p.set_defaults(f=cmd_simulasyon)
    p = alt.add_parser('oyuncu', help='oyuncu kartı'); lig_sezon(p); p.add_argument('ad'); p.set_defaults(f=cmd_oyuncu)
    p = alt.add_parser('oyuncular', help='oyuncu listesi (mevki ve yaş süzgeçli)'); lig_sezon(p)
    p.add_argument('--mevki', help='ayrıntılı (GK CB RB LB DM CM AM RW LW ST) ya da ana mevki (D M W F G)')
    p.add_argument('--yas', choices=list(YAS_GRUPLARI),
                   help='yaş grubu (süren sezonda bugünkü, geçmiş sezonlarda sezon ortasındaki yaşa göre)')
    p.add_argument('--sirala', default='g', choices=['g', 'a', 'xg', 'xa', 'min', 'mp', 'yas'],
                   help='sıralama ölçütü (varsayılan: gol)')
    p.add_argument('--adet', type=int, default=25)
    p.set_defaults(f=cmd_oyuncular)
    p = alt.add_parser('roller', help='oyuncu rolleri (k-means kümeleme)'); lig_sezon(p)
    p.add_argument('rol', nargs='?', help='bu roldeki oyuncuları da listele, ör. "bitirici"')
    p.set_defaults(f=cmd_roller)
    p = alt.add_parser('benzer', help='bir oyuncuya en çok benzeyen oyuncular'); lig_sezon(p); p.add_argument('ad')
    p.add_argument('--tum', action='store_true', help='aynı veri kaynağındaki bütün liglerde ara')
    p.set_defaults(f=cmd_benzer)
    p = alt.add_parser('stadyum', help='takımların iç saha stadyumlarını indir (d/stadyumlar.json)')
    p.add_argument('--ham', default=str(PROJE / 'ham'), help='ham yanıtların önbellek klasörü')
    p.add_argument('--yenile', action='store_true', help='önbelleği yok say, yeniden indir')
    p.set_defaults(f=lambda a: stadyumlar_indir(a.veri, a.ham, a.yenile))
    for komut, yardim, pencere in (('uygulama', 'uygulamayı kendi penceresinde aç', True),
                                   ('sunucu', 'uygulamayı tarayıcıda aç', False)):
        p = alt.add_parser(komut, help=yardim)
        p.add_argument('--port', type=int, default=8080, help='yerel port (varsayılan: 8080)')
        p.add_argument('--host', default='127.0.0.1',
                       help='dinlenen adres (varsayılan: 127.0.0.1, yalnızca bu bilgisayar). Uygulamanın parolası yoktur: '
                            '0.0.0.0 gibi bir adres ağdaki herkese açar')
        p.add_argument('--aralik', type=int, default=60, help='canlı skor yenileme aralığı, saniye (varsayılan: 60)')
        p.add_argument('--tarayici-acma', action='store_true', help='tarayıcıyı otomatik açma')
        p.add_argument('--veri-saat', type=float, default=6,
                       help='süren sezonun verisini kaç saatte bir yenilesin (varsayılan: 6; 0 = yenileme)')
        p.set_defaults(f=cmd_sunucu, pencere=pencere)
    p = alt.add_parser('canli', help='canlı skorlar')
    p.add_argument('--tarih', help='YYYYAAGG biçiminde gün (varsayılan: bugün)')
    p.add_argument('--aralik', type=int, default=30, help='yenileme aralığı, saniye (varsayılan: 30)')
    p.add_argument('--bir-kez', action='store_true', help='bir kez yazdır ve çık')
    p.add_argument('--json', metavar='DOSYA', help='skorları bu JSON dosyasına yaz ve çık')
    p.set_defaults(f=cmd_canli)

    a = ana.parse_args(argv)
    try:
        a.f(a)
    except (FileNotFoundError, ValueError, KeyError) as e:
        sys.exit(str(e.args[0]) if e.args else str(e))


if __name__ == '__main__':
    main()
