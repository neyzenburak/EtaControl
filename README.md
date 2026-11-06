# EtaControl

Windows üzerinde çalışan, kuruma özel terminal işleyişini yerel bir paket üzerinden yükleyen kayıt ve Excel otomasyon altyapısı.

Ortak kurulum, güncelleme, kayıt saklama, dosya üretimi ve paket doğrulama kodu bu depodadır. Gerçek ekran adları, alan eşlemeleri, bağlantı işleyişi ve kuruma özel arayüz ayrı dağıtılan **kurum paketindedir**. Çalışan kurum uygulamasının bütün kaynakları bu public depoda bulunmaz.

## Operasyon için hızlı kurulum

Gereksinimler:

- Windows ve PowerShell 5.1 veya üzeri.
- Python 3.10–3.13 (python.org veya Microsoft Store kurulumu). Python 3.14 ve üzeri bu sürümde desteklenmez.
- Python bağımlılıklarını indirmek için internet veya kurumsal paket deposu erişimi.
- Yetkili kişiden alınan `EtaControl_KurumPaketi.zip` dosyası.
- Canlı terminal bağlantısı kullanılacaksa kurumun terminal istemcisi ve gerekli oturum yetkisi.

### 1. Depoyu al

Git kuruluysa:

```powershell
git clone https://github.com/neyzenburak/EtaControl.git
cd EtaControl
```

Git bulunmuyorsa GitHub'daki **Code → Download ZIP** seçeneğini bir kez kullanıp klasörü açabilirsiniz. Sonraki güncellemeler için yeniden elle ZIP indirmeniz gerekmez.

### 2. Kurum paketini kopyala

Dosyayı açmadan aşağıdaki konuma koyun:

```text
EtaControl/
  KURULUM.ps1
  ETA_Control.cmd
  kurum/
    EtaControl_KurumPaketi.zip
```

Bu dosya GitHub'da bulunmaz; yetkili kişi kurum içi kanaldan dağıtır. Paket DB, kaynak Excel veya kişi listesi yerine kuruma özel çalışma zamanı ve tanımları taşır.

### 3. Kurulumu çalıştır

Uygulamayı kapatın. Proje klasöründe PowerShell açıp çalıştırın:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\KURULUM.ps1
```

Kurulum proje içindeki `.venv` ortamını oluşturur, bağımlılıkları yükler, kurum paketini doğrular, Excel üretimini geçici dosyalarla sınar ve uygulamayı açar. Sonraki açılışlarda `ETA_Control.cmd` kullanılabilir.

Kurulumu uygulamayı açmadan sınamak için:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\KURULUM.ps1 -NoStart
```

Python otomatik bulunamazsa:

Kurulum; mevcut sanal ortamı, PATH üzerindeki `python` / `python3` / sürümlü komutları, `py` başlatıcısını ve kullanıcıya kayıtlı Microsoft Store Python paketlerini kontrol eder. `WindowsApps` yolu tek başına ret nedeni değildir: bulunan yorumlayıcının gerçekten çalışması ve sürümünün uygun olması gerekir. Yalnız Store indirme sayfasını açan boş takma adlar Python kurulumu sayılmaz. Store kurulumu görünmüyorsa Windows **Uygulama yürütme diğer adları** ayarından Python paketinin takma adlarını kontrol edin.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\KURULUM.ps1 -PythonExe "D:\Python312\python.exe"
```

Python keşfi başarısız olursa sürüm, erişim ve çalıştırma hatalarını görmek için aşağıdaki salt okunur komutu kullanın. Kurum paketi gerektirmez; kurulum yapmaz:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\KURULUM.ps1 -PythonTani
```

## Güncelleme

Kurum paketi yerinde kalır. Uygulamayı kapatıp çalıştırın:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\GUNCELLE.ps1
```

Git ile kurulmuş kopyalarda temiz çalışma ağacı kontrol edilir ve yalnız hızlı ileri güncelleme yapılır. ZIP ile kurulmuş kopyalarda kaynak GitHub'dan otomatik indirilir; değiştirilen eski kodlar `data/guncelleme_yedekleri` altında yedeklenir. Kurum paketi, yerel kayıtlar ve Python ortamı kaynak paketiyle değiştirilmez. Ardından kurulum kontrolü yeniden çalışır.

Belirli bir commit kullanılacaksa `-Ref` parametresine 40 karakterlik commit kimliği verilebilir. Git kopyasında bu işlem ayrık HEAD durumuna geçer. Normal kullanım `main` dalıdır.

Ortak altyapı değişiklikleri GitHub'dan gelir. Kuruma özel işleyiş veya tanımlar değişirse yetkili kişi yeni kurum paketini ayrıca dağıtır; paket değiştirilince `KURULUM.ps1` yeniden çalıştırılır.

## Mimari

```text
Ortak kaynak kodu                    Yerel kurum alanı
----------------                    ----------------
KURULUM.ps1                         kurum/kurum paketi
GUNCELLE.ps1                              |
etacontrol/institution.py  <--- doğrulama ve hazırlama
         |                               |
         +--------------------> .yerel/<paket-özeti>/runtime
                                         |
etacontrol/storage.py   <------ kurum işleyişi
etacontrol/reports.py   <------ rapor projeksiyonları
                                         |
                                     data/yerel kayıtlar
```

| Bileşen | Sorumluluk |
| --- | --- |
| `etacontrol/institution.py` | Yerel ZIP manifestini, SHA-256 özetlerini, dosya yollarını ve boyut sınırlarını doğrular. Doğrulanmış paketi sürümlü yerel dizine hazırlar. |
| `etacontrol/processes.py` | Kayıtlı süreç kimliği, başlangıç zamanı ve çalıştırılan dosyanın kurulum köküne ait olduğunu denetler. Aktif terminal işi varsa sunucuyu durdurmaz. |
| `etacontrol/storage.py` | SQLite bağlantıları, çalışma/kayıt ayrımı, atomik içe aktarma, iş durumları, planlar ve olay günlüğü için ortak saklama katmanı. |
| `etacontrol/reports.py` | Kurumdan bağımsız tablo oluşturma, metin kimliklerini koruma, tarih biçimleri, filtreler, sabit başlıklar ve atomik XLSX kaydı. |
| `etacontrol/__main__.py` | Kurum çalışma zamanını uygun yerel veri dizini ve modül arama yolu ile başlatır. |
| Kurum paketi | Terminal bağdaştırıcısı, alan tanımları, veri toplama/öneri akışları ve kuruma özel arayüz. Bu içerik public değildir. |

### Dosyaların yaşam döngüsü

| Konum | İçerik | Git'e girer mi? |
| --- | --- | --- |
| `etacontrol/`, `scripts/`, `tests/` | Ortak kaynak ve tamamen sentetik testler | Evet |
| `kurum/README.md` | Paket yerleştirme açıklaması | Evet |
| `kurum/*.zip` | Kuruma özel paket | Hayır |
| `.yerel/` | Doğrulanmış çalışma zamanı, indirme önbelleği ve önceki paket sürümleri | Hayır |
| `data/` | DB, iş günlüğü, kaynak kayıtları, çıktılar ve yerel yedekler | Hayır |
| `.venv/`, `runtime.json` | Bu bilgisayara özel Python ortamı ve yollar | Hayır |

### Paket sözleşmesi

Kurum ZIP'inin kökünde `manifest.json` bulunur. Manifest `format_version`, `adapter_version` ve dosya yolu → SHA-256 eşlemesini içeren `files` alanını taşır. Çalışma zamanı dosyaları yalnız `runtime/` altında bulunabilir. Manifestte olmayan dosya, bozuk özet, üst dizine çıkan yol, sembolik bağlantı veya desteklenmeyen biçim reddedilir.

SHA-256 kontrolü paketin içerik bütünlüğünü denetler; gönderen kişinin kimliğini doğrulayan elektronik imza değildir. Paket yetkili kurum içi dağıtım kanalından alınmalıdır. Kurulum paketteki Python kodunu çalıştırır.

Yükleme önce geçici yerel dizinde tamamlanır; hazır dizine geçiş sonradan yapılır. Önceki bozuk veya değiştirilmiş yerel kopya silinmeden yeniden adlandırılır. Aynı sağlam paket tekrar kurulduğunda yeniden açılmaz.

## Kayıt ve Excel davranışı

Ortak saklama katmanı `meta`, `suppliers`, `runs`, `shipments`, `jobs`, `plans`, `plan_items` ve `events` tablolarını yönetir. Bir kayıt tek başına kimlik alanıyla eşleştirilmez; çalışma ve kayıt anahtarı birlikte kullanılır. Birden çok kurum uyarlaması aynı ortak modeli kullanabilir; kurumun ek tabloları özel çalışma zamanında tanımlanır.

Doğrulanmış içe aktarma tek transaction içinde yayımlanır. Başarısız veya iptal edilmiş aktarım mevcut kayıtları değiştirmez. SQLite dosyası, Excel çıktıları ve hata günlükleri kullanıcı bilgisayarında kalır.

Excel motoru `openpyxl` kullanır; Node.js, harici bir belge çalışma zamanı veya masaüstü Excel kurulumu gerektirmez. Numara gibi görünen kimlikler metin olarak tutulur. Dış kaynaklı hücre metinleri formül olarak çalıştırılmaz. Kurum projeksiyonu tarafından verilen tablo başlıkları ve satırlar biçimlendirilip geçici dosyaya yazılır, dosya tamamlanınca hedefe taşınır. Rapora özgü anlamlar ve gerçek örnekler bu repoda tutulmaz.

## Yerel servis ve çalışma güvenliği

Kurum uygulaması yalnız yerel bilgisayara bağlanacak biçimde çalıştırılır. Genel başlatma işlemi `ETA_CONTROL_DATA` değişkenini kurulumun `data/` klasörüne ayarlar; kurum çalışma zamanı güncellense de veri konumu değişmez.

Kurum sürümünün HTTP arayüzü, arka plan işleri ve yetki kontrolleri özel pakettedir. Ortak güncelleyici yerel iş durumunu okur; aktif terminal işi varken dosya güncellemesine başlamaz. Kurulum veya güncelleme terminalde işletme kaydı değiştirmek için bir komut göndermez. Canlı ekranlar yalnız yetkili kurum işleyişi başlatıldığında kullanılır.

`DURDUR.cmd` yalnız aynı kurulum köküne ait ve kimliği doğrulanmış sunucuyu durdurur. Başka dizindeki veya yeniden kullanılmış PID'ye sahip süreç durdurulmaz.

## Sorun giderme

| Durum | Yapılacak işlem |
| --- | --- |
| Kurum paketi eksik | Yetkiliden alınan ZIP'i `kurum/` klasörüne koyun. Dosyayı açmadan kurulumu yeniden çalıştırın. |
| Python bulunamıyor | Desteklenen Python sürümünü kurun veya `-PythonExe` parametresini kullanın. |
| Pip indirmesi başarısız | Konsoldaki hata ile internet, proxy veya kurum paket deposu erişimini kontrol edin. |
| Excel üretimi başarısız | Aynı klasörde `KURULUM.ps1 -NoStart` çalıştırın; kurulum Excel önkoşullarını tekrar sınar. |
| Aktif iş nedeniyle güncelleme reddedildi | Çekimin bitmesini veya uygulama içindeki güvenli durdurmanın tamamlanmasını bekleyin. |
| İşletme girdileri görünmüyor | Yerel `data/` klasörünü ve kurumun kaynak dosya ayarlarını kontrol edin. Public repo gerçek işletme verisi içermez. |
| Paket değiştirildi veya bozuldu | Yetkili kaynaktan tekrar alın; manifest kontrolünü devre dışı bırakmayın. |

## Geliştirme ve test

Kurum paketi olmadan ortak katmanın testleri çalıştırılabilir:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\yayin_denetimi.py
```

Testler sentetiktir; gerçek terminale bağlanmaz. Paket yokluğu, dosya yolu ihlali, bozuk özet, tekrar yükleme, yerel dosya onarımı, kayıt ayrımı, metin hücreleri ve tarih dönüşümü kontrol edilir. GitHub Actions yalnız public ortak katmanı test eder; kurum dosyası veya işletme verisi CI'a gönderilmez.

## Yayın kuralları

- Kurum paketi, gerçek ekran görüntüsü, alan eşlemesi, DB, kaynak Excel, makro dosyası veya kullanıcıya özel yol commit edilmez.
- Testler ve örnekler tamamen sentetik olmalıdır.
- `.gitignore` ve `scripts/yayin_denetimi.py` ilk koruma katmanlarıdır. Yayın sorumlusu gerektiğinde kurum içinde tutulan özel sözcük listesiyle ek denetim çalıştırır.
- Yeni bir dağıtım hazırlarken yalnız Git ile izlenen kaynakları kullanın. Yerel klasörün tamamını paketlemeyin.
- Hata bildirimine gerçek kayıt, kişi adı veya ekran dökümü eklemeyin. [Güvenlik bildirimi](SECURITY.md).
