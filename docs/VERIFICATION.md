# Doğrulama Senaryoları

> Her senaryo bir gereksinimi (R-ID, `docs/tecnic.md` §2) kanıtlar ve **MUST** / **SHOULD** olarak işaretlidir.
> Hepsi `tests/verification/test_vXX_*.py` altında otomatik testtir; `make verify` hepsini container içinde çalıştırır ve `verification-report.md` üretir.
> Her senaryoda elle tekrar edilebilmesi için manuel (curl) adımlar da verilmiştir.

## Ön koşul

```bash
cp .env.example .env
make up            # docker compose up -d --wait
make seed          # ./data altında gerçek CSV'ler varsa onlar, yoksa sentetik veri → 3 bankaya bölünür, bankaya yüklenir
make verify        # tüm senaryolar + rapor
```

Manuel kontrol için yardımcılar:

```bash
API=http://localhost:8000; BANK=http://localhost:8001
tok() { curl -s -X POST $API/api/auth/token -H 'Content-Type: application/json' \
        -d "{\"username\":\"$1\",\"password\":\"demo1234\"}" | jq -r .access; }
T1=$(tok bank001_user); T2=$(tok bank002_user); T3=$(tok bank003_user)
sync_wait() { # $1=token $2=tenant $3=loan_type → son durum
  id=$(curl -s -X POST $API/api/sync -H "Authorization: Bearer $1" -H 'Content-Type: application/json' \
       -d "{\"tenant_id\":\"$2\",\"loan_type\":\"$3\",\"force\":true}" | jq -r .sync_run_id)
  until s=$(curl -s $API/api/sync/$id -H "Authorization: Bearer $1" | jq -r .status); \
        [[ $s =~ SUCCEEDED|REJECTED|FAILED|SKIPPED ]]; do sleep 1; done; echo $s; }
```

Demo kullanıcıları seed ile oluşur: `bank001_user`, `bank002_user`, `bank003_user` (şifre `demo1234`, yalnızca yerel demo).

---

## A. Kimlik doğrulama ve tenant izolasyonu (R2, R9)

### V-01 · Token olmadan veri endpoint'i çalışmaz — MUST
- **Adım:** Authorization olmadan `/api/data`, `/api/sync`, `/api/profiling`, `/api/runs`, `/api/validation-issues`.
- **Beklenen:** Hepsi `401`, `application/problem+json`.
- **Ek:** Test URL conf'taki **tüm** route'ları gezer; whitelist (`/api/health`, `/api/auth/*`, `/api/docs`, `/api/schema`) dışında 401 dönmeyen route varsa kırılır. Böylece sonradan eklenen bir endpoint korumasız kalamaz.

### V-02 · Geçersiz token ve API key — MUST (JWT kısmı) / SHOULD (API key kısmı)
- **Adım:** Bozuk imzalı JWT; süresi dolmuş JWT; geçersiz `X-API-Key`; geçerli BANK001 `X-API-Key`.
- **Beklenen:** İlk üçü `401`; geçerli API key ile BANK001 verisi `200`.

### V-03 · BANK001 verisi çekilirken BANK002 verisi gelmez — MUST *(görev senaryosu 1)*
- **Adım:** 3 tenant için RETAIL sync. `$T1` ile `GET /api/data?tenant_id=BANK001&loan_type=RETAIL` tüm sayfalar.
- **Beklenen:** Tüm satırlarda `tenant_id == "BANK001"`; loan ID kümesi seed'in BANK002/003 kümeleriyle kesişmez; toplam = seed'in BANK001 sayısı.

### V-04 · Başka tenant'ın verisi istenemez — MUST
- **Adım:** `$T1` ile `tenant_id=BANK002` → data, profiling, sync (POST), runs, validation-issues; BANK002'ye ait bir `sync_run_id` ile `GET /api/sync/{id}`.
- **Beklenen:** `403 tenant-mismatch`; run detayı `404`.

### V-05 · Veritabanı seviyesinde izolasyon (RLS) — MUST
- **Adım (`app_reader` rolüyle SQL):**
  ```sql
  BEGIN; SELECT set_config('app.tenant_id','BANK001',true);
  SELECT DISTINCT tenant_id FROM dwh.fact_loan_retail;                  -- yalnızca BANK001
  SELECT count(*) FROM dwh.fact_installment WHERE tenant_id='BANK002';  -- 0
  COMMIT;
  BEGIN; SELECT count(*) FROM dwh.fact_loan_retail; COMMIT;             -- ayar yok → 0 (fail-closed)
  SELECT count(*) FROM dwh.fact_loan_retail_bank002;                    -- permission denied
  ```
  Ayrıca: `app_writer` ile yayınlanmamış bir batch yüklenir; `app_reader` (doğru tenant ayarıyla) bu satırları **göremez**.
- **Beklenen:** Yorumlardaki gibi; aynı kontroller bir publish **sonrası** tekrar edilir.

---

## B. Veri tipleri ve depolama (R3, R6)

### V-06 · RETAIL ve COMMERCIAL ayrı çekilebilir — MUST *(görev senaryosu 2)*
- **Adım:** BANK001 için RETAIL + COMMERCIAL sync; ayrı `GET /api/data` (credit ve `dataset=payment_plan`).
- **Beklenen:** RETAIL retail şemasında (`insurance_included` var, `sector_code` yok), COMMERCIAL tersi; loan ID kümeleri kesişmez; satır sayıları kaynakla eşit.

### V-07 · 1000 kredi → 2000 kredi = 2000 — MUST *(görev senaryosu 3)*
- **Adım:** BANK001/RETAIL için 1000 kredilik (planlarıyla) `PUT` → sync; sonra 2000 kredilik `PUT` → sync.
- **Beklenen:** API'de önce 1000, sonra **2000**. Run tamamlandıktan (GC dahil) sonra fiziksel tabloda da `count(*) WHERE tenant_id='BANK001'` = 2000 (writer rolüyle). Plan tablosu yalnızca yeni planları içerir. Diğer birimlerin sayıları değişmez.

### V-08 · Geçerli → geçersiz: eski veri korunur — MUST *(görev senaryosu 4)*
- **Adım:** Geçerli veri sync (`batch_id=A`). Sonra ERROR içeren veri (ör. %1 satırda `final_maturity_date < loan_start_date` veya orphan payment) → sync.
- **Beklenen:** İkinci run `REJECTED`; `/api/data` hâlâ `batch_id=A` ve aynı sayı; `/api/profiling` A'nın profili; `GET /api/validation-issues?sync_run_id=<B>` satır, kural, raw değer gösterir; reddedilen batch'in satırları fiziksel tablodan silinmiş.

---

## C. Validation ve normalization (R4, R5)

### V-09 · Field-level validation — MUST
- **Adım:** `tools/make_dirty.py --profile field`: zorunlu alan boş, tip bozuk (`abc` tutar), negatif tutar, aralık dışı oran, bilinmeyen kategori, yanlış kolon adı.
- **Beklenen:** Her biri beklenen `rule_id` ile issue üretir ve batch REJECTED olur; şema hatası dosyayı tamamen reddeder (`SchemaMismatch`).

### V-10 · Cross-file validation — MUST
- **Adım:** (a) planda kredisi olmayan `LOAN_999999`; (b) duplicate `loan_account_number`; (c) duplicate `(loan, installment_number)`.
- **Beklenen:** (a) `ORPHAN_PAYMENT`, (b)/(c) `DUPLICATE_KEY` → REJECTED, satır numaralarıyla raporlanır; planı olmayan kredi ve plan sayısı uyumsuzluğu → WARNING, yayınlanır.

### V-11 · Normalization — MUST
- **Adım:** `make_dirty.py --profile normalize`:
  - Tarih: `20240115`, `15.01.2024`, `2024-01-15`, `15/01/2024`, `2024-01-15T00:00:00`
  - Oran: `18.5%`, `1850 bps`, percent kolonunda `18.5`, fraction kolonunda `0.185`
  - Kategori: `K`, `Kapalı`, `KAPALI `, `kapali`, `Paid`, `Closed`; `E`, `Evet`, `yes`
  - Sayı: `1.234,56`, `1,234.56`, `1234.56`
- **Beklenen:** DWH'de `2024-01-15`, `0.185`, `CLOSED`, `true`, `1234.56`. Kirli değerler için issue'da `raw_value → normalized_value`. Run detayında `unit_decisions`: gerçek veride retail `nominal_interest_rate = percent`, commercial `default_probability = fraction`.
- **Ek (gerçek veriyle):** retail'deki 127 adet `100.00` faiz `RATE_IMPLAUSIBLE` WARNING üretir; veri yayınlanır.

---

## D. Senkronizasyon (R12)

### V-12 · Yeni veri gelince otomatik sync — MUST
- **Adım:** `POLL_INTERVAL_SECONDS=5`; bankaya BANK002/COMMERCIAL için yeni versiyon `PUT`; manuel sync yok.
- **Beklenen:** En geç `2 × poll + işleme süresi` içinde `trigger=POLL` run `SUCCEEDED`; `/api/data` yeni versiyonu gösterir.

### V-13 · Değişiklik yoksa iş yapılmaz — MUST
- **Adım:** Banka versiyonu değişmeden birkaç poll döngüsü; ardından `force=false` manuel sync.
- **Beklenen:** Poll yeni run oluşturmaz; manuel run `SKIPPED`; `batch_id` aynı.

### V-14 · Kısmi güncelleme (PATCH) senkronize olur — MUST
- **Adım:** BANK003/RETAIL'e 50 kredilik `PATCH` (10 yeni, 40 güncellenmiş tutar) → poll.
- **Beklenen:** Toplam = eski + 10; 40 kredinin `outstanding_principal_balance` yeni değerde.

---

## E. Atomiklik ve dayanıklılık (R6)

### V-15 · Yayın sırasında okuyucu yarım/karma veri görmez — MUST
- **Adım:** Bir thread sürekli okur (API + `app_reader` SQL: `count(*)`, `count(DISTINCT batch_id)` hem credit hem plan); paralelde 1000 ↔ 2000 arasında 10 sync.
- **Beklenen:** Her okumada count ∈ {1000, 2000}, tek `batch_id`, credit ve plan `batch_id`'leri eşit; hiçbir okuma hata almaz veya bloklanmaz (okuma gecikmesi p99 ölçülür ve raporlanır).

### V-16 · Çakışan sync ve çöken worker — SHOULD
- **Adım:** (a) Aynı birime aynı anda iki `POST /api/sync`. (b) `PROCESSING` sırasında `docker compose kill worker`, sonra worker'ı yeniden başlat.
- **Beklenen:** (a) ikinci istek `409`; tek publish. (b) Yayındaki veri aynı; reaper run'ı `FAILED` yapar; yarım batch sonraki run'ın GC'siyle silinir; sonraki sync başarılı.

---

## F. Ölçek ve profiling (R7, R10)

### V-17 · 200MB dosya, sabit bellek — MUST
- **Adım:** `make bench`: ~50MB ve ~200MB payment plan (+ uyumlu kredi) üret, bankaya yükle, sync; worker peak RSS'i `ops.sync_run.peak_rss_kb` + `docker stats`'tan.
- **Beklenen:** `SUCCEEDED`; satır sayısı doğru; peak RSS ≤ 256MB; 50MB/200MB farkı < %20; süreler ve GC süresi `verification-report.md` + README'ye.

### V-18 · Profiling doğru — MUST
- **Adım:** `GET /api/profiling?tenant_id=BANK001&loan_type=RETAIL`.
- **Beklenen:** Her kolonda `null_ratio`; sayısallarda `min/max/mean/stddev`; kategoriklerde `distinct_count/most_frequent`. SQL ile (`min, max, avg, stddev_samp, count(DISTINCT), mode() WITHIN GROUP`) karşılaştırma: sayısallarda göreli fark < 1e-9, diğerleri birebir. `loan_closing_date.null_ratio = 1.0`.

### V-19 · Fault-injection manifesti — SHOULD
- **Adım:** `make_dirty.py --profile mixed --seed 42` → sync.
- **Beklenen:** Severity ve `rule_id` bazındaki issue sayıları `expected.json` ile birebir; karar manifestteki ile aynı.

---

## G. Banka simülasyonu, frontend, dokümantasyon (R1, R8, R13)

### V-20 · Bank API kontratı — MUST
- **Adım:** `PUT`, `PATCH`, `GET meta`, `GET records` (NDJSON), `GET records?format=json&limit=`; yanlış `X-Bank-Key` ile başka tenant path'i.
- **Beklenen:** Her yazma `version`'ı 1 artırır; `meta.sha256/row_count` indirilenle tutarlı; NDJSON `application/x-ndjson`, chunked; başka tenant → `403`.

### V-21 · Banka ham veriyi korur — MUST
- **Adım:** `15.01.2024`, `18.5%`, `Kapalı` içeren CSV yükle, `records`'tan geri oku.
- **Beklenen:** Değerler byte-byte aynı.

### V-22 · Frontend — MUST (manuel liste + ekran görüntüleri) / SHOULD (Playwright)
- **Adım:** Login (bank001_user) → Bank Portal'dan CSV yükle → "Sync now" → SUCCEEDED → Data tablosu → Profiling grafikleri → geçersiz CSV + sync → Validation ekranında REJECTED banner + issue tablosu.
- **Beklenen:** Tüm adımlar çalışır; BANK001 kullanıcısı hiçbir yerde BANK002 görmez; ekran görüntüleri `docs/screenshots/`.

### V-23 · Dokümantasyon ve mimari kontratlar — MUST
- **Adım:** `make lint` (ruff, mypy, `cargo clippy -D warnings`, eslint) + `lint-imports`; README'deki curl örnekleri `tests/verification/test_v23_readme.py` tarafından README'den çıkarılıp çalıştırılır.
- **Beklenen:** Hepsi yeşil; README'de kurulum, multi-tenant kararı, testler, API örnekleri, performans tablosu, varsayımlar/açık sorular; `Architecture.md` ve `docs/CODE_TOUR.md` mevcut.

---

## Rapor formatı (`verification-report.md`)

```
| V-ID | Seviye | Başlık | Durum | Süre | Kanıt |
|------|--------|--------|-------|------|-------|
| V-03 | MUST | BANK001 çekerken BANK002 gelmez | PASS | 4.2s | 8457 satır, kesişim=0 |
| V-17 | MUST | 200MB bellek | PASS | 92s | peak RSS 141MB (50MB: 133MB) |
Ortam: git SHA, tarih, makine, Postgres/Python/Rust sürümleri
```

## Hızlı kontrol

```bash
git clone <repo> && cd ledgerbridge-loan-adapter
cp .env.example .env && make up && make seed && make verify
open http://localhost:5173      # bank001_user / demo1234
```
