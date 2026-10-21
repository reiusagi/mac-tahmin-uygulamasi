"""Arayüzden bağımsız küçük biçimleyiciler (komut satırı ve NiceGUI arayüzü ortak kullanır)."""
import re

from .modeller import js_round


def fmt(x, d=2):
    if x is None:
        return '–'
    s = f'{x:.{d}f}'
    if s.lstrip('-').strip('0.') == '':  # "-0,00" yazılmasın
        s = s.lstrip('-')
    return s.replace('.', ',')


def yuzde(p):
    return f'%{js_round(p * 100)}'


def para(x, bos=None, yalniz_m=False):
    """Piyasa değeri: 1 M€ ve üstü '12,5 M€', altı '800 B€'. bos verilirse 0/None için o metin döner;
    yalniz_m=True ise her değer M€ ile yazılır (dar sütun)."""
    if bos is not None and not x:
        return bos
    return f'{fmt(x / 1e6, 1)} M€' if yalniz_m or x >= 1e6 else f'{round(x / 1e3)} B€'


def sayi_kimlik(x):
    """Dış veriden gelen kimlik HTML özniteliğine ya da adrese girmeden önce: yalnızca ASCII rakamlardan oluşuyorsa
    metni, değilse ''."""
    s = str(x)
    return s if not isinstance(x, (bool, float)) and re.fullmatch(r'[0-9]{1,18}', s) else ''
