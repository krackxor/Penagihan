"""
Authentication API - Sunter Dashboard Pro
Sinergi:
1. Handle Login 3 Level (Admin, Petugas, Publik).
2. CRUD User Management untuk Pusat Kendali Admin.
3. Session Management untuk mengunci rute petugas secara sinkron.
"""

from flask import Blueprint, request, session, jsonify, redirect, url_for
from core.database import get_db_connection
from core.helpers import APIResponse
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Proses login dan inisialisasi session berdasarkan Role."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return APIResponse.error("Username dan password wajib diisi", code=400)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Case-insensitive check untuk username agar lebih user-friendly
        user = cursor.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role'].lower()
            # Mapping petugas_id (Contoh: PIAN, TEGUH, atau ALL)
            session['petugas_id'] = user['petugas_id'] if user['petugas_id'] else 'ALL'

            # Tentukan halaman tujuan berdasarkan role
            redirect_to = "/"
            if session['role'] == 'petugas':
                redirect_to = "/belum-bayar"

            return APIResponse.success(data={
                "role": user['role'],
                "redirect": redirect_to
            }, message=f"Selamat datang, {user['username']}")
        
        return APIResponse.error("Username atau password salah", code=401)
    finally:
        conn.close()

@auth_bp.route('/logout')
def logout():
    """Hapus session dan arahkan kembali ke login dengan parameter status."""
    session.clear()
    return redirect(url_for('login_page', logout='success'))

# --- USER MANAGEMENT API (Sinergi Admin Dashboard) ---

@auth_bp.route('/users', methods=['GET'])
def list_users():
    """Mengambil daftar semua user (Hanya untuk Admin)."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)
        
    conn = get_db_connection()
    try:
        users = conn.execute('SELECT id, username, role, petugas_id, created_at FROM users ORDER BY id DESC').fetchall()
        return jsonify([dict(u) for u in users])
    finally:
        conn.close()

@auth_bp.route('/register', methods=['POST'])
def register():
    """Mendaftarkan user baru dari Dashboard Admin."""
    if session.get('role') != 'admin':
        return APIResponse.error("Hanya Admin yang bisa menambah user", code=403)
        
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'petugas')
    petugas_id = data.get('petugas_id', '').upper()

    if not username or not password:
        return APIResponse.error("Username dan Password wajib diisi")

    conn = get_db_connection()
    try:
        hashed_pw = generate_password_hash(password)
        conn.execute('''
            INSERT INTO users (username, password, role, petugas_id) 
            VALUES (?, ?, ?, ?)
        ''', (username, hashed_pw, role, petugas_id))
        conn.commit()
        return APIResponse.success(message=f"User {username} berhasil didaftarkan")
    except Exception as e:
        if 'UNIQUE constraint' in str(e):
            return APIResponse.error("Username sudah terdaftar", code=400)
        return APIResponse.error(str(e))
    finally:
        conn.close()

@auth_bp.route('/delete-user/<username>', methods=['DELETE'])
def delete_user(username):
    """Menghapus user (Kecuali admin_sunter)."""
    if session.get('role') != 'admin':
        return APIResponse.error("Akses ditolak", code=403)

    if username == 'admin_sunter':
        return APIResponse.error("Admin utama tidak boleh dihapus", code=400)

    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM users WHERE username = ?', (username,))
        conn.commit()
        return APIResponse.success(message="User berhasil dihapus")
    finally:
        conn.close()

@auth_bp.route('/create-admin-initial', methods=['GET'])
def create_initial_user():
    """Helper Sinergi: Menjamin adanya akun Admin awal."""
    conn = get_db_connection()
    try:
        pw_admin = generate_password_hash('admin123')
        conn.execute('''
            INSERT OR IGNORE INTO users (username, password, role, petugas_id) 
            VALUES (?, ?, ?, ?)
        ''', ('admin_sunter', pw_admin, 'admin', 'ALL'))
        conn.commit()
        return APIResponse.success(message="Akun admin_sunter:admin123 siap digunakan")
    except Exception as e:
        return APIResponse.error(str(e))
    finally:
        conn.close()
