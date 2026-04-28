"""
BIST100 Günlük Hisse Tarayıcı
==============================
Teknik + Temel + Momentum analizini birleştirerek her sabah
yükselme potansiyeli olan Top 10 hisseyi email ile gönderir.

KURULUM:
  pip install yfinance pandas numpy smtplib

KULLANIM:
  python bist100_screener.py

OTOMATİK ÇALIŞTIRMA:
  - Linux/Mac: crontab -e → 0 8 * * 1-5 /usr/bin/python3 /path/to/bist100_screener.py
  - Windows: Görev Zamanlayıcı (Task Scheduler) ile her sabah 08:00
  - Ücretsiz bulut: GitHub Actions (aşağıda .yml örneği mevcut)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# AYARLAR — sadece bu bölümü düzenle
# ─────────────────────────────────────────────
EMAIL_GONDEREN  = "senin_gmail@gmail.com"       # Gönderen Gmail adresi
EMAIL_SIFRE     = "xxxx xxxx xxxx xxxx"         # Gmail App Password (uygulama şifresi)
EMAIL_ALICI     = "arkasokaklar2727@gmail.com"  # Alıcı adresi
TOP_N           = 10                            # Kaç hisse listelensin

# ─────────────────────────────────────────────
# BIST100 HİSSELERİ
# ─────────────────────────────────────────────
BIST100 = [
    "AKBNK.IS","AKSEN.IS","ALARK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","EKGYO.IS",
    "ENKAI.IS","EREGL.IS","FROTO.IS","GARAN.IS","GUBRF.IS","HALKB.IS","ISCTR.IS",
    "KCHOL.IS","KOZAA.IS","KOZAL.IS","KRDMD.IS","MGROS.IS","ODAS.IS","OTKAR.IS",
    "OYAKC.IS","PETKM.IS","PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SOKM.IS",
    "TAVHL.IS","TCELL.IS","THYAO.IS","TKFEN.IS","TOASO.IS","TTKOM.IS","TTRAK.IS",
    "TUPRS.IS","VAKBN.IS","VESBE.IS","YKBNK.IS","ZOREN.IS","AGHOL.IS","AGESA.IS",
    "ALKIM.IS","ANACM.IS","ASUZU.IS","AYGAZ.IS","BIENY.IS","BRSAN.IS","CCOLA.IS",
    "CIMSA.IS","CLEBI.IS","DOAS.IS","DYOBY.IS","EGEEN.IS","ENJSA.IS","ESEN.IS",
    "EUPWR.IS","FENER.IS","GOLTS.IS","GRSEL.IS","GSDHO.IS","HEKTS.IS","IPEKE.IS",
    "ISGYO.IS","ISKUR.IS","KARTN.IS","KARSN.IS","KATMR.IS","KLNMA.IS","KONTR.IS",
    "KONYA.IS","LOGO.IS","MAVI.IS","MPARK.IS","NETAS.IS","NUHCM.IS","PARSN.IS",
    "PRKAB.IS","PRKME.IS","QUAGR.IS","RTALB.IS","RUBNS.IS","SARKY.IS","SKBNK.IS",
    "SMART.IS","SMRTG.IS","SNGYO.IS","TSKB.IS","ULKER.IS","VESTL.IS","YEOTK.IS",
    "YYLGD.IS","ZRGYO.IS"
]

# ─────────────────────────────────────────────
# ANALİZ FONKSİYONLARI
# ─────────────────────────────────────────────

def rsi(seri, periyot=14):
    delta = seri.diff()
    kazanc = delta.clip(lower=0)
    kayip  = -delta.clip(upper=0)
    ort_k  = kazanc.rolling(periyot).mean()
    ort_z  = kayip.rolling(periyot).mean()
    rs     = ort_k / (ort_z + 1e-9)
    return 100 - (100 / (1 + rs))

def teknik_skor(df):
    """RSI, EMA crossover, hacim artışı → 0-3 puan"""
    if df is None or len(df) < 30:
        return 0, {}
    kapat = df["Close"].squeeze()
    hacim = df["Volume"].squeeze()
    r = rsi(kapat).iloc[-1]
    ema20 = kapat.ewm(span=20).mean().iloc[-1]
    ema50 = kapat.ewm(span=50).mean().iloc[-1]
    ort_hacim = hacim.rolling(20).mean().iloc[-1]
    son_hacim = hacim.iloc[-1]

    puan = 0
    detay = {}
    # RSI 30-50 bandı → aşırı satım çıkışı
    if 30 < r < 55:
        puan += 1
        detay["RSI"] = f"{r:.1f} ✅"
    else:
        detay["RSI"] = f"{r:.1f}"
    # EMA20 > EMA50 → yükselen trend
    if ema20 > ema50:
        puan += 1
        detay["Trend"] = "Yükselen ✅"
    else:
        detay["Trend"] = "Düşen"
    # Hacim ortalamanın üstünde
    if son_hacim > ort_hacim * 1.2:
        puan += 1
        detay["Hacim"] = "Yüksek ✅"
    else:
        detay["Hacim"] = "Normal"
    return puan, detay

def momentum_skor(df):
    """1 haftalık ve 1 aylık getiri → 0-2 puan"""
    if df is None or len(df) < 22:
        return 0, {}
    kapat = df["Close"].squeeze()
    haftalik = (kapat.iloc[-1] / kapat.iloc[-6] - 1) * 100
    aylik    = (kapat.iloc[-1] / kapat.iloc[-22] - 1) * 100
    puan = 0
    detay = {"1H": f"%{haftalik:.1f}", "1A": f"%{aylik:.1f}"}
    if haftalik > 0:
        puan += 1
    if aylik > 0:
        puan += 1
    return puan, detay

def temel_skor(ticker_obj):
    """F/K ve PD/DD oranları → 0-2 puan"""
    try:
        info = ticker_obj.info
        fk   = info.get("trailingPE", None)
        pddd = info.get("priceToBook", None)
        puan = 0
        detay = {}
        if fk and 0 < fk < 15:
            puan += 1
            detay["F/K"] = f"{fk:.1f} ✅"
        elif fk:
            detay["F/K"] = f"{fk:.1f}"
        else:
            detay["F/K"] = "N/A"
        if pddd and 0 < pddd < 2:
            puan += 1
            detay["PD/DD"] = f"{pddd:.2f} ✅"
        elif pddd:
            detay["PD/DD"] = f"{pddd:.2f}"
        else:
            detay["PD/DD"] = "N/A"
        return puan, detay
    except:
        return 0, {"F/K": "N/A", "PD/DD": "N/A"}

# ─────────────────────────────────────────────
# ANA TARAMA
# ─────────────────────────────────────────────

def tara():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] BIST100 taranıyor...")
    sonuclar = []

    for sembol in BIST100:
        try:
            t  = yf.Ticker(sembol)
            df = t.history(period="3mo")
            if df.empty:
                continue

            t_puan, t_detay = teknik_skor(df)
            m_puan, m_detay = momentum_skor(df)
            f_puan, f_detay = temel_skor(t)

            toplam = t_puan + m_puan + f_puan
            fiyat  = df["Close"].iloc[-1]

            sonuclar.append({
                "Hisse":   sembol.replace(".IS", ""),
                "Fiyat":   fiyat,
                "Toplam":  toplam,
                "Teknik":  t_puan,
                "Momentum":m_puan,
                "Temel":   f_puan,
                "RSI":     t_detay.get("RSI", ""),
                "Trend":   t_detay.get("Trend", ""),
                "Hacim":   t_detay.get("Hacim", ""),
                "1H":      m_detay.get("1H", ""),
                "1A":      m_detay.get("1A", ""),
                "F/K":     f_detay.get("F/K", ""),
                "PD/DD":   f_detay.get("PD/DD", ""),
            })
        except Exception as e:
            print(f"  {sembol} atlandı: {e}")

    df_sonuc = pd.DataFrame(sonuclar)
    df_sonuc = df_sonuc.sort_values("Toplam", ascending=False).head(TOP_N).reset_index(drop=True)
    df_sonuc.index += 1
    return df_sonuc

# ─────────────────────────────────────────────
# EMAIL OLUŞTUR
# ─────────────────────────────────────────────

def html_olustur(df):
    tarih = datetime.now().strftime("%d %B %Y, %A")
    satirlar = ""
    for i, r in df.iterrows():
        yildiz = "⭐" * min(r["Toplam"], 5)
        satirlar += f"""
        <tr>
          <td style="text-align:center;font-weight:bold;color:#1a1a2e">{i}</td>
          <td style="font-weight:bold;font-size:15px">{r['Hisse']}</td>
          <td style="text-align:right">{r['Fiyat']:.2f} ₺</td>
          <td style="text-align:center">{yildiz} ({r['Toplam']}/7)</td>
          <td style="text-align:center;color:#555">{r['RSI']}</td>
          <td style="text-align:center;color:#555">{r['Trend']}</td>
          <td style="text-align:center;color:#555">{r['Hacim']}</td>
          <td style="text-align:center;color:#2d7a2d">{r['1H']}</td>
          <td style="text-align:center;color:#2d7a2d">{r['1A']}</td>
          <td style="text-align:center;color:#555">{r['F/K']}</td>
          <td style="text-align:center;color:#555">{r['PD/DD']}</td>
        </tr>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:20px">
    <div style="max-width:900px;margin:auto;background:#fff;border-radius:12px;
                box-shadow:0 2px 12px rgba(0,0,0,0.1);overflow:hidden">
      <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                  padding:28px;color:#fff;text-align:center">
        <h1 style="margin:0;font-size:22px">📈 BIST100 Günlük Tarama</h1>
        <p style="margin:6px 0 0;opacity:.8;font-size:14px">{tarih} — Yükselme Potansiyeli En Yüksek {TOP_N} Hisse</p>
      </div>
      <div style="padding:20px;overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f0f4ff;color:#333">
              <th style="padding:10px 6px">#</th>
              <th>Hisse</th>
              <th>Fiyat</th>
              <th>Skor</th>
              <th>RSI</th>
              <th>Trend</th>
              <th>Hacim</th>
              <th>1 Hafta</th>
              <th>1 Ay</th>
              <th>F/K</th>
              <th>PD/DD</th>
            </tr>
          </thead>
          <tbody>{satirlar}</tbody>
        </table>
      </div>
      <div style="background:#f9fafb;padding:16px 20px;font-size:11px;color:#999;
                  border-top:1px solid #eee">
        ⚠️ Bu liste yatırım tavsiyesi değildir. Kararlarınızı kendi araştırmanıza dayandırın.
        Skor: Teknik (0-3) + Momentum (0-2) + Temel (0-2) = maks 7 puan.
      </div>
    </div>
    </body></html>"""
    return html

# ─────────────────────────────────────────────
# EMAIL GÖNDER
# ─────────────────────────────────────────────

def mail_gonder(html_icerik):
    tarih = datetime.now().strftime("%d.%m.%Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 BIST100 Günlük Tarama — {tarih}"
    msg["From"]    = EMAIL_GONDEREN
    msg["To"]      = EMAIL_ALICI
    msg.attach(MIMEText(html_icerik, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_GONDEREN, EMAIL_SIFRE)
        s.sendmail(EMAIL_GONDEREN, EMAIL_ALICI, msg.as_string())
    print(f"✅ Mail gönderildi → {EMAIL_ALICI}")

# ─────────────────────────────────────────────
# ÇALIŞTIR
# ─────────────────────────────────────────────

if __name__ == "__main__":
    df_sonuc = tara()
    print(df_sonuc[["Hisse","Fiyat","Toplam","RSI","Trend","1H","1A","F/K"]].to_string())
