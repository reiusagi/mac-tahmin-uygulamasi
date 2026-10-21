"""Sunucu erişimi: uygulamanın parolası yoktur, bu yüzden varsayılan olarak yalnızca bu bilgisayardan (127.0.0.1) açılır.
Başka bir adreste (--host) açılırsa uyarı yazılır; MAC_TAHMIN_ANAHTAR ortam değişkeni verilirse ağdan gelen her istek
bu anahtarı ister (adresin sonuna ?anahtar=... eklenir, tarayıcıya çerez olarak bırakılır; betikler için
"Authorization: Bearer <anahtar>" başlığı da olur). Şifreli bağlantı (https) yoktur: anahtar ve veriler ağda düz metin
gider, yalnızca güvendiğin bir ağda kullan. Yerel adreste (varsayılan) Host başlığı denetlenir: kötü niyetli bir sitenin
alan adını 127.0.0.1'e çevirmesiyle (DNS yeniden bağlama) uygulamaya erişmesi engellenir."""
import hmac
import ipaddress
import logging
import re
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, quote, urlencode

ANAHTAR_ORTAM = 'MAC_TAHMIN_ANAHTAR'
CEREZ = 'mac_tahmin_anahtar'
SORGU = 'anahtar'
YEREL_ADLAR = ('localhost', '127.0.0.1', '[::1]')  # yerel kipte kabul edilen Host adları (her portla)


def loopback_mi(host):
    """Adres yalnızca bu bilgisayardan erişilebilir mi (127.0.0.0/8, ::1, localhost)."""
    h = (host or '').strip().lower().strip('[]')
    if h == 'localhost':
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def adres_uyarisi(host, anahtar_var):
    """Dışa açık bir adreste yazılacak uyarı; yerel adreste ''."""
    if loopback_mi(host):
        return ''
    uyari = (f'UYARI: Uygulama {host or "bütün ağ kartları"} adresinde açılıyor. Uygulamanın parolası yoktur: aynı '
             f'ağdaki herkes ona erişebilir ve bağlantı şifreli değildir. Yalnızca güvendiğin bir ağda kullan.')
    if anahtar_var:
        return uyari + '\nErişim anahtarı etkin: adresin sonuna ?anahtar=<anahtar> ekleyerek ilk kez gir.'
    return uyari + f'\nİstersen {ANAHTAR_ORTAM} ortam değişkeniyle bir erişim anahtarı belirleyebilirsin.'


class AnahtarMaskeleme(logging.Filter):
    """Günlük kaydındaki ?anahtar=<değer> (erişim anahtarı) değerini *** yapar; adres satırı günlüğe düşse de sızmaz."""
    _DESEN = re.compile(r'([?&;]' + SORGU + r'=)[^&\s"\']*', re.I)

    def _gizle(self, deger):
        return self._DESEN.sub(r'\1***', deger) if isinstance(deger, str) else deger

    def filter(self, record):
        record.msg = self._gizle(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._gizle(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._gizle(a) for k, a in record.args.items()}
        return True


def gunlukte_anahtari_gizle():
    """uvicorn erişim günlüğüne ve kök günlüğe anahtar maskelemesini ekler (aynı süzgeç iki kez eklenmez)."""
    for ad in ('uvicorn.access', 'uvicorn.error', 'uvicorn', 'nicegui'):
        g = logging.getLogger(ad)
        if not any(isinstance(f, AnahtarMaskeleme) for f in g.filters):
            g.addFilter(AnahtarMaskeleme())


class YerelHostKorumasi:
    """ASGI ara katmanı (yalnızca yerel adreste): Host başlığı localhost / 127.0.0.1 / [::1] değilse (DNS yeniden
    bağlama) istek reddedilir (http 403, websocket 1008)."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _yerel_mi(host):
        host = host.strip().lower()
        if host.startswith('['):  # [::1]:8080
            ad, _, port = host.partition(']')
            ad, port = ad + ']', port.removeprefix(':') if port[:1] in (':', '') else None
        else:
            ad, _, port = host.partition(':')
        return ad in YEREL_ADLAR and port is not None and (not port or (port.isascii() and port.isdigit()))

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        host = next((d.decode('latin-1') for ad, d in scope.get('headers') or [] if ad == b'host'), '')
        if self._yerel_mi(host):
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        govde = 'Bu adresle erişilemez; localhost ya da 127.0.0.1 kullan.'.encode('utf-8')
        await send({'type': 'http.response.start', 'status': 403, 'headers': [
            (b'content-type', b'text/plain; charset=utf-8'), (b'content-length', str(len(govde)).encode())]})
        await send({'type': 'http.response.body', 'body': govde})


class AnahtarKorumasi:
    """ASGI ara katmanı: istek ya doğru anahtarı çerezde / sorguda taşır ya da reddedilir (http 401, websocket 1008)."""

    def __init__(self, app, anahtar):
        if not anahtar or not re.fullmatch(r'[A-Za-z0-9._~+/=-]+', str(anahtar)):  # çerezde olduğu gibi taşınabilsin
            raise ValueError('erişim anahtarı boş olamaz; yalnızca harf, rakam ve ._~+/=- içerebilir')
        self.app, self.anahtar = app, str(anahtar)

    def _dogru(self, deger):
        return bool(deger) and hmac.compare_digest(str(deger).encode(), self.anahtar.encode())

    def _cerezden(self, scope):
        for ad, deger in scope.get('headers') or []:
            if ad == b'cookie':
                c = SimpleCookie()
                try:
                    c.load(deger.decode('latin-1'))
                except Exception:  # bozuk çerez başlığı: anahtarsız sayılır
                    return None
                return c[CEREZ].value if CEREZ in c else None
        return None

    def _bearer(self, scope):
        for ad, deger in scope.get('headers') or []:
            if ad == b'authorization':
                tur, _, anahtar = deger.decode('latin-1').strip().partition(' ')
                return anahtar.strip() if tur.lower() == 'bearer' else None
        return None

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket') or self._dogru(self._cerezden(scope)) \
                or self._dogru(self._bearer(scope)):
            return await self.app(scope, receive, send)
        sorgu = parse_qsl(scope.get('query_string', b'').decode('latin-1'), keep_blank_values=True)
        if scope['type'] == 'http' and self._dogru(dict(sorgu).get(SORGU)):
            kalan = urlencode([(k, v) for k, v in sorgu if k != SORGU])  # anahtar adres çubuğunda kalmasın
            yol = '/' + quote((scope.get('path') or '/').lstrip('/'), safe='/')  # satır sonu ve "//site" kaçamağı olmasın
            await send({'type': 'http.response.start', 'status': 303, 'headers': [
                (b'location', (yol + ('?' + kalan if kalan else '')).encode('latin-1', 'replace')),
                (b'set-cookie', f'{CEREZ}={self.anahtar}; Path=/; HttpOnly; SameSite=Strict'.encode('latin-1', 'replace')),
                (b'content-length', b'0')]})
            return await send({'type': 'http.response.body', 'body': b''})
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        govde = 'Erişim anahtarı gerekli. Adresin sonuna ?anahtar=<anahtar> ekle.'.encode('utf-8')
        await send({'type': 'http.response.start', 'status': 401, 'headers': [
            (b'content-type', b'text/plain; charset=utf-8'), (b'content-length', str(len(govde)).encode())]})
        await send({'type': 'http.response.body', 'body': govde})
