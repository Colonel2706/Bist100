"""
BIST100 Günlük Hisse Tarayıcı — İş Yatırım Versiyonu
======================================================
Teknik veri    : İş Yatırım API (fiyat, hacim)
Temel veri     : İş Yatırım API (F/K, PD/DD)
Momentum       : İş Yatırım fiyat geçmişinden hesaplanır
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

TOP_N = 10

# ─────────────────────────────────────────────
# BIST100 HİSSELERİ
# ─────────────────────────────────────────────
BIST100 = [
    "AKBNK","AKSEN","ALARK","ARCLK","ASELS","BIMAS","EKGYO",
    "ENKAI","EREGL","FROTO","GARAN","GUBRF","HALKB","ISCTR",
    "KCHOL","KOZAA","KOZAL","KRDMD","MGROS","ODAS","OTKAR",
    "OYAKC","PETKM","PGSUS","SAHOL","SASA","SISE","SOKM",
    "TAVHL","TCELL","THYAO","TKFEN","TOASO","TTKOM","TTRAK",
    "TUPRS","VAKBN","VESBE","YKBNK","ZOREN","AGHOL","AGESA",
    "ALKIM","ANACM","ASUZU","AYGAZ","BIENY","BRSAN","CCOLA",
    "CIMSA","CLEBI","DOAS","DYOBY","EGEEN","ENJSA","ESEN",
    "EUPWR","FENER","GOLTS","GRSEL","GSDHO","HEKTS","IPEKE",
    "ISGYO","ISKUR","KARTN","KARSN","KATMR","KLNMA","KONTR",
    "KONYA","LOGO","MAVI","MPARK","NETAS","NUHCM","PARSN",
    "PRKAB","PRKME","QUAGR","RTALB","RUBNS","SARKY","SKBNK",
    "SMART","SMRTG","SNGYO","TSKB","ULKER","VESTL","YEOTK",
    "YYLGD","ZRGYO"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.isyatirim.com.tr"
}

# ─────────────────────────────────────────────
# İŞ YATIRIM API FONKSİYONLARI
# ─────────────────────────────────────────────

def fiyat_gecmisi(sembol, gun=66):
    bitis     = datetime.today()
    baslangic = bitis - timedelta(days=gun * 2)
    url = (
        f"https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil"
        f"?hisse={sembol}"
        f"&startdate={baslangic.strftime('%d-%m-%Y')}"
        f"&enddate={bitis.strftime('%d-%m-%Y')}.json"
    )
    try:
        r  = requests.get(url, headers=HEADERS, timeout=10)
        df = pd.DataFrame(r.json()["value"])
        if df.empty:
            return None
        df = df[["HGDG_TARIH","HGDG_KAPANIS","HGDG_HACIM"]].copy()
        df.columns = ["Tarih","Kapanis","Hacim"]
        df["Kapanis"] = pd.to_numeric(df["Kapanis"], errors="coerce")
        df["Hacim"]   = pd.to_numeric(df["Hacim"],   errors="coerce")
        return df.dropna().tail(gun)
    except:
        return None

def temel_veriler():
    url = (
        "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/MomentumStok"
        "?endeks=XU100&fields=HISSE_KODU,FK,PDDD.json"
    )
    try:
        r  = requests.get(url, headers=HEADERS, timeout=15)
        df = pd.DataFrame(r.json()["value"])
        df.columns = [c.upper() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

# ─────────────────────────────────────────────
# ANALİZ FONKSİYONLARI
# ─────────────────────────────────────────────

def rsi_hesapla(seri, periyot=14):
    delta  = seri.diff()
    kazanc = delta.clip(lower=0)
    kayip  = -delta.clip(upper=0)
    rs     = kazanc.rolling(periyot).mean() / (kayip.rolling(periyot).mean() + 1e-9)
    return 100 - (100 / (1 + rs))

def teknik_skor(df):
    if df is None or len(df) < 30:
        return 0, {}
    kapat = df["Kapanis"]
    hacim = df["Hacim"]
    r     = rsi_hesapla(kapat).iloc[-1]
    ema20 = kapat.ewm(span=20).mean().iloc[-1]
    ema50 = kapat.ewm(span=50).mean().iloc[-1]
    ort_h = hacim.rolling(20).mean().iloc[-1]
    son_h = hacim.iloc[-1]
    puan  = 0
    detay = {}
    if 30 < r < 55:
        puan += 1; detay["RSI"] = f"{r:.1f} ✅"
    else:
        detay["RSI"] = f"{r:.1f}"
    if ema20 > ema50:
        puan += 1; detay["Trend"] = "Yükselen ✅"
    else:
        detay["Trend"] = "Düşen"
    if son_h > ort_h * 1.2:
        puan += 1; detay["Hacim"] = "Yüksek ✅"
    else:
        detay["Hacim"] = "Normal"
    return puan, detay

def momentum_skor(df):
    if df is None or len(df) < 6:
        return 0, {}
    kapat    = df["Kapanis"]
    haftalik = (kapat.iloc[-1] / kapat.iloc[-6]  - 1) * 100 if len(df) >= 6  else 0
    aylik    = (kapat.iloc[-1] / kapat.iloc[-22] - 1) * 100 if len(df) >= 22 else 0
    puan  = 0
    detay = {"1H": f"%{haftalik:.1f}", "1A": f"%{aylik:.1f}"}
    if haftalik > 0: puan += 1
    if aylik    > 0: puan += 1
    return puan, detay

def temel_skor_hesapla(fk, pddd):
    puan = 0; detay = {}
    try:
        v = float(fk)
        detay["F/K"] = f"{v:.1f} ✅" if 0 < v < 15 else f"{v:.1f}"
        if 0 < v < 15: puan += 1
    except:
        detay["F/K"] = "N/A"
    try:
        v = float(pddd)
        detay["PD/DD"] = f"{v:.2f} ✅" if 0 < v < 2 else f"{v:.2f}"
        if 0 < v < 2: puan += 1
    except:
        detay["PD/DD"] = "N/A"
    return puan, detay

# ─────────────────────────────────────────────
# ANA TARAMA
# ─────────────────────────────────────────────

def tara():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] İş Yatırım verileriyle BIST100 taranıyor...")

    df_temel   = temel_veriler()
    temel_dict = {}
    if not df_temel.empty:
        for _, row in df_temel.iterrows():
            kod = str(row.get("HISSE_KODU","")).strip()
            temel_dict[kod] = {"FK": row.get("FK"), "PDDD": row.get("PDDD")}

    sonuclar = []
    for sembol in BIST100:
        try:
            df = fiyat_gecmisi(sembol)
            if df is None or df.empty:
                continue
            t_puan, t_detay = teknik_skor(df)
            m_puan, m_detay = momentum_skor(df)
            bilgi           = temel_dict.get(sembol, {})
            f_puan, f_detay = temel_skor_hesapla(bilgi.get("FK"), bilgi.get("PDDD"))
            sonuclar.append({
                "Hisse":   sembol,
                "Fiyat":   df["Kapanis"].iloc[-1],
                "Toplam":  t_puan + m_puan + f_puan,
                "RSI":     t_detay.get("RSI",""),
                "Trend":   t_detay.get("Trend",""),
                "Hacim":   t_detay.get("Hacim",""),
                "1H":      m_detay.get("1H",""),
                "1A":      m_detay.get("1A",""),
                "F/K":     f_detay.get("F/K",""),
                "PD/DD":   f_detay.get("PD/DD",""),
            })
            print(f"  ✓ {sembol}: {t_puan+m_puan+f_puan}/7")
        except Exception as e:
            print(f"  ✗ {sembol}: {e}")

    df_sonuc = pd.DataFrame(sonuclar)
    df_sonuc = df_sonuc.sort_values("Toplam", ascending=False).head(TOP_N).reset_index(drop=True)
    df_sonuc.index += 1
    return df_sonuc

# ─────────────────────────────────────────────
# ÇALIŞTIR
# ─────────────────────────────────────────────

if __name__ == "__main__":
    df = tara()
    print("\n" + "="*72)
    print(f"  BIST100 GÜNLÜK TARAMA — {datetime.now().strftime('%d.%m.%Y')}")
    print(f"  Yükselme Potansiyeli En Yüksek {TOP_N} Hisse")
    print("="*72)
    print(f"{'#':<4} {'Hisse':<8} {'Fiyat':>8} {'Skor':>5} {'RSI':>7} {'Trend':<15} {'1H':>6} {'1A':>6} {'F/K':>6} {'PD/DD':>7}")
    print("-"*72)
    for i, r in df.iterrows():
        print(f"{i:<4} {r['Hisse']:<8} {r['Fiyat']:>8.2f} {r['Toplam']:>5} {r['RSI']:>7} {r['Trend']:<15} {r['1H']:>6} {r['1A']:>6} {r['F/K']:>6} {r['PD/DD']:>7}")
    print("="*72)
    print("⚠️  Bu liste yatırım tavsiyesi değildir.")
