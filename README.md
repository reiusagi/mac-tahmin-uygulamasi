# Maç Tahmin Laboratuvarı

18 lig için maç tahmini, puan durumu ve sezon simülasyonu, oyuncu istatistikleri ve rolleri, canlı skorlar.
Tamamen Python ile yazılmıştır: hesaplar `mac_tahmin` paketinde, arayüz NiceGUI ile `mac_tahmin/arayuz` içinde.

Kurulum (Python 3.11+): `python -m pip install -r requirements.txt`  
Testler için: `python -m pip install -r requirements-dev.txt` ve `python -m pytest`
Yeni özellik eklemek için: [GELISTIRME.md](GELISTIRME.md)

## Klasördekiler

| Dosya / klasör | Ne işe yarar |
| --- | --- |
| `mac_tahmin/` | Hesaplar ve veri: modeller, sezon, oyuncular, veri indirme, canlı skor, komut satırı |
| `mac_tahmin/arayuz/` | Uygulamanın arayüzü (NiceGUI); her sekme ayrı bir dosya |
| `d/` | Lig-sezon verileri ve `stadyumlar.json` |
| `ham/` | İndirilen ham yanıtların önbelleği ve `dogum.json`; `dogum.json` dışındakiler silinebilir |
| `vendor/` | Yazı tiplerinin yerel kopyası (internetsiz açılış için) |
| `web/` | Eski HTML/JavaScript sürümünün son hâli (claude.ai'deki sayfa); artık geliştirilmiyor |
| `MacTahmin.pyw`, `masaustu_paketle.py` | Masaüstü uygulamasının başlangıcı ve paketleme betiği |

## Uygulamayı açmak

```
python -m mac_tahmin uygulama      # kendi penceresinde
python -m mac_tahmin sunucu        # tarayıcıda: http://localhost:8080
```

Uygulamanın parolası yoktur, bu yüzden varsayılan olarak yalnızca bu bilgisayardan (`127.0.0.1`) erişilir. Aynı ağdaki
başka bir cihazdan açmak istersen `--host 0.0.0.0` ver (uyarı yazılır; bağlantı şifreli değildir, yalnızca güvendiğin
ağda kullan). `MAC_TAHMIN_ANAHTAR` ortam değişkenini ayarlarsan dışa açık adreste her istek bu anahtarı ister: adresin
sonuna `?anahtar=<anahtar>` ekleyerek ilk kez gir, tarayıcı anahtarı çerezde saklar.

Uygulama açık kaldığı sürece veriler kendini günceller (`mac_tahmin/guncelleme.py`):

- canlı skorlar, önümüzdeki 4 günün maçları, hakemler: dakikada bir (`--aralik`)
- süren sezonun sonuçları, puan durumu ve oyuncu istatistikleri: 6 saatte bir; veri bundan eskiyse açılır açılmaz
  (`--veri-saat`, 0 verilirse kapalı). Yenilenince açık sezon kendiliğinden yeniden yüklenir. Alt bilgideki
  "Şimdi güncelle" düğmesi beklemeden yeniler.
- stadyumlar: ayda bir

Son seçilen lig, sezon ve sekme hatırlanır.

## Masaüstü uygulaması

`dist\MacTahmin\MacTahmin.exe` (masaüstündeki ya da Başlat menüsündeki **Maç Tahmin Laboratuvarı** kısayolu).
Python kurulu olmayan bir bilgisayarda da çalışır (`dist\MacTahmin` klasörünün tamamı taşınmalıdır).

- Veriler `%LOCALAPPDATA%\MacTahmin` klasöründe tutulur ve yukarıdaki gibi kendini günceller. Hatalar `uygulama.log`'a yazılır.
- Kod değiştiğinde yeniden paketlemek için: `python masaustu_paketle.py` (önce açık uygulamayı kapat).
- Paketlemeden denemek için: `python -m mac_tahmin.masaustu`

## Komut satırı

```
python -m mac_tahmin tahmin Super_Lig 2026 Galatasaray Fenerbahçe
python -m mac_tahmin tablo EPL 2025
python -m mac_tahmin oyuncu EPL 2024 salah
python -m mac_tahmin oyuncular EPL 2025 --mevki LB --yas U23
python -m mac_tahmin benzer EPL 2025 haaland --tum
python -m mac_tahmin roller Super_Lig 2025 "top kazanan"
python -m mac_tahmin degerlendir La_liga 2025
python -m mac_tahmin simulasyon Super_Lig 2026
python -m mac_tahmin canli
python -m mac_tahmin veri --sezonlar 2026 --yenile
python -m mac_tahmin stadyum
```

Lig anahtarları `mac_tahmin/sezon.py`'deki `LIGLER` listesindedir (ör. `EPL`, `La_liga`, `Super_Lig`, `Brasileirao`).
Sezon başlangıç yılıyla yazılır (2025 = 2025/26; takvim yılına göre oynanan liglerde 2025 = 2025 sezonu).

`oyuncular` komutunda `--mevki` ayrıntılı mevki (GK kaleci, CB stoper, RB sağ bek, LB sol bek, DM ön libero, CM merkez
orta saha, AM on numara, RW sağ kanat, LW sol kanat, ST forvet) ya da ana mevki (D, M, W, F, G) alır; `--yas` U18, U21,
U23, 23-29 ya da 30+ olabilir. Yaş, süren sezonda bugünkü yaştır; geçmiş sezonlarda sezonun ortasındaki yaş
(Ağustos-Mayıs liglerinde 1 Ocak, takvim yılı liglerinde 1 Temmuz).

## Milli takımlar

- **Canlı** sekmesi, liglerin yanında milli maçları da gösterir (Uluslar Ligi, Dünya Kupası ve elemeleri, EURO, Copa
  América, Afrika ve Asya kupaları, Gold Cup, hazırlık maçları). Üstteki küçük takvimle önceki/sonraki güne ya da
  takvimden herhangi bir güne geçilir.
- **Milli takımlar** sekmesi: turnuva ve sezon seçimi, grup tabloları, maçlar (oynanmamışlarda olasılıklar), iki milli
  takım arasında maç tahmini ve milli takım Elo sıralaması.
- Elo, World Football Elo yöntemiyle 2008'den bu yana bütün resmi milli maçlardan hesaplanır (maçın önemi, gol farkı,
  ev sahibi avantajı). 2022 sonrası maçlarda olasılıklar gerçekleşen sonuçlarla uyumlu çıktı (log-loss 0,89).
  FotMob 2026 öncesi hazırlık maçlarını vermediği için kıtalar arası karşılaştırma kabadır.
- Veri `mac_tahmin/milli.py` ile indirilir, `d/milli.json`'a derlenir; süren turnuvalar 6 saatte bir yenilenir.

## Mevkiler ve yaşlar

- Ayrıntılı mevki FotMob'un oyuncunun sahadaki yerine verdiği numaradan çıkarılır (ör. 32 sağ bek, 38 sol bek, 66 ön libero,
  85 on numara, 83 sağ kanat, 87 sol kanat). Understat liglerinde oyuncu FotMob'daki adı ve takımıyla eşleştirilir; FotMob'un
  oyuncu verisi olmayan 2014-2016 sezonlarında oyuncunun sonraki sezonlarındaki mevkisi kullanılır.
- Doğum tarihleri FotMob'dan bir kez çekilip `ham/dogum.json`'da saklanır; ilk toplu doldurma için
  `python -m mac_tahmin.dogum ham` (yaklaşık 15 bin oyuncu, bir saati aşabilir). Sonra veri güncellemesi yalnızca yeni oyuncuları sorar.

## Modeller

- **Poisson** (tahmin ekranı ve sezon simülasyonu): takımların hücum ve savunma gücü bu sezonun ve önceki 3 sezonun
  maçlarından hesaplanır; eski maçların ağırlığı 180 günde yarıya iner. Ligde yeni olan takımlar "yükselen takım"
  ön bilgisiyle başlar.
- **Elo**: sezondan sezona taşınır (ortalamadan uzaklığın üçte ikisi korunur, yükselen takımlar 1450'den başlar).
- **Lojistik regresyon ve Random Forest**: önceki 3 sezonun bütün maçları ve bu sezonun ilk %70'iyle eğitilir;
  Understat liglerinde maç xG'si de özellik olarak kullanılır. `degerlendir` komutu ve "Modeller" sekmesi bunu
  yalnızca bu sezonla eğitilen sürümle aynı test maçlarında karşılaştırır.
- **Sezon simülasyonu**: kalan maçlar Poisson modeliyle 10.000 kez oynatılır (numpy ile, yarım saniye civarı).
- **Benzer oyuncular**: 90 dakika başına istatistik profilleri standartlaştırılır; benzerlik iki profil arasındaki
  mesafeden hesaplanır, böylece hem oyun tarzı hem üretim düzeyi benzer olmalıdır.
- **Oyuncu rolleri**: saha oyuncuları 90 dakika başına profillerine göre k-means ile kümelenir (Understat liglerinde
  5, FotMob liglerinde 7 rol); her küme, merkezinin profiline en çok uyan rolün adını alır. Kaynağın o sezon
  tutmadığı istatistikler kümelemeye girmez (FotMob'un eski sezonlarında xG ve xA yerine gol ve asist kullanılır);
  FotMob'un listesinde olmayan oyuncunun o istatistiği 0 sayılır.

## IDE'de (VS Code, PyCharm)

- Bu klasörü proje olarak aç, yorumlayıcı olarak Python 3.13'ü seç.
- Çalıştırma ayarında "script" yerine **module** seç, modül adı `mac_tahmin`, parametreler örneğin `uygulama` ya da
  `tahmin EPL 2025 Arsenal Chelsea`; çalışma klasörü bu klasör olmalı.
- VS Code için hazır ayarlar: `.vscode/launch.json`.

## Veri kaynakları

Maç sonuçları, xG ve oyuncu istatistikleri: understat.com (5 büyük lig) ve fotmob.com (diğer ligler). Mevki, yaş,
canlı skorlar, hakemler ve stadyumlar: fotmob.com. Tahminler istatistiksel modeldir; kesin sonuç değildir.
