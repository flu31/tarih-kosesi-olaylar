# 📅 Tarih Köşesi

Windows masaüstü widget'ı — her saat başı farklı bir tarihi olay gösterir.

---

## Özellikler

- Her saat başı yeni bir tarihi olay gösterilir
- 2000+ olaylık veritabanı — GitHub'dan otomatik güncellenir
- Çağa göre renk değişimi (Prehistorik → Yakın Çağ)
- Sol kenarda çağ rengi şeridi
- Sıradaki olayın yılını gösterir (üzerine gelince)
- Masaüstüne gömülü — Masaüstünü Göster butonundan etkilenmez
- Kilit butonu ile konumu sabitle
- Sürükleyerek istediğin yere taşı
- Olay değişince ses çalar (tada.wav)
- Sistem tepsisinde çalışır

---

## Kurulum

### Hazır EXE (Kolay)

1. [Releases](../../releases) sayfasından `TarihKosesi.exe` dosyasını indir
2. İstediğin klasöre koy ve çalıştır
3. Hepsi bu kadar — ek dosya gerekmez

### Kaynak Koddan Çalıştırma

**Gereksinimler:**
- Python 3.9+
- PyQt5

```bash
pip install PyQt5
python widget.py
```

### EXE Olarak Derleme

```bash
pip install pyinstaller
python -m PyInstaller widget.spec
```

---

## Kullanım

| Eylem | Nasıl |
|-------|-------|
| Taşımak | Widget'ı sürükle |
| Sabitlemek | İğne butonuna tıkla |
| Gizlemek | ✕ butonuna tıkla |
| Ayarlar | ≡ butonuna tıkla |
| Tray menüsü | Sistem tepsisindeki ikona sağ tıkla |

---

## Ayarlar

- **Opaklık** — Widget'ın saydamlığını ayarla
- **Köşe stili** — Yuvarlak, Keskin, Tek köşe
- **Yazı tipi** — Varsayılan, Serif, Mono
- **Tema** — Çağ renkleri, Açık, Koyu
- **Sol şerit** — Çağ renginde ince şerit
- **Başlangıçta çalıştır** — Windows açılışında başlat
- **Olay sesi** — Saat başı ses çalsın/çalmasın

---

## Olay Veritabanı

Olaylar [ayrı bir repoda](https://github.com/flu31/tarih-kosesi-olaylar) tutulmaktadır. Uygulama her açılışta GitHub'dan kontrol eder — yeni olay eklenirse otomatik indirilir.

Katkıda bulunmak için olay reposuna PR açabilirsin.

---

## Gereksinimler

- Windows 10/11 (64-bit)
- Ek kurulum gerekmez (EXE versiyonu için)

---

## Lisans

MIT License — dilediğin gibi kullan, değiştir, dağıt.
