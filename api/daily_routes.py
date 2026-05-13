from flask import Blueprint, render_template, request
from services.daily_service import DailyService
from datetime import datetime

daily_bp = Blueprint('daily', __name__)

@daily_bp.route('/')
def index():
    # Ambil periode dari filter atau bulan saat ini
    periode = request.args.get('periode', datetime.now().strftime('%Y-%m')).replace('-', '')
    
    # Panggil logika bisnis dari Service Layer [cite: 2718]
    report_data = DailyService.generate_collection_report(periode)
    
    return render_template('daily.html', 
                           data=report_data.get('details', []), 
                           mon_name=periode,
                           periode=request.args.get('periode', datetime.now().strftime('%Y-%m')))
