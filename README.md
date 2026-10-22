# ledgerbridge Finansal Veri Entegrasyon Adaptörü

[![CI](https://github.com/levend18/ledgerbridge-loan-adapter/actions/workflows/ci.yml/badge.svg)](https://github.com/levend18/ledgerbridge-loan-adapter/actions/workflows/ci.yml)

Üç bankanın kredi portföyünü tenant izolasyonu ve atomik yayın ile entegre eden
adaptör. Tasarım: [teknik belge](docs/tecnic.md); kabul kriterleri:
[doğrulama senaryoları](docs/VERIFICATION.md).

Geliştirme sürmektedir; milestone durumları [ilerleme günlüğündedir](docs/PROGRESS.md).

## Geliştirme

Gereksinimler: Docker Desktop ve make.

```bash
cp .env.example .env
make up
make build
make lint
make test
```

Gerçek veri `data/` altında kalır ve Git'e eklenmez. Değerlendirme testleri sentetik
veri kullanır. Kurulum iskeleti M0'dadır; uygulama servisleri sonraki milestone'larda
eklenir.
