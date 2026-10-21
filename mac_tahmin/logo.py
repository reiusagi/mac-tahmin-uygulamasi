"""FotMob logo adresleri ve logo etiketi (arayüzden bağımsız; avrupa/milli modülleri de kullanır)."""
from .bicim import sayi_kimlik

KOK = 'https://images.fotmob.com/image_resources/logo'
LIG_LOGO = KOK + '/leaguelogo/{}.png'
TAKIM_LOGO = KOK + '/teamlogo/{}_xsmall.png'


def takim_logo_url(tid, boyut='xsmall'):
    """Takım logosunun adresi (boyut: 'xsmall' ya da 'small'); id geçersizse ''."""
    tid = sayi_kimlik(tid)
    return f'{KOK}/teamlogo/{tid}_{boyut}.png' if tid else ''


def lig_logo_url(lid):
    """Lig/turnuva logosunun adresi; id geçersizse ''."""
    lid = sayi_kimlik(lid)
    return LIG_LOGO.format(lid) if lid else ''


def logo_html(url, sinif='logo', stil='', bos=''):
    """Arka plan resmi olarak logo (indirilemezse kırık resim simgesi yerine boş kalır); url yoksa bos döner."""
    return f'<span class="{sinif}" style="{stil}background-image:url({url})"></span>' if url else bos
