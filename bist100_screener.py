import yfinance as yf
import pandas as pd
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

TOP_N = 10

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

def rsi_hesapla(seri, periyot=14):
    delta = seri.diff()
    kazanc = delta.clip(lower=0)
    kayip = -delta.clip(upper=0)
    rs = kazanc.rolling(periyot).mean() / (kayip.rolling(periyot).mean() + 1e-9)
    return 100 - (100 / (1 + rs))

def analiz(df):
    if df is None or len(df) < 6:
        return 0, "N/A", "N/A", "N/A", "N/A", "N/A"
    kapat = df["Close"].squeeze()
    hacim = df["Volume"].squeeze()
    r = rsi_hesapla(kapat).iloc[-1] if len(df) >= 14 else 50
    ema20 = kapat.ewm(span=20).mean().iloc[-1] if len(df) >= 20 else kapat.mean()
    ema50 = kapat.ewm(span=50).mean().iloc[-1] if len(df) >= 50 else kapat.mean()
    ort_h = hacim.rolling(20).mean().iloc[-1] if len(df) >= 20 else hacim.mean()
    son_h = hacim.iloc[-1]
    haftalik = (kapat.iloc[-1] / kapat.iloc[-6] - 1) * 100 if len(df) >= 6 else 0
    aylik = (kapat.iloc[-1] / kapat.iloc[-22] - 1) * 100 if len(df) >= 22 else 0
    puan = 0
    if 30 < r < 55:
        puan += 1
    if ema20 > ema50:
        puan += 1
    if son_h > ort_h * 1.2:
        puan += 1
    if haftalik > 0:
        puan += 1
    if aylik > 0:
        puan += 1
    rsi_str = str(round(r, 1))
    trend_str = "Yukseliyor" if ema20 > ema50 else "Dusuyor"
    hacim_str = "Yuksek" if son_h > ort_h * 1.2 else "Normal"
    h1_str = "%" + str(round(haftalik, 1))
    a1_str = "%" + str(round(aylik, 1))
    return puan, rsi_str, trend_str, hacim_str, h1_str, a1_str

def tara():
    print("BIST100 taranıyor...")
    sonuclar = []
    for sembol in BIST100:
        try:
            t = yf.Ticker(sembol)
            df = t.history(period="3mo")
            if df.empty:
                continue
            puan, rsi, trend, hacim, h1, a1 = analiz(df)
            sonuclar.append({
                "Hisse": sembol.replace(".IS", ""),
                "Fiyat": round(df["Close"].squeeze().iloc[-1], 2),
                "Toplam": puan,
                "RSI": rsi,
                "Trend": trend,
                "Hacim": hacim,
                "1H": h1,
                "1A": a1,
            })
            print(sembol.replace(".IS","") + ": " + str(puan) + "/5")
        except Exception as e:
            print(sembol + " hata: " + str(e))

    if not sonuclar:
        print("Veri alinamadi!")
        return pd.DataFrame()

    df_sonuc = pd.DataFrame(sonuclar)
    df_sonuc = df_sonuc.sort_values("Toplam", ascending=False).head(TOP_N).reset_index(drop=True)
    df_sonuc.index += 1
    return df_sonuc

def mail_gonder(df):
    EMAIL_GONDEREN = os.environ.get("EMAIL_GONDEREN", "")
    EMAIL_SIFRE = os.environ.get("EMAIL_SIFRE", "")
    EMAIL_ALICI = os.environ.get("EMAIL_ALICI", "")

    if not EMAIL_GONDEREN or not EMAIL_SIFRE or not EMAIL_ALICI:
        print("Mail bilgileri eksik.")
        return

    tarih = datetime.now().strftime("%d.%m.%Y")
    satirlar = ""
    for i, r in df.iterrows():
        satirlar += (
            "<tr>"
            "<td>" + str(i) + "</td>"
            "<td><b>" + str(r["Hisse"]) + "</b></td>"
            "<td>" + str(r["Fiyat"]) + " TL</td>"
            "<td>" + str(r["Toplam"]) + "/5</td>"
            "<td>" + str(r["RSI"]) + "</td>"
            "<td>" + str(r["Trend"]) + "</td>"
            "<td>" + str(r["1H"]) + "</td>"
            "<td>" + str(r["1A"]) + "</td>"
            "</tr>"
        )

    html = (
        "<html><body style='font-family:Arial;padding:20px'>"
        "<h2 style='color:#1a1a2e'>BIST100 Gunluk Tarama - " + tarih + "</h2>"
        "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse'>"
        "<tr style='background:#1a1a2e;color:white'>"
        "<th>#</th><th>Hisse</th><th>Fiyat</th><th>Skor</th>"
        "<th>RSI</th><th>Trend</th><th>1 Hafta</th><th>1 Ay</th>"
        "</tr>"
        + satirlar +
        "</table>"
        "<p style='color:gray;font-size:11px;margin-top:20px'>Bu liste yatirim tavsiyesi degildir.</p>"
        "</body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "BIST100 Tarama - " + tarih
    msg["From"] = EMAIL_GONDEREN
    msg["To"] = EMAIL_ALICI
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_GONDEREN, EMAIL_SIFRE)
        s.sendmail(EMAIL_GONDEREN, EMAIL_ALICI, msg.as_string())
    print("Mail gonderildi: " + EMAIL_ALICI)

if __name__ == "__main__":
    df = tara()
    if not df.empty:
        print(df.to_string())
        mail_gonder(df)
