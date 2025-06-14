# app.py
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import pikepdf
import tempfile
import os

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
                mat = fitz.Matrix(DPI / 72, DPI / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.thumbnail(LETTER_PX, resample=Image.Resampling.LANCZOS)
                images.append(img)
        doc.close()

        # Monta PDF em memória
        pdf_buf = io.BytesIO()
        images[0].save(
            pdf_buf,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            dpi=(DPI, DPI),
            quality=QUALITY,
            optimize=True,
        )
        pdf_buf.seek(0)

        # Comprime streams via pikepdf
        compressed_buf = io.BytesIO()
        with pikepdf.Pdf.open(pdf_buf) as src:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp_path = tmp.name
            tmp.close()
            try:
                src.save(tmp_path, optimize_streams=True, compress_streams=True)
            except TypeError:
                src.save(tmp_path)
            with open(tmp_path, "rb") as f:
                compressed_buf.write(f.read())
            compressed_buf.seek(0)
            os.remove(tmp_path)

        size_kb = len(compressed_buf.getvalue()) / 1024
        st.write(f"🔄 Tamanho final: **{size_kb:.1f} KB**")
        if size_kb > MAX_PDF_KB:
            st.warning(f"Ainda acima de {MAX_PDF_KB} KB. Ajuste DPI/qualidade.")
        st.download_button(
            label="⬇️ Baixar PDF comprimido",
            data=compressed_buf.getvalue(),
            file_name="compressed.pdf",
            mime="application/pdf",
        )

#################################
# Aba 2: Gerador de Foto Passe
#################################
with tab2:
    st.header("Geração de Foto Tipo Passe (Central Crop)")
    st.write(
        "- JPEG, ≤150 KB\n"
        "- Máximo 2.5×3.5″ → 750×1050 px (a 300 dpi)\n"
        "- Crop central (rosto aproximado no centro da imagem original)"
    )
    uploaded_img = st.file_uploader("Envie uma foto JPEG", type=["jpg", "jpeg"])
    if uploaded_img:
        data = uploaded_img.read()
        if len(data) > MAX_PHOTO_KB * 1024:
            st.error("Arquivo maior que 150 KB.")
            st.stop()

        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            st.error("Não foi possível ler a imagem.")
            st.stop()

        st.image(img, caption="Original (confirme rosto centralizado)")

        # Crop central mantendo proporção TARGET_PHOTO_PX
        orig_w, orig_h = img.size
        target_ratio = TARGET_PHOTO_PX[0] / TARGET_PHOTO_PX[1]
        orig_ratio = orig_w / orig_h

        if orig_ratio > target_ratio:
            new_w = int(orig_h * target_ratio)
            new_h = orig_h
        else:
            new_w = orig_w
            new_h = int(orig_w / target_ratio)

        left = (orig_w - new_w) // 2
        top = (orig_h - new_h) // 2
        crop = img.crop((left, top, left + new_w, top + new_h))

        # Redimensiona para TARGET_PHOTO_PX
        cropped = crop.resize(TARGET_PHOTO_PX, resample=Image.Resampling.LANCZOS)
        st.image(cropped, caption="Preview do Passe (750×1050 px)")

        # Ajusta qualidade até ≤150 KB e salva com 300 dpi
        buf = io.BytesIO()
        qual = 90
        while qual >= 10:
            buf.seek(0)
            buf.truncate(0)
            cropped.save(
                buf,
                format="JPEG",
                quality=qual,
                optimize=True,
                dpi=(300, 300),
            )
            if buf.tell() <= MAX_PHOTO_KB * 1024:
                break
            qual -= 10
        buf.seek(0)

        final_kb = buf.getbuffer().nbytes / 1024
        st.write(f"Tamanho final: **{final_kb:.1f} KB** (qualidade {qual}, 300 dpi)")
        if final_kb > MAX_PHOTO_KB:
            st.warning("Não atingiu ≤150 KB. Use outra foto ou recorte manualmente.")

        st.download_button(
            label="⬇️ Baixar Foto Tipo Passe",
            data=buf.getvalue(),
            file_name="passport_photo.jpg",
            mime="image/jpeg",
        )
