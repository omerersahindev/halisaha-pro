import random
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Halı Saha Pro - Kadro, Kasa & Lig")
DB_NAME = "halisaha.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS maclar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saha_adi TEXT NOT NULL,
            tarih_saat TEXT NOT NULL,
            toplam_ucret REAL NOT NULL,
            kisi_sayisi INTEGER NOT NULL,
            iban TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS oyuncular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_id INTEGER NOT NULL,
            ad_soyad TEXT NOT NULL,
            takim TEXT NOT NULL,
            mevki TEXT DEFAULT 'Orta Saha',
            odedi_mi INTEGER DEFAULT 0,
            gol_sayisi INTEGER DEFAULT 0,
            FOREIGN KEY (mac_id) REFERENCES maclar(id) ON DELETE CASCADE
        );
    """)
    cur = conn.execute("SELECT COUNT(*) as c FROM maclar")
    if cur.fetchone()["c"] == 0:
        cur = conn.execute(
            "INSERT INTO maclar (saha_adi, tarih_saat, toplam_ucret, kisi_sayisi, iban) VALUES (?, ?, ?, ?, ?)",
            ("Boğaziçi Arena Halı Saha", "Cuma 21:00 - 22:00", 2800, 14, "TR00 0000 0000 0000 0000 0000 00")
        )
        mac_id = cur.lastrowid
        ornek_oyuncular = [
            (mac_id, "Ömer", "A", "Orta Saha", 1, 2),
            (mac_id, "Burak", "A", "Forvet", 1, 1),
            (mac_id, "Mert", "A", "Kaleci", 0, 0),
            (mac_id, "Emre", "B", "Defans", 1, 0),
            (mac_id, "Kaan", "B", "Forvet", 0, 3),
            (mac_id, "Can", "B", "Kaleci", 0, 0),
        ]
        conn.executemany(
            "INSERT INTO oyuncular (mac_id, ad_soyad, takim, mevki, odedi_mi, gol_sayisi) VALUES (?, ?, ?, ?, ?, ?)",
            ornek_oyuncular
        )
    conn.commit()
    conn.close()

init_db()

class MacOlustur(BaseModel):
    saha_adi: str
    tarih_saat: str
    toplam_ucret: float
    kisi_sayisi: int
    iban: str = ""

class OyuncuEkle(BaseModel):
    mac_id: int
    ad_soyad: str
    takim: str
    mevki: str = "Orta Saha"

@app.get("/api/maclar")
def maclari_getir():
    conn = get_db()
    maclar = [dict(row) for row in conn.execute("SELECT * FROM maclar ORDER BY id DESC").fetchall()]
    for m in maclar:
        oyuncular = [dict(o) for o in conn.execute("SELECT * FROM oyuncular WHERE mac_id = ? ORDER BY takim, id", (m["id"],)).fetchall()]
        m["oyuncular"] = oyuncular
        m["kisi_basi_ucret"] = round(m["toplam_ucret"] / max(m["kisi_sayisi"], 1), 2)
        odenen_kisi = sum(1 for o in oyuncular if o["odedi_mi"] == 1)
        m["toplanan_tutar"] = round(odenen_kisi * m["kisi_basi_ucret"], 2)
    conn.close()
    return maclar

@app.get("/api/istatistikler")
def istatistikleri_getir():
    conn = get_db()
    maclar = conn.execute("SELECT id FROM maclar").fetchall()
    oyuncular = [dict(o) for o in conn.execute("SELECT * FROM oyuncular").fetchall()]
    conn.close()

    mac_sonuclari = {}
    for m in maclar:
        m_id = m["id"]
        m_oyuncular = [o for o in oyuncular if o["mac_id"] == m_id]
        gol_a = sum(o["gol_sayisi"] for o in m_oyuncular if o["takim"] == "A")
        gol_b = sum(o["gol_sayisi"] for o in m_oyuncular if o["takim"] == "B")
        mac_sonuclari[m_id] = {"A": gol_a, "B": gol_b}

    tablo = {}
    for o in oyuncular:
        anahtar = o["ad_soyad"].strip().lower()
        if not anahtar:
            continue
        if anahtar not in tablo:
            tablo[anahtar] = {
                "ad_soyad": o["ad_soyad"].strip(),
                "mac": 0,
                "galibiyet": 0,
                "beraberlik": 0,
                "maglubiyet": 0,
                "gol": 0,
                "puan": 0
            }
        
        kayit = tablo[anahtar]
        kayit["mac"] += 1
        kayit["gol"] += o["gol_sayisi"]

        skor = mac_sonuclari.get(o["mac_id"], {"A": 0, "B": 0})
        kendi_skor = skor[o["takim"]]
        rakip_skor = skor["B" if o["takim"] == "A" else "A"]

        if kendi_skor > rakip_skor:
            kayit["galibiyet"] += 1
            kayit["puan"] += 3
        elif kendi_skor == rakip_skor:
            kayit["beraberlik"] += 1
            kayit["puan"] += 1
        else:
            kayit["maglubiyet"] += 1

    liste = list(tablo.values())
    for item in liste:
        item["gol_ort"] = round(item["gol"] / max(item["mac"], 1), 2)

    gol_kralligi = sorted(liste, key=lambda x: (x["gol"], x["galibiyet"]), reverse=True)
    puan_durumu = sorted(liste, key=lambda x: (x["puan"], x["galibiyet"], x["gol"]), reverse=True)

    return {
        "toplam_mac": len(maclar),
        "toplam_gol": sum(o["gol_sayisi"] for o in oyuncular),
        "gol_kralligi": gol_kralligi,
        "puan_durumu": puan_durumu
    }

@app.post("/api/maclar")
def mac_ekle(veri: MacOlustur):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO maclar (saha_adi, tarih_saat, toplam_ucret, kisi_sayisi, iban) VALUES (?, ?, ?, ?, ?)",
        (veri.saha_adi, veri.tarih_saat, veri.toplam_ucret, veri.kisi_sayisi, veri.iban)
    )
    conn.commit()
    yeni_id = cur.lastrowid
    conn.close()
    return {"id": yeni_id, "mesaj": "Maç oluşturuldu"}

@app.delete("/api/maclar/{mac_id}")
def mac_sil(mac_id: int):
    conn = get_db()
    conn.execute("DELETE FROM maclar WHERE id = ?", (mac_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Maç silindi"}

@app.post("/api/maclar/{mac_id}/dengeli-dagit")
def dengeli_dagit(mac_id: int):
    conn = get_db()
    oyuncular = [dict(o) for o in conn.execute("SELECT id, mevki FROM oyuncular WHERE mac_id = ?", (mac_id,)).fetchall()]
    if len(oyuncular) < 2:
        conn.close()
        return {"mesaj": "Dağıtım için en az 2 oyuncu gerekli"}

    mevki_sirasi = {"Kaleci": 1, "Defans": 2, "Orta Saha": 3, "Forvet": 4}
    random.shuffle(oyuncular)
    oyuncular.sort(key=lambda x: mevki_sirasi.get(x["mevki"], 5))

    sira = ["A", "B", "B", "A"]
    for idx, o in enumerate(oyuncular):
        yeni_takim = sira[idx % 4]
        conn.execute("UPDATE oyuncular SET takim = ? WHERE id = ?", (yeni_takim, o["id"]))

    conn.commit()
    conn.close()
    return {"mesaj": "Takımlar mevkilere göre dengeli dağıtıldı"}

@app.post("/api/maclar/{mac_id}/kadro-aktar")
def kadro_aktar(mac_id: int):
    conn = get_db()
    onceki_mac = conn.execute(
        "SELECT id FROM maclar WHERE id != ? AND id IN (SELECT DISTINCT mac_id FROM oyuncular) ORDER BY id DESC LIMIT 1",
        (mac_id,)
    ).fetchone()
    if not onceki_mac:
        conn.close()
        raise HTTPException(status_code=404, detail="Aktarılacak önceki maç kadrosu bulunamadı.")

    eski_oyuncular = conn.execute(
        "SELECT ad_soyad, takim, mevki FROM oyuncular WHERE mac_id = ?",
        (onceki_mac["id"],)
    ).fetchall()

    for o in eski_oyuncular:
        conn.execute(
            "INSERT INTO oyuncular (mac_id, ad_soyad, takim, mevki, odedi_mi, gol_sayisi) VALUES (?, ?, ?, ?, 0, 0)",
            (mac_id, o["ad_soyad"], o["takim"], o["mevki"])
        )

    conn.commit()
    conn.close()
    return {"mesaj": f"{len(eski_oyuncular)} oyuncu önceki maçtan aktarıldı"}

@app.post("/api/oyuncular")
def oyuncu_ekle(veri: OyuncuEkle):
    conn = get_db()
    mac = conn.execute("SELECT kisi_sayisi FROM maclar WHERE id = ?", (veri.mac_id,)).fetchone()
    if not mac:
        conn.close()
        raise HTTPException(status_code=404, detail="Maç bulunamadı")

    mevcut_sayi = conn.execute("SELECT COUNT(*) as c FROM oyuncular WHERE mac_id = ?", (veri.mac_id,)).fetchone()["c"]
    if mevcut_sayi >= mac["kisi_sayisi"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Maç kadrosu tamamen doldu!")

    conn.execute(
        "INSERT INTO oyuncular (mac_id, ad_soyad, takim, mevki) VALUES (?, ?, ?, ?)",
        (veri.mac_id, veri.ad_soyad.strip(), veri.takim, veri.mevki)
    )
    conn.commit()
    conn.close()
    return {"mesaj": "Oyuncu eklendi"}

@app.patch("/api/oyuncular/{oyuncu_id}/takim-degistir")
def takim_degistir(oyuncu_id: int):
    conn = get_db()
    conn.execute("UPDATE oyuncular SET takim = CASE WHEN takim = 'A' THEN 'B' ELSE 'A' END WHERE id = ?", (oyuncu_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Takım değiştirildi"}

@app.patch("/api/oyuncular/{oyuncu_id}/odeme")
def odeme_degistir(oyuncu_id: int):
    conn = get_db()
    conn.execute("UPDATE oyuncular SET odedi_mi = CASE WHEN odedi_mi = 1 THEN 0 ELSE 1 END WHERE id = ?", (oyuncu_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Ödeme güncellendi"}

@app.patch("/api/oyuncular/{oyuncu_id}/gol")
def gol_artir(oyuncu_id: int):
    conn = get_db()
    conn.execute("UPDATE oyuncular SET gol_sayisi = gol_sayisi + 1 WHERE id = ?", (oyuncu_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Gol eklendi"}

@app.patch("/api/oyuncular/{oyuncu_id}/gol-azalt")
def gol_azalt(oyuncu_id: int):
    conn = get_db()
    conn.execute("UPDATE oyuncular SET gol_sayisi = MAX(0, gol_sayisi - 1) WHERE id = ?", (oyuncu_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Gol azaltıldı"}

@app.delete("/api/oyuncular/{oyuncu_id}")
def oyuncu_sil(oyuncu_id: int):
    conn = get_db()
    conn.execute("DELETE FROM oyuncular WHERE id = ?", (oyuncu_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Oyuncu silindi"}

@app.get("/", response_class=HTMLResponse)
def arayuz():
    return r"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Halı Saha Pro - Kadro, Kasa & Lig</title>
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --accent: #22c55e; --text: #f8fafc; --muted: #94a3b8; }
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); margin: 0; padding: 16px; display: flex; justify-content: center; }
        .container { width: 100%; max-width: 560px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
        h1 { font-size: 20px; margin: 0; display: flex; align-items: center; gap: 8px; }
        .tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: var(--card); padding: 6px; border-radius: 12px; margin-bottom: 16px; border: 1px solid #334155; }
        .tab-btn { background: transparent; color: var(--muted); border: none; padding: 10px; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 14px; transition: 0.2s; }
        .tab-btn.active { background: var(--accent); color: #052e16; }
        .btn { background: var(--accent); color: #052e16; border: none; padding: 10px 14px; border-radius: 10px; font-weight: 700; cursor: pointer; font-size: 13px; }
        .btn-tool { background: #334155; color: #f8fafc; border: none; padding: 7px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
        .btn-tool:hover { background: #475569; }
        .btn-wa { background: #25D366; color: #000; width: 100%; margin-top: 12px; font-size: 14px; padding: 11px; }
        .card { background: var(--card); border-radius: 16px; padding: 16px; margin-bottom: 16px; border: 1px solid #334155; }
        .toolbar { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; text-align: center; }
        .stat-box { background: #0f172a; padding: 10px; border-radius: 10px; }
        .stat-val { font-size: 16px; font-weight: 800; color: var(--accent); }
        .stat-lbl { font-size: 11px; color: var(--muted); }
        .teams { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
        .team-col { background: #0f172a; padding: 10px; border-radius: 12px; }
        .team-title { font-weight: 800; font-size: 14px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #1e293b; display: flex; justify-content: space-between; }
        .player { display: flex; flex-direction: column; gap: 5px; background: #1e293b; padding: 8px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; }
        .player-top { display: flex; justify-content: space-between; align-items: center; font-weight: 600; gap: 4px; }
        .player-ctrl { display: flex; align-items: center; gap: 4px; }
        .player-actions { display: flex; gap: 4px; justify-content: space-between; align-items: center; margin-top: 2px; }
        .badge { padding: 3px 7px; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; border: none; }
        .paid { background: #166534; color: #bbf7d0; }
        .unpaid { background: #7f1d1d; color: #fecaca; }
        .gol-grup { display: flex; align-items: center; gap: 3px; background: #334155; padding: 2px 5px; border-radius: 6px; }
        .gol-btn { background: transparent; color: #fde047; padding: 1px 4px; border: none; font-size: 11px; font-weight: 700; cursor: pointer; }
        .gol-minus { background: #1e293b; color: #f87171; padding: 1px 5px; border-radius: 4px; border: none; font-size: 11px; font-weight: 800; cursor: pointer; }
        .mini-btn { background: #334155; color: #cbd5e1; border: none; border-radius: 5px; padding: 2px 5px; cursor: pointer; font-size: 11px; }
        .del-mac-btn { background: #7f1d1d; color: #fecaca; border: none; padding: 5px 8px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer; }
        input, select { width: 100%; padding: 10px; margin-bottom: 8px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; }
        .row-form { display: grid; grid-template-columns: 2fr 1fr 1fr auto; gap: 6px; margin-top: 12px; }
        .row-form input, .row-form select { margin: 0; padding: 8px; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
        th { text-align: left; color: var(--muted); font-size: 11px; padding: 8px 6px; border-bottom: 1px solid #334155; }
        td { padding: 10px 6px; border-bottom: 1px solid #0f172a; }
        .rank-1 { color: #fde047; font-weight: 800; }
        .rank-2 { color: #cbd5e1; font-weight: 700; }
        .rank-3 { color: #fdba74; font-weight: 700; }
        .invite-banner { background: #14532d; border: 1px solid #22c55e; color: #dcfce7; padding: 10px 14px; border-radius: 12px; margin-bottom: 14px; font-size: 13px; display: none; justify-content: space-between; align-items: center; }
        #yeniMacForm, #istatistikAlani { display: none; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>⚽ Halı Saha Pro</h1>
        <button class="btn" id="yeniMacBtn" onclick="toggleForm()">+ Yeni Maç</button>
    </header>

    <div id="inviteBanner" class="invite-banner">
        <span>🎯 Davet linki ile maça katılıyorsun.</span>
        <button class="btn-tool" onclick="tumMaclariGoster()">Tüm Maçlar</button>
    </div>

    <div class="tabs" id="mainTabs">
        <button class="tab-btn active" id="tabMaclar" onclick="sekmeDegistir('maclar')">🏟️ Maçlar & Kasa</button>
        <button class="tab-btn" id="tabIstatistik" onclick="sekmeDegistir('istatistik')">🏆 Sezon İstatistikleri</button>
    </div>

    <div id="maclarAlani">
        <div id="yeniMacForm" class="card">
            <h3 style="margin-top:0">Yeni Maç Oluştur</h3>
            <input id="sahaAdi" placeholder="Saha Adı (Örn: Yıldız Halı Saha)">
            <input id="tarihSaat" placeholder="Tarih & Saat (Örn: Cumartesi 22:00)">
            <input id="toplamUcret" type="number" placeholder="Toplam Saha Ücreti (TL)">
            <input id="kisiSayisi" type="number" value="14" placeholder="Kişi Sayısı (Örn: 14)">
            <input id="iban" placeholder="Kaptan IBAN (Opsiyonel)">
            <button class="btn" style="width:100%" onclick="macKaydet()">Maçı Kaydet</button>
        </div>
        <div id="macListesi"></div>
    </div>

    <div id="istatistikAlani">
        <div class="card">
            <div class="stats" style="grid-template-columns: 1fr 1fr; margin-top:0;">
                <div class="stat-box">
                    <div class="stat-val" id="sezonToplamMac">0</div>
                    <div class="stat-lbl">Oynanan Maç</div>
                </div>
                <div class="stat-box">
                    <div class="stat-val" id="sezonToplamGol">0</div>
                    <div class="stat-lbl">Atılan Toplam Gol</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h3 style="margin:0 0 8px 0; font-size:16px;">👟 Sezonluk Gol Krallığı</h3>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Oyuncu</th>
                        <th>Maç</th>
                        <th>Ort.</th>
                        <th style="text-align:right">Gol</th>
                    </tr>
                </thead>
                <tbody id="golKralligiBody"></tbody>
            </table>
        </div>

        <div class="card">
            <h3 style="margin:0 0 8px 0; font-size:16px;">🏅 Galibiyet & Puan Tablosu</h3>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Oyuncu</th>
                        <th>G</th>
                        <th>B</th>
                        <th>M</th>
                        <th style="text-align:right">Puan</th>
                    </tr>
                </thead>
                <tbody id="puanTablosuBody"></tbody>
            </table>
            <small style="color:var(--muted); display:block; margin-top:10px; font-size:11px;">* Galibiyet: 3 Puan, Beraberlik: 1 Puan üzerinden hesaplanır.</small>
        </div>
    </div>
</div>

<script>
    const urlParams = new URLSearchParams(window.location.search);
    let filtreMacId = urlParams.get('mac') ? parseInt(urlParams.get('mac')) : null;
    let tumMaclarCache = {};

    if (filtreMacId) {
        document.getElementById('inviteBanner').style.display = 'flex';
    }

    function tumMaclariGoster() {
        filtreMacId = null;
        window.history.replaceState({}, '', '/');
        document.getElementById('inviteBanner').style.display = 'none';
        yukle();
    }

    function sekmeDegistir(sekme) {
        const maclarDiv = document.getElementById('maclarAlani');
        const istatistikDiv = document.getElementById('istatistikAlani');
        const yeniMacBtn = document.getElementById('yeniMacBtn');

        document.getElementById('tabMaclar').classList.toggle('active', sekme === 'maclar');
        document.getElementById('tabIstatistik').classList.toggle('active', sekme === 'istatistik');

        if (sekme === 'maclar') {
            maclarDiv.style.display = 'block';
            istatistikDiv.style.display = 'none';
            yeniMacBtn.style.display = 'inline-block';
            yukle();
        } else {
            maclarDiv.style.display = 'none';
            istatistikDiv.style.display = 'block';
            yeniMacBtn.style.display = 'none';
            istatistikYukle();
        }
    }

    function toggleForm() {
        const f = document.getElementById('yeniMacForm');
        f.style.display = f.style.display === 'none' || f.style.display === '' ? 'block' : 'none';
    }

    async function yukle() {
        const res = await fetch('/api/maclar');
        let maclar = await res.json();
        if (filtreMacId) {
            maclar = maclar.filter(m => m.id === filtreMacId);
        }

        const alan = document.getElementById('macListesi');
        alan.innerHTML = '';
        tumMaclarCache = {};

        if (maclar.length === 0) {
            alan.innerHTML = '<div class="card" style="text-align:center;color:#94a3b8;padding:30px">Henüz kayıtlı maç bulunmuyor.<br>Sağ üstteki <b>+ Yeni Maç</b> butonuna basarak ilk maçını oluşturabilirsin!</div>';
            return;
        }

        maclar.forEach(m => {
            tumMaclarCache[m.id] = m;
            const takimA = m.oyuncular.filter(o => o.takim === 'A');
            const takimB = m.oyuncular.filter(o => o.takim === 'B');
            const golA = takimA.reduce((t, o) => t + o.gol_sayisi, 0);
            const golB = takimB.reduce((t, o) => t + o.gol_sayisi, 0);

            const oyuncuKarti = (o) => `
                <div class="player">
                    <div class="player-top">
                        <span>${o.ad_soyad} <small style="color:#94a3b8;font-weight:400">(${o.mevki[0]})</small></span>
                        <div class="player-ctrl">
                            <button class="mini-btn" onclick="takimDegistir(${o.id})" title="Diğer takıma geçir">⇄</button>
                            <button class="mini-btn" onclick="oyuncuSil(${o.id})" title="Oyuncuyu çıkar">✕</button>
                        </div>
                    </div>
                    <div class="player-actions">
                        <button class="badge ${o.odedi_mi ? 'paid' : 'unpaid'}" onclick="odemeDegistir(${o.id})">
                            ${o.odedi_mi ? '✓ Ödedi' : '⏳ Bekliyor'}
                        </button>
                        <div class="gol-grup">
                            <button class="gol-minus" onclick="golAzalt(${o.id})" title="Gol azalt">-</button>
                            <button class="gol-btn" onclick="golArtir(${o.id})" title="Gol ekle">⚽ ${o.gol_sayisi}</button>
                        </div>
                    </div>
                </div>
            `;

            alan.innerHTML += `
                <div class="card">
                    <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
                        <div>
                            <h3 style="margin:0;font-size:17px">${m.saha_adi}</h3>
                            <small style="color:var(--muted)">📅 ${m.tarih_saat}</small>
                        </div>
                        <div style="display:flex;align-items:center;gap:6px">
                            <span style="background:#334155;padding:4px 8px;border-radius:8px;font-size:12px">${m.oyuncular.length}/${m.kisi_sayisi} Kişi</span>
                            <button class="del-mac-btn" onclick="macSil(${m.id}, '${m.saha_adi.replace(/'/g, "")}')" title="Maçı Sil">🗑️</button>
                        </div>
                    </div>

                    <div class="toolbar">
                        <button class="btn-tool" onclick="dengeliDagit(${m.id})">⚖️ Dengeli Takım Kur</button>
                        ${m.oyuncular.length === 0 ? `<button class="btn-tool" onclick="kadroAktar(${m.id})">📥 Önceki Kadroyu Aktar</button>` : ''}
                        <button class="btn-tool" onclick="davetLinkiKopyala(${m.id})">🔗 Davet Linki</button>
                    </div>

                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-val">${m.kisi_basi_ucret} ₺</div>
                            <div class="stat-lbl">Kişi Başı</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-val">${m.toplanan_tutar} ₺</div>
                            <div class="stat-lbl">Toplanan</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-val" style="color:#f87171">${Math.max(0, m.toplam_ucret - m.toplanan_tutar)} ₺</div>
                            <div class="stat-lbl">Kalan Kasa</div>
                        </div>
                    </div>

                    <div class="teams">
                        <div class="team-col">
                            <div class="team-title"><span>⚪ A Takımı</span><span>${golA}</span></div>
                            ${takimA.map(oyuncuKarti).join('') || '<small style="color:#64748b">Oyuncu yok</small>'}
                        </div>
                        <div class="team-col">
                            <div class="team-title"><span>⚫ B Takımı</span><span>${golB}</span></div>
                            ${takimB.map(oyuncuKarti).join('') || '<small style="color:#64748b">Oyuncu yok</small>'}
                        </div>
                    </div>

                    <div class="row-form">
                        <input id="ad_${m.id}" placeholder="Oyuncu adı">
                        <select id="takim_${m.id}">
                            <option value="A">A Takımı</option>
                            <option value="B">B Takımı</option>
                        </select>
                        <select id="mevki_${m.id}">
                            <option value="Orta Saha">Orta Saha</option>
                            <option value="Forvet">Forvet</option>
                            <option value="Defans">Defans</option>
                            <option value="Kaleci">Kaleci</option>
                        </select>
                        <button class="btn" onclick="oyuncuEkle(${m.id})">+</button>
                    </div>

                    <button class="btn btn-wa" onclick="whatsappKopyala(${m.id})">📋 WhatsApp Kadro & IBAN Kopyala</button>
                </div>
            `;
        });
    }

    async function istatistikYukle() {
        const res = await fetch('/api/istatistikler');
        const data = await res.json();

        document.getElementById('sezonToplamMac').innerText = data.toplam_mac;
        document.getElementById('sezonToplamGol').innerText = data.toplam_gol;

        const madalya = (idx) => idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : (idx + 1);
        const sinif = (idx) => idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : '';

        const golBody = document.getElementById('golKralligiBody');
        golBody.innerHTML = data.gol_kralligi.map((o, i) => `
            <tr class="${sinif(i)}">
                <td>${madalya(i)}</td>
                <td>${o.ad_soyad}</td>
                <td>${o.mac}</td>
                <td>${o.gol_ort}</td>
                <td style="text-align:right">⚽ ${o.gol}</td>
            </tr>
        `).join('') || '<tr><td colspan="5" style="color:#64748b">Henüz veri yok</td></tr>';

        const puanBody = document.getElementById('puanTablosuBody');
        puanBody.innerHTML = data.puan_durumu.map((o, i) => `
            <tr class="${sinif(i)}">
                <td>${madalya(i)}</td>
                <td>${o.ad_soyad}</td>
                <td>${o.galibiyet}</td>
                <td>${o.beraberlik}</td>
                <td>${o.maglubiyet}</td>
                <td style="text-align:right">${o.puan} P</td>
            </tr>
        `).join('') || '<tr><td colspan="6" style="color:#64748b">Henüz veri yok</td></tr>';
    }

    async function macKaydet() {
        const veri = {
            saha_adi: document.getElementById('sahaAdi').value || 'Halı Saha',
            tarih_saat: document.getElementById('tarihSaat').value || 'Bu Hafta',
            toplam_ucret: parseFloat(document.getElementById('toplamUcret').value) || 2800,
            kisi_sayisi: parseInt(document.getElementById('kisiSayisi').value) || 14,
            iban: document.getElementById('iban').value
        };
        await fetch('/api/maclar', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(veri) });
        toggleForm();
        yukle();
    }

    async function macSil(macId, sahaAdi) {
        if (!confirm(`"${sahaAdi}" maçını ve bu maça ait tüm istatistikleri silmek istediğine emin misin?`)) return;
        await fetch(`/api/maclar/${macId}`, { method: 'DELETE' });
        yukle();
    }

    async function dengeliDagit(macId) {
        await fetch(`/api/maclar/${macId}/dengeli-dagit`, { method: 'POST' });
        yukle();
    }

    async function kadroAktar(macId) {
        const res = await fetch(`/api/maclar/${macId}/kadro-aktar`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            return alert(err.detail || "Aktarılacak kadro bulunamadı.");
        }
        yukle();
    }

    function davetLinkiKopyala(macId) {
        const link = `${window.location.origin}/?mac=${macId}`;
        navigator.clipboard.writeText(link);
        alert("Maç katılım linki kopyalandı! WhatsApp grubuna yapıştırabilirsin:\n" + link);
    }

    async function oyuncuEkle(macId) {
        const ad = document.getElementById('ad_' + macId).value.trim();
        if (!ad) return;
        const veri = {
            mac_id: macId,
            ad_soyad: ad,
            takim: document.getElementById('takim_' + macId).value,
            mevki: document.getElementById('mevki_' + macId).value
        };
        const res = await fetch('/api/oyuncular', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(veri) });
        if (!res.ok) {
            const err = await res.json();
            return alert(err.detail || "Oyuncu eklenemedi.");
        }
        yukle();
    }

    async function takimDegistir(id) {
        await fetch(`/api/oyuncular/${id}/takim-degistir`, { method: 'PATCH' });
        yukle();
    }

    async function odemeDegistir(id) {
        await fetch(`/api/oyuncular/${id}/odeme`, { method: 'PATCH' });
        yukle();
    }

    async function golArtir(id) {
        await fetch(`/api/oyuncular/${id}/gol`, { method: 'PATCH' });
        yukle();
    }

    async function golAzalt(id) {
        await fetch(`/api/oyuncular/${id}/gol-azalt`, { method: 'PATCH' });
        yukle();
    }

    async function oyuncuSil(id) {
        await fetch(`/api/oyuncular/${id}`, { method: 'DELETE' });
        yukle();
    }

    function whatsappKopyala(macId) {
        const m = tumMaclarCache[macId];
        if (!m) return;
        const a = m.oyuncular.filter(o => o.takim === 'A').map((o, i) => `${i+1}. ${o.ad_soyad} (${o.mevki[0]}) ${o.odedi_mi ? '✅' : '⏳'}`).join('\n');
        const b = m.oyuncular.filter(o => o.takim === 'B').map((o, i) => `${i+1}. ${o.ad_soyad} (${o.mevki[0]}) ${o.odedi_mi ? '✅' : '⏳'}`).join('\n');
        const link = `${window.location.origin}/?mac=${m.id}`;
        const metin = `⚽ *${m.saha_adi}*\n📅 ${m.tarih_saat}\n💰 Kişi Başı: *${m.kisi_basi_ucret} TL*\n` +
                      (m.iban ? `🏦 IBAN: ${m.iban}\n` : '') +
                      `\n⚪ *A TAKIMI*\n${a || '-'}\n\n⚫ *B TAKIMI*\n${b || '-'}\n\n🔗 Kadroya yazılmak için: ${link}`;
        navigator.clipboard.writeText(metin);
        alert("WhatsApp kadro, ödeme ve katılım linki panoya kopyalandı!");
    }

    yukle();
</script>
</body>
</html>
"""