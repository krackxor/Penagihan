"""
Authentication API - Sunter Dashboard Pro
Sinergi:
1. Handle Login 3 Level (Admin, Petugas, Publik).
2. CRUD User Management untuk Pusat Kendali Admin.
3. Session Management untuk mengunci rute petugas secara sinkron.
"""

from flask import Blueprint, request, session, jsonify, redirect, url_for, current_app
from core.database import get_db_connection
from core.helpers import APIResponse
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Proses login, inisialisasi session, dan update timestamp last_login."""
    data = request.get_json()
    if not data:
        return APIResponse.error("Data tidak valid", code=400)

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return APIResponse.error("Username dan password wajib diisi", code=400)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Case-insensitive check agar 'Pian' dan 'pian' dianggap sama
        user = cursor.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            # Pembersihan session lama
            session.clear()
            session.permanent = True  # Mengikuti PERMANENT_SESSION_LIFETIME di config
            
            # NORMALISASI ROLE: Paksa ke lowercase agar cocok dengan logika di menu.html
            user_role = user['role'].lower() if user['role'] else 'publik'
            
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user_role
            
            # SINERGI: petugas_id digunakan sebagai filter data global di API lain
            session['petugas_id'] = user['petugas_id'] if user['petugas_id'] else 'ALL'

            # Update Last Login untuk audit log
            conn.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                         (datetime.datetime.now(), user['id']))
            conn.commit()

            # Routing cerdas berdasarkan Level Akses (menggunakan role yang sudah dinormalisasi)
            redirect_to = "/"
            if user_role == 'petugas':
                redirect_to = "/belum-bayar"
            elif user_role == 'admin':
                redirect_to = "/admin/dashboard"

            return APIResponse.success(data={
                "username": user['username'],
                "role": user_role, # Mengirimkan role dalam format lowercase ke frontend
                "petugas_id": session['petugas_id'],
                "redirect": redirect_to
            }, message=f"Login berhasil. Selamat bertugas, {user['username']}")
        
        return APIResponse.error("Kredensial tidak valid", code=401)
    except Exception as e:
        return APIResponse.error(f"Terjadi kesalahan sistem: {str(e)}", code=500)
    finally:
        conn.close()

@auth_bp.route('/logout')
def logout():
    """Menghapus session dan mengirim sinyal status logout ke frontend."""
    session.clear()
    return redirect(url_for('login_page', logout='success'))

# --- USER MANAGEMENT (Hanya Admin) ---

@auth_bp.route('/users', methods=['GET'])
def list_users():
    """Mengambil daftar semua user untuk manajemen akun di Pusat Kendali."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses terbatas untuk Administrator", code=403)
        
    conn = get_db_connection()
    try:
        users = conn.execute('''
            SELECT id, username, role, petugas_id, no_hp, last_login, created_at 
            FROM users ORDER BY role ASC, username ASC
        ''').fetchall()
        return jsonify([dict(u) for u in users])
    finally:
        conn.close()

@auth_bp.route('/register', methods=['POST'])
def register():
    """Pendaftaran user baru melalui Admin Dashboard."""
    if session.get('role') != 'admin':
        return APIResponse.error("Hanya Admin yang diizinkan mendaftarkan user baru", code=403)
        
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'petugas').lower()
    petugas_id = data.get('petugas_id', '').strip().upper()
    no_hp = data.get('no_hp', '').strip()

    if not username or not password:
        return APIResponse.error("Username dan Password tidak boleh kosong")

    if len(password) < 6:
        return APIResponse.error("Password minimal 6 karakter")

    conn = get_db_connection()
    try:
        hashed_pw = generate_password_hash(password)
        conn.execute('''
            INSERT INTO users (username, password, role, petugas_id, no_hp) 
            VALUES (?, ?, ?, ?, ?)
        ''', (username, hashed_pw, role, petugas_id, no_hp))
        conn.commit()
        return APIResponse.success(message=f"Akun {username} ({role}) berhasil diaktifkan")
    except Exception as e:
        if 'UNIQUE constraint' in str(e):
            return APIResponse.error("Gagal: Username sudah digunakan", code=400)
        return APIResponse.error(f"Kesalahan database: {str(e)}")
    finally:
        conn.close()

@auth_bp.route('/delete-user/<username>', methods=['DELETE'])
def delete_user(username):
    """Menghapus akses user tertentu."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    # Proteksi Akun Master
    if username.lower() == 'admin_sunter':
        return APIResponse.error("Akun Master Admin tidak dapat dihapus demi keamanan sistem", code=400)

    conn = get_db_connection()
    try:
        result = conn.execute('DELETE FROM users WHERE username = ?', (username,))
        conn.commit()
        if result.rowcount > 0:
            return APIResponse.success(message=f"Akses user {username} telah dicabut")
        return APIResponse.error("User tidak ditemukan", code=404)
    finally:
        conn.close()

@auth_bp.route('/check-session', methods=['GET'])
def check_session():
    """Endpoint internal untuk memvalidasi status login di frontend."""
    if 'username' in session:
        return APIResponse.success(data={
            "is_logged_in": True,
            "username": session['username'],
            "role": session['role'],
            "petugas_id": session['petugas_id']
        })
    return APIResponse.error("Session expired", code=401)
