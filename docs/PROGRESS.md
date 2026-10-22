# İlerleme günlüğü

## 2026-10-22 — Kurulum ve başlangıç incelemesi

Kullanıcının talimatı: M0–M10 boyunca milestone sonunda onay beklemeden devam
et; her milestone'u doğrula, commit et ve push et. GitHub girişi kullanıcıya ait.

Okunan kaynaklar: `AGENTS.md`, `docs/tecnic.md`, `docs/VERIFICATION.md` ve
repo dışındaki özel hazırlık prompt'u. Gerçek CSV'ler yalnızca `head -n 6` ile
incelendi; değiştirilmedi ve herhangi bir dış servise gönderilmedi.

### Mimari anlayışı

1. Senkronizasyon birimi tenant ve kredi tipidir; kredi ve plan birlikte yayınlanır.
2. Banka simülasyonu ayrı FastAPI servisi ve SQLite depolamasıdır.
3. Ham değerler bankada korunur; normalizasyon Rust motorunda yapılır.
4. Python çekirdeği framework bağımsız domain, application ve infrastructure katmanlarından oluşur.
5. Django kimlik doğrular; tenant kimlikten türetilir.
6. DWH PostgreSQL'dir; okuyucu rolü RLS ile tenant ve güncel batch'e sınırlandırılır.
7. COPY ile görünmez batch yüklenir; doğrulama sonrası snapshot pointer atomik çevrilir.
8. ERROR yayını reddeder; WARNING ve CORRECTED raporlanır.
9. Celery işleme, beat metadata polling yapar; büyük dosyalar akış halinde işlenir.
10. Kabul ölçütleri container testleri, gerçek bellek ölçümü ve temiz klon denemesidir.

### Uygulama öncesi dikkat noktaları

- §9.4 deterministik hash ister: Python'ın süreçten sürece değişen `hash()`
  fonksiyonu yerine sabit algoritma seçilmeli ve dokümana açıklanmalıdır.
- §15 benchmark ID soneki, §7 örnek altı basamaklı ID pattern'i ile çelişir;
  M3 öncesinde veri sözleşmesi netleştirilmelidir.
- V-15 kredi ve planın birlikte okunmasını gerektirir. Ayrı READ COMMITTED
  sorguları yayın anında farklı snapshot görebilir; tutarlı okuma transaction'ı gerekir.
- V-18 kesin kategorik sayım ile §15 kategori limiti yüksek kardinalitede
  farklı davranış gerektirir; limit aşımı açık biçimde raporlanmalıdır.
- V-02 JWT kısmı MUST kapsamındadır; API key kısmı M11'e aittir.

### M0 planı ve mevcut durum

1. Docker Desktop ve GitHub CLI kur; daemon ve GitHub kimliğini doğrula.
2. Git main, veri/secret koruması ve katman iskeletini oluştur.
3. Container kalite ortamını, sabit bağımlılıkları, Makefile ve compose'u kur.
4. Pre-commit ve CI'ı kur; lint ve testleri çalıştır.
5. Public repoyu oluştur, küçük commit'leri push et ve CI'ı doğrula.

Başlangıçta Docker ve gh yoktu; Git deposu henüz oluşturulmamıştı.
Codex mevcut masaüstü oturumunda çalışıyor; Git ve make mevcut.
Kurulum başlatıldı. M0 tamamlanmadı; M1–M10 yapılmadı.
Henüz geçen V-ID, CI sonucu veya verification raporu yok.

### Kurulum engelleri

- `gh` 2.103.0 kuruldu. `gh auth status` oturum olmadığını doğruladı.
  Kullanıcının talimatı uyarınca `gh auth login` kullanıcıya iletildi.
  Sonraki kontrolde giriş başarıyla doğrulandı: aktif hesap `levend18`,
  Git protokolü HTTPS; repo ve workflow yetkileri mevcut. GitHub giriş
  engeli çözüldü.
- `brew install --cask docker`, önceden kayıtlı 4.75.0 cask'ını 4.96.2'ye
  yükseltmeye çalıştı. `/Applications/Docker.app` başlangıçta mevcut değildi.
  Eski ayrıcalıklı yardımcı dosyalarını temizleme aşaması yönetici parolası
  istedi; etkileşimsiz `sudo` hata kodu 1 ile sonlandı. Docker kurulumu
  tamamlanmadı; daemon başlatılamadı ve container testleri çalıştırılamadı.
- Kullanıcı kendi terminalinde Docker kurulumunu ve GitHub girişini
  tamamladığında M0 planından devam edilecek. Parola veya token istenmedi.
  GitHub girişi sonrasındaki kontrolde Docker komutu ve
  `/Applications/Docker.app` hâlâ bulunamadı; Docker engeli devam ediyor.

### Docker kurulumu — disk alanı engeli

Kullanıcının bildirdiği `hdiutil: Resource busy` hatasından sonra aktif
kurulum süreçleri ve bağlı imajlar kontrol edildi. Docker DMG'si doğrudan
başarıyla bağlandı; Homebrew'un eski cask yardımcılarını kaldırırken
sudo istemesinden bağımsız olarak uygulama kopyalama yolu denendi.
`ditto /Volumes/Docker/Docker.app /Applications/Docker.app` işlemi
`No space left on device` ile başarısız oldu. Bu sırada boş alan 575 MiB,
eksik uygulama 1.5 GiB, kaynak uygulama 2.2 GiB idi.
Yalnızca bu denemede oluşturulan eksik uygulama kaldırıldı ve Docker
imajı ayrıldı; kullanıcının diğer dosyaları silinmedi. Container image,
build cache ve PostgreSQL verileri için de disk alanı gerektiğinden
Docker ve M0 doğrulaması disk alanı açılana kadar engelli.

## M0 — Container iskeleti ve yerel doğrulama

Disk temizliği kullanıcı talimatıyla tamamlandı. Docker Desktop 4.96.2 kuruldu;
Docker Engine 29.9.2 ve Compose v5.6.1 yanıt veriyor. PostgreSQL 16.10 ve Redis
7.4.6 healthcheck'leri geçti. Python 3.12.12 / uv 0.9.5 container'ı oluşturuldu;
71 bağımlılık lock dosyasında sabitlendi.

`make lint`: ruff, format, strict mypy ve dört import kontratı geçti.
`make test`: veri koruması için iki unit testi geçti. Pre-commit tüm staged
kaynaklarda geçti. Git hook container içinden çalışır; host Python bağımlılığı
oluşturmaz. M0 aşamasında Rust/Node kodu yok; ilgili kalite kontrolleri M3/M8'de
CI'a eklenecek. Seed, verify ve bench hedeflerinin işlevleri henüz yapılmadı.

ADR-10 revizyonu: import-linter tek kök paket ayarı düzeltildi; framework
importlarının gerçekten denetlenmesi için harici paket taraması açıldı.
Public repo oluşturma ve CI kontrolü sıradaki adımdır; M0 henüz CI ile
kanıtlanmadı. M1–M10 yapılmadı.

Public repo oluşturuldu: https://github.com/levend18/ledgerbridge-loan-adapter.
İlk CI, container ile runner dosya sahipliği farkından dolayı pre-commit'in
Git deposunu okuyamaması nedeniyle kırıldı. Yalnızca container içindeki `/app`
çalışma dizini Git safe.directory olarak tanımlandı; host ayarları değiştirilmedi.

İkinci CI'da pre-commit ve lint geçti; boş integration klasörü Git'te
izlenmediğinden `make test` temiz klonda bulunamayan dizin hatası verdi.
Integration ve verification dizinleri `.gitkeep` ile iskelete eklendi.
Test kapsamı veya assert'ler değiştirilmedi.

M0 tamamlandı: `f931f6b` için CI 39757749673 PASS. Gerçek pre-commit hook'u
stage edilmiş sentetik `.guard-probe.csv` dosyasını reddetti; probe index'ten
ve diskten temizlendi. Hiçbir gerçek CSV izlenmiyor. M1 başlatıldı.

## M1 — PostgreSQL izolasyonu ve atomik yayın

Django RunSQL migration'ı ile ref/ops/dwh şemaları, üç tenant, üç fact parent,
dokuz statik partition, current_snapshot ve security_invoker ortak view kuruldu.
Reader salt SELECT ve tenant+snapshot RLS ile sınırlı; partition'lara doğrudan
SELECT yok. Writer BYPASSRLS fakat superuser değil. Django rolü yalnızca public
şemasına yetkili. Servis parolaları env üzerinden parametreli bootstrap ile gelir.

`make lint` PASS, `make test` 5 PASS. V-05 ve V-15'in SQL kısmı 2 PASS:
10 adet 1000/2000 yayın değişiminde eşzamanlı okuma, transaction rollback,
GC idempotency ve diğer tenant'ın korunması kanıtlandı. Ölçülen SQL okuma
p99 4.391 ms (yerel arm64 Docker; API gecikmesi değildir).

ADR-03/04 revizyonları: kaynak kolon adı loan_status_code korunur; çok sorgulu
okumalar READ ONLY REPEATABLE READ transaction kullanır. API kapsamındaki
V-15 henüz yapılmadı. M1 CI kontrolü bekleniyor; M2–M10 yapılmadı.

M1 tamamlandı: `3c52209` için CI 39758465166 PASS. M2 başlatıldı.

## M2 — Domain, port'lar ve use case'ler

Tenant/loan/dataset/severity değerleri, finite Decimal Money/Rate, sınırlı detaylı
validation raporu, SyncRun geçişleri ve severity politikası eklendi. Her modülün
port'u kendi domain'inde; orkestrasyon dış bağımlılıklara yalnızca Protocol ile
bağlanır. Poll değişmeyen sürüme run açmaz; tek bir bankanın ağ hatası diğer
birimlerin kontrolünü kesmez. Aynı sürümde manuel sync SKIPPED olur; force işler.

`make lint` PASS; `make test` 20 PASS. Fake'lerle hata/uyarı/schema, lock, force,
rollback, GC, state machine ve Decimal kontrolleri geçti. Domain/application
unit testleri DB kullanmaz. ADR-10 ortak saf DTO'ları açıklar; ADR-04 terminal
başarıyı GC sonrasına taşır (V-07 fiziksel satır garantisi). GC sonrası teknik
hata yayındaki batch'i silmez. Retry ağ sınıfları tipli; Celery bağlaması M5'tedir.
M2 CI bekleniyor; M3–M10 yapılmadı.

M2 tamamlandı: `a18fc35` için CI 39759264049 PASS. M3 başlatıldı.

## M3 — Rust normalizasyon, doğrulama ve profil motoru

Sabit Rust 1.90.0/PyO3 bağımlılıkları, YAML kolon sözleşmeleri, COPY yazıcısı,
Decimal normalizasyonu, satır kuralları ve Welford profilleri eklendi. İlk 10.000
satır birim/biçim tespiti için sınırlı buffer'da; devamı streaming. Kategoriler
1000 farklı değerde sınırlandırılır, yüksek kardinalite açıkça işaretlenir.
Issue detayları 1000 ile sınırlı; sayaçlar tüm satırları kapsar.
Boş CSV dahil header kontrolü, kolon kanıtıyla belirsiz sayı çözümü ve ham→kanonik
kanıtlar test edildi. V-11 default_probability örneği gerçek sözleşmeyle uyumlu
olarak commercial'a düzeltildi; gerçek veriler test girdisi yapılmadı.

`make lint` PASS (clippy dahil), Rust 3 test PASS (iki proptest), Python 57 PASS.
Motor V-11 parametreleri + V-05/V-15 SQL: 17 PASS. Banka/API/uçtan uca V-ID'ler
henüz tamamlanmadı. M3 CI bekleniyor; M4–M10 yapılmadı.

M3 tamamlandı: `a3f18a8` için CI 39761271388 PASS. M4 başlatıldı.

## M4 — Banka simülasyonu ve seed

FastAPI/SQLite WAL servisi: transaction'lı PUT replace/PATCH upsert, birim sürümü,
SHA-256/satır sayısı meta, NDJSON chunked stream ve cursor sayfalaması. Tenant
bank key'den çözülür; ham stringler korunur. Bozuk CSV transaction'ı geri alır.
PUT duplicate'leri korur (adaptörün V-10 kontrolü için). ADR-07 açıklandı.
Sentetik üretici, SQLite eşlemeli deterministik seed, güncelleme için v2 parçaları
ve field/schema/normalize/cross kirletme profilleri eklendi. Seed'in demo kullanıcı
ve sync adımı M6 bağlamasıyla tamamlanacak; henüz uçtan uca seed değildir.

`make lint` PASS; Rust 3 ve Python 61 PASS; mevcut verification 18 PASS.
V-20/V-21: ham değerler, version, digest, sayfalama ve tenant kontrolü geçti;
gerçek HTTP üzerinden chunked indirme ayrıca doğrulandı. Sentetik seed altı birime
başarıyla yüklendi. M4 CI bekleniyor; M5–M10 yapılmadı.

M4 tamamlandı: `d4708f5` için CI 39762096258 PASS. M5 başlatıldı.

## M5 — Gerçek adaptörler ve Celery

HTTP indirme digest/satır sayısı ve sürüm kontrolü, Rust bağlaması, COPY yükleme,
SQL duplicate/orphan/plan sayısı doğrulamaları, atomik profil+snapshot yayını,
GC, kalıcı run/issue kayıtları ve Celery polling/retry eklendi. Reader RLS,
writer ve Django yetkileri ayrıdır. Run süresi, GC süresi ve peak RSS kaydedilir.

`make lint` PASS; Rust 3 ve Python 70 PASS. Mevcut verification 25 PASS;
canlı worker/beat testi 1 PASS (otomatik yayın ve değişmeyen sürümde yeni run yok).
1000→2000 replace, rejected batch'in eski snapshot/profili koruması, duplicate,
orphan, schema, indirme bütünlüğü ve 40 update + 10 insert PATCH doğrulandı.
Tekrarlı test bankanın iterator thread değişiminde SQLite hatasını yakaladı;
istek başına bağlantı yaşam döngüsü ve 64KB stream ile düzeltildi, regresyon testi
geçti. API/UI/200MB ve temiz klon kapsamı henüz yapılmadı. M5 CI bekleniyor.

M5 ve yerel talimat dosyalarının Git'ten çıkarılması: temizlenmiş geçmişte
`30b35d1` için CI 39764118393 PASS. Önceki commit SHA'ları geçmiş temizliğiyle
 değişti. M6 başlatıldı.

## M6 — JWT ve REST API

JWT tenant/sub/role claim'leri hesap üyeliğinden üretilir. Veri, run, issue ve
sync uçları kimlik doğrular; parametre tenant'ı sadece eşleşme kontrolüdür.
DWH reader transaction'ları READ ONLY REPEATABLE READ; cursor snapshot'a bağlıdır.
API writer parolası almaz; Django rolüne tenant policy'li run INSERT ve yalnızca
kuyruk hatasını FAILED yapacak dar UPDATE yetkisi verildi. RFC 9457 hata içerikleri,
OpenAPI/Swagger ve seed demo kullanıcıları eklendi.

Lint PASS; Python 78 PASS, mevcut verification 31 PASS. V-01 tüm route taraması,
V-02 JWT, V-03/04/06 tenant/type/pagination, sync 202/409 ve 10 yayın sırasında
API okuma tutarlılığı geçti. Gerçek HTTP: token/health/schema 200, anonim veri 401.
`make seed` gerçek kaynakları değiştirmeden işledi: 25.430 retail, 4.440 commercial
kredi ve 269.442/25.070 plan; altı SEED run SUCCEEDED. Son ortamın temiz klon ve
izole uçtan uca doğrulaması M10'da ayrıca yapılacak. M6 CI bekleniyor.
