# Scraper

Sosyal medya metriklerini kazıyan HTTP mikro servisi. URL gonder, JSON al.

[Scrapling](https://github.com/AhmedYousri2022/scrapling) (Camoufox/Firefox tabanli gizli tarayici) kullanarak oturum acmadan gercek zamanli metrik cikarir.

---

## Desteklenen Platformlar

Canli testlerden alinan degerler (2026-04-03):

| Platform | Metrikler | Yontem | Ornek |
|---|---|---|---|
| `instagram.com` | likes, comments, username | Embedded Relay JSON regex | likes=529, comments=58 |
| `youtube.com` | views, likes | ytInitialData JSON regex | views=16.807.599.978, likes=46.457.670 |
| `x.com` | likes, reposts, replies, views | Aria-label regex (oturum gerektirmez) | views=696, replies=1 |
| `facebook.com` | reactions, comments, shares | Embedded JSON payload regex | reactions=1.043, comments=172, shares=3.662 |
| `sikayetvar.com` | view_count, comment_count | CSS secici | view_count=820, comment_count=1 |

---

## Hizli Baslangic

```bash
# Bagimliliklari yukle
pip install .

# Scrapling icin Camoufox/Firefox tarayicisini indir (tek seferlik)
python -m scrapling install

# HTTP sunucusunu baslat
uvicorn src.server:app --host 0.0.0.0 --port 8000
```

Gelistirme ortami icin:

```bash
pip install ".[dev]"
```

---

## API

### `GET /fetch?url=<url>`

Tek bir URL'yi kaziyip birlesik metrik JSON'u dondurur.

```bash
curl "http://localhost:8000/fetch?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Yanit:

```json
{
  "success": true,
  "platform": "youtube",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "scraped_at": "2026-04-06T12:00:00Z",
  "metrics": {
    "likes": 46457670,
    "comments": null,
    "views": 16807599978,
    "shares": null,
    "reposts": null,
    "replies": null,
    "reactions": null
  },
  "meta": {},
  "error": null
}
```

Desteklenmeyen platformlar `success: false` ile hata mesaji dondurur:

```bash
curl "http://localhost:8000/fetch?url=https://reddit.com/r/test"
```

```json
{
  "success": false,
  "platform": null,
  "url": "https://reddit.com/r/test",
  "error": "Unsupported platform: reddit.com"
}
```

### `GET /health`

Saglik kontrolu.

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

---

## Docker

```bash
docker compose up -d
```

Sunucu 8000 portunda calisir:

```bash
curl http://localhost:8000/health
```

---

## Yapilandirma

`config/settings.yaml` (`config/settings.example.yaml`'dan kopyalayin):

```yaml
scrapling:
  headless: true          # false = tarayici penceresini goster
  max_sessions: 3         # eszamanli tarayici oturumu (~400-500MB RAM)
  timeout: 60000          # sayfa basina maksimum bekleme (ms)
  solve_cloudflare: true  # Cloudflare bypass
  block_webrtc: true      # WebRTC sizinti engellemesi
  hide_canvas: true       # Canvas parmak izi gizleme

rate_limiting:
  default_delay: 2.0      # istek arasindaki bekleme (saniye)
  per_domain:
    instagram.com: 4.0
    x.com: 3.0
    youtube.com: 2.0

scraper:
  concurrency: 10         # paralel istek siniri

server:
  host: "0.0.0.0"
  port: 8000

proxies:
  rotation_strategy: "round_robin"  # round_robin | random | least_used
  pool:
    - server: "http://proxy1.example.com:8080"
      username: "user"
      password: "pass"
```

---

## Yeni Platform Ekleme

`src/platform_selectors.py` icindeki `PLATFORM_DEFS` sozlugune ekleyin:

```python
"ornek.com": PlatformDef(
    domain="ornek.com",
    wait_selector=".metric-element",
    network_idle=False,
    metrics={
        "likes": [
            SelectorDef(
                selector=r'"likeCount"\s*:\s*(\d+)',
                method="regex",
                transform="parse_number",
            ),
        ],
    },
),
```

Test icin:

```bash
python scripts/test_mapping.py https://ornek.com/bir-gonderi
```

### Secici Metodlari

| Metod | Kullanim |
|---|---|
| `css` | CSS secici, metin veya attribute cikarir |
| `xpath` | XPath ifadesi, ilk esleme |
| `regex` | Ham HTML uzerinde `re.search`; grup 1 veya tam esleme |
| `js_eval` | Playwright `page.evaluate()` — canli DOM |
| `css_json_path` | CSS ile bulunup JSON olarak parse, `json_path` ile alan erisimi |

### Donusumler

| Transform | Aciklama |
|---|---|
| `parse_number` | `"1,234"` -> `1234` / `"16,807,599,978"` -> `16807599978` |
| `identity` | Ham string olarak dondurur (kullanici adi gibi metin metrikler icin) |

---

## Mimari

```
src/
  server.py             FastAPI HTTP sunucusu (/fetch, /health)
  scraper.py            Rate-limited tekil URL kaziyici
  scrapling_pool.py     Stealth + Dynamic tarayici oturum havuzu
  platform_selectors.py Platform tanimlari (seciciler, page_action'lar)
  extractor.py          SelectorDef dispatch ve metrik cikarma
  transforms.py         Ham metin -> sayisal/string deger donusumleri
  config.py             YAML yapilandirma, ortam degiskeni cozumleme
  models.py             Pydantic veri modelleri
  proxy_pool.py         Proxy rotasyonu
  rate_limiter.py       Domain basina hiz sinirlandirma
  logging_config.py     structlog kurulumu
scripts/
  test_mapping.py       Tek URL test araci
tests/                  56 birim testi
config/
  settings.yaml         Yapilandirma dosyasi
Dockerfile
docker-compose.yml
```

---

## Testler

```bash
pytest

# Coverage raporu ile
pytest --cov=src --cov-report=term-missing
```
