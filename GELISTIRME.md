# Geliştirme rehberi

Bu belge, uygulamaya yeni bir şey eklerken nereye dokunulacağını anlatır. Amaç: her yeni özellik **tek bir yere**
eklensin, mevcut kodu değiştirmek gerekmesin.

## Katmanlar

```
veri.py, canli.py, hakem.py, stadyum.py, dogum.py   → veriyi indirir, d/ ve ham/ klasörlerine yazar
sezon.py, modeller.py                                → bütün hesaplar (tahmin, Elo, roller, benzer oyuncular…)
guncelleme.py                                        → verilerin arka planda kendini güncellemesi
arayuz/                                              → yalnızca gösterim (NiceGUI)
__main__.py                                          → komut satırı (aynı hesapları metin olarak yazar)
```

**Kural:** hesap `sezon.py`/`modeller.py`'de yapılır, arayüz yalnızca sonucu gösterir. Böylece aynı hesap hem
uygulamada hem komut satırında kullanılır ve test etmesi kolaydır.

## Veri akışı

Maç ve oyuncu verisi iki siteden, herkese açık JSON uç noktalarından gelir (`veri.json_getir`: tarayıcı gibi istek, gzip;
yalnızca bilgi olarak gösterilen hava tahmini Open-Meteo'dan). İki
klasör vardır: **`ham/`** kaynakların yanıtları olduğu gibi (önbellek; varsa yeniden indirilmez), **`d/`** uygulamanın
okuduğu küçük, derlenmiş dosyalar.

| Ne | Kaynak (uç nokta) | Ham | Derleyen → d/ | Ne zaman yenilenir |
| --- | --- | --- | --- | --- |
| Beş büyük lig: maçlar, xG, oyuncular | understat.com `getLeagueData/LİG/YIL` | `ham/LİG-YIL.json` | `veri.understat_sezon` → `LİG-YIL.json` | süren sezon 6 saatte bir, maç bitince 5 dk sonra |
| …mevki, doğum tarihi, ek istatistik, transfer | fotmob.com `leagues?id=…&season=…` ve listeleri | `ham/fm-LİG-YIL*.json`, `ham/dogum.json` | aynı dosyaya eklenir | aynı |
| Diğer ligler | fotmob.com `leagues` + istatistik listeleri | `ham/fm-LİG-YIL*.json` | `veri.fotmob_sezon` → `LİG-YIL.json` | aynı |
| Canlı skor, hakem, stadyum | fotmob.com `matches?date=`, `matchDetails` | `ham/mac/` | bellekte (`Guncelleyici.canli`) | dakikada bir (sonraki 4 gün 30 dk'da bir) |
| Maç kartı | fotmob.com `matchDetails` | `ham/mac_tam/` (bitmiş maçlar) | `mac_ozeti.ayrinti` | kart açılınca; canlıda 30 sn'de bir |
| Milli takımlar | fotmob.com `leagues` (24 turnuva) | `ham/milli/` | `milli.derle` → `milli.json` | 6 saatte bir, maç bitince 5 dk sonra |
| Avrupa ve yerel kupalar | fotmob.com `leagues` (kupalar, elemeler) | `ham/avrupa/` | `avrupa.derle` → `avrupa.json`, `avrupa_yurtici.json` | aynı |
| Takım sayfası, güncel kadro | fotmob.com `teams?id=` | `ham/takim/` (1 saat) | `takim.takim_sayfasi` | açılınca |
| Oyuncunun son maçları | fotmob.com `playerData?id=` | `ham/oyuncu/` (6 saat) | `takim.oyuncu_son_maclar` | kart açılınca |
| Tahmin karnesi | `d/LİG-YIL.json` (indirme yok) | – | `karne.guncelle` → `karne.json` | lig verisi yenilenince (yalnızca yeni haftalar) |
| Maç saatinin hava tahmini | api.open-meteo.com `forecast` (anahtarsız, CC BY 4.0) | `ham/hava/` (konum başına) | `hava.mac_havasi` | gösterilince; konum başına 3 saatte bir |

Hava yalnızca bilgi olarak gösterilir (Maç tahmini sekmesinde hakemin altında, maç kartında skorun altında; maça en çok
`TAHMIN_GUN` = 7 gün kala, maç süresince 2 saatin sıcaklık / yağış / rüzgârı), tahmine katılmaz (ölçüm aşağıda).
Stadyum konumu FotMob'dan: maç detayının `Stadium` alanı (`hakem.mac_detay` → `konum`) ya da ev sahibinin iç sahası
(`d/stadyumlar.json` → `konum`); maç saati canlı skor verisinden, yoksa ligin fikstüründen (`Depo.lig_mac_havasi`).

Fiziksel veri (koşu mesafesi, sprint, en yüksek hız): FotMob yalnızca Premier League'de verir; maç maç `mac_ozeti`
(`FIZIKSEL`, oyuncu kaydında 'fiziksel'), sezonluk `lig_maclari.fiziksel_ozet`; gösterim maç performansı penceresi, oyuncu
kartı (`oyuncu_karti.FIZIKSEL_LIGLER`) ve Öne çıkanlar'daki "Fiziksel liderler". FotMob başka liglerde de vermeye başlarsa
`FIZIKSEL_LIGLER`'e eklemek yeter.
Oyuncu hesapları: `lig_maclari.py` (ligin bitmiş maçlarının oyuncu puanları → haftanın 11'i, form endeksi),
`oyuncu_tahmin.py` (gol/asist krallığı simülasyonu, kim asist yapar, kim kart görür, performans endeksi,
fiyat-performans, `scout_adaylari` ve mevki grupları `SCOUT_GRUPLARI`; krallık yarışı, kim gol atar / asist yapar ve kadro
eksikleri aynı oyuncu oranını kullanır: `oran()` bu sezonu, önceki iki sezonu (`onceki_sezonlar`, `ONCEKI_AGIRLIK` /
`ONCEKI_TAVAN`) ve mevkinin ortalamasını (`ON_MAC`) harmanlar; kart oranı `KART_ON_MAC`, hakem çarpanı `HAKEM_ON_MAC`,
performans endeksi `ENDEKS_ON_MAC` ile küçük örneklemde ortalamaya çekilir. Bu değerler geri testle seçildi); piyasa değerleri `Depo.lig_degerleri`
(FotMob takım kadroları; bellekte ve `ham/degerler/LİG.json`'da 24 saat). Gösterim: `arayuz/yildizlar.py`
(Öne çıkanlar), `arayuz/tahmin.py`, `arayuz/scout.py` (Scout: mevki mevki genç oyuncu önerileri; transfer zorluğu
`oyuncu_tahmin.transfer_zorlugu`: kulüp büyüklüğü, takımdaki rol, kulüp için önem ve yaş, ayarlar `ZORLUK_AGIRLIK`,
`ZORLUK_ETIKET`, `YAS_DUZELTME`, `GERCEKCI_CEZA`; sözleşme bitişi `Depo.sozlesmeler` (FotMob oyuncu sayfası, 30 gün
önbellek `ham/sozlesme.json`), FotMob'da yoksa `transfermarkt.py` (kullanıcının izniyle YALNIZCA sözleşme bitiş tarihi;
istekler arası 3 sn, 90 gün önbellek `ham/transfermarkt.json`, engel görülürse 6 saat hiç istek yok; kapatmak için
`transfermarkt.ACIK = False`), düzeltmesi `SOZLESME_DUZELTME`, `sozlesme_uygula`).
Kesin ilk 11: maçın başlamasına `ILK11_DK` dakika kala `tahmin.kesin_ilk11` maç sayfasına bakar (kadro türü `standard` =
açıklanmış); varsa gol/asist/kart listeleri yalnızca ilk 11'den, kadro düzeltmesi maç kadrosuna göre. Favori takımlar
için "İlk 11 açıklandı" bildirimi `bildirim._ilk11_kontrol`; maça `OZET_DK` (60) dakika kala bir kez "Maç öncesi" özeti
`bildirim.ozet_metni` (modelin olasılıkları, beklenen gol, en olası skor, ilk 11'ler ve ilk 11'den en olası golcüler;
hepsi hesaplanmış veri, `bildirim.DEPO` ile). Karne gol piyasalarını da tutar (`karne.gol_ozeti`).
Puan durumu sekmesi: "Hak edilen puan (xPts)" `Sezon.hak_edilen_puan` (her maç iki takımın gol dağılımlarıyla oynatılır,
`sezon.gol_dagilimi`: şutları biliniyorsa şut şut — her şut kendi xG'siyle gol olur ya da olmaz, şutların xG'si maçın
toplam xG'sine ölçeklenir —, bilinmiyorsa toplam xG'den Poisson; şutlar indirilmiş maç sayfalarından
`lig_maclari.takim_xg_maclari` → `Depo.xg_maclari`, büyük 5 ligde sezon verisinin maçıyla takım id'si ve ±2 gün
tarihle eşleşir; "şanslı / şanssız" eşiği her yerde `sezon.SANS_ESIK`) ve
"Ya şöyle olursa" (`Sezon.simulasyon(sabit={(ev, dep): (eg, dg)})`: seçilen maçların skoru sabitlenip sezon yeniden
simüle edilir; rastgele sayı üreteci aynı tohumla, fark yalnızca sabitlenen skorlardan gelir). Takım kartındaki xG
gelişimi `Depo.xg_maclari`. Scout'taki "Takımın ihtiyacına göre öner": `oyuncu_tahmin.takim_ihtiyaci` (mevki gruplarının
güç puanı ortalaması ligin ortalamasıyla kıyaslanır, `IHTIYAC_KISI` kişiye bakılır; asıl ihtiyaç olan ayrıntılı mevki
`detay`: en zayıf oyuncununki, bek / kanatta bir yan boşsa o yan — öneriler önce o mevkiden, `scout.ihtiyac_adaylari`);
Scout'un endeksi önceki sezonla harmanlı (`oyuncu_tahmin.endeks_harmanla` / `scout_endeksi`, önceki sezonu bulan
`Depo.endeks_harmanla`; `ONCEKI_ENDEKS_AGIRLIK`, `ONCEKI_ENDEKS_TAVAN`). Bütün liglerin aday havuzu diske yazılır
(`Depo.scout_havuzu_oku` / `scout_havuzu_hesapla`, `ham/scout/`; lig dosyaları değişince ya da `SCOUT_HAVUZ_SAAT`
dolunca bayat: hemen gösterilir, yenisi arkada hesaplanır; açılıştan `scout_on_hazirla` sonra varsayılan süzgeçlerinki
arka planda hazırlanır; hesap değişince `SCOUT_SURUM` artırılır). Öneriler her zaman bütün liglerden
(kapsam "Açık lig"ken ayrı havuz, `scout.havuz_hazirla`), uyruk süzgeci (yerli: takımın ülkesi) `Depo.uyruklar` /
`Depo.takim_ulkesi` ile önbellekteki takım sayfalarından (`takim.onbellekteki_uyruklar`). Süren sezonda takımının
güncel FotMob kadrosunda olmayan oyuncu `Depo._guncel_kulup_ekle` ile `p['ayrildi'] = [yeni kulüp ya da '', None]` alır
(yeni kulüp `Depo.kadro_dizini`: bütün liglerin önbellekteki kadroları); Scout, golcü listeleri ve ilk 11 onu eski
takımında saymaz, Oyuncular tablosu güncel kulübünü gösterir. Oyuncu kartındaki piyasa değeri
geçmişi ve şut haritası FotMob oyuncu sayfasından (`takim.deger_ve_sutlar`; önbellekteki sayfa `degerler` alanı yoksa
yeniden indirilir). "Büyük maç oyuncusu" ve "Hava hâkimi" rolleri `Depo._hava_hakimi_ekle` (önbellekteki maç
satırlarından; büyük takımlar Elo'ya göre ilk `BUYUK_TAKIM_SAYISI`).
Model güveni (Maç tahmini, `tahmin.guven_metni`): etiket `GUVEN_YUKSEK` / `GUVEN_ORTA`, geçmiş isabet
`karne.favori_isabeti` (en olası sonuca ± `GUVEN_PAY` olasılık verilen Karne kayıtları; `karne.oku_onbellek`).
Şans analizi ve fikstür zorluğu Puan durumu sekmesinde: `tablo.sans_analizi` (gerçek puan − xPts ≥ `SANS_ESIK`, neden:
gol − xG, xGA − yenen) ve `sezon.fikstur_zorlugu` (rakiplerin etkin Elo'su; sıradaki `FIKSTUR_SONRAKI` maça göre
sıralı; hafif olasılık `Sezon.olasilik`). Takım kıyaslama `arayuz/takim_kiyas.py` (Kıyasla sekmesinin altı; yeni ölçüt
`olcutler()`'e). Oyuncu kartında benzer oyuncu süzgeci (`BENZER_SUZGEC`: daha genç / daha ucuz, değerler
`Depo.degerler_onbellek`) ve gelişim grafiği (`gelisim_yukle`: sezon sezon `performans_endeksi`; eğilim
`GELISIM_TREND_DK` dakikadan uzun sezonlardan). Benzer oyuncu havuzu `sezon.benzer_esik` dakikadan (sezon başında
yüzdelik eşiğinin iki katı, en çok `BENZER_MIN_DK`; sabit 600 dk ilk haftalarda havuzu ~12 oyuncuya indiriyordu);
değerlerinin en çok çeyreği eksik olabilir (FotMob listelerinde olmayan istatistik), mesafe ortak değerlerden ölçeklenir.
Takım kartında kadro yaş haritası (`yas_ciz`). Scout'ta "Sözleşmesi bitecek iyi oyuncular" (`bitenler_ciz`,
`BITEN_ADET`); güçlü yanlar yalnızca `scout.GUCLU_ESIK` (70) ve üstü yüzdelikler (Kıyasla'daki gibi). Golcü / asist
listelerinde önceki sezonlarıyla giren, bu sezon eşikten az oynamış oyuncunun süresi yazılır ("bu sezon 9 dk").
Karne sekmesi (`arayuz/karne_sekme.py`) sade dille: dört cümlelik özet, güvene göre başarı (`GUVEN`, `guven_dilimleri`),
hafta hafta (`haftalik`, "hep ev sahibi" ile), kalibrasyon (`kalibrasyon_sapmasi`), lig lig, son tahminler; log-kayıp
ve Brier açılır "Teknik ölçüler"de. Canlı maç olasılığı: `modeller.canli_olasilik` (maç öncesi beklenen gollerin kalan
süreye düşen kısmı Poisson'la, şu anki skora eklenir; `MAC_SURESI`, dakika `modeller.dakika_oku`; kırmızı kart yok),
liste için `Depo.mac_olasiliklari` (Canlı sekmesi arka planda hesaplar, gelince yeniden çizer). İstikrar:
`lig_maclari.istikrar` (maç puanlarının standart sapması, ligde yüzdelik; kaleciler kendi aralarında; `ISTIKRAR_*`),
oyuncu kartında ve Scout'ta; ortalaması düşük ya da maçlarının en az yarısı kötü geçen istikrarlı oyuncuya "ama düşük
düzeyde" eklenir (`istikrar_yazisi`). Oyuncu takip listesi `arayuz/takip.py` (liste `app.storage.general['takip']`, arka plan
durumu `ham/takip_durum.json`; gol / asist maç bitince `TAKIP_BEKLE_SN` sonra maç sayfasından, değer ve sözleşme
`KONTROL_SAAT`'te bir). Kadro eksiklerini ana tahmine katma denendi (gerçek ilk 11'le, katkı yalnızca maç öncesi dakikalarla): 1.444 maçta
k = 0,25 / 0,5 log-kaybı ~0,001 düşürdü (anlamsız, t ≈ −0,4), k = 0,75 kötüleştirdi; ana tahmine katılmadı, ayrı satır
olarak duruyor (ilk 476 maçlık örnekteki büyük fark rastlantıydı). Maç tahmini sekmesindeki şerit hafta hafta
(`lig_maclari.fikstur`: FotMob turları; `tahmin.haftalik_serit`, `tura_git`). Canlı sekmesinde olasılık satırına ya da
maç kartındaki "Maç tahmini"ne tıklayınca `ortak.tahmine_git` (lig maçı → Maç tahmini; kupa / milli → ilgili sekme).
Hız ve bellek: lig değişince yalnızca Maç tahmini ve Canlı hemen yenilenir, diğer sekmeler `TEMBEL` (açılınca); Maç
tahmini dakikalık canlı veride yalnızca açık ligin maçlarının saati / durumu / hakemi / stadyumu değiştiyse yeniden çizilir
(`tahmin.canli_yenile`); `lig_maclari.fikstur` ve `takim_xg_maclari` dosyalar değişmedikçe bellekten; geçmiş sezonların
oyuncu endeksleri bir kez hesaplanıp `ham/endeks/`'e yazılır, hesap için kurulan geçmiş sezon önbellekte tutulmaz
(`Depo._gecmis_endeksler`, `Depo._kur`); krallık simülasyonu sezonda bir kez (`S._krallik`). Bellekte sürekli kalan
büyük yapılar sözlük yerine hafif tutulur (sözlük gibi okunur): kariyer dizini `sezon._KariyerSatiri` (`__slots__`; kilitle
tek kez kurulur, açılıştaki arka plan hazırlığı ve ilk istek ikişer kez kurmasın), maç maç oyuncu satırları
`lig_maclari._OyuncuSatiri` (sezon sonunda 18 lig için ~150 bin satır), kulüp Elo'sunun maç geçmişi demet olarak
(`avrupa._Gecmis`, `get()` sözlük listesi döndürür). Ölçüm (Ekim 2026): kariyer dizini 69 → 34 MB, oyuncu satırları
56 → 29 MB, kulüp Elo'su 103 → 62 MB.
Kulüp Elo'su (`avrupa.KulupElo`) uygulamadaki liglerin yanında `avrupa.EK_LIGLER`'in (Avrupa kupalarına takım gönderen
24 ülkenin üst ligi) maçlarıyla da beslenir: `K_EK` = 10, başlangıç `EK_BASLANGIC` = 1375; ham veri `ham/ek_lig/`, süren
sezon `EK_YENILE_SAAT`'te bir, eski sezonlar derlenmiş `d/avrupa_yurtici.json`'da (pakete hazır gelir). Karne düzeninde
iki yönlü sınandı: 8.174 kupa maçında log-kayıp iki yönde de ~0,004 düştü (ek ligli takımların maçlarında ~0,007), iki yön
aynı ayarı seçti. Ligi hiç bilinmeyen takımda Kupalar'da "⚠ belirsiz" uyarısı (`KulupElo.belirsizlik`, `BELIRSIZ_MAC`).
Maç tahmini sekmesi: haftanın maçları en üstte; panoda sade dilde özet (`tahmin.ozet_cumlesi`), özet çipleri, tek satır
maç bilgisi, açıklamalar katlanır; skor tablosunda eksen başlıkları.
Gol piyasaları `modeller.piyasalar` (skor tablosundan; çifte şans `cs_*`, handikap ±1,5 `ev_m15`…; kutular
`ortak.cifte_sans_html`). İlk yarı tahmini `modeller.ilk_yari` (maçın beklenen golünün `IY_PAY` = 0,47'si; süren sezonun
1.672 maçında ikiye bölünüp iki yönlü sınandı: sabit oranlardan anlamlı iyi, iyi kalibre; kutular `ortak.ilk_yari_html`).
Takım kartında ilk yarı / ikinci yarı istatistikleri (`lig_maclari.yari_maclari`: devre skorları maç sayfalarından;
takıma özgü yarı eğilimi tahmine katılmadı: sezonun iki bölümü arasında korelasyon 0,15–0,22) ve Avrupa kupalarındaki
güncel sıra (`takim_karti.avrupa_siralari`). Canlı skordan kupa / milli maçta "Maç tahmini": ilgili sekme arkada açılır,
maçın ayrıntılı tahmini önde (`G.avrupa_mac_ac`, `G.milli_mac_ac`, `ortak.tahmine_git`).
Form endeksi (`lig_maclari.form_tablosu`): oyuncunun değil takımının son 5 maçı; bunların en az 3'ünde oynamayan (sakat,
cezalı) listeye girmez. Özel roller `sezon.OZEL_ROLLER` (koşul `(p, y, k)`; k sezonun ilerleyişi: gol / asist sayısına
dayanan eşikler sezon başında ölçeklenir); eşikler lig başına tam sezonda ~8–20 oyuncu çıkacak şekilde ayarlı. "Box to
box": orta sahalarda savunma ve xG + xA yüzdeliklerinin küçüğü ≥ 55 (ikisi ters orantılı, korelasyon ≈ −0,35).
Elo gelişimi grafiği (`guc.elo_ciz`) güncel Elo'ya göre sıralı, renkler seçilme sırasında kalır. Oyuncu kartı başka
lig-sezonun oyuncusunu açık lig değişmeden gösterir (`G.git` oyuncuyla: `sayfa.oyuncu_goster`; kartta "… sayfasına geç"
`G.lige_gec`). Kıyasla'da seçilen oyuncunun diğer sezonları (saat simgesi, `kiyas.sezonlar_ac`, `sezon.kariyer`). Maç
tahmini sekmesinin altında "Farklı liglerden iki takım" (kulüp Elo'su `avrupa.KulupElo`, ayrıntısı `mac_tahmini`
penceresi). Görünüm (başlıktaki palet düğmesi): tema bilgisayara göre / açık / koyu (`ui.dark_mode`), renk paleti
`ortak.PALETLER` (CSS'te `body.palet-…`, açık ve koyu ayrı; ayar `app.storage.general['gorunum']`). Bildirim sesi
(Takımlarım): genel ses ve takıma özel ses `bildirim.ses_secimi` (hazırlar `SESLER`, eklenen MP3 / WAV dosyaları
`SES_KLASORU` = veri klasörünün yanında `sesler/`; ayar `app.storage.general['ses']`).
Tahmin oyunu sekmesi `arayuz/oyun.py` (altında lig lig istatistik ve haftalık puan grafiği, `istatistik_ciz`): kullanıcının skor tahminleri ve kaydedildiği andaki modelin skoru
`app.storage.general['tahmin_oyunu']`'nda; puanlama `KESIN` / `SONUC`, sonuçlar lig verisinden okunur.
Denenip eklenmeyenler (karneyle ölçüldü, iyileştirmedi): yorgunluk (az dinlenme) düzeltmesi, gol seviyesinin hızlı uyumu,
olasılıkları sonradan keskinleştirme / yumuşatma ve beraberlik çarpanı, Elo'da K (15–30) ve ev avantajı (40–80) değişikliği,
xG'li Elo (sonuç puanına maçın xG'sinden pay), öğrenilen harman (stacking: Poisson ve Elo olasılıklarından çok sınıflı
lojistik regresyon; Pi-rating gol farkı, beklenen gol toplamı, ligin beraberlik oranı, sezonun ilerlemesi, veri kaynağı
etkileşimleriyle de; 2025→2026 küçük iyileşme ama 2026→2025 açıkça kötü: ezber), veri kaynağına göre ayrı Elo payı
(iki yön zıt ayar seçti, ikisi de sınavda kötü), derbi etkisi (aynı şehir: ev avantajını azaltma; 285 derbide tutarlı
etki yok) ve maçın önemi (haftalık simülasyonla şampiyonluk / ilk 4 / küme düşme olasılığı farkı → beklenen gol;
sınavda kötüleştirdi; süren sezonda geç sezon maçı az olduğundan sezon sonunda yeniden denenebilir), hava durumu
(Open-Meteo arşivi, ev sahibinin şehri, maç günü yerel 12–23 arası yağış / rüzgâr / sıcaklık; 6.744 maç: yağış golü
tutarlı biçimde artırıyor, 5 mm başına ~%4, sert rüzgâr azaltıyor; ama 2,5 üst log-kaybında kazanç binde 0,3–1,3, yalnız
bir yönde anlamlı, 1X2'ye etkisi yok; gerçek hava yerine tahmin kullanılınca daha da azalır), takıma özel ev avantajı
(haftadan önceki maçlarla takımın evdeki ve deplasmandaki gol / xG farkı, ligin ev avantajına göre fazlası, az maçta
sıfıra çekilerek; takımlar arası yayılım şansın üreteceği kadar, gol farkıyla bir yönde açıkça kötü, xG'yle etkisiz) ve
deplasman yolculuğu (stadyum konumlarından uzaklık, ligin ortalamasına göre; iki yönde de binde 0,4'ten küçük, anlamsız;
yakın / uzak maçlar arasındaki ham fark lig içinde bakınca kayboluyor: ligler arası fark), yaz dönemi kadro
değişimiyle sezon başı Elo düzeltmesi (gelen − giden oyuncuların önceki sezon xG + xA'sı ya da kadroda kalan dakika payı;
2025→2026 ilk 8 haftada binde 0,3–0,4 iyileşme, 2026→2025 seçilen ayar uç değerde ve kötüleştirdi: tutarlı değil;
geçmiş sezon başlarının piyasa değerleri veride yok), korner ve sarı kart tahmini (takımın maç başına yaptığı /
yaptırdığı korner, gördüğü / gördürdüğü kart, az maçta lig ortalamasına çekilerek; hakem çarpanı: hakemin bu sezonki
maçlarındaki kart ortalaması; süren sezon ikiye bölünüp iki yönlü; ligin ortalamasından tutarlı ve anlamlı iyi değil,
hakem çarpanı bir yönde kötü; Brezilya, Arjantin ve Suudi ligi maç sayfalarında kart sayısı yok; sezon ilerleyince ya da
geçen sezonun maç sayfaları indirilince yeniden denenebilir). Sabit 0,65 / 0,35
harman iki yönde de en sağlamı. Magazinsel / psikolojik bilgi bilinçli olarak kullanılmıyor (güvenilir ve sınanabilir
veri yok, gerçek kişiler hakkında çıkarım). Eklenen: Elo'nun sezon arası koruması `ELO_KORU` 2/3 → 0,9 (iki sezonda da
log-kaybı düşürdü; 18 ligin 11'inde iyileşti). Denemelerin betikleri: karne düzeninde her hafta yalnızca önceki maçlar;
Poisson olasılıkları bir kez hesaplanıp Elo varyantları üstüne harmanlanır.
Kıyasla sekmesinin altındaki yazılı değerlendirme `kiyas.cikarim`'da kurallarla üretilir (yeni kural: oraya bir cümle ekle).
Kupa ve milli maçların ayrıntılı tahmini: `arayuz/mac_tahmini.py` (pencere; `G.ayrintili_tahmin(bilgi)`), hesaplar
`modeller.piyasalar` (alt/üst, karşılıklı gol) ve `modeller.tur_atlama` (tek ya da iki maçlı eleme, uzatma ve penaltı);
form ve aralarındaki maçlar Elo modellerinin `gecmis` kaydından (`avrupa.KulupElo`, `milli.MilliElo`).

Arka plan işleri `guncelleme.Guncelleyici`'de: canlı skor döngüsü (dakikada bir; biten maçların lig/turnuvasını
5 dk sonra yeniler, `dinleyiciler` ile favori takım bildirimlerini tetikler) ve sezon döngüsü (10 dk'da bir bakar,
süren sezonlar 6 saatte bir ya da "Şimdi güncelle"de; son başarılı tam yenileme `d/son_yenileme.txt` işaretiyle
izlenir, çünkü `veri.indir` içeriği değişmeyen lig dosyasını yeniden yazmaz). Sezon döngüsü her turda biten maçların
henüz inmemiş sayfalarından en yenisinden başlayarak bir parti indirir (`lig_maclari.eksikleri_indir`,
`ON_INDIRME_BUTCE`; maç bitince o ligin sayfaları hemen): Öne çıkanlar, roller ve xG gelişimi açılınca beklemez.
Arayüz `veri_surum` ve `canli` değişimini 15 sn'de bir izler (`sayfa.py` → `takip`); açık lig yalnızca kendi dosyası
değiştiyse yeniden kurulur. `Depo.sezon` önbelleği lig liginedir (dosya zamanı + `SEZON_TAZE_SAAT`; `Depo.guncel_mi`).
Hız için "önce elde olanı göster": piyasa değerleri eskiyse eskisi hemen döner, yenisi tek bir kuyrukta arka planda
gelir (`Depo.lig_degerleri`, `DEGER_SAAT`); Öne çıkanlar önce önbellekteki maçlarla çizilir, eksikler inince yenilenir.
Maç sayfaları geçici dosyaya yazılıp yerine konur (`mac_ozeti._yaz`): arka plan ve arayüz aynı anda okuyabilir. Masaüstü uygulaması paketteki `d/`'yi kullanıcı klasörüne (`%LOCALAPPDATA%\MacTahmin`)
kopyalar (yalnızca daha yeniyse) ve oradan kendi `ham/`'ıyla günceller.

## Sezon nesnesi (sezon.Sezon)

Arayüzde `G.S` olarak açık sezondur. Sık kullanılan alanlar:

| Alan | İçerik |
| --- | --- |
| `S.lig`, `S.yil`, `S.src` | lig anahtarı, sezonun başlangıç yılı, veri kaynağı (`understat` / `fotmob`) |
| `S.T` | takım adları (indeksle: `S.T[i]`) |
| `S.M`, `S.U` | oynanan / oynanmamış maçlar: `Mac(d, h, a, hg, ag, hx, ax)` (tarih, ev/dep indeksi, goller, xG) |
| `S.tablo`, `S.tb` | puan durumu (sıralı) ve takım indeksine göre satırlar |
| `S.reyting`, `S.elo`, `S.hist`, `S.elo_bas` | Elo ve hücum/savunma gücü, maç maç Elo geçmişi |
| `S.PLY` | oyuncular: `n` ad, `t` takım, `pos` ana mevki, `detay` ayrıntılı mevki, `yas`, `mp`, `min`, `g`, `xg`, `a`, `xa`, `sh`, `kp`, `yc`, `rc`, `ex` (kaynağa özgü ek istatistikler), `rol`, `id`, `idx` |
| `S.roller` | rol kümeleri (yoksa `None`) |
| `S.tahmin(h, a)`, `S.simulasyon()`, `S.degerlendir()`, `S.oyuncu_karti(p)` | hesaplar |
| `S.raw`, `S.sim` | ham veri ve simülasyon önbelleği (arayüzün deposu ekler) |

## Yeni sekme eklemek

1. `mac_tahmin/arayuz/` altına bir dosya aç, örneğin `transfer.py`:

```python
from nicegui import ui

ID, AD = 'transfer', 'Transferler'      # sekmenin kimliği ve başlığı
# TEMBEL = True                         # hesap ağırsa: yalnızca sekme açıkken yenilenir


def kur(G):
    """Sekmenin öğelerini bir kez kurar; sezon her değiştiğinde çağrılacak işlevi döner."""
    with ui.column().classes('panel'):
        ui.html('<h3>Transferler</h3>', sanitize=False)
        icerik = ui.label().classes('lead')

    def yenile():                       # async def de olabilir
        S = G.S
        icerik.text = f'{len(S.PLY)} oyuncu'

    return yenile
```

2. `arayuz/sayfa.py`'deki `SEKMELER` listesine ekle: `from . import transfer` ve `SEKMELER = [..., transfer]`.

Başka hiçbir yere dokunmak gerekmez: sezon değişince `yenile` çağrılır, son açılan sekme hatırlanır.

**Sekmenin kullanabileceği bağlantılar (`G`):**

- `G.S`: açık sezon · `G.depo`: veri deposu (`G.depo.veri_klasoru`, `G.depo.stadyumlar()`, `G.depo.g.canli`)
- `G.oyuncu_ac(idx)`: oyuncu kartını açar · `G.git(lig, yil, oyuncu_id)`: o sezonun oyuncusunun kartı (açık lig
  değişmeden); oyuncusuz `G.git(lig, yil)` ya da `G.lige_gec(lig, yil, oyuncu_id=None)`: uygulamayı o sezona geçirir
- `G.mac_ac(mac)`: canlı skor verisindeki bir maçın kartı · `G.sekme_ac(sekme_id)`: sekmeye geçer
- `G.kiyasa_ekle(lig, yil, oyuncu)`: oyuncuyu Kıyasla sekmesine ekler (kıyasa yeni istatistik: `kiyas.py` → `METRIKLER`)
- `G.tahmin_ac(lig, ev adı, dep adı)`: Maç tahmini sekmesinde bu maçı açar (gerekirse lige geçer)
- `G.yay('favoriler')`: favori takımlar değişti (Takımlarım dinler); favoriler ve bildirimler `arayuz/bildirim.py`
- `G.takim_ac(anahtar)`: takım sayfası (FotMob takım id'si ya da açık ligdeki takım adı). HTML içindeki takım adını
  tıklanır yapmak için `ortak.takim_link(ad, anahtar)` yaz ve kapsayan `ui.html`'e `ortak.takim_tiklama(oge, G)` uygula.
  Veri `takim.py` (FotMob takım sayfası, 1 saat önbellek; "en çok oynayan 11" `takim.en_cok_oynayan`).
- `G.dinle('canli', fn)`: yeni canlı skor verisi gelince `fn` çağrılır · `G.dinle('sezon', fn)`: sezon değişince
- `G.yay('olay_adi')`: kendi olayını duyurur (başka sekmeler `G.dinle` ile dinler)
- `G.arka_plan(coro)`: arka plan işi · uzun hesaplar için `await run.io_bound(islev, ...)` (arayüz donmaz)
- Sekme başlığına rozet gibi bir şey eklemek için modülde `sekme_ek()` tanımla; döndürdüğü öğe `G.ek[ID]`'de olur
  (örnek: `canli_sekme.py`).

**Görünüm:** ortak biçimler `arayuz/ortak.py`'de (`fmt` virgüllü sayı, `yuzde`, `sayi` binlik nokta, `tarih_uzun`,
`kisa_gun`, `kucuk` Türkçe küçük harf, `e` HTML'e güvenli yazı). Hazır CSS sınıfları: `panel`, `lead`, `cap`,
`tb` (tablo), `liste`/`satir`/`track` (çubuklu liste), `kaydir` (yatay kaydırma). Grafikler için `ui.echart`.

## Var olan bir sekmeye bölüm eklemek

Sekmenin `kur` işlevinde öğeyi oluştur, `yenile` içinde doldur. Örnek: `guc.py`'deki "Elo sıralaması" tablosu.

## Oyuncu tablosuna sütun eklemek

`arayuz/oyuncular.py`'deki `SUTUNLAR` listesine `(alan, başlık)` ekle. Alan oyuncu sözlüğündeki anahtardır
(`S.PLY` satırları). 90 dakikaya çevrilebilecekse `ORAN` kümesine, yazıysa `YAZI` kümesine de ekle; özel bir
biçim gerekiyorsa `goster()` işlevine bir satır yaz. Sıralama ve sayfalama kendiliğinden çalışır.

## Yeni lig eklemek

1. `sezon.py`: `LIGLER`'e `(anahtar, ad, ülke, ilk sezon, kaynak)`, `FOTMOB_ID`'ye FotMob lig kimliği;
   takvim yılına göre oynanıyorsa `TAKVIM_YILI`'na anahtar.
2. `python -m mac_tahmin veri --ligler ANAHTAR` ve `python -m mac_tahmin stadyum`
3. İstersen `arayuz/ortak.py`'deki `LIG_GRUPLARI`'nda bir bölgeye ekle (eklemezsen listenin sonunda görünür).

## Yeni milli turnuva eklemek

`milli.py`'deki `TURNUVALAR` listesine `(FotMob kimliği, Türkçe ad, tür, tarafsız saha mı)` ekle. Tür maçın Elo'daki
ağırlığını belirler (`K` sözlüğü: dunya, kita, eleme, bolge, hazirlik). Sonra `python -m mac_tahmin veri`. Turnuva
hem Milli takımlar sekmesinde hem canlı skorlarda kendiliğinden görünür. FotMob kimliğini bulmak için:
`https://www.fotmob.com/api/data/leagues?id=KİMLİK` adresindeki `details.name`.

## Avrupa kupaları

`avrupa.py`: `KUPALAR` (Şampiyonlar Ligi, Avrupa Ligi, Konferans Ligi) ve Elo için `ELEMELER`. Veri `ham/avrupa/`
altına iner, `d/avrupa.json` (fikstür, puan durumu, eleme ağacı) ve `d/avrupa_yurtici.json` (Elo için lig maçları)
derlenir. `KulupElo` lig ve kupa maçlarından kulüp Elo'su; `simulasyon(v, E, kupa, sezon, N)` sezonu sonuna kadar
oynatır (lig aşaması + UEFA'nın sabit eleme ağacı; gerçekleşen kura/maçlar olduğu gibi). Kupa eklemek için `KUPALAR`'a
ekle: sekmede ve canlı skorlarda kendiliğinden görünür. Biçim (36 takım, ilk 8 / 9-24) değişirse `AGAC` ve
`simulasyon`'u uyarla. Arayüz: `arayuz/avrupa_sekme.py`. FotMob kura çekilmeden eleme ağacında o anki sıralamaya göre
olası eşleşmeleri gösterir (`hasTwoPossibleMatchups`, önceki turun galibi eksi id): `_eleme` bunları "belli değil" sayar
(yoksa simülasyon kurayı çekilmiş sanıp çöküyordu, Ekim 2026); hiçbir eşleşmesi belli olmayan ağaç sekmede gösterilmez.

## Maç tahmini modeli

`Sezon.tahmin(h, a)`: Poisson hücum/savunma modeli (`modeller.poisson_kur`; son 3 sezon, maç ağırlığı `YARI_OMUR` günde
yarıya iner, güçlerde golle birlikte `XG_PAYI` kadar xG), süren sezonda kadro değeri eğimi (`Sezon.lambdalar`,
`DEGER_US`, en fazla `DEGER_TAVAN`; değerler `Depo.kadro_degerleri`, 7 gün önbellek), Dixon-Coles düzeltmesi (`DC_RHO`)
ve maç maç Elo ile harman (`ELO_PAYI`, `Sezon.elo_olasilik`). Skor tablosu (`hucreler`) harmana göre ölçeklenir, yüzdelerle
tutarlıdır. Ayarlar `sezon.py`'nin başında; karneyle aynı düzende (her hafta yalnızca önceki maçlar) 2025'te seçilip 2026'da
doğrulandı. Değiştirince `d/karne.json`'ı silip `karne.guncelle('d')` ile karneyi yeniden üret ve log-kaybı karşılaştır.

## Yeni tahmin modeli eklemek

`sezon.py`'de bir işlev yaz ve `MODEL_LISTESI`'ne ekle:

```python
def _benim_modelim(c):
    # c['Xtr'], c['Ytr'] ile eğit; her test maçı için [ev, beraberlik, deplasman] olasılığı döndür
    return [[0.45, 0.27, 0.28] for _ in c['Xte']]

MODEL_LISTESI = [..., ('Benim modelim', _benim_modelim)]
```

Modeller sekmesi ve `degerlendir` komutu yeni modeli aynı test maçlarında puanlar (doğruluk, log-loss),
tek sezonluk ve önceki sezonlarla eğitilmiş hâlini karşılaştırır. Bağlamdaki alanlar `egit_ve_test`'in üstünde yazılı.
Süren sezonda `model_sekme.EN_AZ_MAC` (120) maçtan azı oynanmışsa sekme aynı ligin geçen sezonunu gösterir (üstte yazar).

## Yeni oyuncu istatistiği (FotMob)

1. `veri.py`: FotMob'un istatistik listesinin adını `LISTELER`'e, `(anahtar, ad, tür)`'ü `FOTMOB_EK`'e ekle ve
   `fotmob_sezon` içindeki `ek = [...]` listesine aynı sırada değeri yaz (tür: `t` toplam, `r` oran).
2. `sezon.py`: `EK` sözlüğüne aynı anahtarla ad ve tür. Oyuncu kartının "Ayrıntılar" bölümünde kendiliğinden görünür.
   Mevkidaş yüzdeliklerinde ya da benzer oyuncu hesabında kullanılacaksa `YUZDELIK`'e, rollerde kullanılacaksa `ROL`'e ekle.
3. `python -m mac_tahmin veri --yenile` ile verileri yeniden üret.

## Yeni özel rol (kural tabanlı)

`sezon.py`'deki `OZEL_ROLLER` listesine `(ad, açıklama, koşul)` ekle. Koşul `lambda p, y: ...`: `p` oyuncu, `y('xa')`
ligdeki saha oyuncularına göre 90 dk başına yüzdelik (`y('pres', 'FW')`: yalnızca forvet ve kanatlar arasında); birleşik
istatistik için `OZEL_ISTATISTIK`'e ekle. Oyuncular sekmesinde kartı, tablodaki rol sütunu ve oyuncu kartındaki rozeti
kendiliğinden çıkar. Bir oyuncu birden çok özel rol alabilir; kümeleme rolünden bağımsızdır.
Sezon verisinde olmayan istatistikle kurulan rol (ör. "Hava hâkimi": hava topu yalnızca maç maç veride) için örnek:
`sezon.HAVA_HAKIMI`, `lig_maclari.hava_hakimleri`, `Depo._hava_hakimi_ekle` (süren sezon, yalnızca indirilmiş maçlar).

## Yeni oyuncu rolü

`sezon.py`'deki `ROL` sözlüğüne `(ad, açıklama, şablon, mevkiler)` ekle. Şablon, `feats` sırasıyla her istatistiğin
ağırlığıdır (+ yüksek, − düşük); mevkiler rolün açık olduğu ana mevkiler (`F` forvet, `W` kanat, `M` orta saha,
`D` defans). Rol sayısı küme sayısını da belirler.

## Arka plan güncellemesi

Aralıklar `guncelleme.Guncelleyici`'de (`canli_aralik`, `veri_saat`); komut satırında `--aralik`, `--veri-saat`.
Yeni bir otomatik iş (ör. günlük haber çekme) eklemek için `Guncelleyici`'ye bir döngü yaz, `baslat`'ta başlat ve
sonucunu bir alanda tut; arayüz `sayfa.py`'deki `takip` işlevinde bunu izleyip `G.yay(...)` ile duyurabilir.

## Denemek

```
python -m mac_tahmin sunucu --tarayici-acma     # http://localhost:8080 (tarayıcının geliştirici araçlarıyla bakılabilir)
python -m mac_tahmin uygulama                   # pencerede
python -m mac_tahmin degerlendir EPL 2025       # hesapları arayüzsüz kontrol etmek için
python masaustu_paketle.py                      # masaüstü paketini yeniden üret
```

## Testler

```
python -m pip install -r requirements-dev.txt   # uygulamanın bağımlılıkları + pytest
python -m pytest                                # bütün testler (tests/); tek dosya: python -m pytest tests/test_modeller.py
```

Testler ağa çıkmaz (`tests/conftest.py` `urlopen`'ı engeller) ve `d/` ile `ham/` klasörlerine yazmaz; geçici dosyalar
`tmp_path` altında kurulur. `veri` işaretli testler `d/` içindeki gerçek verilerle çalışır, veri yoksa atlanır.
Yeni bir hesap ya da veri dönüşümü eklerken yanına bir test yaz (biçim: `tests/test_*.py`, ortak yardımcılar `tests/yardimci.py`).

Masaüstü paketi verisini `%LOCALAPPDATA%\MacTahmin` altına kopyalar (`masaustu.hazirla`). Pakette bir başlangıç önbelleği
de var (`masaustu_paketle.baslangic_onbellegi`: biten maçların ve takımların sayfaları, piyasa değerleri, scout havuzu,
sözleşme tarihleri, süren sezonun lig dosyaları; proje `ham/`'ı ile uygulamanın kendi önbelleğinden yenisi). Yeni bir
bilgisayarda ilk açılışta yalnızca eksik dosyalar kopyalanır (`masaustu.baslangic_kopyala`, paketin her sürümü bir kez):
binlerce sayfa kaynaklardan tek tek inmez. Paket ve önbellek yalnızca kişisel kullanım içindir; kaynakların verisi bir
sunucuya konup başkalarına dağıtılmaz.
