# ledgerbridge – Finansal Veri Entegrasyon Adaptörü · Teknik Tasarım

> Bu doküman sistemin **nasıl** kurulduğunu ve **neden** böyle kurulduğunu anlatır.
> - Önemli kararlar **ADR** olarak numaralıdır (seçilen yol · alternatifler · gerekçe).
> - Gereksinimler **R-ID**, doğrulama senaryoları **V-ID** taşır (`docs/VERIFICATION.md`).
> - Kapsam **MUST / SHOULD / COULD** olarak önceliklendirilmiştir (§0).

**İçindekiler:** §0 kapsam · §1–3 problem, izlenebilirlik, veri · §4–5 mimari · §6 ADR'ler · §7–16 bileşenler · §17–20 API, güvenlik, frontend, config · §21–25 test, repo, çalıştırma, trade-off'lar, açık sorular · §26 milestone'lar

---

## 0. Kapsam ve önceliklendirme

Prensip: **önce bütün gereksinimler sağlam ve uçtan uca çalışır, sonra derinlik.** Yarım kalmış "ileri" bir özellik, eksiksiz bir temel özellikten değersizdir.

| Seviye | Kapsam |
|---|---|
| **MUST** | Görevdeki tüm gereksinimler (R1–R13); 4 görev senaryosu; tenant izolasyonu (API + RLS); atomik replace; validation + normalization; 200MB bellek ölçümü; profiling dashboard; JWT; `docker compose` ile tek komut kurulum; README + Architecture.md; CI |
| **SHOULD** | API key auth; eşzamanlı sync koruması için 409; çöken worker için reaper; fault-injection manifest testi; Playwright UI smoke testi; rate limit |
| **COULD** | İç analist rolü (çapraz tenant okuma) + audit log; snapshot arşivi; yaklaşık yüzdelikler (p50/p95); webhook ile tetikleme |

Bir SHOULD işine ancak tüm MUST V-ID'leri yeşilken başlanır.

---

## 1. Problem ve kapsam

Bir dış sistemden (banka) **tenant × kredi tipi** bazında gelen büyük ve kirli kredi portföy verisini **periyodik olarak** çekip **doğrulayan, normalize eden**, Data Warehouse'ta **atomik olarak eskisinin yerine koyan** ve bunu **tenant izolasyonu bozulmadan** REST API + web arayüzü ile sunan bir entegrasyon adaptörü.

**Senkronizasyon birimi:** `(tenant_id, loan_type)`. Bir birim iki dataset'ten oluşur: `credit` + `payment_plan`. İkisi **birlikte** doğrulanır ve **birlikte** yayınlanır (cross-file tutarlılık).

**Zorunlu stack:** Django, Python, Rust, PostgreSQL, Data Warehouse.

---

## 2. Gereksinim izlenebilirlik matrisi

| R-ID | Gereksinim | Tasarım | Kanıt |
|---|---|---|---|
| R1 | Banka simülasyonu: upload, update, JSON endpoint, basit storage | §8, ADR-07 | V-20, V-21 |
| R2 | 3 tenant, izolasyon | §9, ADR-03 | V-03, V-04, V-05 |
| R3 | RETAIL + COMMERCIAL ayrı | §7, §13 | V-06 |
| R4 | Validation: field-level + cross-file | §11 | V-09, V-10 |
| R5 | Normalization: tarih, oran, kategori, hatalı veri | §12 | V-11 |
| R6 | En güncel veri, replace, atomik, fail → eski korunur | §13–14, ADR-04 | V-07, V-08, V-15 |
| R7 | 200MB, memory efficient | §15, ADR-01 | V-17 |
| R8 | Frontend: upload, sync, görselleştirme, validation hataları | §19 | V-22 |
| R9 | JWT/API key, her request auth, API'de tenant izolasyonu | §18 | V-01, V-02, V-04 |
| R10 | Profiling + dashboard | §16 | V-18 |
| R11 | `/api/sync`, `/api/data`, `/api/profiling` | §17 | V-06, V-18 |
| R12 | Periyodik kontrol, gelince otomatik sync | §10, ADR-05 | V-12, V-13, V-14 |
| R13 | README + Architecture.md | §23 | V-23 |

---

## 3. Veri analizi

### 3.1 Dosyalar

| Dosya | Satır | Boyut | Kolon |
|---|---|---|---|
| `retail_credit_masked.csv` | 25.430 | 3.7 MB | 27 |
| `retail_payment_plan_masked.csv` | 269.442 | 21 MB | 14 |
| `commercial_credit_masked.csv` | 4.440 | 608 KB | 32 (retail'den farklı şema) |
| `commercial_payment_plan_masked.csv` | 25.070 | 1.8 MB | 14 (retail plan ile aynı) |

Ayraç `;`, UTF-8, ondalık `.`, header var.

### 3.2 Bulgular → tasarım etkisi

| Bulgu | Etki |
|---|---|
| Tarih formatı aynı dosyada karışık (`actual_payment_date=20250208`, `scheduled_payment_date=2025-02-08`) | Normalizer gerçek bir ihtiyaç (§12.1) |
| Retail `nominal_interest_rate` 44.21–100.00, medyan 52.89 → yüzde | Kolon birimi (§12.2) |
| Retail'de 127 satırda faiz tam `100.00` (diğerleri 44–56) | Makullük aralığı dışı → WARNING, veri uydurulmaz |
| Commercial `nominal_interest_rate` 0–8.03, medyan 1.85 | Retail'den ~28× düşük → muhtemelen **aylık** oran. Birim dataset bazında tanımlanır; açık soru (§25) |
| Commercial `kkdf_rate`: 3.691 satır `0` | Birim tespitinde sıfırlar yok sayılır |
| `default_probability` 0.0093–0.7997 | Zaten fraction |
| Kodlar: `installment_status∈{A,K}`, `insurance_included∈{E,H}`, `customer_type∈{I,T,V}` | Kod sözlüğü (§12.3) |
| Orphan payment 0, retail/commercial ID çakışması 0 | Cross-file kontrolleri negatif testle (fault injection) kanıtlanır |
| `paid + outstanding ≠ total_installment_count`: retail %64, commercial 2.468 | ERROR olamaz (verinin çoğunu reddederdi) → WARNING (ADR-09) |
| `outstanding > original_loan_amount`: retail 1.447, commercial 1.555 | WARNING |
| Plan satır sayısı ≠ `total_installment_count`: retail 14.181 | WARNING |
| Commercial'da `total_installment_count = 0` | WARNING |
| `loan_closing_date` tamamen boş, `grace_period_months` hep 0 | Nullable; profiling'de beklenen |
| Veride tenant kolonu yok | Seed deterministik böler (§9.4) |

**Gerekçe:** Kurallar veriyi profilledikten sonra yazıldı. `paid+outstanding=total` ERROR olsaydı gerçek verinin %64'ü reddedilirdi; bu yüzden kurallar severity seviyeli.

---

## 4. Sistem görünümü (deployment)

```
                ┌────────────────────────────────────────────┐
                │ Frontend (React + Vite + TS)               │
                │  ├─ Bank Portal (simülasyon): CSV yükle    │
                │  └─ Platform: sync, data, profiling, issues│
                └──────┬───────────────────────┬─────────────┘
              JWT      │                       │ X-Bank-Key (bankanın kendi portalı)
                       ▼                       ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ api  (Django + DRF)          │   │ bank (FastAPI) — DIŞ SİSTEM  │
│ /api/sync /api/data          │   │ PUT / PATCH dataset          │
│ /api/profiling /api/runs     │   │ GET meta (version, sha256)   │
└──────┬───────────────────────┘   │ GET records (NDJSON stream)  │
       │ enqueue                   │ SQLite (ham değerler)        │
       ▼                           └──────────────▲───────────────┘
┌──────────────┐                                  │ HTTP, tenant başına key
│ redis        │                                  │
└──────┬───────┘                                  │
       ▼                                          │
┌─────────────────────────────────────────────────┴──┐
│ worker (Celery) + beat (poller)                    │
│  meta → download → Rust engine → COPY (yeni batch) │
│  → SQL cross-file → publish (pointer flip) → GC    │
└──────┬─────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────┐
│ postgres 16 — Data Warehouse                        │
│  ref · ops · dwh (tenant partition, RLS)            │
└─────────────────────────────────────────────────────┘
```

`docker compose up --wait` → `postgres`, `redis`, `bank`, `api`, `worker`, `beat`, `frontend`. Tümünün healthcheck'i var. **Değerlendiricinin makinesinde Docker + make dışında hiçbir şey gerekmez** (§23).

---

## 5. Kod mimarisi: modüler monolit + katmanlı mimari (ADR-10)

§4 deployment görünümüdür; §5 kodun iç organizasyonudur (hangi kod hangi koda bağımlı olabilir).

### 5.1 İki eksen

- **Yatay — katmanlar:** Presentation / Application / Domain / Infrastructure
- **Dikey — modüller:** `ingestion`, `quality`, `warehouse`, `profiling` (+ `shared`, `identity`)

```
                 ┌─────────────┬─────────────┬─────────────┬─────────────┐
                 │  ingestion  │   quality   │  warehouse  │  profiling  │
┌────────────────┼─────────────┼─────────────┼─────────────┼─────────────┤
│ Presentation   │ Celery task │      –      │ DRF view    │ DRF view    │  (api/)
│ Application    │ SyncUseCase │ ProcessDS   │ Query svc   │ Query svc   │
│ Domain         │ SyncRun     │ Rule,Policy │ Snapshot    │ ColumnStats │
│ Infrastructure │ HttpBankGw  │ RustEngine  │ PgWarehouse │ PgProfiles  │
└────────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

### 5.2 Katmanlar

| Katman | Sorumluluk | İçerir | İçeremez |
|---|---|---|---|
| Presentation | Girdi al, kimlik doğrula, çıktıyı biçimle | DRF view/serializer, middleware, Celery task giriş noktası | İş kuralı, SQL |
| Application | Use case orkestrasyonu, **transaction sınırı (UoW)** | `SyncDatasetUseCase`, `CheckForUpdatesUseCase`, `GetLoanDataQuery`, `GetProfileQuery`, DTO | `django`, `psycopg`, `httpx` |
| Domain | İş kavramları ve kuralları | `TenantId`, `LoanType`, `Money`, `Rate`, `SyncRun` state machine, `SeverityPolicy`, **port'lar** (`Protocol`) | I/O, framework |
| Infrastructure | Port implementasyonları | `HttpBankGateway`, `RustDatasetProcessor`, `PostgresWarehouseRepository`, `PgSyncRunRepository`, SQL | İş kararı |

**Bağımlılık kuralı:** `Presentation → Application → Domain ← Infrastructure` (DIP / Ports & Adapters). Bağlama tek yerde: **Composition Root** (`api/composition.py`).

### 5.3 Bir sync'in katmanlardan geçişi

```
POST /api/sync {tenant_id, loan_type}
 ├─ [Presentation] SyncView: JWT → TenantContext; tenant eşleşmesi; SyncRun PENDING; enqueue → 202
 ├─ [Presentation] celery task run_sync(run_id)          # sadece use case çağrısı
 ├─ [Application] SyncDatasetUseCase.execute(run_id)
 │     with unit_lock(tenant, loan_type):                 # aynı birimde tek sync
 │       meta = bank.get_meta(...)
 │       if meta.version == snapshots.current_version(...) and not force: run.skip(); return
 │       files  = bank.download(..., workdir)             # stream → disk
 │       report = processor.process(files, schema, out)   # Rust: parse/normalize/validate/profile
 │       batch  = warehouse.load(tenant, loan_type, report.outputs)   # COPY, yeni batch_id, görünmez
 │       report += warehouse.validate_cross_file(batch)   # SQL
 │       if policy.decide(report).rejected:
 │           warehouse.discard(batch); run.reject(report); return     # yayındaki veri aynen kalır
 │       with uow:                                         # TEK kısa transaction
 │           warehouse.publish(batch)                      # pointer flip
 │           profiles.save(batch, report.profile); run.succeed(report)
 │       warehouse.collect_garbage(tenant, loan_type)      # eski batch satırlarını sil
 ├─ [Domain] SyncRun, SeverityPolicy, ValidationReport — saf Python
 └─ [Infrastructure] HttpBankGateway / RustDatasetProcessor / PostgresWarehouseRepository
```

### 5.4 Modüller

| Modül | Sorumluluk | Public arayüz | Sahip olduğu tablolar |
|---|---|---|---|
| `shared` | `TenantId`, `LoanType`, `DatasetKind`, `Money`, `Rate`, hata tipleri | value object'ler | – |
| `ingestion` | Değişiklik tespiti, indirme, `SyncRun`, orkestrasyon | `SyncDatasetUseCase`, `CheckForUpdatesUseCase` | `ops.sync_run` |
| `quality` | Şema, kurallar, normalizer, kod sözlüğü, severity, Rust motoru | `DatasetProcessor`, `SeverityPolicy` | `ops.validation_issue*`, `ref.code_mapping` |
| `warehouse` | Yükleme, cross-file SQL, publish, GC, tenant-scoped okuma | `WarehouseRepository`, `LoanDataQuery` | `dwh.*` |
| `profiling` | İstatistik saklama/sunma | `ProfileRepository`, `GetProfileQuery` | `ops.data_profile` |
| `identity` (`api/`) | Kullanıcı, JWT, API key, `TenantContext` | `TenantContext` | Django auth tabloları |

Kurallar: modüller birbirinin iç paketine import yapmaz (sadece `__init__.py` export'ları); başka modülün tablolarına SQL atmaz; döngü yok (`ingestion → {quality, warehouse, profiling} → shared`).

### 5.5 Kuralların CI'da zorlanması (`import-linter`)

```ini
[importlinter]
root_package = adapter

[importlinter:contract:layers]
name = Her modülde katman sırası
type = layers
containers =
    adapter.ingestion
    adapter.quality
    adapter.warehouse
    adapter.profiling
layers =
    infrastructure
    application
    domain

[importlinter:contract:framework-free-core]
name = adapter paketi Django/DRF/Celery bilmez
type = forbidden
source_modules = adapter
forbidden_modules =
    django
    rest_framework
    celery

[importlinter:contract:pure-domain]
name = Domain I/O kütüphanesi bilmez
type = forbidden
source_modules =
    adapter.shared
    adapter.ingestion.domain
    adapter.quality.domain
    adapter.warehouse.domain
    adapter.profiling.domain
forbidden_modules =
    psycopg
    httpx
    adapter_engine

[importlinter:contract:module-independence]
name = Yardımcı modüller birbirini bilmez
type = independence
modules =
    adapter.quality
    adapter.warehouse
    adapter.profiling
```

Mimari kural, CI'da kırılan bir kontrattır; diyagramdaki bir niyet değil.

### 5.6 Rust motoru

```
adapter/quality/engine/            # crate; Python modülü: adapter_engine (maturin)
└── src/
    ├── domain/     # saf: normalize_date, normalize_rate, normalize_code, rules, Severity
    ├── schema/     # YAML şema tanımlarının tipli hali
    ├── pipeline/   # read → normalize → validate → profile → write (satır satır)
    ├── io/         # csv/ndjson reader, COPY-text writer, issue writer
    └── bindings/   # PyO3: sadece tip dönüşümü + py.allow_threads (GIL bırakılır)
```

Python'da Rust yalnızca `RustDatasetProcessor` (infrastructure) üzerinden görünür; domain `DatasetProcessor` portunu bilir; testte `FakeDatasetProcessor` kullanılır.

### 5.7 Prensipler

| Prensip | Karşılığı |
|---|---|
| SRP | Normalizer tek tip; view sadece HTTP; use case sadece orkestrasyon |
| OCP | Yeni tarih formatı / eşanlamlı kod / kural seçimi = YAML veya `ref.code_mapping` satırı |
| LSP | `FakeBankGateway` ≡ `HttpBankGateway` (aynı port) |
| ISP | Küçük port'lar: yazma (`WarehouseRepository`) ve okuma (`LoanDataQuery`) ayrı |
| DIP | Use case'ler `Protocol`'lere bağlı; bağlama Composition Root'ta |
| CQS / hafif CQRS | Yazma yolu domain'den geçer; okuma yolu optimize SQL query servisi |
| Unit of Work | Transaction sınırı application'da; repository'ler commit etmez |
| Tipli hatalar | `SchemaMismatch`, `ValidationRejected`, `BankUnavailable`, `DownloadIntegrityError` → retry hata tipine göre |
| Idempotency | `(tenant, loan_type, source_version)` zaten yayındaysa no-op |
| 12-Factor | Config env'den (§20) |
| Gözlemlenebilirlik | JSON yapılandırılmış log, her satırda `run_id`, `tenant_id`, `loan_type` |

### 5.8 Bilinçli olarak hafif tutulanlar

- **Bank simülasyonu:** basit 3 katman (routes / service / storage). Bizim domain'imiz değil.
- **Okuma tarafı** domain modelinden geçmez.
- **Django ORM** sadece `identity` için; DWH/ops `psycopg` ile (COPY ve RLS ORM'e uygun değil; `adapter` Django'dan bağımsız kalmalı).
- **Tek migration aracı:** Django migrations + `RunSQL`; SQL dosyaları sahibi modülün `infrastructure/sql/` klasöründe.
- **Şema YAML'ı** Rust motorunu besler; DDL elle yazılır ve bir test YAML kolonları ile DB kolonlarının eşleştiğini doğrular (kod üretici yazmak yerine).

---

## 6. Mimari kararlar (ADR)

### ADR-01 · Rust: PyO3 + maturin extension modülü

**Revizyon (M3):** V-11'deki default_probability örneği commercial olarak
düzeltildi; retail kaynak başlığında bu kolon yoktur. Kolonlar YAML
sözleşmesinde eksiksiz tanımlanır; kaynak kolon adı korunur.
| Seçenek | Artı | Eksi |
|---|---|---|
| ✅ PyO3 extension | Ağ/serileştirme yok, tek deploy, GIL bırakılır, Python'dan doğrudan test | maturin build adımı |
| Ayrı Rust servisi | Bağımsız ölçek | Veriyi ağdan bir kez daha taşımak, ek servis/auth/hata yönetimi |
| CLI + subprocess | Basit | Hata/ilerleme raporu stdout parse'a kalır |

Rust, sistemin CPU ve bellek bağımlı tek kısmında (parse/normalize/validate/profile) kullanılır. Port arkasında olduğu için ayrı servise taşımak yeni bir adapter yazmak demektir.
**pandas neden değil:** Varsayılanda dosyayı belleğe alır (bellek kullanımı dosya boyutunun birkaç katı), para için float kullanır. Rust: sabit bellek + `rust_decimal` + tip güvenliği.

### ADR-02 · Data Warehouse: PostgreSQL
| Kriter | PostgreSQL | ClickHouse / DuckDB |
|---|---|---|
| Çok tablolu atomik yayın | ✅ | ❌ / sınırlı |
| RLS | ✅ | kısmi |
| Bu ölçek (GB) | rahat | gereğinden güçlü |
| Zorunlu stack | ✅ | ek bileşen |

En kritik iki gereksinim (atomik replace + izolasyon) transactional garanti ister. Hacim TB'a çıkarsa `dwh` ELT ile kolon-bazlı motora replike edilir.

### ADR-03 · Multi-tenancy: paylaşılan tablo + `tenant_id` + RLS + statik tenant partition'ları

**Revizyon (M1):** PostgreSQL bootstrap kimliği `app_migrator` yalnızca
kurulum/migration için kullanılır; reader/writer/django rollerinin parolası env
üzerinden kurulur. Parent dışında partition SELECT yetkisi verilmez.
Kaynak sözleşmesiyle aynı kolon adı `loan_status_code` korunur.
Detay §9.

**Revizyon (M1, tutarlı okuma):** Kredi, plan, pointer ve profil için birden
fazla sorgu yapan okuma aynı READ ONLY REPEATABLE READ transaction
içinde yürütülür. Birbirinden bağımsız HTTP istekleri farklı yayınları
görebilir; V-15 eşleştirilmiş okuması tek transaction içindedir.

**Revizyon (M2, GC tamamlanması):** V-07'nin terminal run sonrası fiziksel
satır sayısı garantisi için publish transaction'ı pointer, profil ve run'ın
batch bilgisini PUBLISHING durumunda birlikte kaydeder. GC tamamlandıktan
sonra SUCCEEDED yazılır. GC teknik hata verirse run FAILED olabilir fakat
yayınlanmış batch geri silinmez; sonraki sync GC'yi tekrar çalıştırır.

### ADR-04 · Atomik replace: batch yükle → doğrula → **snapshot pointer'ını çevir** → eski batch'i temizle
| Seçenek | Sorun |
|---|---|
| `DELETE` + `INSERT` tek transaction | Ağır iş (2.5M satır) transaction içinde; uzun tutulan kilitler |
| `TRUNCATE` + `INSERT` | Tabloyu kilitler; tenant bazında yapılamaz |
| Partition swap (DETACH/ATTACH) | Parent'ta `ACCESS EXCLUSIVE` → tüm tenant'ların okumaları bekler; yayın yolunda DDL; her yeni partition'a yetki/RLS kurulumu, isim değiştirme koreografisi → çok sayıda hata noktası |
| ✅ **Snapshot pointer** | Ağır iş (COPY, doğrulama) transaction dışında ve görünmez; yayın = tek satır `UPDATE`; okuyucu kilitlenmez; RLS bir kez tanımlanır |

**Revizyon notu:** İlk tasarım partition swap'tı. Kilit kapsamı (tüm tenant'lar) ve operasyonel hata noktaları nedeniyle pointer yaklaşımına geçildi. Swap'ın tek avantajı (eski satırların silinmesi gerekmemesi) GC adımıyla karşılanır. Bloat sorun olursa evrim yolu: batch başına partition + `DETACH ... CONCURRENTLY` ile kilitsiz GC. Detay §14.

### ADR-05 · Değişiklik tespiti: metadata polling (version + sha256)
Görev "düzenli aralıklarla" diyor; dış sisteme webhook kurduramadığımızı varsayıyoruz. Tüm veriyi indirmek yerine ucuz `meta` çağrısı.

### ADR-06 · Asenkron iş: Celery + Redis
`POST /api/sync` → 202. Beat ile periyodik görev, retry/backoff hazır. Alternatif: Postgres tabanlı kuyruk (bir bileşen az); tanıdıklık ve olgunluk için Celery.

### ADR-07 · Banka simülasyonu: ayrı FastAPI servisi + SQLite
"Başka şirketin sistemi" → ayrı process, ayrı DB, ayrı auth; adapter bankaya yalnızca HTTP kontratıyla bağlı. Banka veriyi **ham haliyle** saklar; normalizasyon adapter'ın işidir.

### ADR-08 · Frontend: React + Vite + TypeScript
TanStack Query (polling), TanStack Table (sanal scroll), ECharts.

### ADR-09 · Severity politikası: ERROR / WARNING / CORRECTED
Gerçek verideki yaygın tutarsızlıklar (§3.2) ikili geçerli/geçersiz ayrımını yetersiz kılıyor. Detay §11.3.

### ADR-10 · Modüler monolit + katmanlı mimari, import-linter ile zorlanır

**Revizyon (M2):** Modül bağımsızlığı için Issue, ValidationReport ve ProcessReport
gibi modüller arasında taşınan saf veri nesneleri shared altında tutulur;
severity kararı quality domain'inde, sync durum makinesi ingestion domain'indedir. Hiçbir shared tip I/O yapmaz.

**Revizyon (M0):** Tek kök paket için import-linter 2.5.2 ayarı `root_package`
olarak düzeltildi; `root_packages` tek satırlık metni karakter listesi olarak
yorumluyordu. Harici framework bağımlılıklarını da taramak için
`include_external_packages = True` etkinleştirildi. Kontratlar gevşetilmedi.
Mikroservis: tek ekip, tek DB ve modüller arası transaction (credit + plan yayını) → dağıtık transaction gerekirdi.

### ADR-11 · Para ve oranlar decimal; istatistikler f64
Rust `rust_decimal`, Python `Decimal`, Postgres `NUMERIC`. Profiling istatistikleri (mean, stddev) `f64` ve öyle etiketlenir.

---

## 7. Veri sözleşmesi

### 7.1 Dataset'ler

| `loan_type` | `dataset` | Anahtar |
|---|---|---|
| RETAIL | `credit` | `loan_account_number` |
| RETAIL | `payment_plan` | `(loan_account_number, installment_number)` |
| COMMERCIAL | `credit` | `loan_account_number` |
| COMMERCIAL | `payment_plan` | `(loan_account_number, installment_number)` |

### 7.2 Şema tanımı (YAML)

`adapter/quality/schemas/{retail_credit,commercial_credit,payment_plan}.yaml`

```yaml
dataset: retail_credit
key: [loan_account_number]
columns:
  loan_account_number: {type: string, required: true, pattern: '^LOAN_\d{6}$'}
  customer_id:         {type: string, required: true}
  customer_type:       {type: code, domain: customer_type, required: true}
  loan_status_code:    {type: code, domain: loan_status, required: true}
  days_past_due:       {type: int, min: 0, required: true}
  loan_start_date:     {type: date, required: true}
  final_maturity_date: {type: date, required: true}
  first_payment_date:  {type: date}
  loan_closing_date:   {type: date}
  original_loan_amount:          {type: money, min: 0, required: true}
  outstanding_principal_balance: {type: money, min: 0, required: true}
  nominal_interest_rate: {type: rate, unit: percent, max: 2.0, warn_above: 0.80}
  kkdf_rate:             {type: rate, unit: percent, max: 1.0}
  bsmv_rate:             {type: rate, unit: percent, max: 1.0}
  insurance_included:    {type: bool_code, domain: yes_no}
  # ... tüm kolonlar
rules:
  - {id: MATURITY_AFTER_START,    severity: ERROR}
  - {id: INSTALLMENT_COUNT_SUM,   severity: WARNING}
  - {id: OUTSTANDING_LE_ORIGINAL, severity: WARNING}
```

Kurallar Rust'ta kayıtlı fonksiyonlardır (registry); YAML yalnızca hangi kuralın hangi severity ile çalışacağını seçer. Genel amaçlı expression engine yazılmaz.

### 7.3 Tip eşlemesi

| Şema tipi | Rust | Postgres |
|---|---|---|
| `string` | `String` | `TEXT` |
| `int` | `i64` | `INTEGER` |
| `money` | `Decimal` | `NUMERIC(18,2)` |
| `rate` | `Decimal` | `NUMERIC(12,8)` (fraction) |
| `probability` | `Decimal` | `NUMERIC(10,8)` |
| `date` | `NaiveDate` | `DATE` |
| `code` | `String` | `TEXT` + `CHECK` |
| `bool_code` | `bool` | `BOOLEAN` |

---

## 8. Banka simülasyonu (`external_bank/`)

| Method | Path | Açıklama |
|---|---|---|
| `PUT` | `/v1/tenants/{tenant}/loans/{loan_type}/{dataset}` | CSV yükle (diske stream) → **tam replace**, `version++` |
| `PATCH` | aynı | CSV ile anahtara göre **upsert** → `version++` |
| `GET` | `/v1/tenants/{tenant}/loans/{loan_type}/meta` | `{version, updated_at, datasets:{credit:{sha256,row_count}, payment_plan:{...}}}` |
| `GET` | `.../{dataset}/records` | **NDJSON stream**, ham string değerler |
| `GET` | `.../{dataset}/records?format=json&cursor=&limit=` | Sayfalı JSON |
| `GET` | `/health` | |

- Tenant `X-Bank-Key`'den çözülür; path'teki tenant ile eşleşmezse 403.
- `version` birim seviyesinde (credit + plan birlikte).
- Yapısal olarak bozuk CSV → 400; içerik kirliliği bankada **reddedilmez** (gerçek bankalar da kirli veri gönderir).
- `PATCH`, görevdeki "verinin bir parçasını ayırıp güncelleme için kullan" maddesini karşılar.
- Storage: SQLite (WAL), `records(tenant, loan_type, dataset, key, payload_json)`, 10k'lık batch insert.
- **Bütünlük:** Adapter indirdiği verinin satır sayısı + sha256'sını `meta` ile karşılaştırır; uyuşmazlık → `DownloadIntegrityError` (retry). İndirme sırasında versiyon değişirse run baştan başlar (karışık versiyon işlenmez).

---

## 9. Multi-tenancy (ADR-03)

### 9.1 Seçenekler

| Model | İzolasyon | Operasyon | |
|---|---|---|---|
| DB-per-tenant | en güçlü | yüksek | ❌ |
| Schema-per-tenant | güçlü | orta (N migration) | ❌ |
| **Paylaşılan tablo + tenant_id + RLS** | güçlü (DB zorlar) | düşük | ✅ |

### 9.2 Katmanlı izolasyon

1. **Kimlik:** `tenant_id` her zaman JWT claim'inden / API key'in tenant'ından. Parametredeki `tenant_id` sadece eşleşme kontrolü; uyuşmazlık → **403**.
2. **Uygulama:** Query servisleri `TenantContext` almadan çağrılamaz (zorunlu parametre).
3. **Veritabanı (asıl güvence):** RLS — hem **tenant**'ı hem **yayındaki snapshot**'ı zorlar:
   ```sql
   ALTER TABLE dwh.fact_loan_retail ENABLE ROW LEVEL SECURITY;
   CREATE POLICY reader_current_tenant_snapshot ON dwh.fact_loan_retail
     FOR SELECT TO app_reader
     USING (
       tenant_id = current_setting('app.tenant_id', true)
       AND batch_id IN (SELECT batch_id FROM dwh.current_snapshot
                        WHERE tenant_id = current_setting('app.tenant_id', true))
     );
   ```
   - Query servisi her okumayı kendi transaction'ında yapar ve başında `SELECT set_config('app.tenant_id', $1, true)` çağırır (transaction-local). Bu iş Django middleware'inde değil, `adapter` içindeki query servisindedir.
   - Ayar yoksa (NULL/boş) **hiç satır dönmez** (fail-closed).
   - Alt sorgu korelasyonsuz → planner bir kez çalıştırır; maliyeti ihmal edilebilir.
   - **Roller:** `app_migrator` (sahip, DDL), `app_writer` (worker; `BYPASSRLS`, HTTP'ye açık değil), `app_reader` (API; sahip değil, `BYPASSRLS` yok, **yalnızca parent tablolarda** `SELECT`; partition'lara doğrudan yetkisi yok), `app_django` (sadece `public` şeması).
   - View kullanılırsa `WITH (security_invoker = true)` zorunlu; aksi halde view sahibinin yetkisiyle çalışır ve RLS atlanır.
4. **Fiziksel:** `tenant_id` ile statik LIST partition (migration'da 3 tenant için oluşturulur; yeni tenant = migration).
5. **Banka tarafı:** Tenant başına ayrı bank API key.

### 9.3 İç kullanıcı (COULD)
`role=internal_analyst` → ayrı policy ile çapraz tenant okuma + `ops.audit_log`.

### 9.4 Verinin 3 bankaya bölünmesi
`tools/seed.py`: `hash(customer_id) mod 3` → BANK001/002/003 (müşterinin tüm kredileri aynı bankada; plan kredisini takip eder). Her tenant için ayrıca güncelleme senaryoları için bir "v2" parçası ayrılır.

---

## 10. Senkronizasyon (ADR-05, ADR-06)

### 10.1 Akış
```
beat (her POLL_INTERVAL_SECONDS, varsayılan 30)
  └─ CheckForUpdatesUseCase: 6 birim için bank.get_meta()
       └─ meta.version ≠ yayındaki source_version → SyncRun(trigger=POLL), enqueue
POST /api/sync → SyncRun(trigger=MANUAL, force?), enqueue
```

### 10.2 `SyncRun` state machine
```
PENDING → FETCHING → PROCESSING → VALIDATING → PUBLISHING → SUCCEEDED
   │          │           │            └→ REJECTED  (validation; yayındaki veri korunur; retry yok)
   │          └───────────┴────────────────→ FAILED (teknik; retry/backoff)
   └→ SKIPPED (versiyon zaten yayında / birim meşgul)
```
Geçişler domain'de (`SyncRun.advance()`); geçersiz geçiş exception. Run kaydı: `counts`, `issues_summary`, `unit_decisions`, `duration_ms`, `peak_rss_kb`, `source_version`, `batch_id`.

### 10.3 Eşzamanlılık ve dayanıklılık
- **Birim başına tek sync:** session-level `pg_try_advisory_lock(hashtext(tenant||':'||loan_type))` run boyunca; worker çökerse bağlantı kapanır ve kilit kendiliğinden düşer. API tarafında aktif run varsa `POST /api/sync` → **409** (mevcut run id ile).
- **Retry:** ağ / bütünlük hatası → exponential backoff (max 5); validation reddi → retry yok.
- **Çöken worker:** Yayın tek transaction olduğu için DWH tutarlı kalır. Yarım yüklenmiş batch hiç yayınlanmamıştır (görünmez); sonraki run'ın GC'si siler. `RUNNING` kalan run'ları reaper `FAILED` yapar (SHOULD).
- **Geçici dosyalar:** `WORK_DIR/{run_id}/`, run sonunda silinir.

---

## 11. Validation

### 11.1 Katmanlar
| Seviye | Nerede | Örnek |
|---|---|---|
| Şema | Rust, header | Eksik/fazla kolon → ERROR, dosya reddedilir |
| Field | Rust, satır | Zorunluluk, tip, aralık, pattern, enum |
| Row | Rust, satır | `maturity ≥ start`, `paid+outstanding=total` |
| Dataset | SQL (yüklenen batch) | Anahtar tekilliği (`GROUP BY … HAVING count(*) > 1`) |
| **Cross-file** | **SQL (yüklenen batch)** | Orphan payment (anti-join), planı olmayan kredi, plan satır sayısı ≠ `total_installment_count` |

**Cross-file neden SQL:** İki dosyayı uygulama belleğinde join'lemek yerine, zaten yüklenmiş batch üzerinde anti-join. Postgres gerekirse diske taşar; worker sabit bellekte kalır.

> **Neden fact tablolarında PK yok?** PK olsaydı tek bir duplicate anahtar COPY'yi tek bir hatayla kırardı ve hangi satırların sorunlu olduğu raporlanamazdı. Bunun yerine `(tenant_id, batch_id, key)` üzerinde **unique olmayan** index var; tekillik SQL kontrolüyle `DUPLICATE_KEY` issue'su olarak (satır numaralarıyla) raporlanır. Duplicate içeren batch REJECTED olduğu için yayındaki veride duplicate olmadığı garanti edilir.

### 11.2 Issue modeli
`ops.validation_issue(run_id, dataset, row_number, key, column, rule_id, severity, raw_value, normalized_value, message)`. İlk `ISSUE_DETAIL_LIMIT` (1000) issue detaylı, geri kalanı `rule_id` bazında sayaç (`ops.validation_issue_summary`).

### 11.3 Severity politikası (ADR-09)
| Severity | Anlamı | Sonuç |
|---|---|---|
| ERROR | Değer güvenle kullanılamaz | Herhangi bir ERROR → batch **REJECTED** (varsayılan) |
| WARNING | Şüpheli ama kullanılabilir | Yayınlanır, UI'da görünür |
| CORRECTED | Normalizer düzeltti | Orijinal + yeni değer loglanır |

`ERROR_TOLERANCE` (varsayılan `0`): finansal veride sessiz satır kaybı portföy toplamlarını bozar; varsayılan güvenli taraf. Şema hataları toleranstan bağımsız reddeder.

---

## 12. Normalization

Tüm normalizer'lar Rust `domain/` içinde saf fonksiyon → `proptest`.

### 12.1 Tarih
Desteklenen: `YYYYMMDD`, `YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`, `YYYY/MM/DD`, ISO datetime (saat atılır).
- `DD/MM` vs `MM/DD`: TR bankası → `DD/MM`; ikisi de geçerliyse ve dosyada gün > 12 kanıtı yoksa `AMBIGUOUS_DATE` WARNING.
- Geçersiz tarih (`30.02.2024`) veya 1900–2100 dışı → ERROR.

### 12.2 Oran → decimal fraction
1. **Değerde birim varsa o kazanır:** `18.5%` → 0.185; `1850 bps` → 0.185.
2. **Birim yoksa kolonun birimi:** şemadaki `unit` (bankayla sözleşme). Ayrıca ilk 10.000 satırın sıfır olmayan değerlerinden birim **tespit edilir** (tümü ≤ 1 → fraction; çoğunluk 1–100 → percent; çoğunluk > 100 → bps). Bu satırlar buffer'lanır (sınırlı bellek).
   - Tespit edilen birim şemadakiyle çelişirse → `UNIT_MISMATCH` WARNING; tespit edilen birim kullanılır.
   - Kolonun dominant büyüklüğüyle çelişen tekil değer (ör. percent kolonunda çıplak `0.185`) → değer tespit edilen birimle yorumlanır + `UNIT_AMBIGUOUS_VALUE` WARNING.
   - Karar run'a kaydedilir (`unit_decisions`): "bu değeri neden 100'e böldün?" sorusunun kanıtı.
3. Satır bazlı tahmin yapılmaz: çıplak `0.9` tek başına belirsizdir, kolonun geri kalanı belirsizliği çözer.
4. Normalize sonrası `[0, max]` dışı → ERROR; `warn_above` üstü → `RATE_IMPLAUSIBLE` WARNING (retail'deki `100.00` vakaları).

### 12.3 Kategori → kanonik kod
`ref.code_mapping(domain, raw_key, canonical)`: `raw_key` = trim + Türkçe-duyarlı casefold (`İ→i`, `I→ı`) + aksan sadeleştirme.

| domain | raw | canonical |
|---|---|---|
| `installment_status` | A, Açık, Open, Active, Unpaid | `OPEN` |
| `installment_status` | K, Kapalı, Paid, Closed, Ödendi | `CLOSED` |
| `loan_status` | A, Aktif, Active | `ACTIVE` |
| `loan_status` | K, Kapalı, Closed | `CLOSED` |
| `yes_no` | E, Evet, Y, Yes, 1, true | `true` |
| `yes_no` | H, Hayır, N, No, 0, false | `false` |
| `customer_type` | I, Bireysel, Individual | `INDIVIDUAL` |
| `customer_type` | T, V | `T`, `V` (anlamı açık soru §25; uydurulmaz) |

Bilinmeyen değer → ERROR (`UNKNOWN_CODE`). Yeni eşanlamlı = `ref.code_mapping` satırı (Django admin), deploy gerekmez; sözlük run başında Rust'a parametre olarak geçer.

### 12.4 Sayı
`1234.56`, `1,234.56`, `1.234,56`, `1 234,56`, `₺`/`TL` soneki → `Decimal`. Son ayraç ondalık kabul edilir; belirsizse (`1,234`) kolonun diğer değerlerine bakılır, yine belirsizse WARNING.

### 12.5 Hatalı veriyi tespit / düzeltme
| Kural | Aksiyon |
|---|---|
| `installment_status=CLOSED` ve `actual_payment_date` boş | WARNING |
| `actual_payment_date` gelecekte | ERROR |
| Kapalı taksitte `remaining_*` ≠ 0 | CORRECTED → 0 |
| Negatif tutar | ERROR |
| `installment_amount` ≠ bileşenler toplamı (±0.01) | WARNING |
| Boşluk / büyük-küçük harf tutarsızlığı | sessiz normalize |

---

## 13. DWH veri modeli

```sql
CREATE TABLE dwh.fact_loan_retail (
  tenant_id TEXT NOT NULL,
  batch_id  UUID NOT NULL,
  loan_account_number TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  customer_type TEXT NOT NULL,
  loan_status_code TEXT NOT NULL,
  days_past_due INTEGER NOT NULL,
  loan_start_date DATE NOT NULL,
  final_maturity_date DATE NOT NULL,
  original_loan_amount NUMERIC(18,2) NOT NULL,
  outstanding_principal_balance NUMERIC(18,2) NOT NULL,
  nominal_interest_rate NUMERIC(12,8),
  -- ... diğer kolonlar
  source_row_number INTEGER NOT NULL
) PARTITION BY LIST (tenant_id);
CREATE INDEX ON dwh.fact_loan_retail (tenant_id, batch_id, loan_account_number);
-- dwh.fact_loan_commercial: aynı desen
-- dwh.fact_installment: + loan_type, installment_number; index (tenant_id, batch_id, loan_account_number, installment_number)

CREATE TABLE dwh.current_snapshot (           -- yayındaki veri = bu tablonun gösterdiği batch
  tenant_id TEXT NOT NULL,
  loan_type TEXT NOT NULL,
  batch_id  UUID NOT NULL,
  source_version INTEGER NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  row_counts JSONB NOT NULL,
  PRIMARY KEY (tenant_id, loan_type)
);
```

- Retail/commercial kredi şemaları farklı → iki fact tablo. Plan şemaları aynı → tek tablo + `loan_type`.
- `dwh.v_loan_common` (`security_invoker = true`): iki kredi tipinin ortak kolonları.
- Lineage: `batch_id` → `ops.sync_run`; `source_row_number` → issue'ları kaynak satıra bağlar.
- Okuma: keyset pagination `loan_account_number` üzerinden.

**ops:** `sync_run`, `validation_issue`, `validation_issue_summary`, `data_profile`, (`audit_log` — COULD). **ref:** `tenant`, `code_mapping`.

---

## 14. Atomik replace (ADR-04)

```
(transaction dışı — ağır ve görünmez işler)
1. batch_id = uuid
2. COPY dwh.fact_loan_retail (… batch_id …) FROM STDIN   ← Rust'ın ürettiği COPY-text dosyası
   COPY dwh.fact_installment  (…)            FROM STDIN
   (RLS policy'si batch'in current_snapshot'ta olmasını şart koştuğu için okuyucu bu satırları GÖREMEZ)
3. SQL doğrulama: tekillik + cross-file → issue'lar
   REJECTED → DELETE … WHERE batch_id = $new ; yayındaki veri hiç değişmedi ✔

(TEK, kısa transaction)
4. BEGIN;
     INSERT INTO dwh.current_snapshot (tenant_id, loan_type, batch_id, source_version, published_at, row_counts)
       VALUES (…) ON CONFLICT (tenant_id, loan_type) DO UPDATE SET batch_id = EXCLUDED.batch_id, …;
     INSERT INTO ops.data_profile …;
     UPDATE ops.sync_run SET status = 'PUBLISHING', … ;
   COMMIT;

(transaction dışı)
5. GC: DELETE FROM dwh.fact_* WHERE tenant_id = $t AND <loan_type koşulu> AND batch_id <> $current;
   (idempotent; çökme olursa sonraki run tekrar dener)
6. GC tamamlanınca run SUCCEEDED olur.
```

**Garantiler:**
- **Credit + plan aynı pointer** ile yayınlanır → karma snapshot görünmez.
- Okuyucular COMMIT anına kadar eski batch'i, sonra yenisini görür (MVCC); arada hiçbir şey görmezler. Okuyucu hiçbir zaman kilitlenmez.
- "1000 → 2000 = 2000": görünür veri tek batch'tir; GC sonrası fiziksel tabloda da yalnızca 2000 satır kalır (V-07 her ikisini kontrol eder).
- Validation başarısızsa pointer değişmez → eski veri korunur.

**Bilinen maliyet:** GC `DELETE` bloat üretir; autovacuum toplar. Ölçülür (V-17). Gerekirse evrim yolu: batch başına partition + `DETACH … CONCURRENTLY` + `DROP` (kilitsiz, bloat'sız).

---

## 15. Büyük dosyalar ve bellek (R7)

**Prensip:** hiçbir katmanda dosyanın tamamı belleğe alınmaz.

| Aşama | Teknik | Bellek |
|---|---|---|
| UI → Bank | Multipart diske stream | O(chunk) |
| Bank storage | SQLite batch insert | O(batch) |
| Bank → Adapter | NDJSON stream → `WORK_DIR` | O(chunk) |
| Parse/normalize/validate | Rust `BufReader`, satır satır (birim tespiti için ilk 10k satır buffer) | O(10k satır) |
| Profiling | Welford (mean/var), min/max, null sayacı; kategorik HashMap, `PROFILE_MAX_CATEGORIES=1000` üstünde sayım durur ve kolon "high cardinality" etiketlenir | O(kolon × kategori) |
| DB yazma | `COPY FROM STDIN`, 1MB bloklar | O(blok) |
| Cross-file | SQL anti-join | DB tarafında |

**Hedefler (README'de gerçek ölçümle raporlanır):**
| Metrik | Hedef |
|---|---|
| Worker peak RSS, 200MB plan dosyası | ≤ 256 MB; 50MB ile 200MB arasındaki fark < %20 |
| 200MB birim uçtan uca sync | ölçülür ve raporlanır |
| Publish transaction | < 100 ms |
| `/api/data` 500 satırlık sayfa p95 | < 300 ms |

`tools/multiply.py`: örnek CSV'leri hedef boyuta çoğaltır, loan ID'lerini sonekle tekilleştirir.

---

## 16. Data Profiling (R10)

- Rust motorunda yükleme sırasında **tek geçişte**, normalize edilmiş değerler üzerinden. Publish transaction'ında `ops.data_profile(tenant, loan_type, dataset, batch_id, column, stats JSONB)`'ye yazılır.
- Veri yalnızca sync'te değiştiği için `GET /api/profiling` hazır sonucu okur.
- İçerik: sayısal `count, min, max, mean, stddev (sample)`; kategorik `distinct_count, top 10, most_frequent`; tarih `min, max`; her kolon `null_count, null_ratio`; dataset `row_count`, severity bazında issue sayıları. (p50/p95 — COULD.)
- Doğrulama: aynı istatistikler SQL ile hesaplanıp karşılaştırılır (V-18).

---

## 17. REST API (R11)

| Method | Path | Açıklama |
|---|---|---|
| POST | `/api/auth/token`, `/api/auth/token/refresh` | JWT |
| POST | `/api/sync` | `{tenant_id, loan_type, force?}` → **202** `{sync_run_id, status}`; aktif run varsa **409** |
| GET | `/api/sync/{id}` | status, counts, unit_decisions, issue özeti |
| GET | `/api/runs?tenant_id=&loan_type=` | geçmiş |
| GET | `/api/data?tenant_id=X&loan_type=Y&dataset=credit&cursor=&limit=` | keyset pagination; `dataset` varsayılan `credit` |
| GET | `/api/profiling?tenant_id=X&loan_type=Y` | iki dataset |
| GET | `/api/validation-issues?sync_run_id=&severity=` | sayfalı |
| GET | `/api/health` | |
| GET | `/api/schema/`, `/api/docs/` | OpenAPI + Swagger UI |

```http
GET /api/data?tenant_id=BANK001&loan_type=RETAIL&limit=2
200 OK
{"tenant_id":"BANK001","loan_type":"RETAIL","dataset":"credit",
 "snapshot":{"batch_id":"…","source_version":7,"published_at":"2026-10-22T10:00:00Z","row_count":8457},
 "results":[{…},{…}], "next_cursor":"LOAN_000123"}
```

Hatalar RFC 9457 `application/problem+json`:
| Durum | Kod |
|---|---|
| Token yok/geçersiz | 401 |
| Başka tenant | 403 (`tenant-mismatch`) |
| Başka tenant'ın run'ı | 404 (varlığı sızdırılmaz) |
| Geçersiz parametre | 400 |
| Henüz yayın yok | 404 (`no-snapshot`) |
| Birim meşgul | 409 |

---

## 18. Güvenlik

- **JWT** (simplejwt): access 15 dk, refresh 1 gün; claim'ler `sub, tenant_id, role`.
- **API key** (SHOULD): `X-API-Key`, DB'de hash'li, tenant'a bağlı, iptal edilebilir.
- Varsayılan permission `IsAuthenticated + TenantMatches`; whitelist dışında public endpoint yok (V-01 bunu tüm route'lar için test eder).
- CORS yalnızca frontend origin'i; rate limit (SHOULD).
- Secret'lar `.env`; repoda yalnızca `.env.example`.
- SQL parametreli; tablo isimleri yalnızca enum'lardan + `psycopg.sql.Identifier`.
- Upload: `MAX_UPLOAD_MB=250`, header/kolon kontrolü.

---

## 19. Frontend (R8)

Feature bazlı: `features/{auth,bank-portal,sync,data,profiling,issues}`.

| Ekran | İçerik |
|---|---|
| Login | Tenant kullanıcıya bağlı (seçilmez) |
| Bank Portal (simülasyon) | loan_type + dataset seç, CSV yükle (replace/patch), progress, banka versiyonu. Bankanın kendi portalını temsil eder; demo bank key'leri yalnızca bu ekranda |
| Sync | Birim kartları: banka versiyonu vs yayındaki versiyon, "Sync now", canlı durum, son run'lar |
| Data | Sanal scroll tablo; credit / payment_plan sekmeleri |
| Profiling | Kolon kartları: null oranı, sayısal min/max/mean/std, kategorik top-N bar chart |
| Validation | Severity sayaçları, rule dağılımı, issue tablosu (raw → normalized), REJECTED banner |

README'ye ekran görüntüleri eklenir.

---

## 20. Konfigürasyon (env)

| Değişken | Varsayılan |
|---|---|
| `DATABASE_URL_WRITER` / `DATABASE_URL_READER` / `DATABASE_URL_DJANGO` | |
| `REDIS_URL` | |
| `BANK_BASE_URL` | `http://bank:8001` |
| `BANK_API_KEYS` | `BANK001:…,BANK002:…,BANK003:…` |
| `POLL_INTERVAL_SECONDS` | 30 |
| `ERROR_TOLERANCE` | 0 |
| `ISSUE_DETAIL_LIMIT` | 1000 |
| `WORK_DIR` | `/var/tmp/adapter` |
| `JWT_SIGNING_KEY`, `JWT_ACCESS_MINUTES` | |
| `MAX_UPLOAD_MB` | 250 |
| `DATA_DIR` | `./data` (gerçek CSV'ler; gitignored) |

---

## 21. Test stratejisi

| Katman | Araç | Kapsam |
|---|---|---|
| Rust | `cargo test`, `proptest` | Normalizer'lar ("geçerli tarih → her formatta yaz → aynı sonuç"), birim tespiti, kod sözlüğü, Türkçe casefold |
| Domain | `pytest` (I/O yok) | `SyncRun` geçişleri, `SeverityPolicy`, value object'ler |
| Application | `pytest` + in-memory fake port'lar | "REJECTED ise publish çağrılmaz", "versiyon aynıysa SKIPPED", retry sınıflandırması |
| Infrastructure | `pytest` + gerçek PostgreSQL | COPY, publish/GC, RLS, roller, advisory lock |
| Verification | `pytest` + çalışan compose | V-ID'ler (`docs/VERIFICATION.md`) |
| Mimari | `lint-imports` | §5.5 |
| Performans | `tools/bench.py` | 50MB / 200MB süre + peak RSS |
| Fault injection | `tools/make_dirty.py` | Kirlilik + beklenen sonuç manifesti (`expected.json`) |
| Frontend | Vitest (+ Playwright — SHOULD) | |

**Veri:** Sağlanan örnek veri repoya commit edilmez (`data/` gitignored). CI sentetik veri kullanır (`tools/generate_synthetic.py`, aynı şema). Gerçek veri `./data` altına konursa `make seed` onu kullanır.

---

## 22. Repo yapısı

```
ledgerbridge-loan-adapter/
├── external_bank/                  # Ayrı deployable (FastAPI): app/{routes,service,storage}
├── adapter/                        # Çekirdek — Django bilmez (import-linter)
│   ├── shared/
│   ├── ingestion/{domain,application,infrastructure}/
│   ├── quality/
│   │   ├── {domain,application,infrastructure}/
│   │   ├── schemas/                # YAML
│   │   └── engine/                 # Rust crate → adapter_engine
│   ├── warehouse/{domain,application,infrastructure/sql}/
│   └── profiling/{domain,application,infrastructure}/
├── api/                            # Presentation — Django projesi
│   ├── config/                     # settings, urls, celery app
│   ├── identity/                   # kullanıcı, JWT, API key, TenantContext
│   ├── endpoints/                  # DRF view + serializer
│   ├── tasks/                      # Celery giriş noktaları
│   └── composition.py              # Composition Root
├── frontend/
├── tests/
│   ├── unit/{domain,application}/
│   ├── integration/                # gerçek Postgres
│   ├── external_bank/
│   └── verification/               # V-ID'ler (make verify)
├── tools/                          # seed, generate_synthetic, make_dirty, multiply, bench
├── docs/{tecnic.md, VERIFICATION.md, PROGRESS.md, CODE_TOUR.md}
├── .github/workflows/ci.yml
├── .importlinter · .pre-commit-config.yaml · Makefile · docker-compose.yml · .env.example
├── README.md · Architecture.md · AGENTS.md
```

---

## 23. Çalıştırma ve teslim

- **Ön koşul yalnızca Docker + make.** Rust, Python ve Node build'leri image içinde (multi-stage; Rust bağımlılıkları cache'lenir). `linux/amd64` ve `linux/arm64` (Apple Silicon) çalışır.
- `make test` ve `make verify` testleri container içinde çalıştırır.
- Hızlı yol: `cp .env.example .env && make up && make seed && make verify` → `verification-report.md`.
- **README.md:** proje özeti + mimari diyagram, hızlı başlangıç, demo kullanıcıları, multi-tenant kararı ve nedeni, test çalıştırma, curl örnekleri, ekran görüntüleri, ölçülen performans tablosu, varsayımlar ve açık sorular.
- **Architecture.md:** Mermaid ile bileşen, sync sequence, state machine, ER diyagramları; ADR özetleri.
- **docs/CODE_TOUR.md:** Kodu okuyacak kişi için rehberli tur: bir sync'i uçtan uca takip eden dosya/fonksiyon sırası.

---

## 24. Bilinçli trade-off'lar

| Konu | Karar | Gerekçe / evrim |
|---|---|---|
| Geçmiş snapshot | Sadece güncel (GC) | Gereksinim; GC'yi ertelemek arşiv/time-travel sağlar (COULD) |
| Delta sync | Full replace | Gereksinim; satır hash'iyle delta ileride |
| Kolon-bazlı DWH | Yok | ADR-02 |
| Rust'ta DB yazımı | Yok | Transaction yönetimi tek yerde (Python UoW); Rust saf |
| Expression engine | Yok | Kayıtlı kural fonksiyonları + YAML seçimi |
| GC bloat | Kabul | Ölçülür; evrim yolu ADR-04 |
| Kubernetes | Yok | compose ile değerlendirme kolaylığı |
| Webhook | Yok | ADR-05; aynı use case'i tetikleyen endpoint olarak eklenebilir |

---

## 25. Açık sorular ve varsayımlar

| # | Soru | Cevap gelene kadar varsayım |
|---|---|---|
| 1 | `customer_type` `T`/`V` anlamı? | Kod olduğu gibi tutulur |
| 2 | `nominal_interest_rate` birimi: retail yıllık %, commercial aylık % mı? | Her ikisi de "percent" olarak fraction'a çevrilir; periyot dönüşümü yapılmaz, dokümante edilir |
| 3 | Retail'deki `100.00` faizler gerçek mi? | Yayınlanır + `RATE_IMPLAUSIBLE` WARNING |
| 4 | `paid+outstanding≠total` — referans alan? | WARNING; veri değiştirilmez |
| 5 | `outstanding > original` — kapitalizasyon mu? | WARNING |
| 6 | `external_rating` ölçekleri farklı kurumlardan mı? | Ham tutulur |
| 7 | Validation reddinde kısmi kabul iş tarafında kabul edilir mi? | `ERROR_TOLERANCE=0` |

---

## 26. Milestone'lar

| M | Seviye | İçerik | Çıkış kriteri |
|---|---|---|---|
| M0 | MUST | İskelet: klasörler, `.importlinter`, pre-commit (veri/secret koruması), Makefile, compose (postgres+redis), CI, public repo | `make lint` + `lint-imports` yeşil, CI yeşil |
| M1 | MUST | DB: şemalar, roller, partition'lar, RLS, `current_snapshot`; publish/GC'nin SQL entegrasyon testi | V-05, V-15 (SQL seviyesi) |
| M2 | MUST | Domain + port'lar + use case'ler, fake'lerle test | application testleri |
| M3 | MUST | Rust motoru: YAML şema, normalizer, validator, profiler, COPY writer | `cargo test`, V-11 (motor seviyesi) |
| M4 | MUST | Bank simülasyonu + seed + synthetic generator | V-20, V-21 |
| M5 | MUST | Infrastructure adapter'ları + Celery pipeline uçtan uca | V-06–V-10, V-12–V-15 |
| M6 | MUST | Django API + JWT + TenantContext | V-01, V-03, V-04 |
| M7 | MUST | Profiling API | V-18 |
| M8 | MUST | Frontend | V-22 (manuel kontrol listesi + ekran görüntüleri) |
| M9 | MUST | 200MB bench | V-17 |
| M10 | MUST | README, Architecture.md, CODE_TOUR.md, `make verify` raporu | V-23, tüm MUST V'ler yeşil |
| M11 | SHOULD | API key, 409, reaper, fault-injection manifest, Playwright, rate limit | V-02, V-16, V-19, V-22 (otomatik) |
| M12 | COULD | İç analist + audit log, arşiv, p50/p95 | – |

En riskli varsayım (RLS + snapshot pointer) M1'de, kod yazılmadan önce SQL seviyesinde doğrulanır.
