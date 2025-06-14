# app.py
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import pikepdf
import tempfile
import os
import cv2
import numpy as np

# Configurações gerais
MAX_PDF_KB = 1200
MAX_PHOTO_KB = 150
# Foto de 2.5×3.5″ @300 dpi → 750×1050 px
TARGET_PHOTO_PX = (750, 1050)
DEFAULT_DPI = 150
DEFAULT_QUALITY = 50

st.set_page_config(page_title="Doc & Photo Tool", layout="wide")
st.title("🗎 Compressor de PDF & 📸 Gerador de Foto Passe (sem OpenAI)")

tab1, tab2 = st.tabs(["📑 Compressor de PDF", "📸 Gerador de Foto Passe"])

#################################
# Aba 1: Compressor de PDF
#################################
with tab1:
    st.header("Compressão de PDF")
    st.sidebar.header("Configurações de PDF")
    DPI = st.sidebar.slider("DPI de saída", 72, 300, DEFAULT_DPI, 1)
    QUALITY = st.sidebar.slider("Qualidade JPEG", 10, 95, DEFAULT_QUALITY, 1)
    LETTER_PX = (int(8.5 * DPI), int(11 * DPI))

    uploaded_pdf = st.file_uploader("Envie um PDF (único, sem senha)", type="pdf")
    if uploaded_pdf:
        raw = uploaded_pdf.read()
        try:
            doc = fitz.open(stream=raw, filetype="pdf")
        except Exception:
            st.error("Não foi possível abrir o PDF.")
            st.stop()
        if doc.is_encrypted:
            st.error("PDF protegido — envie sem senha.")
            doc.close()
            st.stop()

        images = []
        with st.spinner("Renderizando páginas…"):
            for i in range(len(doc)):
                page = doc.load_page(i)
                mat = fitz.Matrix(DPI/72, DPI/72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.thumbnail(LETTER_PX, resample=Image.Resampling.LANCZOS)
                images.append(img)
        doc.close()

        buf = io.BytesIO()
        images[0].save(
            buf, format="PDF", save_all=True, append_images=images[1:],
            dpi=(DPI, DPI), quality=QUALITY, optimize=True
        )
        buf.seek(0)

        comp = io.BytesIO()
        with pikepdf.Pdf.open(buf) as src:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            path = tmp.name; tmp.close()
            try:
                src.save(path, optimize_streams=True, compress_streams=True)
            except TypeError:
                src.save(path)
            with open(path, "rb") as f:
                comp.write(f.read())
            comp.seek(0); os.remove(path)

        size_kb = len(comp.getvalue())/1024
        st.write(f"🔄 Tamanho final: **{size_kb:.1f} KB**")
        if size_kb > MAX_PDF_KB:
            st.warning(f"Ainda acima de {MAX_PDF_KB} KB. Ajuste DPI/qualidade.")
        st.download_button("⬇️ Baixar PDF comprimido", comp.getvalue(),
                           "compressed.pdf", "application/pdf")

#################################
# Aba 2: Gerador de Foto Passe
#################################
with tab2:
    st.header("Geração de Foto Tipo Passe (Local)")
    st.write(
        "- JPEG, ≤150 KB\n"
        "- Máximo 2.5×3.5″ → 750×1050 px\n"
        "- Full-front head & shoulders, rosto centralizado"
    )
    uploaded_img = st.file_uploader(
        "Envie uma foto JPEG", type=["jpg","jpeg"]
    )
    if uploaded_img:
        data = uploaded_img.read()
        if len(data) > MAX_PHOTO_KB*1024:
            st.error("Arquivo maior que 150 KB.")
            st.stop()

        # Abre imagem e converte para RGB
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            st.error("Não foi possível ler a imagem.")
            st.stop()

        # Detecta rosto
        img_np = np.array(img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) == 0:
            st.error("Nenhum rosto detectado. Use uma foto com rosto de frente.")
            st.stop()

        # Escolhe o maior rosto detectado
        x,y,w,h = max(faces, key=lambda b: b[2]*b[3])
        # Expande a caixa para incluir ombros (1.5× altura do rosto)
        pad_h = int(0.5 * h)
        y0 = max(0, y - pad_h//2)
        y1 = min(img.height, y + h + pad_h)
        x0 = max(0, x - w//4)
        x1 = min(img.width, x + w + w//4)
        crop = img.crop((x0, y0, x1, y1))

        # Redimensiona e pad para TARGET_PHOTO_PX
        crop.thumbnail(TARGET_PHOTO_PX, Image.Resampling.LANCZOS)
        bg = Image.new("RGB", TARGET_PHOTO_PX, (255,255,255))
        bx = (TARGET_PHOTO_PX[0] - crop.width)//2
        by = (TARGET_PHOTO_PX[1] - crop.height)//2
        bg.paste(crop, (bx, by))

        st.image(bg, caption="Preview", use_column_width=False)

        # Ajusta qualidade para ficar ≤150 KB
        buf = io.BytesIO()
        qual = 90
        while qual >= 10:
            buf.seek(0); buf.truncate(0)
            bg.save(buf, format="JPEG", quality=qual, optimize=True)
            size = buf.tell()
            if size <= MAX_PHOTO_KB*1024:
                break
            qual -= 10
        buf.seek(0)
        final_size_kb = buf.getbuffer().nbytes / 1024
        st.write(f"Tamanho final: **{final_size_kb:.1f} KB** (qualidade {qual})")
        if final_size_kb > MAX_PHOTO_KB:
            st.warning("Não foi possível atingir ≤150 KB. Considere recortar / usar outra foto.")

        st.download_button(
            "⬇️ Baixar Foto Tipo Passe",
            buf.getvalue(),
            file_name="passport_photo.jpg",
            mime="image/jpeg"
        )
