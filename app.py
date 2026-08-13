#!/usr/bin/env python3
"""Servidor local para el registro de gastos. Solo usa la librería estándar."""

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import date
from html import escape as xml_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CUENTAS_PATH = os.path.join(DATA_DIR, "cuentas.json")
GASTOS_PATH = os.path.join(DATA_DIR, "gastos.json")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

PORT = int(os.environ.get("GASTOS_PORT", "5000"))

_lock = threading.Lock()

STATIC_MIME = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def git_sync(message):
    def _run():
        try:
            subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, capture_output=True, timeout=15)
            subprocess.run(["git", "commit", "-m", message], cwd=BASE_DIR, capture_output=True, timeout=15)
            result = subprocess.run(["git", "push"], cwd=BASE_DIR, capture_output=True, timeout=30)
            if result.returncode != 0:
                print(f"[git-sync] aviso al hacer push: {result.stderr.decode(errors='replace').strip()}")
        except Exception as exc:
            print(f"[git-sync] aviso: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def current_month():
    return date.today().strftime("%Y-%m")


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        return None
    try:
        return load_json(CONFIG_PATH)
    except Exception:
        return None


def add_gasto(fecha, categoria, monto, descripcion, origen="web"):
    gasto = {
        "id": str(uuid.uuid4()),
        "fecha": fecha,
        "categoria": (categoria or "Otros").strip() or "Otros",
        "monto": float(monto),
        "descripcion": (descripcion or "").strip(),
    }
    with _lock:
        gastos = load_json(GASTOS_PATH)
        gastos.append(gasto)
        save_json(GASTOS_PATH, gastos)
    git_sync(f"Agrega gasto ({origen}): {gasto['categoria']} ${gasto['monto']}")
    return gasto


def verify_twilio_signature(auth_token, full_url, form_params, signature):
    if not signature:
        return False
    data = full_url
    for key in sorted(form_params.keys()):
        data += key + form_params[key][0]
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def parse_gasto_mensaje(texto):
    partes = texto.strip().split(maxsplit=2)
    if len(partes) < 2:
        return None
    monto_str = partes[0].replace("$", "").replace(",", "")
    try:
        monto = float(monto_str)
    except ValueError:
        return None
    if monto <= 0:
        return None
    categoria = partes[1]
    descripcion = partes[2] if len(partes) > 2 else ""
    return monto, categoria, descripcion


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    # ---------- helpers ----------
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _read_form_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        return parse_qs(raw.decode("utf-8"))

    def _send_twiml(self, mensaje, status=200):
        body = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{xml_escape(mensaje)}</Message></Response>".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self._send_json({"error": "no encontrado"}, status=404)

    # ---------- routing ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            return self._send_file(os.path.join(TEMPLATES_DIR, "index.html"), "text/html; charset=utf-8")

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            full = os.path.normpath(os.path.join(STATIC_DIR, rel))
            if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
                return self._not_found()
            ext = os.path.splitext(full)[1]
            return self._send_file(full, STATIC_MIME.get(ext, "application/octet-stream"))

        if path == "/api/cuentas":
            with _lock:
                cuentas = load_json(CUENTAS_PATH)
            return self._send_json(cuentas)

        if path == "/api/gastos":
            mes = qs.get("mes", [current_month()])[0]
            with _lock:
                gastos = load_json(GASTOS_PATH)
            gastos_mes = [g for g in gastos if g["fecha"].startswith(mes)]
            gastos_mes.sort(key=lambda g: g["fecha"], reverse=True)
            return self._send_json(gastos_mes)

        if path == "/api/resumen":
            mes = qs.get("mes", [current_month()])[0]
            return self._send_json(self._build_resumen(mes))

        return self._not_found()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/cuentas":
            body = self._read_json_body()
            cuenta = {
                "id": str(uuid.uuid4()),
                "nombre": body.get("nombre", "").strip(),
                "monto": float(body.get("monto", 0)),
                "dia_vencimiento": int(body.get("dia_vencimiento", 1)),
                "categoria": body.get("categoria", "Otros").strip() or "Otros",
                "activa": True,
            }
            if not cuenta["nombre"] or cuenta["monto"] <= 0:
                return self._send_json({"error": "faltan datos válidos"}, status=400)
            with _lock:
                cuentas = load_json(CUENTAS_PATH)
                cuentas.append(cuenta)
                save_json(CUENTAS_PATH, cuentas)
            git_sync(f"Agrega cuenta fija: {cuenta['nombre']}")
            return self._send_json(cuenta, status=201)

        if path == "/api/gastos":
            body = self._read_json_body()
            fecha = body.get("fecha", date.today().isoformat())
            monto = float(body.get("monto", 0))
            if monto <= 0 or not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
                return self._send_json({"error": "faltan datos válidos"}, status=400)
            gasto = add_gasto(fecha, body.get("categoria"), monto, body.get("descripcion"), origen="web")
            return self._send_json(gasto, status=201)

        if path == "/webhook/whatsapp":
            return self._handle_whatsapp_webhook()

        return self._not_found()

    def do_PUT(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/cuentas/([\w-]+)$", parsed.path)
        if m:
            cuenta_id = m.group(1)
            body = self._read_json_body()
            with _lock:
                cuentas = load_json(CUENTAS_PATH)
                found = None
                for c in cuentas:
                    if c["id"] == cuenta_id:
                        for campo in ("nombre", "monto", "dia_vencimiento", "categoria", "activa"):
                            if campo in body:
                                c[campo] = body[campo]
                        found = c
                        break
                if found is None:
                    return self._not_found()
                save_json(CUENTAS_PATH, cuentas)
            git_sync(f"Actualiza cuenta fija: {found['nombre']}")
            return self._send_json(found)
        return self._not_found()

    def do_DELETE(self):
        parsed = urlparse(self.path)

        m = re.match(r"^/api/cuentas/([\w-]+)$", parsed.path)
        if m:
            cuenta_id = m.group(1)
            with _lock:
                cuentas = load_json(CUENTAS_PATH)
                nuevas = [c for c in cuentas if c["id"] != cuenta_id]
                if len(nuevas) == len(cuentas):
                    return self._not_found()
                save_json(CUENTAS_PATH, nuevas)
            git_sync("Elimina cuenta fija")
            return self._send_json({"ok": True})

        m = re.match(r"^/api/gastos/([\w-]+)$", parsed.path)
        if m:
            gasto_id = m.group(1)
            with _lock:
                gastos = load_json(GASTOS_PATH)
                nuevos = [g for g in gastos if g["id"] != gasto_id]
                if len(nuevos) == len(gastos):
                    return self._not_found()
                save_json(GASTOS_PATH, nuevos)
            git_sync("Elimina gasto")
            return self._send_json({"ok": True})

        return self._not_found()

    # ---------- whatsapp ----------
    def _handle_whatsapp_webhook(self):
        config = load_config()
        if not config:
            return self._send_json({"error": "webhook no configurado (falta data/config.json)"}, status=503)

        form = self._read_form_body()
        signature = self.headers.get("X-Twilio-Signature", "")
        full_url = config.get("public_base_url", "").rstrip("/") + "/webhook/whatsapp"

        if not verify_twilio_signature(config.get("twilio_auth_token", ""), full_url, form, signature):
            return self._send_json({"error": "firma inválida"}, status=403)

        from_number = form.get("From", [""])[0]
        allowed = config.get("whatsapp_allowed_from", [])
        if from_number not in allowed:
            return self._send_twiml("No autorizado para cargar gastos en esta cuenta.", status=403)

        texto = form.get("Body", [""])[0]
        parsed = parse_gasto_mensaje(texto)
        if parsed is None:
            return self._send_twiml(
                "No entendí ese mensaje. Mandá: MONTO CATEGORIA DESCRIPCION (ej: 8500 alimentacion super)."
            )

        monto, categoria, descripcion = parsed
        add_gasto(date.today().isoformat(), categoria, monto, descripcion, origen="whatsapp")
        return self._send_twiml(f"Gasto cargado: {categoria} ${monto:.2f}" + (f" ({descripcion})" if descripcion else ""))

    # ---------- resumen ----------
    def _build_resumen(self, mes):
        with _lock:
            cuentas = load_json(CUENTAS_PATH)
            gastos = load_json(GASTOS_PATH)

        cuentas_activas = [c for c in cuentas if c.get("activa", True)]
        total_cuentas = round(sum(c["monto"] for c in cuentas_activas), 2)

        gastos_mes = [g for g in gastos if g["fecha"].startswith(mes)]
        total_gastado = round(sum(g["monto"] for g in gastos_mes), 2)

        por_categoria = {}
        for g in gastos_mes:
            por_categoria[g["categoria"]] = round(por_categoria.get(g["categoria"], 0) + g["monto"], 2)

        return {
            "mes": mes,
            "total_cuentas_fijas": total_cuentas,
            "cuentas_fijas": sorted(cuentas_activas, key=lambda c: c["dia_vencimiento"]),
            "total_gastado": total_gastado,
            "por_categoria": dict(sorted(por_categoria.items(), key=lambda kv: kv[1], reverse=True)),
        }


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Servidor de gastos corriendo en http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
