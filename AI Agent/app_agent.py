"""
SANAL PLANNER - Agentic Streamlit Arayüzü
Claude API Tool Calling ile akıllı retail planner
🔊 Sesli Yanıt Özellikli (Edge TTS - Kaliteli Türkçe)
📑 PDF Rapor Desteği (Türkçe karakter tam uyumlu)
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import os
import base64
from io import BytesIO
import asyncio

# ============================================
# 📑 PDF RAPOR MODÜLÜ - TÜRKÇE DESTEKLI
# ============================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, gray
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re

# Emoji → Metin dönüşüm tablosu
EMOJI_MAP = {
    '📊': '[GRAFIK]', '📋': '[LISTE]', '📦': '[KUTU]', '🔴': '[!]',
    '🟡': '[~]', '🟢': '[OK]', '✅': '[OK]', '❌': '[X]', '⚠️': '[!]',
    '🚨': '[!!]', '💰': '[TL]', '💵': '[TL]', '📈': '[+]', '📉': '[-]',
    '🏆': '[TOP]', '🏪': '[MAG]', '🏭': '[DEPO]', '🎯': '[*]', '⭐': '[*]',
    '🤖': '', '🧑': '', '💬': '', '📁': '[DOSYA]', '📌': '[*]',
    '💡': '[i]', '🔍': '[?]', '📅': '[TARIH]', '🔧': '[AYAR]',
    '📥': '[INDIR]', '📑': '[PDF]',
}

def setup_turkish_fonts():
    """Türkçe karakter destekleyen fontları yükle"""
    import sys as _sys

    # Platform bazlı font arama
    candidate_dirs = [
        '/usr/share/fonts/truetype/dejavu',  # Linux
        '/usr/share/fonts/TTF',  # Arch Linux
        'C:/Windows/Fonts',  # Windows
        os.path.expanduser('~/AppData/Local/Microsoft/Windows/Fonts'),  # Windows user fonts
    ]

    font_names = {
        'DejaVuSans': ['DejaVuSans.ttf', 'dejavu-sans/DejaVuSans.ttf'],
        'DejaVuSans-Bold': ['DejaVuSans-Bold.ttf', 'dejavu-sans/DejaVuSans-Bold.ttf'],
    }

    # Windows fallback: Arial destekler Türkçe
    win_fallback = {
        'DejaVuSans': ['arial.ttf', 'calibri.ttf', 'segoeui.ttf'],
        'DejaVuSans-Bold': ['arialbd.ttf', 'calibrib.ttf', 'segoeuib.ttf'],
    }

    for font_id, filenames in font_names.items():
        registered = False
        for d in candidate_dirs:
            if registered:
                break
            for fn in filenames:
                path = os.path.join(d, fn)
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_id, path))
                        registered = True
                        break
                    except:
                        pass

        # Windows fallback
        if not registered and _sys.platform == 'win32':
            for fn in win_fallback.get(font_id, []):
                path = os.path.join('C:/Windows/Fonts', fn)
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_id, path))
                        registered = True
                        break
                    except:
                        pass

        if not registered:
            print(f"PDF hatasi: {font_id} fontu bulunamadi, Helvetica kullanilacak")

def _get_pdf_font(style='normal'):
    """PDF için mevcut font adını döndür"""
    from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames
    registered = getRegisteredFontNames()
    if style == 'bold':
        return 'DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered else 'Helvetica-Bold'
    return 'DejaVuSans' if 'DejaVuSans' in registered else 'Helvetica'

def temizle_emoji(text: str) -> str:
    """Emojileri metin karşılıklarıyla değiştir"""
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # Kalan emojileri kaldır
    text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)
    text = re.sub(r'[\U0001F300-\U0001F5FF]', '', text)
    text = re.sub(r'[\U0001F680-\U0001F6FF]', '', text)
    text = re.sub(r'[\U0001F900-\U0001F9FF]', '', text)
    return text

def get_turkish_styles():
    """Türkçe karakter destekli stiller"""
    styles = getSampleStyleSheet()

    # Kayıtlı fontları kontrol et
    from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames
    registered = getRegisteredFontNames()
    font_normal = 'DejaVuSans' if 'DejaVuSans' in registered else 'Helvetica'
    font_bold = 'DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered else 'Helvetica-Bold'

    # Tüm stillere Türkçe font ata
    for style_name in ['Normal', 'BodyText', 'Title', 'Heading1', 'Heading2', 'Heading3']:
        if style_name in styles:
            styles[style_name].fontName = font_normal
    
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 14
    
    styles['Heading1'].fontName = font_bold
    styles['Heading1'].fontSize = 14
    styles['Heading1'].textColor = HexColor('#1E3A8A')
    
    styles['Heading2'].fontName = font_bold
    styles['Heading2'].fontSize = 12
    styles['Heading2'].textColor = HexColor('#374151')
    
    styles['Heading3'].fontName = font_bold
    styles['Heading3'].fontSize = 10
    styles['Heading3'].textColor = HexColor('#4B5563')
    
    # Özel stiller
    styles.add(ParagraphStyle(
        name='TurkishTitle',
        fontName=font_bold,
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=HexColor('#1E3A8A')
    ))
    
    styles.add(ParagraphStyle(
        name='ListItem',
        fontName=font_normal,
        fontSize=10,
        leading=14,
        leftIndent=20,
    ))

    styles.add(ParagraphStyle(
        name='Footer',
        fontName=font_normal,
        fontSize=8,
        textColor=gray,
        alignment=TA_CENTER
    ))
    
    return styles

def parse_markdown_to_elements(text: str, styles) -> list:
    """Markdown'ı PDF elementlerine çevir"""
    elements = []
    lines = text.split('\n')
    
    table_buffer = []
    in_table = False
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            if in_table and table_buffer:
                elements.append(create_table_element(table_buffer))
                table_buffer = []
                in_table = False
            elements.append(Spacer(1, 6))
            i += 1
            continue
        
        line = temizle_emoji(line)
        
        # Ayraç
        if re.match(r'^[=\-]{3,}$', line):
            if in_table and table_buffer:
                elements.append(create_table_element(table_buffer))
                table_buffer = []
                in_table = False
            elements.append(HRFlowable(width="100%", thickness=1, color=gray))
            i += 1
            continue
        
        # Tablo satırı
        if '|' in line and not line.startswith('#'):
            if re.match(r'^[\|\-\s:]+$', line):
                i += 1
                continue
            in_table = True
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                table_buffer.append(cells)
            i += 1
            continue
        
        if in_table and table_buffer:
            elements.append(create_table_element(table_buffer))
            table_buffer = []
            in_table = False
        
        # Başlıklar
        if line.startswith('# '):
            title = line[2:].strip()
            title = re.sub(r'\*\*(.+?)\*\*', r'\1', title)
            elements.append(Paragraph(title, styles['Heading1']))
            elements.append(Spacer(1, 10))
            i += 1
            continue
        
        if line.startswith('## '):
            title = line[3:].strip()
            title = re.sub(r'\*\*(.+?)\*\*', r'\1', title)
            elements.append(Paragraph(title, styles['Heading2']))
            elements.append(Spacer(1, 8))
            i += 1
            continue
        
        if line.startswith('### '):
            title = line[4:].strip()
            title = re.sub(r'\*\*(.+?)\*\*', r'\1', title)
            elements.append(Paragraph(title, styles['Heading3']))
            elements.append(Spacer(1, 6))
            i += 1
            continue
        
        # Liste
        if re.match(r'^[\-\*]\s+', line):
            item = re.sub(r'^[\-\*]\s+', '', line)
            item = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', item)
            elements.append(Paragraph(f"• {item}", styles['ListItem']))
            i += 1
            continue
        
        # Numaralı liste
        if re.match(r'^\d+\.\s+', line):
            num = re.match(r'^(\d+)\.', line).group(1)
            item = re.sub(r'^\d+\.\s+', '', line)
            item = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', item)
            elements.append(Paragraph(f"{num}. {item}", styles['ListItem']))
            i += 1
            continue
        
        # Normal paragraf
        para = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        elements.append(Paragraph(para, styles['Normal']))
        i += 1
    
    if table_buffer:
        elements.append(create_table_element(table_buffer))
    
    return elements

def create_table_element(rows: list) -> Table:
    """Tablo oluştur"""
    if not rows:
        return Spacer(1, 1)
    
    max_cols = max(len(row) for row in rows)
    normalized = [row + [''] * (max_cols - len(row)) for row in rows]
    
    table = Table(normalized)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), _get_pdf_font('bold')),
        ('FONTNAME', (0, 1), (-1, -1), _get_pdf_font('normal')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#E8E8E8')),
        ('GRID', (0, 0), (-1, -1), 0.5, gray),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table

def create_pdf_report(soru: str, cevap: str, title: str = "Sanal Planner - Analiz Raporu") -> bytes:
    """PDF raporu oluştur"""
    setup_turkish_fonts()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                           leftMargin=2*cm, rightMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    styles = get_turkish_styles()
    story = []
    
    # Başlık
    story.append(Paragraph(title, styles['TurkishTitle']))
    story.append(Paragraph("Thorius AI4U", styles['Footer']))
    tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
    story.append(Paragraph(f"Tarih: {tarih}", styles['Footer']))
    story.append(HRFlowable(width="100%", thickness=2, color=HexColor('#1E3A8A')))
    story.append(Spacer(1, 20))
    
    # Soru
    if soru:
        story.append(Paragraph("SORU", styles['Heading2']))
        story.append(Paragraph(temizle_emoji(soru), styles['Normal']))
        story.append(Spacer(1, 15))
    
    # Cevap
    story.append(Paragraph("ANALİZ SONUCU", styles['Heading2']))
    story.append(Spacer(1, 10))
    
    cevap_elements = parse_markdown_to_elements(cevap, styles)
    story.extend(cevap_elements)
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=gray))
    story.append(Paragraph("⭐ Sanal Planner | Thorius AI4U", styles['Footer']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def create_chat_pdf(messages: list) -> bytes:
    """Tüm sohbetten PDF oluştur"""
    setup_turkish_fonts()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                           leftMargin=2*cm, rightMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    styles = get_turkish_styles()
    story = []
    
    story.append(Paragraph("Sanal Planner", styles['TurkishTitle']))
    story.append(Paragraph("Thorius AI4U", styles['Footer']))
    tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
    story.append(Paragraph(f"Tarih: {tarih}", styles['Footer']))
    story.append(HRFlowable(width="100%", thickness=2, color=HexColor('#1E3A8A')))
    story.append(Spacer(1, 20))

    for i, msg in enumerate(messages):
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        
        if role == 'user':
            story.append(Paragraph("KULLANICI", styles['Heading3']))
            story.append(Paragraph(temizle_emoji(content), styles['Normal']))
        else:
            story.append(Paragraph("SANAL PLANNER", styles['Heading3']))
            elements = parse_markdown_to_elements(content, styles)
            story.extend(elements)
        
        story.append(Spacer(1, 15))
        if role == 'agent' and i < len(messages) - 1:
            story.append(HRFlowable(width="80%", thickness=0.5, color=gray))
            story.append(Spacer(1, 15))
    
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=gray))
    story.append(Paragraph("⭐ Sanal Planner | Thorius AI4U", styles['Footer']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================
# 🔊 TTS (Text-to-Speech) FONKSİYONU - EDGE TTS
# ============================================
def sesli_oku(metin: str, ses: str = "tr-TR-AhmetNeural") -> str:
    """Metni Türkçe sese çevirir ve HTML audio player döner."""
    try:
        import edge_tts
        
        temiz_metin = metin[:3000] if len(metin) > 3000 else metin
        for char in ['===', '---', '📊', '🚨', '✅', '❌', '⚠️', '🔴', '🏆', '🏪', '🏭', '📦', '💰', '📈', '🤖', '🧑', '💬', '*', '#']:
            temiz_metin = temiz_metin.replace(char, '')
        
        async def generate_audio():
            communicate = edge_tts.Communicate(temiz_metin, ses)
            audio_buffer = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            return audio_buffer.getvalue()
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        audio_data = loop.run_until_complete(generate_audio())
        audio_base64 = base64.b64encode(audio_data).decode()
        
        audio_html = f'''
        <audio autoplay controls style="width: 100%; margin-top: 10px; border-radius: 10px;">
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        </audio>
        '''
        return audio_html
        
    except ImportError:
        return "<p style='color: orange;'>⚠️ Sesli okuma için: pip install edge-tts</p>"
    except Exception as e:
        return f"<p style='color: red;'>❌ Ses hatası: {str(e)}</p>"


# ============================================
# STREAMLIT ARAYÜZÜ
# ============================================

st.set_page_config(
    page_title="⭐ Sanal Planner | Thorius AI4U",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Matrix giriş animasyonu - sadece ilk açılışta
if 'intro_shown' not in st.session_state:
    st.session_state['intro_shown'] = False

if not st.session_state['intro_shown']:
    intro_placeholder = st.empty()
    intro_placeholder.markdown("""
    <style>
        @keyframes matrixFade { 0% { opacity: 1; } 100% { opacity: 0; } }
        @keyframes matrixGlow { 0%,100% { text-shadow: 0 0 5px #00ff41; } 50% { text-shadow: 0 0 20px #00ff41, 0 0 40px #00ff41; } }
        @keyframes titleReveal { 0% { opacity: 0; transform: scale(0.5); } 50% { opacity: 1; transform: scale(1.1); } 100% { opacity: 1; transform: scale(1); } }
    </style>
    <div id="matrix-intro" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
         background: #000; z-index: 99999; display: flex; align-items: center; justify-content: center;
         animation: matrixFade 0.5s ease-in 4.5s forwards;">
        <canvas id="matrixCanvas" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></canvas>
        <div style="position: relative; z-index: 2; text-align: center; animation: titleReveal 1s ease-out 2s both;">
            <h1 style="font-size: 3.5rem; color: #00ff41; font-family: 'Courier New', monospace; margin: 0;
                       animation: matrixGlow 1.5s infinite; letter-spacing: 8px;">
                SANAL PLANNER
            </h1>
            <p style="color: #00cc33; font-size: 1.2rem; font-family: 'Courier New', monospace; margin-top: 10px;
                      letter-spacing: 3px;">AI-Powered Retail Analytics</p>
            <div style="margin-top: 20px; display: flex; justify-content: center; gap: 8px;">
                <span style="width: 8px; height: 8px; background: #00ff41; border-radius: 50; display: inline-block;
                             animation: matrixGlow 0.5s infinite 0s;"></span>
                <span style="width: 8px; height: 8px; background: #00ff41; border-radius: 50%; display: inline-block;
                             animation: matrixGlow 0.5s infinite 0.2s;"></span>
                <span style="width: 8px; height: 8px; background: #00ff41; border-radius: 50%; display: inline-block;
                             animation: matrixGlow 0.5s infinite 0.4s;"></span>
            </div>
        </div>
    </div>
    <script>
    (function() {
        const c = document.getElementById('matrixCanvas');
        if (!c) return;
        const ctx = c.getContext('2d');
        c.width = window.innerWidth;
        c.height = window.innerHeight;
        const chars = '01アイウエオカキクケコサシスセソ%$#@!&*+=<>';
        const fontSize = 14;
        const cols = Math.floor(c.width / fontSize);
        const drops = Array(cols).fill(1);
        function draw() {
            ctx.fillStyle = 'rgba(0,0,0,0.05)';
            ctx.fillRect(0, 0, c.width, c.height);
            ctx.fillStyle = '#00ff41';
            ctx.font = fontSize + 'px monospace';
            for (let i = 0; i < drops.length; i++) {
                const text = chars[Math.floor(Math.random() * chars.length)];
                ctx.fillStyle = Math.random() > 0.98 ? '#fff' : '#00ff41';
                ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                if (drops[i] * fontSize > c.height && Math.random() > 0.975) drops[i] = 0;
                drops[i]++;
            }
        }
        const interval = setInterval(draw, 35);
        setTimeout(function() {
            clearInterval(interval);
            const el = document.getElementById('matrix-intro');
            if (el) el.style.display = 'none';
        }, 5000);
    })();
    </script>
    """, unsafe_allow_html=True)
    import time
    time.sleep(5)
    intro_placeholder.empty()
    st.session_state['intro_shown'] = True

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: bold; color: #1E3A8A; margin-bottom: 0; }
    .sub-header { font-size: 1.1rem; color: #6B7280; margin-top: 0; }
    .chat-message { padding: 1rem; border-radius: 10px; margin: 0.5rem 0; color: #FFFFFF; line-height: 1.6; }
    .user-message { background-color: #1E3A8A; margin-left: 20%; }
    .agent-message { background-color: #1F2937; margin-right: 20%; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #3b82f6 100%);
            padding: 2rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
            box-shadow: 0 10px 40px rgba(30,58,138,0.3);">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div>
            <h1 style="color: white; margin: 0; font-size: 2.2rem; font-weight: 700; letter-spacing: -0.5px;">
                Sanal Planner
            </h1>
            <p style="color: #93c5fd; margin: 0.3rem 0 0 0; font-size: 1rem; font-weight: 400;">
                AI-Powered Retail Planning & Analytics
            </p>
        </div>
        <div style="text-align: right;">
            <p style="color: #cbd5e1; margin: 0; font-size: 0.85rem;">""" + datetime.now().strftime('%d.%m.%Y') + """</p>
            <p style="color: #60a5fa; margin: 0.2rem 0 0 0; font-size: 0.75rem; font-weight: 500;">
                POWERED BY CLAUDE AI
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Ayarlar")
    
    # API Key - secrets.toml'dan otomatik yüklenir
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "").strip()
    except:
        api_key = ""

    if api_key:
        st.success("✅ API Bağlantısı Aktif")
    else:
        st.error("❌ API yapılandırması eksik. Sistem yöneticisi ile irtibata geçin.")
    
    st.markdown("---")

    # Admin Girişi - Veri bölümünden ÖNCE olmalı
    if 'admin_mode' not in st.session_state:
        st.session_state['admin_mode'] = False

    with st.expander("🔐 Admin Girişi", expanded=False):
        admin_pass = st.text_input("Admin Şifre", type="password", key="admin_pass_input")
        if admin_pass == "admin2024":
            if not st.session_state['admin_mode']:
                st.session_state['admin_mode'] = True
                st.rerun()
            st.success("Admin modu aktif")
        elif admin_pass:
            st.error("Yanlış şifre")

    st.markdown("---")

    # Veri Yükleme
    # Ana veri klasörü - dosyalar buraya kalıcı kaydedilir
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)

    # Uygulama başlarken data klasöründen otomatik yükle
    if not st.session_state.get('kup_yuklendi') and 'kup' not in st.session_state:
        # CUBE dosyası var mı kontrol et
        cube_var = any(
            'cube' in f.lower() for f in os.listdir(DATA_DIR)
            if f.endswith('.xlsx') or f.endswith('.xls')
        ) if os.path.exists(DATA_DIR) else False

        if cube_var:
            try:
                from agent_tools import KupVeri
                st.session_state['kup'] = KupVeri(DATA_DIR)
                st.session_state['kup_yuklendi'] = True
            except Exception as e:
                st.error(f"❌ Otomatik yükleme hatası: {e}")

    st.subheader("📊 Veri Durumu")

    if st.session_state.get('kup_yuklendi') and 'kup' in st.session_state:
        st.success("✅ Veri hazır")
        kup = st.session_state['kup']
        if len(kup.trading) > 0:
            st.caption(f"📈 Trading: {len(kup.trading):,} satır")
        if hasattr(kup, 'cover_diagram') and len(kup.cover_diagram) > 0:
            st.caption(f"🎯 Cover Diagram: {len(kup.cover_diagram):,} satır")
        if hasattr(kup, 'kapasite') and len(kup.kapasite) > 0:
            st.caption(f"🏪 Kapasite: {len(kup.kapasite):,} satır")
        if hasattr(kup, 'siparis_takip') and len(kup.siparis_takip) > 0:
            st.caption(f"📋 Sipariş Takip: {len(kup.siparis_takip):,} satır")
    else:
        # CUBE dosyası yoksa uyarı göster
        cube_var = any(
            'cube' in f.lower() for f in os.listdir(DATA_DIR)
            if f.endswith('.xlsx') or f.endswith('.xls')
        ) if os.path.exists(DATA_DIR) else False
        if not cube_var:
            st.error("⚠️ Veri dosyası bulunamadı. Lütfen sistem yöneticisi ile irtibata geçin.")
        else:
            st.info("👆 Verileri yüklemek için 'Verileri Güncelle' butonuna basın")

    # Veri güncelleme - Sadece Admin
    if st.session_state.get('admin_mode', False):
        with st.expander("📂 Verileri Güncelle", expanded=False):
            uploaded_files = st.file_uploader(
                "Dosyaları seçin (CUBE + Kapasite vb.)",
                type=['csv', 'xlsx', 'xls'],
                accept_multiple_files=True
            )

            if uploaded_files:
                if st.button("📂 Yükle ve Kaydet", use_container_width=True):
                    try:
                        from agent_tools import KupVeri

                        # Lokale kaydet
                        for uploaded_file in uploaded_files:
                            file_path = os.path.join(DATA_DIR, uploaded_file.name)
                            with open(file_path, 'wb') as f:
                                f.write(uploaded_file.getbuffer())
                            st.caption(f"✅ {uploaded_file.name} kaydedildi")

                        # GitHub'a push et (kalıcı)
                        try:
                            gh_token = st.secrets.get("GITHUB_TOKEN", "")
                            gh_repo = st.secrets.get("GITHUB_REPO", "HAKAN8080/Thorius_ai_planner")
                            if gh_token:
                                import requests as _req
                                from urllib.parse import quote
                                import base64 as _b64

                                # Token doğrulama
                                auth_check = _req.get("https://api.github.com/user",
                                    headers={"Authorization": f"token {gh_token}"})
                                if auth_check.status_code != 200:
                                    st.warning(f"⚠️ GitHub token geçersiz! (HTTP {auth_check.status_code})")
                                else:
                                    gh_user = auth_check.json().get("login", "?")
                                    st.caption(f"🔑 GitHub kullanıcı: {gh_user}")

                                    # Repo erişim kontrolü
                                    repo_check = _req.get(f"https://api.github.com/repos/{gh_repo}",
                                        headers={"Authorization": f"token {gh_token}"})
                                    if repo_check.status_code != 200:
                                        st.warning(f"⚠️ Repo erişim yok: {gh_repo} (HTTP {repo_check.status_code}) - Token'ın bu repoya yazma yetkisi olmalı!")
                                    else:
                                        perms = repo_check.json().get("permissions", {})
                                        st.caption(f"📦 Repo izinleri: push={perms.get('push')}, admin={perms.get('admin')}")

                                        if not perms.get("push"):
                                            st.warning("⚠️ Token'ın bu repoya PUSH yetkisi yok! Token scope'una 'repo' eklenmeli.")
                                        else:
                                            for uploaded_file in uploaded_files:
                                                file_content = uploaded_file.getbuffer().tobytes()
                                                gh_path = f"AI Agent/data/{uploaded_file.name}"
                                                api_url = f"https://api.github.com/repos/{gh_repo}/contents/{quote(gh_path, safe='/')}"
                                                headers = {"Authorization": f"token {gh_token}", "Accept": "application/vnd.github+json"}

                                                # Mevcut dosyanın SHA'sını al (güncelleme için gerekli)
                                                sha = None
                                                r = _req.get(api_url, headers=headers)
                                                if r.status_code == 200:
                                                    sha = r.json().get("sha")

                                                payload = {
                                                    "message": f"Veri güncelleme: {uploaded_file.name}",
                                                    "content": _b64.b64encode(file_content).decode('utf-8'),
                                                }
                                                if sha:
                                                    payload["sha"] = sha

                                                r2 = _req.put(api_url, json=payload, headers=headers)
                                                if r2.status_code in (200, 201):
                                                    st.caption(f"☁️ {uploaded_file.name} GitHub'a yüklendi")
                                                else:
                                                    st.warning(f"⚠️ GitHub yükleme hatası: {r2.status_code} - {r2.text[:200]}")
                            else:
                                st.caption("ℹ️ GitHub token yok, sadece lokale kaydedildi")
                        except Exception as gh_err:
                            st.caption(f"ℹ️ GitHub push atlandı: {gh_err}")

                        with st.spinner("Veri işleniyor..."):
                            st.session_state['kup'] = KupVeri(DATA_DIR)
                            st.session_state['kup_yuklendi'] = True

                        st.success("✅ Veriler güncellendi ve kaydedildi!")
                        st.rerun()

                    except Exception as e:
                        import traceback
                        st.error(f"❌ Hata: {str(e)}")
                        st.code(traceback.format_exc())

        # Verileri yenile butonu - Admin
        if st.button("🔄 Verileri Yenile", use_container_width=True):
            cube_var = any(
                'cube' in f.lower() for f in os.listdir(DATA_DIR)
                if f.endswith('.xlsx') or f.endswith('.xls')
            ) if os.path.exists(DATA_DIR) else False
            if cube_var:
                try:
                    from agent_tools import KupVeri
                    with st.spinner("Veriler yenileniyor..."):
                        st.session_state['kup'] = KupVeri(DATA_DIR)
                        st.session_state['kup_yuklendi'] = True
                    st.success("✅ Veriler yenilendi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Hata: {e}")
            else:
                st.error("⚠️ Veri dosyası bulunamadı. Lütfen sistem yöneticisi ile irtibata geçin.")
    
    st.markdown("---")
    
    # Sesli Yanıt
    st.subheader("🔊 Sesli Yanıt")
    sesli_aktif = st.toggle("Cevapları sesli oku", value=False)
    st.session_state['sesli_aktif'] = sesli_aktif
    
    if sesli_aktif:
        ses_secimi = st.radio("Ses seçin:", ["👨 Erol (Erkek)", "👩 Eftelya (Kadın)"], horizontal=True)
        st.session_state['ses_turu'] = "tr-TR-AhmetNeural" if "Erol" in ses_secimi else "tr-TR-EmelNeural"
    
    st.markdown("---")

    # Analiz Kuralları - Sadece admin görebilir
    if st.session_state.get('admin_mode', False):
        st.subheader("📋 Analiz Kuralları")
        with st.expander("⚙️ AI Eğitim Ayarları", expanded=False):
            analiz_sirasi = st.multiselect(
                "Analiz sırası",
                ["Trading Analiz", "Cover Analiz", "Sevkiyat Kontrolü", "Stok/Ciro Dengesi"],
                default=["Trading Analiz", "Cover Analiz"]
            )

            col1, col2 = st.columns(2)
            with col1:
                esik_cover_yuksek = st.number_input("Cover Yüksek (hf)", 6, 20, 12)
                esik_cover_dusuk = st.number_input("Cover Düşük (hf)", 1, 8, 4)
            with col2:
                esik_butce_sapma = st.number_input("Bütçe Sapma (%)", 5, 30, 15)
                esik_lfl_dusus = st.number_input("LFL Düşüş (%)", 5, 40, 20)

            st.markdown("---")
            st.markdown("**📝 Yorum Eğitimi**")
            st.caption("Analize nasıl bakılacağını ve yorum önceliğini yazın. Agent önce sizin kurallarınıza göre değerlendirme yapar, sonra kendi analizlerini ekler.")

            VARSAYILAN_YORUM_KURALLARI = """1. GRAND TOTAL ANALİZİ:
   - Bütçe gerçekleşme: Adet, Ciro, Kar ayrı ayrı
   - LFL: Stok, Adet, Ciro, Kar değişimleri
   - Haftalık ciro değişimi ve birim fiyat analizi

2. ANA GRUP TABLOSU:
   Tablo: Ana Grup, Bütçe%, LFL Stok, LFL Adet, LFL Ciro, Cover

3. DETAYLI ANA GRUP DEĞERLENDİRMESİ:
   - Her sorunlu grubu detaylı yorumla, sığ analiz yapma
   - Bütçe, LFL, cover, marj, stok/ciro dengesi, fiyat artışı hepsini kullan
   - Neden sorunlu olduğunu açıkla, aksiyon öner

4. ENF vs FİYAT ARTIŞI:
   - Enflasyon altı fiyat artışı + cover < 8 → fiyat artış açığı uyarısı
   - Promolar hariç fiyat artışını değerlendir

5. TOP 3 ANA GRUP DETAY + Top 1'in Top 2 SubGroup'u

6. SWOT ANALİZİ:
   - Güçlü/Zayıf yönler, Fırsatlar, Tehditler detaylı tablo

7. YASAK KURALLAR:
   - ASLA "delist" kelimesini kullanma, bahsetme
   - Bütçe verisi boş olan SubGroupDesc'lerden bahsetme
   - Her zaman aksiyon önerisi sun"""

            yorum_kurallari = st.text_area(
                "Yorum kuralları ve bakış açısı",
                value=st.session_state.get('yorum_kurallari_text', VARSAYILAN_YORUM_KURALLARI),
                height=350,
                key="yorum_kurallari_input"
            )
            st.session_state['yorum_kurallari_text'] = yorum_kurallari

            st.markdown("---")
            st.markdown("**🔀 Raporlama Öncelik Sırası**")
            oncelik_sirasi = st.multiselect(
                "Raporda hangi metrikler önce gelsin?",
                ["Bütçe Gerçekleşme", "LFL Ciro", "Cover", "Marj", "Stok/Ciro Dengesi", "Fiyat Artışı", "Adet Değişimi"],
                default=st.session_state.get('oncelik_sirasi_saved', ["Bütçe Gerçekleşme", "LFL Ciro", "Cover"]),
                key="oncelik_sirasi_input"
            )
            st.session_state['oncelik_sirasi_saved'] = oncelik_sirasi

            ai_yorum_ekle = st.checkbox("AI kendi ek yorumlarını da eklesin", value=True, key="ai_yorum_ekle")

            st.session_state['analiz_kurallari'] = {
                'analiz_sirasi': analiz_sirasi,
                'esikler': {
                    'cover_yuksek': esik_cover_yuksek,
                    'cover_dusuk': esik_cover_dusuk,
                    'butce_sapma': esik_butce_sapma,
                    'lfl_dusus': esik_lfl_dusus,
                },
                'yorumlar': {},
                'oncelik_sirasi': oncelik_sirasi,
                'ek_talimatlar': yorum_kurallari if yorum_kurallari else None,
                'ai_yorum_ekle': ai_yorum_ekle,
            }
    else:
        # Admin değilse varsayılan kuralları kullan
        if 'analiz_kurallari' not in st.session_state:
            st.session_state['analiz_kurallari'] = {
                'analiz_sirasi': ["Trading Analiz", "Cover Analiz"],
                'esikler': {'cover_yuksek': 12, 'cover_dusuk': 4, 'butce_sapma': 15, 'lfl_dusus': 20},
                'yorumlar': {},
                'oncelik_sirasi': ["Bütçe Gerçekleşme", "LFL Ciro", "Cover"],
                'ek_talimatlar': st.session_state.get('yorum_kurallari_text', None),
                'ai_yorum_ekle': True,
            }

    st.markdown("---")

    # Hızlı Komutlar
    st.subheader("⚡ Hızlı Komutlar")
    if st.button("📊 Genel Durum", use_container_width=True):
        st.session_state['hizli_komut'] = "Genel durum analizi ve SWOT analizi yapar mısın?"
    if st.button("🏪 Kapasite Analizi", use_container_width=True):
        st.session_state['hizli_komut'] = "Sadece kapasite analizi yap. Trading analizi yapma. Mağaza doluluk oranları, doluluk aralıkları dağılımı, acil sevkiyat gereken mağazalar, stok eritme gereken mağazalar ve en kritik 5 mağazayı raporla."
    
    # Grup Detay Analizi
    st.markdown("---")
    st.subheader("🔍 Grup Detay Analizi")
    
    # Ana grupları trading'den çek
    ana_grup_listesi = []
    if st.session_state.get('kup_yuklendi') and 'kup' in st.session_state:
        kup = st.session_state['kup']
        if len(kup.trading) > 0:
            # Mevcut Ana Grup kolonunu bul (hem eski hem CUBE format)
            ana_grup_kolon = None
            for col in kup.trading.columns:
                col_lower = str(col).lower().strip()
                if col_lower in ('ana grup', 'ana_grup', 'maingroupdesc', 'main group', 'main_group_desc'):
                    ana_grup_kolon = col
                    break

            if ana_grup_kolon:
                # Unique ana grupları al, Toplam/Total/Grand Total hariç
                tum_gruplar = kup.trading[ana_grup_kolon].dropna().unique().tolist()
                ana_grup_listesi = [
                    g for g in tum_gruplar
                    if g and str(g).strip() != '' and str(g).lower() != 'nan'
                    and 'toplam' not in str(g).lower()
                    and str(g).lower() not in ('total', 'grand total')
                    and not str(g).strip().endswith(' Total')
                ]
                ana_grup_listesi = sorted(set(ana_grup_listesi))
    
    if ana_grup_listesi:
        secili_ana_grup = st.selectbox(
            "Ana Grup Seçin:",
            options=["-- Seçiniz --"] + ana_grup_listesi,
            key="ana_grup_secim"
        )
        
        if secili_ana_grup and secili_ana_grup != "-- Seçiniz --":
            if st.button(f"🔎 {secili_ana_grup} Tam Detay", use_container_width=True, key="btn_detay"):
                st.session_state['hizli_komut'] = f"{secili_ana_grup} grubunu detaylı analiz et. Mevcut tüm raporları kullanarak bütçe gerçekleşme, ciro, cover, marj, LFL performansı, alt grupları, sorunlu alanları ve aksiyon önerilerini sun."
    else:
        st.caption("📁 Veri yüklenince ana gruplar burada listelenecek")


# Ana içerik - Chat
st.header("💬 Planner ile Konuş")

if 'messages' not in st.session_state:
    st.session_state['messages'] = []

for msg in st.session_state['messages']:
    if msg['role'] == 'user':
        st.markdown(f'<div class="chat-message user-message">🧑 {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="chat-message agent-message">🤖 {msg["content"]}</div>', unsafe_allow_html=True)

# Hızlı komut
if 'hizli_komut' in st.session_state and st.session_state['hizli_komut']:
    kullanici_mesaji = st.session_state['hizli_komut']
    st.session_state['hizli_komut'] = None
else:
    kullanici_mesaji = None

user_input = st.chat_input("Soru sor...")
mesaj = kullanici_mesaji or user_input

if mesaj:
    if not api_key:
        st.error("❌ API key girin.")
    elif 'kup' not in st.session_state:
        st.error("❌ Veri yükleyin.")
    else:
        st.markdown(f'<div class="chat-message user-message">🧑 {mesaj}</div>', unsafe_allow_html=True)

        # Custom AI thinking animasyonu
        thinking_placeholder = st.empty()
        thinking_placeholder.markdown("""
        <div style="display: flex; align-items: center; gap: 16px; padding: 1.2rem 1.5rem;
                    background: linear-gradient(135deg, #0f172a, #1e293b); border-radius: 12px;
                    margin: 0.5rem 0; border: 1px solid #334155;">
            <div style="position: relative; width: 48px; height: 48px; flex-shrink: 0;">
                <div style="position: absolute; inset: 0; border-radius: 50%;
                            background: conic-gradient(#3b82f6, #8b5cf6, #06b6d4, #3b82f6);
                            animation: spin 2s linear infinite;"></div>
                <div style="position: absolute; inset: 3px; border-radius: 50%; background: #0f172a;
                            display: flex; align-items: center; justify-content: center;
                            font-size: 20px;">🧠</div>
            </div>
            <div>
                <div style="color: #e2e8f0; font-size: 1rem; font-weight: 600;">Sanal Planner Analiz Ediyor</div>
                <div style="color: #94a3b8; font-size: 0.85rem; margin-top: 2px;">
                    Veriler isleniyor
                    <span style="display: inline-block; animation: dotPulse 1.5s infinite;">.</span>
                    <span style="display: inline-block; animation: dotPulse 1.5s infinite 0.3s;">.</span>
                    <span style="display: inline-block; animation: dotPulse 1.5s infinite 0.6s;">.</span>
                </div>
            </div>
        </div>
        <style>
            @keyframes spin { to { transform: rotate(360deg); } }
            @keyframes dotPulse { 0%,100% { opacity: 0.2; } 50% { opacity: 1; } }
        </style>
        """, unsafe_allow_html=True)

        try:
            from agent_tools import agent_calistir

            analiz_kurallari = st.session_state.get('analiz_kurallari', None)
            sonuc = agent_calistir(api_key, st.session_state['kup'], mesaj, analiz_kurallari=analiz_kurallari)

            thinking_placeholder.empty()

            if sonuc and len(sonuc.strip()) > 0:
                st.session_state['messages'].append({'role': 'user', 'content': mesaj})
                st.session_state['messages'].append({'role': 'agent', 'content': sonuc})
                st.markdown(f'<div class="chat-message agent-message">🤖 {sonuc}</div>', unsafe_allow_html=True)

                if st.session_state.get('sesli_aktif', False):
                    sesli_metin = sonuc.split("📊")[0] if "📊" in sonuc else sonuc[:1500]
                    ses_turu = st.session_state.get('ses_turu', 'tr-TR-AhmetNeural')
                    audio_html = sesli_oku(sesli_metin.strip(), ses=ses_turu)
                    st.markdown(audio_html, unsafe_allow_html=True)
            else:
                st.warning("⚠️ Agent yanıt vermedi.")

        except Exception as e:
            thinking_placeholder.empty()
            import traceback
            st.error(f"❌ Hata: {str(e)}")
            st.code(traceback.format_exc())


# Alt butonlar
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🗑️ Sohbeti Temizle", use_container_width=True):
        st.session_state['messages'] = []
        st.rerun()

with col2:
    if st.session_state.get('messages'):
        sohbet_metni = ""
        for msg in st.session_state['messages']:
            prefix = "🧑 KULLANICI" if msg['role'] == 'user' else "🤖 SANAL PLANNER"
            sohbet_metni += f"{prefix}:\n{msg['content']}\n\n{'='*60}\n\n"
        
        st.download_button(
            label="📋 TXT İndir",
            data=sohbet_metni,
            file_name="sanal_planner_sohbet.txt",
            mime="text/plain",
            use_container_width=True
        )

with col3:
    # Son cevabı PDF olarak indir
    if st.session_state.get('messages'):
        son_soru = ""
        son_cevap = ""
        for msg in reversed(st.session_state['messages']):
            if msg['role'] == 'agent' and not son_cevap:
                son_cevap = msg['content']
            elif msg['role'] == 'user' and son_cevap and not son_soru:
                son_soru = msg['content']
                break
        
        if son_cevap:
            try:
                pdf_bytes = create_pdf_report(soru=son_soru, cevap=son_cevap)
                st.download_button(
                    label="📄 Son Rapor PDF",
                    data=pdf_bytes,
                    file_name=f"sanal_planner_rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"PDF hatası: {e}")

with col4:
    # Tüm sohbeti PDF olarak indir
    if st.session_state.get('messages') and len(st.session_state['messages']) >= 2:
        try:
            pdf_bytes = create_chat_pdf(st.session_state['messages'])
            st.download_button(
                label="📑 Tüm Sohbet PDF",
                data=pdf_bytes,
                file_name=f"sanal_planner_sohbet_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"PDF hatası: {e}")


# Footer
st.markdown("---")
st.markdown(
    """<div style='text-align: center; color: #6B7280; font-size: 0.9rem;'>
    ⭐ Sanal Planner v2.1 | Thorius AI4U
    </div>""",
    unsafe_allow_html=True
)
