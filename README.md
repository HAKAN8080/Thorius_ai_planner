# ⭐ Sanal Planner | Thorius AI4U

AI-Powered Retail Planning & Analytics

## Kurulum

```bash
cd "AI Agent"
pip install -r requirements.txt
```

## API Key Ayarı

**Yöntem 1 - Secrets dosyası (önerilen):**
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```
`secrets.toml` dosyasını açıp Anthropic API key'inizi girin.

**Yöntem 2 - Sidebar'dan giriş:**
Uygulamayı çalıştırın, sidebar'daki API Key alanına key'inizi yapıştırın.

API key almak için: https://console.anthropic.com/

## Veri Dosyaları

`AI Agent/data/` klasörüne Excel dosyalarınızı koyun:
- `AI CUBE ŞABLON.xlsx` (zorunlu - Trading verisi)
- `Özet Kapasite-*.xlsx` (opsiyonel - Kapasite analizi)

## Çalıştırma

```bash
cd "AI Agent"
streamlit run app_agent.py
```

## Admin Paneli

Sidebar'dan Admin Girişi yaparak:
- Veri dosyalarını güncelleyebilir
- Analiz kurallarını özelleştirebilir
- Yorum eğitimi ayarlayabilirsiniz
