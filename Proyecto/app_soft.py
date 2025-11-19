import streamlit as st
import os
import json
import hashlib
import io
import fitz
from docx import Document
from PIL import Image
import pytesseract
# Ajusta la ruta si es necesario
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from dotenv import load_dotenv
# --- MODIFICACIÓN (NOTIFICACIONES): Importamos error específico de conexión ---
from openai import OpenAI, APIConnectionError
from difflib import SequenceMatcher

# CONFIGURACIÓN INICIAL
st.set_page_config(page_title="SOFT-IA", layout="wide")

# --- MODIFICACIÓN (NOTIFICACIONES): GESTOR DE NOTIFICACIONES PENDIENTES ---
# Este bloque soluciona el problema de que los mensajes desaparecían al cambiar de pantalla.
if "notificacion_pendiente" not in st.session_state:
    st.session_state.notificacion_pendiente = None

if st.session_state.notificacion_pendiente:
    msg = st.session_state.notificacion_pendiente
    st.toast(msg["texto"], icon=msg["icono"])
    # Limpiamos para que no salga cada vez que toques un botón
    st.session_state.notificacion_pendiente = None 
# ---------------------------------------------------------------------------

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

CARPETA_RESUMENES = "libros_resumen"
CARPETA_USUARIOS = "usuarios"
os.makedirs(CARPETA_RESUMENES, exist_ok=True)
os.makedirs(CARPETA_USUARIOS, exist_ok=True)

# FUNCIONES DE USUARIOS
def cifrar_contrasena(c):
    return hashlib.sha256(c.encode()).hexdigest()

def archivo_usuario(u):
    return os.path.join(CARPETA_USUARIOS, f"{u}.json")

def usuario_existe(u):
    return os.path.exists(archivo_usuario(u))

def crear_usuario(u, p):
    if usuario_existe(u): return False
    with open(archivo_usuario(u), "w") as f:
        json.dump({"contrasena": cifrar_contrasena(p),
                   "mensajes": [],
                   "archivos": [] 
                }, f, indent=2)
    return True

def verificar_usuario(u, p):
    if not usuario_existe(u): return False
    with open(archivo_usuario(u)) as f: data = json.load(f)
    return data["contrasena"] == cifrar_contrasena(p)

def cargar_mensajes(u):
    with open(archivo_usuario(u)) as f: data = json.load(f)
    return data.get("mensajes", [])

def guardar_mensajes(u, m):
    with open(archivo_usuario(u)) as f: data = json.load(f)
    data["mensajes"] = m
    with open(archivo_usuario(u), "w") as f: json.dump(data, f, indent=2)

def cargar_archivos_usuario(u):
    with open(archivo_usuario(u)) as f:
        data = json.load(f)
    return data.get("archivos", [])

def guardar_archivo_usuario(u, nombre, contenido):
    with open(archivo_usuario(u)) as f:
        data = json.load(f)

    for nom_arch in data["archivos"]:
        if nom_arch["nombre"] == nombre:
            return 
        
    data["archivos"].append({
        "nombre": nombre,
        "contenido": contenido
    })

    with open(archivo_usuario(u), "w") as f:
        json.dump(data, f, indent=2)

def procesar_pdf(archivo):
    doc = fitz.open(stream=archivo.read(), filetype="pdf")
    texto = ""
    for page in doc:
        texto += page.get_text()
    return texto

def procesar_docx(archivo):
    doc = Document(io.BytesIO(archivo.read()))
    return "\n".join([p.text for p in doc.paragraphs])

def procesar_imagen(archivo):
    try:
        img = Image.open(io.BytesIO(archivo.read()))
        texto_extraido = pytesseract.image_to_string(img, lang="spa")
        if not texto_extraido.strip():
            texto_extraido = "(No se detectó texto legible en la imagen)"
        return {"tipo": "texto", "texto": texto_extraido}
    except Exception as e:
        return {"tipo": "texto", "texto": f"(Error procesando la imagen: {e})"}

def guardar_en_bibliografia(nombre, texto):
    ruta = os.path.join(CARPETA_RESUMENES, f"{nombre}.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    st.session_state.resumenes = cargar_resumenes()

def cargar_resumenes():
    resumenes = []
    for nombre in os.listdir(CARPETA_RESUMENES):
        if nombre.endswith(".txt"):
            with open(os.path.join(CARPETA_RESUMENES, nombre), "r", encoding="utf-8") as f:
                resumenes.append({"nombre": nombre, "texto": f.read()})
    return resumenes

if "resumenes" not in st.session_state:
    st.session_state.resumenes = cargar_resumenes()

def buscar_fragmentos(texto_usuario, top_n=6):
    resultados = []
    for r in st.session_state.resumenes:
        similitud = SequenceMatcher(None, texto_usuario.lower(), r["texto"].lower()).ratio()
        resultados.append((similitud, r["nombre"], r["texto"]))
    resultados.sort(reverse=True, key=lambda x: x[0])
    return resultados[:top_n]

# ESTADO DE SESIÓN
if "logueado" not in st.session_state:
    st.session_state.logueado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

# LOGIN / INVITADO
if not st.session_state.logueado:
    st.title("SOFT-IA — Agente de Ingenieria de Software")
    modo = st.radio("Modo de uso:", ["Invitado", "Registrarse / Iniciar sesión"])

    if modo == "Invitado":
        if st.button("Usar como invitado"):
            st.session_state.logueado = True
            st.session_state.usuario = None
            st.session_state.mensajes = []
            st.rerun()
    else:
        with st.form("registro"):
            st.subheader("Crear cuenta")
            nuevo = st.text_input("Usuario", key="reg_user")
            contrasena = st.text_input("Contraseña", type="password", key="reg_pass")
            repetir = st.text_input("Repetir contraseña", type="password", key="reg_pass2")
            if st.form_submit_button("Crear cuenta"):
                if not nuevo or not contrasena:
                    st.warning("Completa todos los campos.")
                elif contrasena != repetir:
                    st.error("Las contraseñas no coinciden.")
                elif usuario_existe(nuevo):
                    st.error("El usuario ya existe.")
                else:
                    crear_usuario(nuevo, contrasena)
                    st.session_state.logueado = True
                    st.session_state.usuario = nuevo
                    
                    # --- MODIFICACIÓN (NOTIFICACIONES): Guardar mensaje antes del rerun ---
                    st.session_state.notificacion_pendiente = {
                        "texto": f"¡Bienvenido {nuevo}! Cuenta creada.",
                        "icono": "🎉"
                    }
                    st.rerun()

        with st.form("login"):
            st.subheader("Iniciar sesión")
            nombre = st.text_input("Usuario", key="login_user")
            contrasena = st.text_input("Contraseña", type="password", key="login_pass")
            if st.form_submit_button("Entrar"):
                if verificar_usuario(nombre, contrasena):
                    st.session_state.logueado = True
                    st.session_state.usuario = nombre
                    st.session_state.mensajes = cargar_mensajes(nombre)
                    
                    # --- MODIFICACIÓN (NOTIFICACIONES): Guardar mensaje antes del rerun ---
                    st.session_state.notificacion_pendiente = {
                        "texto": f"Hola de nuevo, {nombre}.",
                        "icono": "👋"
                    }
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

# CHAT PRINCIPAL
if st.session_state.logueado:
    st.sidebar.write(f"👤 Usuario: {st.session_state.usuario or 'Invitado'}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.logueado = False
        st.session_state.usuario = None
        st.session_state.mensajes = []
        st.rerun()

    archivo_biblio = st.sidebar.file_uploader(
        "Subir archivo a Bibliografía",
        type=["pdf", "docx"],
        key="biblio_uploader"
    )

    if archivo_biblio:
        nombre = archivo_biblio.name.split(".")[0]
        if archivo_biblio.name.endswith(".pdf"):
            texto = procesar_pdf(archivo_biblio)
        elif archivo_biblio.name.endswith(".docx"):
            texto = procesar_docx(archivo_biblio)
        else:
            st.sidebar.error("Formato no soportado.")
            texto = ""
        guardar_en_bibliografia(nombre, texto)
        st.sidebar.success(f"'{nombre}' agregado a la bibliografía.")

    st.title("🤖 SOFT-IA — Agente de Ingenieria de Software")

    chat_area = st.container()

    with chat_area:
        for mensaje in st.session_state.mensajes:
            with st.chat_message(mensaje["role"]):
                st.markdown(mensaje["content"])
    
    archivo = st.file_uploader(
        "Sube un archivo a tu memoria personal",
        type=["pdf", "docx", "png", "jpg", "jpeg"])

    if archivo:
        nombre = archivo.name.lower()
        if nombre.endswith(".pdf"):
            contenido = {"tipo": "texto", "texto": procesar_pdf(archivo)}
        elif nombre.endswith(".docx"):
            contenido = {"tipo": "texto", "texto": procesar_docx(archivo)}
        else:
            contenido = procesar_imagen(archivo)

        if st.session_state.usuario:
            guardar_archivo_usuario(st.session_state.usuario, archivo.name, contenido)
            # --- MODIFICACIÓN (NOTIFICACIONES): Aviso simple de archivo guardado ---
            st.toast(f"Archivo '{archivo.name}' guardado en memoria.", icon="💾")

    if mensaje_usuario := st.chat_input("¿En qué puedo ayudarte hoy?"):
        # --- MODIFICACIÓN (CONTEXTO): Guardamos input usuario antes de llamar API ---
        st.session_state.mensajes.append({"role": "user", "content": mensaje_usuario})
        
        with chat_area.chat_message("user"):
            st.markdown(mensaje_usuario)

        memoria_archivos = []
        if st.session_state.usuario:
            archivos_usuario = cargar_archivos_usuario(st.session_state.usuario)
            for a in archivos_usuario:
                if a["contenido"]["tipo"] == "texto":
                    memoria_archivos.append(f"[Archivo usuario: {a['nombre']}]\n{a['contenido']['texto'][:2000]}")
                else:
                    memoria_archivos.append(f"[Imagen usuario: {a['nombre']} (OCR)]")
        memoria_str = "\n\n".join(memoria_archivos)

        fragmentos = buscar_fragmentos(mensaje_usuario)
        contexto_libros = "\n\n".join([f" [Fuente: {f[1]}]\n{f[2][:2000]}" for f in fragmentos])

        # --- MODIFICACIÓN (CONTEXTO): Prompt de Sistema reforzado para usar memoria ---
        instrucciones_sistema = (
            "Eres SOFT-IA, un experto en ingeniería de software. "
            "IMPORTANTE: Tienes acceso total al historial de esta conversación. "
            "Revisa los mensajes anteriores para mantener el contexto. "
            "CONTEXTO ADICIONAL (Archivos y Libros):\n"
            f"{memoria_str}\n"
            f"{contexto_libros}\n"
        )

        # --- MODIFICACIÓN (CONTEXTO): Construcción de la lista con historial completo ---
        mensajes_api = [{"role": "system", "content": instrucciones_sistema}]
        mensajes_api.extend(st.session_state.mensajes)

        with chat_area.chat_message("assistant"):
            try:
                with st.spinner("Pensando..."): 
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=mensajes_api, # Enviamos todo el historial
                        temperature=0.4
                    )
                texto_respuesta = response.choices[0].message.content
                
                st.markdown(texto_respuesta)
                st.session_state.mensajes.append({"role": "assistant", "content": texto_respuesta})
                if st.session_state.usuario:
                    guardar_mensajes(st.session_state.usuario, st.session_state.mensajes)

            # --- MODIFICACIÓN (NOTIFICACIONES): Manejo de errores de conexión ---
            except APIConnectionError:
                st.error("⚠️ SIN CONEXIÓN A INTERNET: No se pudo conectar con el agente. Verifica tu red.")
                
            except Exception as e:
                st.error(f"❌ ERROR DE CONEXIÓN CON API: Ocurrió un problema técnico. Detalle: {e}")