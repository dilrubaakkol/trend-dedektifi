-- Trend Dedektifi veri tabanı şeması (MS SQL Server). Kurulum: python app/db/kur.py
-- Her blok "GO" ile ayrılır ve tekrar çalıştırılabilir (tablo varsa dokunmaz).
-- Şifreler düz metin tutulmaz: sifre_ozeti = PBKDF2-SHA256 özeti (app/auth.py).
-- Trend tablolarının sütunları ekip belgesindeki CSV sütunlarıyla birebir aynıdır.

IF OBJECT_ID('dbo.kullanicilar') IS NULL
CREATE TABLE dbo.kullanicilar (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    rol           NVARCHAR(20)  NOT NULL CHECK (rol IN (N'vatandas', N'akademisyen')),
    ad            NVARCHAR(120) NOT NULL,
    kurum         NVARCHAR(200) NULL,
    eposta        NVARCHAR(200) NULL,
    orcid         VARCHAR(19)   NULL,
    sifre_ozeti   VARCHAR(200)  NULL,
    kurum_eposta  BIT           NOT NULL DEFAULT 0,
    ornek         BIT           NOT NULL DEFAULT 0,   -- 1 = örnek (kurgusal) kayıt
    olusturma     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    son_giris     DATETIME2     NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_kullanicilar_eposta')
CREATE UNIQUE INDEX ux_kullanicilar_eposta ON dbo.kullanicilar (eposta) WHERE eposta IS NOT NULL;
GO

IF OBJECT_ID('dbo.makaleler') IS NULL
CREATE TABLE dbo.makaleler (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    kullanici_id  INT            NOT NULL REFERENCES dbo.kullanicilar(id) ON DELETE CASCADE,
    baslik        NVARCHAR(400)  NOT NULL,
    yazarlar      NVARCHAR(400)  NOT NULL,
    dergi         NVARCHAR(200)  NULL,
    yil           SMALLINT       NULL,
    doi           VARCHAR(200)   NULL,
    ozet          NVARCHAR(MAX)  NULL,
    degiskenler   NVARCHAR(400)  NULL,   -- virgülle: sicaklik_2m,kar_ortusu
    iller         NVARCHAR(800)  NULL,   -- virgülle: Erzurum,Kars
    veri_surumu   VARCHAR(20)    NULL,   -- kullanılan veri seti sürümü (ör. v0.1)
    durum         NVARCHAR(30)   NOT NULL DEFAULT N'yayimlandi'
                  CHECK (durum IN (N'hazirlaniyor', N'degerlendirmede', N'yayimlandi')),
    ornek         BIT            NOT NULL DEFAULT 0,
    olusturma     DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF OBJECT_ID('dbo.indirmeler') IS NULL
CREATE TABLE dbo.indirmeler (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    kullanici_id  INT           NULL REFERENCES dbo.kullanicilar(id) ON DELETE SET NULL,
    tarih         DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    dosya         NVARCHAR(200) NOT NULL,
    satir_sayisi  INT           NULL,
    secim         NVARCHAR(MAX) NULL     -- JSON: değişkenler, mevsimler, iller
);
GO

IF OBJECT_ID('dbo.trend_iller') IS NULL
CREATE TABLE dbo.trend_iller (
    id INT IDENTITY(1,1) PRIMARY KEY,
    il NVARCHAR(60) NOT NULL, plaka TINYINT NOT NULL, bolge VARCHAR(40) NULL,
    degisken VARCHAR(60) NOT NULL, urun VARCHAR(80) NOT NULL, mevsim VARCHAR(20) NOT NULL, donem VARCHAR(20) NULL,
    n_yil SMALLINT NULL, n_hucre INT NULL, egim_10yil FLOAT NULL, ci_alt FLOAT NULL, ci_ust FLOAT NULL,
    birim NVARCHAR(40) NULL, p_mk FLOAT NULL, p_mk_kontrol FLOAT NULL, p_ttest FLOAT NULL,
    belirsiz BIT NULL, anlamli_fdr BIT NULL, yil_sayisi_gereken FLOAT NULL, kaynak_uyumu VARCHAR(10) NULL,
    veri_surumu VARCHAR(20) NOT NULL, yer_tutucu BIT NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_trend_iller_secim')
CREATE INDEX ix_trend_iller_secim ON dbo.trend_iller (degisken, mevsim, urun);
GO

IF OBJECT_ID('dbo.trend_bolgeler') IS NULL
CREATE TABLE dbo.trend_bolgeler (
    id INT IDENTITY(1,1) PRIMARY KEY,
    bolge VARCHAR(40) NOT NULL,
    degisken VARCHAR(60) NOT NULL, urun VARCHAR(80) NOT NULL, mevsim VARCHAR(20) NOT NULL, donem VARCHAR(20) NULL,
    n_yil SMALLINT NULL, n_hucre INT NULL, egim_10yil FLOAT NULL, ci_alt FLOAT NULL, ci_ust FLOAT NULL,
    birim NVARCHAR(40) NULL, p_mk FLOAT NULL, p_mk_kontrol FLOAT NULL, p_ttest FLOAT NULL,
    belirsiz BIT NULL, anlamli_fdr BIT NULL, yil_sayisi_gereken FLOAT NULL, kaynak_uyumu VARCHAR(10) NULL,
    veri_surumu VARCHAR(20) NOT NULL, yer_tutucu BIT NOT NULL
);
GO

-- Uyarı rozetleri için L3 alanları (sözleşme 2.2); eski kurulumlara da eklenir.
IF COL_LENGTH('dbo.trend_iller', 'trend_uyarisi') IS NULL
ALTER TABLE dbo.trend_iller ADD p_fdr FLOAT NULL, anlamli SMALLINT NULL, etkin_n FLOAT NULL,
    trend_uyarisi NVARCHAR(600) NULL, dogrulanmadi NVARCHAR(10) NULL, kademe TINYINT NULL, [not] NVARCHAR(200) NULL;
GO
IF COL_LENGTH('dbo.trend_bolgeler', 'trend_uyarisi') IS NULL
ALTER TABLE dbo.trend_bolgeler ADD p_fdr FLOAT NULL, anlamli SMALLINT NULL, etkin_n FLOAT NULL,
    trend_uyarisi NVARCHAR(600) NULL, dogrulanmadi NVARCHAR(10) NULL, kademe TINYINT NULL, [not] NVARCHAR(200) NULL;
GO

-- Eski taslak tablo (iliski_iller) sözleşme 2.3 ile ciftler oldu; yalnız yer tutucu veri taşıyordu.
IF OBJECT_ID('dbo.iliski_iller') IS NOT NULL DROP TABLE dbo.iliski_iller;
GO
-- L4_iliski/ciftler.csv ile aynı sütunlar (docs/sozlesmeler.md 2.3). İl, bölge ve Türkiye satırları birlikte.
IF OBJECT_ID('dbo.ciftler') IS NULL
CREATE TABLE dbo.ciftler (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cift_no TINYINT NOT NULL, cift VARCHAR(160) NULL, degisken_1 VARCHAR(60) NOT NULL, degisken_2 VARCHAR(60) NOT NULL,
    seri VARCHAR(40) NULL, gecikme_ay TINYINT NULL, beklenen_yon VARCHAR(2) NULL,
    bolge_turu VARCHAR(10) NOT NULL, bolge_kodu NVARCHAR(40) NOT NULL, bolge_adi NVARCHAR(80) NULL,
    hucre_sayisi INT NULL, donem VARCHAR(20) NULL, n INT NULL, r FLOAT NULL, r1_1 FLOAT NULL, r1_2 FLOAT NULL,
    etkin_n FLOAT NULL, p FLOAT NULL, p_fdr FLOAT NULL, anlamli TINYINT NULL, etiket VARCHAR(20) NULL,
    [not] NVARCHAR(400) NULL, urun_surumu NVARCHAR(40) NULL, veri_seti_doi NVARCHAR(120) NULL, lisans NVARCHAR(40) NULL,
    kademe TINYINT NULL, dogrulanmadi NVARCHAR(10) NULL, doi_1 NVARCHAR(160) NULL, doi_2 NVARCHAR(160) NULL,
    veri_surumu VARCHAR(20) NOT NULL, yer_tutucu BIT NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ciftler_secim')
CREATE INDEX ix_ciftler_secim ON dbo.ciftler (cift_no, gecikme_ay, bolge_turu);
GO

IF OBJECT_ID('dbo.sifre_sifirlama') IS NULL
CREATE TABLE dbo.sifre_sifirlama (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    kullanici_id  INT          NOT NULL REFERENCES dbo.kullanicilar(id) ON DELETE CASCADE,
    kod_ozeti     VARCHAR(200) NOT NULL,          -- 6 haneli kodun PBKDF2 özeti (kod düz metin tutulmaz)
    son_gecerlilik DATETIME2   NOT NULL,          -- 15 dakika
    deneme        TINYINT      NOT NULL DEFAULT 0, -- en fazla 5 yanlış deneme
    kullanildi    BIT          NOT NULL DEFAULT 0,
    olusturma     DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
