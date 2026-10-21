"""Modern görünüm (Görünüm menüsü → Stil: Modern): spor uygulaması havası; koyu öncelikli yüzeyler, tek canlı vurgu rengi,
büyük skor ve yüzde yazıları, logolu kartlar, renkli olasılık çubukları.

Bütün kurallar body.stil-modern altında: klasik görünüm hiç değişmez. Tek istisna en üstteki iki satır: modern için
eklenen öğeler (.md-ust: maç tahmini panosunun logolu başlığı, .md-lejant: puan durumunun bölge açıklaması) klasikte gizli.
Renk paletleri (ortak.PALETLER) modernde vurgu rengini belirler; açık ve koyu temada ayrı tonlar (yazı karşıtlığı ≥ 4,5:1).
sayfa.py ui.add_css(CSS) ardından eklenir.
"""

CSS_MODERN = r'''
/* modern için eklenen öğeler klasikte görünmez */
.md-ust,.md-lejant{display:none}

/* ---------------------------------------------------------------- renkler: önce palet vurgusu, sonra tema yüzeyleri.
   -k: koyu zemin üstünde (koyu tema ve pano), -a: açık zemin üstünde; -isi: skor ısı haritası; -ana: beyaz yazılı düğme zemini */
html body.stil-modern:not(#m){
  --m-vurgu-k:#34d399; --m-vurgu-a:#047857; --m-isi-k:#15803d; --m-isi-a:#10b981; --m-ana:#0b7d3e; --m-ikinci:#60a5fa;
}
html body.stil-modern.palet-gece:not(#m){
  --m-vurgu-k:#60a5fa; --m-vurgu-a:#1d4ed8; --m-isi-k:#1d4ed8; --m-isi-a:#3b82f6; --m-ana:#2563eb; --m-ikinci:#fbbf24;
}
html body.stil-modern.palet-bordo:not(#m){
  --m-vurgu-k:#fb7185; --m-vurgu-a:#be123c; --m-isi-k:#be123c; --m-isi-a:#f43f5e; --m-ana:#be123c; --m-ikinci:#60a5fa;
}
html body.stil-modern.palet-grafit:not(#m){
  --m-vurgu-k:#2dd4bf; --m-vurgu-a:#0f766e; --m-isi-k:#0f766e; --m-isi-a:#14b8a6; --m-ana:#0f766e; --m-ikinci:#fbbf24;
}
/* açık tema */
html body.stil-modern:not(.body--dark):not(#m){
  --bg:#f2f4f7; --panel:#ffffff; --panel-2:#f5f7fa; --ink:#0f141a; --soft:#556070; --line:#e3e7ed;
  --m-vurgu:var(--m-vurgu-a); --m-isi:var(--m-isi-a); --m-zebra:#f8fafc; --m-ust:#eef1f5;
  --m-golge:0 1px 2px rgba(15,20,26,.04),0 4px 16px rgba(15,20,26,.05);
  --lamp:#a16207; --bad:#c62d36; --away:#1d4ed8; --draw:#6b7482;
}
/* koyu tema */
html body.stil-modern.body--dark:not(#m){
  --bg:#0b0e13; --panel:#141921; --panel-2:#1b212b; --ink:#eef2f6; --soft:#9aa5b4; --line:#262e3a;
  --m-vurgu:var(--m-vurgu-k); --m-isi:var(--m-isi-k); --m-zebra:#171c25; --m-ust:#11151c;
  --m-golge:0 1px 0 rgba(255,255,255,.03) inset;
  --lamp:#f5c542; --bad:#ff6b6b; --away:#60a5fa; --draw:#8b94a1;
  --q-dark:#141921; --q-dark-page:#0b0e13;
}
/* ikisinde ortak: vurgu, pano (iki temada da koyu "skorbord"), form ve olasılık rozetleri (beyaz yazı ≥ 4,5:1) */
html body.stil-modern:not(#m){
  --pitch:var(--m-vurgu); --pitch-2:var(--m-vurgu); --q-primary:var(--m-ana) !important;
  --board:#121822; --board-ink:#f2f5f8; --board-soft:#a9b4c2; --board-line:rgba(255,255,255,.10);
  --b-home:var(--m-vurgu-k); --b-draw:#8b94a1; --b-away:var(--m-ikinci); --b-text:#0b0e13;
  --m-kazan:#0b7d3e; --m-kayip:#c62d36; --m-ber:#5f6876;
  --mk-ev:#f59a4a; --mk-dep:#5b9bff;
  --m-r:16px; --m-r-ic:12px;
}

/* ---------------------------------------------------------------- iskelet: başlık, sekmeler, paneller */
body.stil-modern{background:var(--bg);-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
body.stil-modern .app-ust{padding:20px 20px 10px}
body.stil-modern .app-ust h1{font-family:var(--body);font-size:1.55rem;font-weight:700;letter-spacing:-.01em;
  display:flex;align-items:center;gap:10px}
body.stil-modern .app-ust h1::before{content:"";width:10px;height:22px;border-radius:3px;background:var(--m-vurgu);flex:none}
body.stil-modern .app-ust .alt{padding-left:20px;font-size:.88rem}
body.stil-modern .app-ust .q-field--outlined .q-field__control{border-radius:12px;background:var(--panel)}
body.stil-modern .sekmeler{position:sticky;top:0;z-index:20;border-bottom:1px solid var(--line);padding:6px 12px;
  background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
body.stil-modern .sekmeler .q-tab{border-radius:999px;min-height:34px;padding:0 14px;margin:0 2px;color:var(--soft);
  transition-property:background-color,color;transition-duration:150ms;transition-timing-function:ease-out}
body.stil-modern .sekmeler .q-tab:hover{color:var(--ink);background:var(--panel-2)}
body.stil-modern .sekmeler .q-tab__label{font-family:var(--body);font-size:.92rem;font-weight:600;letter-spacing:0}
body.stil-modern .sekmeler .q-tab--active{color:var(--ink) !important;background:color-mix(in srgb,var(--m-vurgu) 16%,transparent)}
body.stil-modern .sekmeler .q-tab--active .q-tab__label{color:var(--ink)}
body.stil-modern .sekmeler .q-tab__indicator{display:none}
body.stil-modern .sekmeler .q-tabs__arrow{color:var(--ink)}
body.stil-modern .q-tab:focus-visible,body.stil-modern .q-btn:focus-visible,body.stil-modern .fx:focus-visible,
body.stil-modern .link:focus-visible{outline:2px solid var(--m-vurgu);outline-offset:2px}
body.stil-modern .icerik{gap:18px}
body.stil-modern .panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--m-r);padding:18px 20px;
  box-shadow:var(--m-golge)}
body.stil-modern .panel h3{font-family:var(--body);font-size:1.12rem;font-weight:700;letter-spacing:-.005em;margin:0;
  text-wrap:balance}
body.stil-modern h4.mt-h{font-family:var(--body);font-size:1rem;font-weight:700}
body.stil-modern .lead{text-wrap:pretty}
body.stil-modern .cap{text-wrap:pretty}
body.stil-modern .link{color:var(--m-vurgu)}
body.stil-modern .q-expansion-item .q-item{border-radius:10px}
body.stil-modern .alt-bilgi{padding:10px 20px 28px}
/* koyu temada Quasar yüzeyleri (açılır menü, pencere, tablo) panel renginde */
body.stil-modern .q-menu,body.stil-modern .q-dialog .q-card{background:var(--panel);color:var(--ink)}
body.stil-modern .q-dialog .q-card{border-radius:20px;border:1px solid var(--line)}
body.stil-modern .q-menu{border-radius:12px;border:1px solid var(--line)}
body.stil-modern .q-table__card,body.stil-modern .q-table__container{background:transparent;color:var(--ink);box-shadow:none}

/* ---------------------------------------------------------------- maç tahmini: hafta şeridi */
body.stil-modern .serit{gap:10px;padding:4px 2px 12px}
body.stil-modern .fx{background:var(--panel);border:1px solid var(--line);border-radius:var(--m-r-ic);padding:10px 12px;
  min-width:176px;box-shadow:var(--m-golge);transition-property:border-color,background-color,transform;transition-duration:150ms;
  transition-timing-function:ease-out}
body.stil-modern .fx:hover{border-color:color-mix(in srgb,var(--m-vurgu) 60%,var(--line))}
body.stil-modern .fx:active{transform:scale(.97)}
body.stil-modern .fx.sec{border-color:var(--m-vurgu);box-shadow:0 0 0 1px var(--m-vurgu) inset;
  background:color-mix(in srgb,var(--m-vurgu) 8%,var(--panel))}
body.stil-modern .fx.done{opacity:1} body.stil-modern .fx.done b{color:var(--soft)}
body.stil-modern .fx b{font-size:.92rem;line-height:1.55;align-items:center}
body.stil-modern .fx b > span:last-child{font-variant-numeric:tabular-nums;font-weight:700;color:var(--ink)}
body.stil-modern .fx small{font-size:.74rem;margin-bottom:3px}
body.stil-modern .fx .zaman{color:var(--m-vurgu)}
body.stil-modern .fx b .logo{width:18px;height:18px;vertical-align:-4px;margin-right:6px}

/* ---------------------------------------------------------------- maç tahmini: pano (koyu skorbord) */
body.stil-modern .board{--ink:var(--board-ink);--soft:var(--board-soft);--line:var(--board-line);--panel-2:rgba(255,255,255,.06);
  --m-vurgu:var(--m-vurgu-k);--pitch:var(--m-vurgu-k);--pitch-2:var(--m-vurgu-k);--lamp:#f5c542;--bad:#ff6b6b;
  border-radius:22px;padding:20px 22px 14px;gap:14px;color:var(--board-ink);border:1px solid rgba(255,255,255,.06);
  background:radial-gradient(90% 70% at 18% -10%,color-mix(in srgb,var(--b-home) 20%,transparent),transparent 60%),
             radial-gradient(90% 70% at 82% -10%,color-mix(in srgb,var(--b-away) 16%,transparent),transparent 60%),var(--board);
  box-shadow:0 10px 30px rgba(5,10,20,.18)}
body.stil-modern .board .q-field--outlined .q-field__control{border-radius:12px;background:rgba(255,255,255,.04)}
body.stil-modern .board .q-field__label{font-size:.72rem;letter-spacing:.04em}
/* sıra: seçim · logolu başlık · maç bilgisi · çubuk ve yüzdeler · özet · eksikler · açıklama */
body.stil-modern .board > div:has(> .md-ust){display:contents}
body.stil-modern .board > div:has(> .md-ust) > *{width:100%;box-sizing:border-box}
body.stil-modern .board > *{order:6}
body.stil-modern .board > .secim-satiri{order:0}
body.stil-modern .board .md-ust{order:1}
body.stil-modern .board > .mac-bilgi{order:2}
body.stil-modern .board > div > .bar,body.stil-modern .board > div > .oran{order:3}
body.stil-modern .board > div > .ozet-cumle,body.stil-modern .board > div > .ozet-cipler,
body.stil-modern .board > div:has(> .md-ust) > .soft{order:4}
body.stil-modern .board > div:has(> .md-ust) > .oran + div{display:none !important}  /* beklenen gol başlıkta */
body.stil-modern .board > .q-expansion-item{order:7}
body.stil-modern .md-ust{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:18px;padding:10px 0 2px}
body.stil-modern .md-takim{display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center;min-width:0;
  font-size:1.25rem;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
body.stil-modern .md-takim .logo{width:76px;height:76px;filter:drop-shadow(0 6px 14px rgba(0,0,0,.35))}
body.stil-modern .md-orta{display:flex;flex-direction:column;align-items:center;gap:4px}
body.stil-modern .md-eg{font-family:var(--display);font-size:3.4rem;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;
  white-space:nowrap}
body.stil-modern .md-eg i{font-style:normal;color:var(--board-soft);margin:0 .14em;font-weight:500}
body.stil-modern .md-eg-ad{font-size:.72rem;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--board-soft)}
body.stil-modern .mac-bilgi{margin:0;padding:0;border:0;gap:8px}
body.stil-modern .mac-bilgi span{background:rgba(255,255,255,.06);border:1px solid var(--board-line);border-radius:999px;padding:4px 12px;
  color:var(--board-ink);font-size:.82rem}
body.stil-modern .mac-bilgi .material-icons{opacity:.8;color:var(--board-soft)}
body.stil-modern .board .bar{height:12px;gap:4px;border-radius:0;background:transparent;margin-top:6px}
body.stil-modern .board .bar > div{border-radius:999px;min-width:6px}
body.stil-modern .oran{gap:10px;margin-top:0 !important}
body.stil-modern .oran > div{background:rgba(255,255,255,.05);border:1px solid var(--board-line);border-radius:14px;padding:10px 8px 12px;
  position:relative}
body.stil-modern .oran > div::before{content:"";position:absolute;left:14px;right:14px;top:-1px;height:3px;border-radius:0 0 3px 3px}
body.stil-modern .oran > div:nth-child(1)::before{background:var(--b-home)}
body.stil-modern .oran > div:nth-child(2)::before{background:var(--b-draw)}
body.stil-modern .oran > div:nth-child(3)::before{background:var(--b-away)}
body.stil-modern .oran .k{font-size:.8rem;font-weight:600;color:var(--board-soft);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
body.stil-modern .oran .v{font-size:2.6rem;line-height:1.05;font-variant-numeric:tabular-nums;color:var(--board-ink)}
body.stil-modern .oran .top{background:rgba(255,255,255,.09);border-color:rgba(255,255,255,.18)}
body.stil-modern .oran .top .v{color:var(--board-ink)}
body.stil-modern .oran .top .k::after{content:" · en olası";color:var(--lamp)}
body.stil-modern .ozet-cumle{font-size:1rem;margin:4px 0 0;text-wrap:balance}
body.stil-modern .ozet-cipler{margin-top:0}
body.stil-modern .ozet-cip{background:rgba(255,255,255,.06);padding:4px 12px;font-size:.84rem}
body.stil-modern .board .q-expansion-item{border-top:1px solid var(--board-line);margin-top:2px;padding-top:4px}

/* ---------------------------------------------------------------- maç tahmini: skor ısı haritası ve listeler */
body.stil-modern .matris{--pitch:var(--m-isi);gap:4px;grid-template-columns:28px repeat(6,minmax(0,1fr))}
body.stil-modern .matris span{height:40px;border-radius:8px;font-variant-numeric:tabular-nums;font-weight:600}
body.stil-modern .matris span:not(.ax){color:var(--ink) !important;box-shadow:inset 0 0 0 1px var(--line)}
body.stil-modern .matris .ax{font-size:.78rem}
body.stil-modern .matris span.best{outline:none;box-shadow:0 0 0 2px var(--lamp),0 6px 16px rgba(0,0,0,.18);font-weight:800;
  position:relative;z-index:1}
body.stil-modern .matris span.real{box-shadow:inset 0 0 0 2px var(--ink)}
body.stil-modern .matris span.best.real{box-shadow:0 0 0 2px var(--lamp),inset 0 0 0 2px var(--ink)}
body.stil-modern .matris-eksen,body.stil-modern .matris-dikey{font-size:.74rem;letter-spacing:.02em}
body.stil-modern .liste{gap:2px}
body.stil-modern .satir{grid-template-columns:minmax(0,1fr) minmax(40px,110px) 50px;gap:12px;padding:7px 10px;border-radius:10px;
  transition-property:background-color;transition-duration:150ms}
body.stil-modern .satir:hover{background:var(--panel-2)}
body.stil-modern .satir small{font-size:.76rem;text-wrap:pretty}
body.stil-modern .track{height:6px;border:0;border-radius:999px;background:color-mix(in srgb,var(--soft) 22%,transparent)}
body.stil-modern .track i{border-radius:999px;background:var(--m-vurgu)}
body.stil-modern .pv{font-weight:700}
/* dar listede (ör. asist ve kart: iki takım yan yana) çubuk adın altına iner, ad kesilmez */
body.stil-modern .liste{container-type:inline-size}
@container (max-width:340px){body.stil-modern .satir{grid-template-columns:minmax(0,1fr) 46px;row-gap:5px}
  body.stil-modern .satir > .track,body.stil-modern .satir > div:has(> .track){grid-column:1 / -1;grid-row:2}}
body.stil-modern .tahmin-takim{padding:2px 10px 6px;font-family:var(--body);font-size:1rem}
body.stil-modern .tahmin-takim .logo{width:24px;height:24px}
/* olasılık kartları (piyasa_kartlari) */
body.stil-modern .pz-izgara{gap:12px}
body.stil-modern .pz-kart{background:var(--panel-2);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
body.stil-modern .pz-baslik{font-family:var(--body);font-size:.78rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--soft);margin-bottom:8px}
body.stil-modern .pz-satir{grid-template-columns:minmax(0,1fr) 56px 46px;padding:4px 0}
body.stil-modern .pz-satir .cubuk{height:6px;border-radius:999px;background:color-mix(in srgb,var(--soft) 22%,transparent)}
body.stil-modern .pz-satir .cubuk i{border-radius:999px;background:color-mix(in srgb,var(--m-vurgu) 55%,var(--soft))}
body.stil-modern .pz-satir.en{background:color-mix(in srgb,var(--m-vurgu) 12%,transparent);border-radius:8px;margin:0 -6px;padding:4px 6px}
body.stil-modern .pz-satir.en .ad,body.stil-modern .pz-satir.en b{color:var(--ink);font-weight:700}
body.stil-modern .pz-satir.en .cubuk i{background:var(--m-vurgu)}
body.stil-modern .pz-ayrac{border-top:1px solid var(--line);margin:6px 0}
/* geçmiş karşılaşmalar çubuğu ve ayrıntılı tahmin penceresi */
body.stil-modern .panel .bar,body.stil-modern .q-card .bar{height:30px;gap:3px;border-radius:0;font-size:.85rem}
body.stil-modern .panel .bar > div,body.stil-modern .q-card .bar > div{border-radius:8px}
body.stil-modern .mt-ust{grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:14px;margin-bottom:12px}
body.stil-modern .mt-takim{flex-direction:column;align-items:center;text-align:center;gap:8px;font-family:var(--body);font-size:1.1rem}
body.stil-modern .mt-takim.sag{flex-direction:column-reverse}
body.stil-modern .mt-takim .logo{width:56px;height:56px}
body.stil-modern .mt-eg .eg{font-size:2.8rem}
body.stil-modern .mt-oran .tile{border:1px solid var(--line);border-radius:12px}
body.stil-modern .mt-top{background:color-mix(in srgb,var(--m-vurgu) 14%,var(--panel-2))}
body.stil-modern .mt-top .num{color:var(--ink)}
body.stil-modern .tile{border-radius:12px}
body.stil-modern .tile .num{font-variant-numeric:tabular-nums}

/* ---------------------------------------------------------------- tablolar */
body.stil-modern table.tb{font-size:.9rem;border-collapse:separate;border-spacing:0}
body.stil-modern table.tb th{font-size:.7rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--soft);
  padding:10px 10px;border-bottom:1px solid var(--line);background:var(--panel)}
body.stil-modern table.tb td{padding:9px 10px;border-bottom:1px solid var(--line)}
body.stil-modern table.tb tbody tr:nth-child(even) td{background:var(--m-zebra)}
body.stil-modern table.tb tbody tr:hover td{background:color-mix(in srgb,var(--m-vurgu) 8%,var(--panel))}
body.stil-modern table.tb tbody tr:last-child td{border-bottom:0}
body.stil-modern table.tb tr.champ td:first-child{box-shadow:inset 4px 0 0 var(--lamp)}
body.stil-modern table.tb tr.cl td:first-child{box-shadow:inset 4px 0 0 var(--m-vurgu)}
body.stil-modern table.tb tr.rel td:first-child{box-shadow:inset 4px 0 0 var(--bad)}
body.stil-modern table.tb tr.champ.cl td:first-child{box-shadow:inset 4px 0 0 var(--lamp)}  /* lider ilk 4'te de: altın kalsın */
body.stil-modern table.tb tr.cur td,body.stil-modern table.tb tr.best-row td{background:color-mix(in srgb,var(--m-vurgu) 12%,var(--panel))}
body.stil-modern td.takim-hucre{font-weight:600}
body.stil-modern td.takim-hucre .logo{width:22px;height:22px;vertical-align:-6px;margin-right:10px}
body.stil-modern table.tb .takim-link{color:var(--ink)} body.stil-modern table.tb .takim-link:hover{color:var(--m-vurgu)}
/* puan durumu: sayılar sağa yaslı, sıra ortada, puan büyük */
body.stil-modern table.puan-tablo td:first-child,body.stil-modern table.puan-tablo th:first-child{text-align:center;width:44px;
  font-weight:700;color:var(--soft)}
body.stil-modern table.puan-tablo td:nth-child(n+3):nth-child(-n+12),
body.stil-modern table.puan-tablo th:nth-child(n+3):nth-child(-n+12){text-align:right}
body.stil-modern table.puan-tablo th:last-child,body.stil-modern table.puan-tablo td:last-child{text-align:right;padding-right:16px}
body.stil-modern table.puan-tablo td.pts{font-family:var(--display);font-size:1.15rem;font-weight:700}
body.stil-modern table.puan-tablo td{padding-top:10px;padding-bottom:10px}
body.stil-modern .md-lejant{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.8rem;color:var(--soft);padding:10px 4px 2px}
body.stil-modern .md-lejant span{display:inline-flex;align-items:center;gap:7px}
body.stil-modern .md-lejant i{width:4px;height:14px;border-radius:2px;display:inline-block}
body.stil-modern .md-lejant .champ{background:var(--lamp)} body.stil-modern .md-lejant .cl{background:var(--m-vurgu)}
body.stil-modern .md-lejant .rel{background:var(--bad)}
/* yapışkan tablo başlığı: geniş ekranda tablo sayfayla kayar, başlık sekme çubuğunun altında kalır */
@media (min-width:1000px){
  body.stil-modern .q-tab-panels.q-panel-parent{overflow:visible}
  body.stil-modern .kaydir:has(> table.puan-tablo){overflow:visible}
  body.stil-modern table.puan-tablo thead th{position:sticky;top:47px;z-index:2}
  body.stil-modern .oyuncu-tablo .q-table__middle{overflow:visible}
  body.stil-modern .oyuncu-tablo thead th{position:sticky;top:47px;z-index:2;background:var(--panel)}
}
/* form rozetleri: harf kalır (renk tek başına anlam taşımaz) */
body.stil-modern .form{gap:4px}
body.stil-modern .form i{width:22px;height:22px;border-radius:7px;font-size:.72rem;letter-spacing:0;color:#fff}
body.stil-modern .form i.G{background:var(--m-kazan)} body.stil-modern .form i.B{background:var(--m-ber)}
body.stil-modern .form i.M{background:var(--m-kayip)}
body.stil-modern .olas{gap:3px}
body.stil-modern .olas span{border-radius:7px;padding:3px 8px}
body.stil-modern .olas .kaz{background:var(--m-kazan)} body.stil-modern .olas .kay{background:var(--m-kayip)}
body.stil-modern .olas .ber,body.stil-modern.body--dark .olas .ber{background:var(--m-ber);color:#fff}
body.stil-modern .fk-cip.k{background:var(--m-kazan)} body.stil-modern .fk-cip.z{background:var(--m-kayip)}
body.stil-modern .fk-cip.o{background:#a16207}
body.stil-modern .sc-z.kolay{background:var(--m-kazan)} body.stil-modern .sc-z.cokzor{background:var(--m-kayip)}
body.stil-modern .sc-z.zor{background:#b45309} body.stil-modern .sc-z.orta{background:#f5c542;color:#2a2005}
body.stil-modern .dist i{border-radius:3px}
/* oyuncular tablosu (Quasar) */
body.stil-modern .oyuncu-tablo .q-table th{font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--soft);
  border-bottom:1px solid var(--line)}
body.stil-modern .oyuncu-tablo .q-table td{border-bottom-color:var(--line);height:42px}
body.stil-modern .oyuncu-tablo .q-table tbody tr:nth-child(even) td{background:var(--m-zebra)}
body.stil-modern .oyuncu-tablo .q-table tbody tr:hover td{background:color-mix(in srgb,var(--m-vurgu) 8%,var(--panel))}
body.stil-modern .oyuncu-tablo .q-table tbody td:first-child{font-weight:600}
body.stil-modern .oyuncu-tablo .q-table__bottom{border-top:1px solid var(--line);color:var(--soft)}
body.stil-modern .q-table tbody td:before{background:transparent}
/* kartlar: roller, kıyas, lider, ihtiyaç, şans, değerlendirme */
body.stil-modern .rol,body.stil-modern .kiyas-kart,body.stil-modern .lider-kutu,body.stil-modern .perf-grup,body.stil-modern .tl-kart,
body.stil-modern .sans-kutu,body.stil-modern .dg-kart,body.stil-modern .ih-kutu,body.stil-modern .kariyer-ozet{
  background:var(--panel-2);border:1px solid var(--line);border-radius:14px}
body.stil-modern .rol{transition-property:border-color,background-color;transition-duration:150ms}
body.stil-modern .rol:hover{border-color:color-mix(in srgb,var(--m-vurgu) 50%,var(--line))}
body.stil-modern .rol.sec{border-color:var(--m-vurgu);box-shadow:0 0 0 1px var(--m-vurgu) inset;background:color-mix(in srgb,var(--m-vurgu) 8%,var(--panel-2))}
body.stil-modern .rol .ad{font-family:var(--body);font-size:1.02rem}
body.stil-modern .chip{background:var(--panel);border-color:var(--line);border-radius:999px;padding:2px 9px}

/* ---------------------------------------------------------------- scout ve bu hafta */
body.stil-modern .sc-izgara{gap:14px}
body.stil-modern .sc-grup{background:var(--panel-2);border:1px solid var(--line);border-radius:16px;padding:12px 14px}
body.stil-modern .sc-baslik{font-family:var(--body);font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
body.stil-modern .sc-oyuncu{padding:10px 0}
body.stil-modern .sc-oyuncu .cap .logo{width:18px;height:18px;vertical-align:-4px;margin-right:5px}
body.stil-modern .sc-endeks{font-size:1.55rem;color:var(--m-vurgu);font-variant-numeric:tabular-nums}
body.stil-modern .sc-bar{height:5px;border-radius:999px;background:color-mix(in srgb,var(--soft) 22%,transparent)}
body.stil-modern .sc-bar i{border-radius:999px}
body.stil-modern .sc-bar i:not([style*="background"]){background:var(--m-vurgu)}
body.stil-modern .hm-mac,body.stil-modern .tk-mac,body.stil-modern .tl-mac{padding:9px 8px;border-radius:10px;column-gap:12px;
  transition-property:background-color;transition-duration:150ms}
body.stil-modern .hm-mac .logo{width:20px;height:20px;vertical-align:-5px}
body.stil-modern .hm-mac > .cap{font-size:.74rem}
body.stil-modern .tk-grup{font-family:var(--body);font-size:.8rem;letter-spacing:.07em;text-transform:uppercase;color:var(--soft);
  margin-top:14px;padding-bottom:4px;border-bottom:1px solid var(--line)}

/* ---------------------------------------------------------------- canlı, kupalar, milli, maç kartı */
body.stil-modern .lig-panel{padding:14px 16px 8px}
body.stil-modern .lig-baslik{border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:4px}
body.stil-modern .lig-baslik .disp{font-family:var(--body);font-size:1rem;font-weight:700}
body.stil-modern .cm{border-radius:0;padding:10px 8px;border-bottom:1px solid var(--line)}
body.stil-modern .cm:hover{background:var(--panel-2)}
body.stil-modern .cm .skor{background:var(--panel-2);border:1px solid var(--line);border-radius:10px;font-size:1.3rem;min-width:70px}
body.stil-modern .cm .skor.canli{background:var(--m-kayip);border-color:transparent}
body.stil-modern .cm .skor.saat{color:var(--m-vurgu);border-color:var(--line)}
body.stil-modern .cm .durum.bitti{background:var(--panel-2);border-radius:7px}
body.stil-modern .cm.canli{background:color-mix(in srgb,var(--m-kayip) 9%,transparent)}
body.stil-modern .cm .takim .logo{width:24px;height:24px}
body.stil-modern .gun-panel{padding:10px 16px}
body.stil-modern .gun-dugme{font-family:var(--body);font-size:1.05rem}
body.stil-modern .mm{padding:10px 6px;border-radius:10px}
body.stil-modern .mm.secilebilir:hover{background:var(--panel-2)}
body.stil-modern .agac-mac{background:var(--panel-2);border-color:var(--line);border-radius:10px;padding:6px 9px}
body.stil-modern .agac-baslik{font-family:var(--body);font-size:.75rem;letter-spacing:.08em;text-transform:uppercase}
body.stil-modern .mk-logo{width:68px;height:68px}
body.stil-modern .mk-skor{font-size:2.8rem;border-radius:14px;border:1px solid var(--line);font-variant-numeric:tabular-nums}
body.stil-modern .mk-skor.canli{background:var(--m-kayip);border-color:transparent}
body.stil-modern .mk-takim{font-weight:700}
body.stil-modern .ist-grup{font-family:var(--body);font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
body.stil-modern .perf-baslik,body.stil-modern .tk-grup{font-family:var(--body)}
body.stil-modern .saha{border-radius:16px}
body.stil-modern .belirsiz-kutu{border-radius:10px}

/* Quasar'ın !important renk sınıflarını (text-primary, bg-grey-3…) aşmak için: NiceGUI'nin "overrides" katmanındaki
   !important, Quasar'ın sonraki katmandaki !important'ından önce gelir */
@layer overrides{
  body.stil-modern.body--dark .text-primary{color:var(--m-vurgu) !important}
  body.stil-modern .gun-panel .q-btn.bg-grey-3{background:var(--panel-2) !important;box-shadow:inset 0 0 0 1px var(--line)}
  body.stil-modern .gun-panel .q-btn.text-grey-9{color:var(--ink) !important}
  body.stil-modern .satir .q-btn.link{color:var(--ink) !important;font-weight:600}
  body.stil-modern .satir .q-btn.link:hover{color:var(--m-vurgu) !important}
}
@media (prefers-reduced-motion:reduce){
  body.stil-modern .fx,body.stil-modern .satir,body.stil-modern .sekmeler .q-tab,body.stil-modern .rol{transition:none}
  body.stil-modern .fx:active{transform:none}
}
@media (max-width:700px){
  body.stil-modern .md-takim{font-size:1rem} body.stil-modern .md-takim .logo{width:52px;height:52px}
  body.stil-modern .md-eg{font-size:2.4rem} body.stil-modern .oran .v{font-size:1.9rem}
  body.stil-modern .app-ust h1{font-size:1.3rem}
}
'''
