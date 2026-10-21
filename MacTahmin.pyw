"""Masaüstü uygulamasının başlangıç dosyası (çift tıklayınca konsolsuz açılır; PyInstaller da bunu paketler)."""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()  # pencere ayrı bir süreçte açılır; paketlenmiş uygulamada gerekli
    from mac_tahmin.masaustu import main
    main()
