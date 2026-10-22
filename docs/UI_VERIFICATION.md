# M8 — Arayüz kabul kaydı

22 Ekim 2026, yerel Docker/arm64 ortamında uygulama tarayıcı üzerinden kontrol
edildi. Yalnızca `tools.make_dirty` ile oluşturulan altı satırlık sentetik veriler
kullanıldı. Bu kayıt V-22'nin manuel MUST kapsamıdır; otomatik Playwright testi
uygulandı anlamına gelmez.

- `bank001_user` ile giriş başarılı: [giriş](screenshots/login.jpg).
- Banka portalından kredi ve plan CSV dosyaları yüklendi; kaynak sürümü ve iki
  dataset'in altı satırlık sayıları görüldü: [yükleme](screenshots/bank-upload.jpg).
- Manuel sync SUCCEEDED oldu; yayın sürümü 480, kredi/plan sayıları 6/6 idi:
  [senkronizasyon ekranı](screenshots/sync.jpg) ilk demo yüklemesini gösterir.
- Data ekranında altı kredi, `1234.56`, `0.18500000`, ISO tarih ve boolean değerler
  görüldü: [veri](screenshots/data.jpg).
- Profil ekranında null oranları, min/max/ortalama/standart sapma ve kategori
  dağılım grafikleri görüldü: [profil](screenshots/profiles.jpg).
- Field hatalı CSV yüklendi (kaynak 481); manuel sync REJECTED oldu. Hata
  ekranında REQUIRED, INVALID_NUMBER, OUT_OF_RANGE, UNKNOWN_CODE ve
  MATURITY_AFTER_START kuralları, ham değerler ve ERROR filtresi kontrol edildi:
  [reddetme](screenshots/validation-rejected.jpg).
- Reddetmeden sonra Data hâlâ sürüm 480 ve altı kredi gösterdi.
- Bu akış boyunca çalışma alanı BANK001 idi; ekranlarda BANK002 verisi yoktu.
  API ve RLS izolasyonunun otomatik kanıtları V-03/V-04/V-05 testlerindedir.
- Tarayıcı konsolunda error kaydı yoktu. Süresi dolan JWT ile API hata gösterdi;
  çıkış ve yeniden giriş sonrasında akış devam etti.

Ekran görüntüleri aşamalar arasında alınmıştır; sayaçlar o aşamadaki sentetik
veriye aittir. `make test` ve `make verify` demo verisini değiştirir; sonrasında
`make seed` ile başlangıç portföyü yeniden yüklenebilir.
