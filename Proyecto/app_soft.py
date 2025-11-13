import streamlit as st
import os
import json
import hashlib
from dotenv import load_dotenv
from openai import OpenAI
from difflib import SequenceMatcher

# CONFIGURACIÓN INICIAL
st.set_page_config(page_title="SOFT-IA", layout="wide")

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
        json.dump({"contrasena": cifrar_contrasena(p), "mensajes": []}, f, indent=2)
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

    st.title("🤖 SOFT-IA — Agente de Ingenieria de Software")

    chat_area = st.container()

    # Mostrar historial persistente
    with chat_area:
        for mensaje in st.session_state.mensajes:
            with st.chat_message(mensaje["role"]):
                st.markdown(mensaje["content"])

    if mensaje_usuario := st.chat_input("¿En qué puedo ayudarte hoy?"):
        st.session_state.mensajes.append({"role": "user", "content": mensaje_usuario})
        with chat_area.chat_message("user"):
            st.markdown(mensaje_usuario)

        fragmentos = buscar_fragmentos(mensaje_usuario)
        contexto = "\n\n".join([f" [{f[1]}]\n{f[2][:2000]}" for f in fragmentos])

        with chat_area.chat_message("assistant"):
            st.write("💭 Analizando tus libros, un momento...")

        prompt = (
            "Responde de forma clara y académica en español. "
            "Usa la siguiente información de libros de ingeniería de software como base, "
            "pero complementa con tu conocimiento general cuando sea necesario.\n\n"
            f"{contexto}\n\n"
            f"Pregunta del estudiante: {mensaje_usuario}"
        )


        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Eres un experto en ingeniería de software."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )

        texto_respuesta = response.choices[0].message.content

        st.session_state.mensajes.append({"role": "assistant", "content": texto_respuesta})
        with chat_area.chat_message("assistant"):
            st.markdown(texto_respuesta)

        if st.session_state.usuario:
            guardar_mensajes(st.session_state.usuario, st.session_state.mensajes)
