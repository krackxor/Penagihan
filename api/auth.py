"""
Authentication API - Sunter Dashboard Pro
Sinergi:
1. Handle Login 3 Level (Admin, Petugas, Publik).
2. Session Management untuk mengunci rute petugas.
3. Integrasi dengan rute_petugas untuk mapping otomatis.
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
        # Ambil user dan data petugas terkait (untuk mapping rute)
        user = cursor.execute('''
            SELECT * FROM users WHERE username = ?
        ''', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            # SIMPAN KE SESSION
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['petugas_id'] = user['petugas_id'] # Nama petugas di rute_petugas

            return APIResponse.success(data={
                "role": user['role'],
                "redirect": "/" if user['role'] in ['admin', 'publik'] else "/belum-bayar"
            }, message="Login Berhasil")
        
        return APIResponse.error("Username atau password salah", code=401)
    finally:
        conn.close()

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Hapus session dan keluar."""
    session.clear()
    return redirect(url_for('login_page'))

@auth_bp.route('/create-admin-initial', methods=['GET'])
def create_initial_user():
    """Helper sementara untuk membuat user admin pertama kali (bisa dihapus nanti)."""
    conn = get_db_connection()
    try:
        # Contoh membuat 1 Admin dan 1 Petugas
        pw_admin = generate_password_hash('admin123')
        pw_petugas = generate_password_hash('petugas123')
        
        conn.execute('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)',
                    ('admin_sunter', pw_admin, 'admin'))
        
        conn.execute('INSERT OR IGNORE INTO users (username, password, role, petugas_id) VALUES (?, ?, ?, ?)',
                    ('ahmad', pw_petugas, 'petugas', 'AHMAD')) # AHMAD harus ada di rute_petugas
        
        conn.commit()
        return APIResponse.success(message="User awal berhasil dibuat")
    except Exception as e:
        return APIResponse.error(str(e))
    finally:
        conn.close()
