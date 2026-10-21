"""Maç Tahmin Laboratuvarı'nın Python sürümü: veri indirme, modeller, tahmin ve oyuncu kartları."""
import os

# numpy'nin matematik kütüphanesi (OpenBLAS) açılışta her işlemci çekirdeği için bellek ayırır (32 çekirdekte ~750 MB).
# Uygulama numpy'yi yalnızca simülasyonda, çok iş parçacığına ihtiyaç duymayan işlemler için kullanır.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')

from .sezon import LIGLER, Sezon, ham_oku, kariyer  # noqa: E402

__all__ = ['LIGLER', 'Sezon', 'ham_oku', 'kariyer']
