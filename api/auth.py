from flask import Blueprint, request, session, jsonify, redirect, url_for
from core.database import get_db_connection
from core.helpers import APIResponse
from werkzeug.security import check_password_hash
import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session.permanent = True
            
            # Paksa lowercase agar cocok dengan menu.html
            user_role = user['role'].lower() if user['role'] else 'publik'
            
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user_role
            session['petugas_id'] = user['petugas_id'] if user['petugas_id'] else 'ALL'

            conn.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.datetime.now(), user['id']))
            conn.commit()

            redirect_to = "/"
            if user_role == 'petugas': redirect_to = "/belum-bayar"
            elif user_role == 'admin': redirect_to = "/admin/dashboard"

            return APIResponse.success(data={"redirect": redirect_to, "role": user_role})
        
        return APIResponse.error("Kredensial tidak valid", code=401)
    finally:
        conn.close()

@auth_bp.route('/check-session')
def check_session():
    if 'role' in session:
        return jsonify({"is_logged_in": True, "role": session['role']})
    return jsonify({"is_logged_in": False}), 401
