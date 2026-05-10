{% extends "base.html" %}

{% block title %}Analisa Detail SBRS - 1 Sinergi{% endblock %}

{% block extra_css %}
<style>
    .anomaly-badge { font-size: 0.75rem; padding: 6px 12px; border-radius: 6px; font-weight: bold; letter-spacing: 0.5px; }
    .status-badge { font-size: 0.7rem; text-transform: uppercase; font-weight: 600; }
    .table-hover tbody tr:hover { background-color: #f4f7f6; }
    .btn-audit { border-radius: 8px; font-size: 0.8rem; transition: 0.3s; font-weight: 600; }
    .btn-audit:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    .filter-card { background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 12px; }
    .indikasi-badge { font-size: 0.65rem; padding: 4px 8px; border-radius: 6px; letter-spacing: 0.5px; font-weight: 600; }
    
    /* Nomen Link */
    .nomen-link { cursor: pointer; text-decoration: underline dotted; transition: 0.2s; font-size: 1.1rem; }
    .nomen-link:hover { color: #0056b3 !important; background-color: #e7f1ff; border-radius: 4px; padding: 0 4px; }
    
    /* Tabel Tren 3 Bulan (Clean UI) */
    .trend-box { display: flex; align-items: center; justify-content: space-between; background: #f8f9fa; padding: 8px 12px; border-radius: 8px; border: 1px solid #dee2e6; }
    .trend-item { text-align: center; flex: 1; }
    .trend-label { font-size: 0.6rem; color: #6c757d; display: block; font-weight: 700; text-transform: uppercase; margin-bottom: 2px; }
    .trend-val { font-size: 0.95rem; font-weight: 800; color: #495057; }
    .trend-kini { background: #fff3cd; color: #856404; padding: 4px; border-radius: 6px; border: 1px solid #ffeeba; }
    .trend-arrow { font-size: 0.7rem; color: #ced4da; margin: 0 5px; }

    /* Master Table 3 Bulan di Modal */
    .master-table th { background-color: #212529 !important; color: white !important; font-size: 0.85rem; letter-spacing: 0.5px; vertical-align: middle; }
    .master-table td { font-size: 0.85rem; vertical-align: middle; }
    .col-header { font-weight: 700; color: #495057; background-color: #f8f9fa !important; width: 25%; font-size: 0.8rem; }
    
    /* Statis Info Card */
    .static-info-label { font-size: 0.7rem; color: #6c757d; text-transform: uppercase; font-weight: 700; margin-bottom: 0;}
    .static-info-val { font-size: 0.9rem; font-weight: 700; color: #212529; }
</style>
{% endblock %}

{% block content %}
<div class="row align-items-center mb-4">
    <div class="col-md-5">
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb mb-1">
                <li class="breadcrumb-item"><a href="/sbrs/summary?ab={{ current_ab }}&periode={{ periode_aktif }}&cycle={{ current_cycle }}" class="text-decoration-none">Summary SBRS</a></li>
                <li class="breadcrumb-item active fw-bold" aria-current="page">Detail Analisa</li>
            </ol>
        </nav>
        <h3 class="fw-bold mb-0 text-dark"><i class="fas fa-search-chart text-primary me-2"></i>Verifikasi SBRS Desktop</h3>
        <p class="text-muted small mb-0 mt-1">Periode: <span class="badge bg-primary-subtle text-primary">{{ label_kini|default(periode_aktif) }}</span> | Wilayah: <b>{{ current_ab }}</b></p>
    </div>
    
    <div class="col-md-7 d-flex justify-content-md-end align-items-center">
        <form method="GET" action="/sbrs/analisa" class="d-flex gap-2 align-items-end filter-card p-3 shadow-sm">
            <input type="hidden" name="ab" value="{{ current_ab }}">
            <input type="hidden" name="periode" value="{{ periode_aktif }}">
            
            <div style="min-width: 130px;">
                <label class="static-info-label mb-1">FILTER CYCLE</label>
                <select name="cycle" class="form-select form-select-sm fw-bold border-secondary" onchange="this.form.submit()">
                    <option value="all" {% if current_cycle == 'all' %}selected{% endif %}>Semua Cycle</option>
                    {% for c in cycles %}
                    <option value="{{ c }}" {% if current_cycle == c %}selected{% endif %}>Cycle {{ c }}</option>
                    {% endfor %}
                </select>
            </div>

            <div style="min-width: 150px;">
                <label class="static-info-label mb-1">FILTER KATEGORI</label>
                <select name="kategori" class="form-select form-select-sm fw-bold border-secondary text-danger" onchange="this.form.submit()">
                    <option value="all" class="text-dark" {% if not current_kat or current_kat == 'all' %}selected{% endif %}>Semua Anomali</option>
                    <option value="MINUS" {% if current_kat == 'MINUS' %}selected{% endif %}>Hanya MINUS</option>
                    <option value="ZERO" {% if current_kat == 'ZERO' %}selected{% endif %}>Hanya ZERO</option>
                    <option value="EKSTREM" {% if current_kat == 'EKSTREM' %}selected{% endif %}>Hanya EKSTREM</option>
                    <option value="TURUN" {% if current_kat == 'TURUN' %}selected{% endif %}>Hanya TURUN</option>
                </select>
            </div>
        </form>
    </div>
</div>

<div class="card border-0 shadow-sm mb-5" style="border-radius: 12px; overflow: hidden;">
    <div class="table-responsive" style="min-height: 500px;">
        <table class="table table-hover align-middle mb-0">
            <thead style="background: #212529; color: #fff; font-size: 0.8rem; letter-spacing: 0.5px;">
                <tr>
                    <th class="ps-4 py-3" style="width: 25%;">DATA PELANGGAN</th>
                    <th class="text-center py-3" style="width: 28%;">TREN KONSUMSI (3 BULAN)</th>
                    <th class="py-3" style="width: 17%;">INFO PETUGAS (KINI)</th>
                    <th class="py-3" style="width: 20%;">CATATAN DESKTOP</th>
                    <th class="text-center pe-4 py-3" style="width: 10%;">AKSI</th>
                </tr>
            </thead>
            <tbody>
                {% for item in data %}
                <tr>
                    <td class="ps-4 py-3">
                        <div class="fw-bold text-primary nomen-link mb-1" onclick='openCidDetail({{ item.modal_info|tojson }})' title="Buka Detail Master 3 Bulan">
                            {{ item.nomen }} <i class="fas fa-search-plus ms-1 text-muted" style="font-size: 0.7rem;"></i>
                        </div>
                        <div class="fw-bold text-dark text-uppercase small" style="line-height: 1.2;">{{ item.nama }}</div>
                        <div class="text-muted mt-1" style="font-size: 0.7rem;">
                            <i class="fas fa-map-marker-alt me-1 text-danger"></i>{{ item.kelurahan }} <span class="mx-1">|</span> PCEZ: <b>{{ item.pcez }}</b>
                        </div>
                        {% if item.modal_info.indikasi and item.modal_info.indikasi != 'Aman' %}
                            <div class="mt-2">
                                <span class="badge {% if 'FRAUD' in item.modal_info.indikasi %}bg-danger{% elif 'TEKNIS' in item.modal_info.indikasi %}bg-info text-dark{% else %}bg-warning text-dark{% endif %} indikasi-badge">
                                    <i class="fas fa-exclamation-circle me-1"></i>{{ item.modal_info.indikasi }}
                                </span>
                            </div>
                        {% endif %}
                    </td>
                    
                    <td class="text-center px-3">
                        <div class="trend-box mb-2 shadow-sm">
                            <div class="trend-item">
                                <span class="trend-label" title="Dua Bulan Lalu">{{ label_lalu_2|default('H-2') }}</span>
                                <span class="trend-val">{{ item.vol_lalu_2 }}</span>
                            </div>
                            <i class="fas fa-angle-right trend-arrow"></i>
                            <div class="trend-item">
                                <span class="trend-label" title="Bulan Lalu">{{ label_lalu_1|default('H-1') }}</span>
                                <span class="trend-val text-primary">{{ item.vol_lalu_1 }}</span>
                            </div>
                            <i class="fas fa-angle-right trend-arrow"></i>
                            <div class="trend-item trend-kini">
                                <span class="trend-label text-dark" title="Bulan Ini">{{ label_kini|default('KINI') }}</span>
                                <span class="trend-val {% if item.vol_kini < 0 %}text-danger{% endif %}">{{ item.vol_kini }}</span>
                            </div>
                        </div>
                        <div class="text-muted" style="font-size: 0.7rem; background: #fff; border: 1px dashed #dee2e6; padding: 4px; border-radius: 6px;">
                            Stand: <b class="text-dark">{{ item.stand_awal }}</b> <i class="fas fa-long-arrow-alt-right mx-1"></i> <b class="text-primary">{{ item.stand_akhir }}</b>
                        </div>
                    </td>
                    
                    <td>
                        <div class="d-flex align-items-center mb-1">
                            <span class="badge bg-light text-dark border me-2" style="width: 50px;">MRID</span>
                            <span class="fw-bold text-primary small">{{ item.cmr_mrid }}</span>
                        </div>
                        <div class="d-flex align-items-center mb-1">
                            <span class="badge bg-light text-dark border me-2" style="width: 50px;">TRBL</span>
                            <span class="fw-bold text-danger small">{{ item.cmr_trbl1_code }}</span>
                        </div>
                        <div class="d-flex align-items-center">
                            <span class="badge bg-light text-dark border me-2" style="width: 50px;">MODE</span>
                            <span class="fw-bold text-secondary small">{{ item.read_method }}</span>
                        </div>
                    </td>
                    
                    <td>
                        <div class="mb-2">
                            {% if item.kategori_anomali == 'ZERO' %}<span class="anomaly-badge bg-danger text-white border border-danger">KASUS: ZERO</span>
                            {% elif item.kategori_anomali == 'EKSTREM' %}<span class="anomaly-badge bg-warning text-dark border border-warning">KASUS: EKSTREM</span>
                            {% elif item.kategori_anomali == 'MINUS' %}<span class="anomaly-badge bg-dark text-white border border-secondary">KASUS: MINUS</span>
                            {% else %}<span class="anomaly-badge bg-info text-white border border-info">KASUS: TURUN</span>{% endif %}
                        </div>
                        <div class="input-group input-group-sm">
                            <input type="text" class="form-control border-secondary" id="catatan_{{ item.nomen }}" value="{{ item.catatan }}" placeholder="Input analisa..." style="border-radius: 6px 0 0 6px;">
                            <button class="btn btn-secondary" onclick="simpanCatatan('{{ item.nomen }}', '{{ periode_aktif }}')" title="Simpan" style="border-radius: 0 6px 6px 0;"><i class="fas fa-save"></i></button>
                        </div>
                        <small id="alert_{{ item.nomen }}" class="text-success d-none fw-bold mt-1 d-block" style="font-size: 0.65rem;"><i class="fas fa-check-circle me-1"></i>Tersimpan</small>
                    </td>

                    <td class="text-center pe-4">
                        {% if item.status_audit == 1 %}
                            <span class="badge bg-success status-badge mb-2 w-100 py-2"><i class="fas fa-check-circle me-1"></i>Selesai</span>
                        {% else %}
                            <span class="badge bg-light text-muted status-badge border mb-2 w-100 py-2">Blm Audit</span>
                        {% endif %}
                        <a href="/lapor?nomen={{ item.nomen }}&sumber=SBRS&periode={{ periode_aktif }}" class="btn btn-sm btn-outline-primary btn-audit w-100">
                            <i class="fas fa-camera me-1"></i> Lapangan
                        </a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="5" class="text-center py-5">
                        <i class="fas fa-folder-open fa-3x text-muted opacity-25 mb-3"></i>
                        <h6 class="text-muted fw-bold">Data Tidak Ditemukan</h6>
                        <p class="text-muted small">Coba ubah filter Cycle atau Kategori.</p>
                        <a href="/sbrs/analisa?ab={{ current_ab }}&periode={{ periode_aktif }}" class="btn btn-sm btn-primary px-4 rounded-pill">Reset Filter</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<div class="modal fade" id="modalCid" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content border-0 shadow-lg" style="border-radius: 12px; background-color: #f4f7f6;">
            
            <div class="modal-header bg-dark text-white p-3 border-0" style="border-radius: 12px 12px 0 0;">
                <div>
                    <h5 class="modal-title fw-bold mb-0 text-uppercase">
                        <i class="fas fa-database text-warning me-2"></i>DATA MASTER 3 BULAN: <span id="m_nomen" class="text-info"></span>
                    </h5>
                </div>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            
            <div class="modal-body p-3">
                
                <div class="row g-3 mb-3">
                    <div class="col-md-7">
                        <div class="bg-white p-3 rounded shadow-sm h-100 border">
                            <div class="row align-items-center">
                                <div class="col-sm-2 text-center border-end">
                                    <i class="fas fa-map-marked-alt text-primary" style="font-size: 2.5rem; opacity: 0.5;"></i>
                                </div>
                                <div class="col-sm-10">
                                    <p class="static-info-label">Alamat Pelanggan</p>
                                    <p class="static-info-val mb-2" id="m_alamat" style="line-height: 1.2;"></p>
                                    <div class="d-flex gap-3 small">
                                        <div><i class="fab fa-whatsapp text-success me-1"></i> <span id="m_wa" class="fw-bold"></span></div>
                                        <div><i class="fas fa-phone text-primary me-1"></i> <span id="m_telp" class="fw-bold"></span></div>
                                        <div><i class="fas fa-envelope text-danger me-1"></i> <span id="m_email" class="fw-bold"></span></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-5">
                        <div class="bg-white p-3 rounded shadow-sm h-100 border">
                            <div class="row g-2">
                                <div class="col-6">
                                    <p class="static-info-label">Petugas (MRID)</p>
                                    <p class="static-info-val text-primary mb-1" id="m_mrid"></p>
                                </div>
                                <div class="col-6">
                                    <p class="static-info-label">Kode Rayon</p>
                                    <p class="static-info-val text-success mb-1" id="m_rayon"></p>
                                </div>
                                <div class="col-12 mt-2">
                                    <p class="static-info-label text-danger">Indikasi Sinergi</p>
                                    <div id="m_indikasi" class="fw-bold text-dark bg-danger-subtle px-2 py-1 rounded d-inline-block small"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded shadow-sm border overflow-hidden">
                    <table class="table table-bordered table-striped master-table mb-0">
                        <thead class="text-center">
                            <tr>
                                <th style="width: 25%; background: #343a40 !important;" class="text-start ps-3">PARAMETER SBRS</th>
                                <th style="width: 25%;">H-2 ({{ label_lalu_2|default('2 Bln Lalu') }})</th>
                                <th style="width: 25%;">H-1 ({{ label_lalu_1|default('1 Bln Lalu') }})</th>
                                <th style="width: 25%; background: #0056b3 !important;">KINI ({{ label_kini|default('Bulan Ini') }})</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td class="col-header ps-3 text-primary"><i class="fas fa-cog me-1"></i> INFO TEKNIS BACA</td>
                                <td colspan="3" class="bg-light"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">TARIF (GOLONGAN)</td>
                                <td class="text-center" id="t_tarif_h2"></td>
                                <td class="text-center" id="t_tarif_h1"></td>
                                <td class="text-center fw-bold text-dark bg-primary-subtle" id="t_tarif_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">NO SERI METER</td>
                                <td class="text-center" id="t_mtrnum_h2"></td>
                                <td class="text-center" id="t_mtrnum_h1"></td>
                                <td class="text-center fw-bold text-dark bg-primary-subtle" id="t_mtrnum_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CYCLE TAGIHAN</td>
                                <td class="text-center" id="t_cycle_h2"></td>
                                <td class="text-center" id="t_cycle_h1"></td>
                                <td class="text-center fw-bold text-dark bg-primary-subtle" id="t_cycle_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">READ METHOD</td>
                                <td class="text-center" id="t_method_h2"></td>
                                <td class="text-center" id="t_method_h1"></td>
                                <td class="text-center fw-bold text-primary bg-primary-subtle" id="t_method_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CMR TRBL1 CODE</td>
                                <td class="text-center text-danger fw-bold" id="t_trbl_h2"></td>
                                <td class="text-center text-danger fw-bold" id="t_trbl_h1"></td>
                                <td class="text-center fw-bold text-danger bg-primary-subtle" id="t_trbl_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CMR CHG SPCL MSG</td>
                                <td class="text-center text-warning" id="t_spcl_h2"></td>
                                <td class="text-center text-warning" id="t_spcl_h1"></td>
                                <td class="text-center fw-bold text-warning bg-primary-subtle" id="t_spcl_kini"></td>
                            </tr>
                            
                            <tr>
                                <td class="col-header ps-3 text-success"><i class="fas fa-tachometer-alt me-1"></i> STAND METER & DURASI</td>
                                <td colspan="3" class="bg-light"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CMR LOC CODE</td>
                                <td class="text-center" id="t_loc_h2"></td>
                                <td class="text-center" id="t_loc_h1"></td>
                                <td class="text-center fw-bold bg-primary-subtle" id="t_loc_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">HARI BACA (Durasi)</td>
                                <td class="text-center" id="t_hb_h2"></td>
                                <td class="text-center" id="t_hb_h1"></td>
                                <td class="text-center fw-bold bg-primary-subtle" id="t_hb_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">PREV READ 1 (Awal Lapangan)</td>
                                <td class="text-center" id="t_pr1_h2"></td>
                                <td class="text-center" id="t_pr1_h1"></td>
                                <td class="text-center fw-bold bg-primary-subtle" id="t_pr1_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CURR READ 1 (Akhir Lapangan)</td>
                                <td class="text-center" id="t_cr1_h2"></td>
                                <td class="text-center" id="t_cr1_h1"></td>
                                <td class="text-center fw-bold text-success bg-primary-subtle" id="t_cr1_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CMR PREV READ (Awal Pusat)</td>
                                <td class="text-center text-muted" id="t_cpr_h2"></td>
                                <td class="text-center text-muted" id="t_cpr_h1"></td>
                                <td class="text-center fw-bold text-muted bg-primary-subtle" id="t_cpr_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">CMR READING (Akhir Pusat)</td>
                                <td class="text-center text-muted" id="t_cr_h2"></td>
                                <td class="text-center text-muted" id="t_cr_h1"></td>
                                <td class="text-center fw-bold text-muted bg-primary-subtle" id="t_cr_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">SB STAND (Stand Tagihan)</td>
                                <td class="text-center" id="t_sb_h2"></td>
                                <td class="text-center" id="t_sb_h1"></td>
                                <td class="text-center fw-bold text-primary bg-primary-subtle fs-6" id="t_sb_kini"></td>
                            </tr>
                            
                            <tr>
                                <td class="col-header ps-3 text-danger"><i class="fas fa-file-invoice-dollar me-1"></i> KALKULASI VOLUME & KEUANGAN</td>
                                <td colspan="3" class="bg-light"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4 text-dark">VOL LAPANGAN (m3)</td>
                                <td class="text-center fw-bold" id="v_lap_h2"></td>
                                <td class="text-center fw-bold" id="v_lap_h1"></td>
                                <td class="text-center fw-bold text-dark bg-warning-subtle fs-6" id="v_lap_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4 text-dark">VOL SISTEM PUSAT (m3)</td>
                                <td class="text-center fw-bold" id="v_pus_h2"></td>
                                <td class="text-center fw-bold" id="v_pus_h1"></td>
                                <td class="text-center fw-bold text-dark bg-warning-subtle fs-6" id="v_pus_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4 text-success">VOL CETAK TAGIHAN (m3)</td>
                                <td class="text-center fw-bold text-success" id="v_cet_h2"></td>
                                <td class="text-center fw-bold text-success" id="v_cet_h1"></td>
                                <td class="text-center fw-bold text-success bg-warning-subtle fs-5" id="v_cet_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4 text-secondary">VOL PERIODE LALU (SBRS)</td>
                                <td class="text-center fw-bold text-secondary" id="v_lalu_h2"></td>
                                <td class="text-center fw-bold text-secondary" id="v_lalu_h1"></td>
                                <td class="text-center fw-bold text-secondary bg-warning-subtle fs-6" id="v_lalu_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">BILL AMOUNT (Total Tagih)</td>
                                <td class="text-end pe-4 text-danger" id="t_bill_h2"></td>
                                <td class="text-end pe-4 text-danger" id="t_bill_h1"></td>
                                <td class="text-end pe-4 fw-bold text-danger bg-primary-subtle" id="t_bill_kini"></td>
                            </tr>
                            <tr>
                                <td class="col-header ps-4">PAYMENT AMOUNT (Bayar)</td>
                                <td class="text-end pe-4 text-success" id="t_pay_h2"></td>
                                <td class="text-end pe-4 text-success" id="t_pay_h1"></td>
                                <td class="text-end pe-4 fw-bold text-success bg-primary-subtle" id="t_pay_kini"></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="modal-footer bg-dark border-0 p-2">
                <button type="button" class="btn btn-outline-light fw-bold px-5" data-bs-dismiss="modal">TUTUP DATA MASTER</button>
            </div>
        </div>
    </div>
</div>

<script>
// Auto format Rupiah
function formatRupiah(angka) {
    let number = parseFloat(angka);
    if(isNaN(number)) return "Rp 0";
    return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(number);
}

// INJEKSI DATA KE TABEL RAKSASA
function openCidDetail(info) {
    const kini = info.kini || {};
    const lalu1 = info.lalu_1 || {};
    const lalu2 = info.lalu_2 || {};
    
    // --- STATIC INFO ---
    document.getElementById('m_nomen').innerText = info.nomen || '-';
    document.getElementById('m_alamat').innerText = info.alamat !== '-' ? info.alamat : 'Tidak Ada Data Alamat';
    document.getElementById('m_wa').innerText = info.wa !== '-' ? info.wa : '-';
    document.getElementById('m_telp').innerText = info.telp !== '-' ? info.telp : '-';
    document.getElementById('m_email').innerText = info.email !== '-' ? info.email : '-';
    
    document.getElementById('m_mrid').innerText = info.cmr_mrid;
    document.getElementById('m_rayon').innerText = info.rayon;
    document.getElementById('m_indikasi').innerText = info.indikasi;

    // --- TABEL 3 BULAN: BARIS DEMI BARIS ---
    // BLOK 1: TEKNIS
    document.getElementById('t_tarif_kini').innerText = kini.tariff || '-';
    document.getElementById('t_tarif_h1').innerText = lalu1.tariff || '-';
    document.getElementById('t_tarif_h2').innerText = lalu2.tariff || '-';

    document.getElementById('t_mtrnum_kini').innerText = kini.cmr_mtr_num || '-';
    document.getElementById('t_mtrnum_h1').innerText = lalu1.cmr_mtr_num || '-';
    document.getElementById('t_mtrnum_h2').innerText = lalu2.cmr_mtr_num || '-';

    document.getElementById('t_cycle_kini').innerText = kini.cmr_cycle || '-';
    document.getElementById('t_cycle_h1').innerText = lalu1.cmr_cycle || '-';
    document.getElementById('t_cycle_h2').innerText = lalu2.cmr_cycle || '-';

    document.getElementById('t_method_kini').innerText = kini.read_method || '-';
    document.getElementById('t_method_h1').innerText = lalu1.read_method || '-';
    document.getElementById('t_method_h2').innerText = lalu2.read_method || '-';

    document.getElementById('t_trbl_kini').innerText = kini.cmr_trbl1_code || '-';
    document.getElementById('t_trbl_h1').innerText = lalu1.cmr_trbl1_code || '-';
    document.getElementById('t_trbl_h2').innerText = lalu2.cmr_trbl1_code || '-';

    document.getElementById('t_spcl_kini').innerText = kini.cmr_chg_spcl_msg || '-';
    document.getElementById('t_spcl_h1').innerText = lalu1.cmr_chg_spcl_msg || '-';
    document.getElementById('t_spcl_h2').innerText = lalu2.cmr_chg_spcl_msg || '-';

    // BLOK 2: STAND METER
    document.getElementById('t_loc_kini').innerText = kini.cmr_loc_code || '-';
    document.getElementById('t_loc_h1').innerText = lalu1.cmr_loc_code || '-';
    document.getElementById('t_loc_h2').innerText = lalu2.cmr_loc_code || '-';

    document.getElementById('t_hb_kini').innerText = kini.hari_baca || '-';
    document.getElementById('t_hb_h1').innerText = lalu1.hari_baca || '-';
    document.getElementById('t_hb_h2').innerText = lalu2.hari_baca || '-';

    document.getElementById('t_pr1_kini').innerText = kini.prev_read_1 ?? '-';
    document.getElementById('t_pr1_h1').innerText = lalu1.prev_read_1 ?? '-';
    document.getElementById('t_pr1_h2').innerText = lalu2.prev_read_1 ?? '-';

    document.getElementById('t_cr1_kini').innerText = kini.curr_read_1 ?? '-';
    document.getElementById('t_cr1_h1').innerText = lalu1.curr_read_1 ?? '-';
    document.getElementById('t_cr1_h2').innerText = lalu2.curr_read_1 ?? '-';

    document.getElementById('t_cpr_kini').innerText = kini.cmr_prev_read ?? '-';
    document.getElementById('t_cpr_h1').innerText = lalu1.cmr_prev_read ?? '-';
    document.getElementById('t_cpr_h2').innerText = lalu2.cmr_prev_read ?? '-';

    document.getElementById('t_cr_kini').innerText = kini.cmr_reading ?? '-';
    document.getElementById('t_cr_h1').innerText = lalu1.cmr_reading ?? '-';
    document.getElementById('t_cr_h2').innerText = lalu2.cmr_reading ?? '-';

    document.getElementById('t_sb_kini').innerText = kini.sb_stand ?? '-';
    document.getElementById('t_sb_h1').innerText = lalu1.sb_stand ?? '-';
    document.getElementById('t_sb_h2').innerText = lalu2.sb_stand ?? '-';

    // BLOK 3: VOLUME & KEUANGAN
    document.getElementById('v_lap_kini').innerText = kini.vol_lapangan ?? '-';
    document.getElementById('v_lap_h1').innerText = lalu1.vol_lapangan ?? '-';
    document.getElementById('v_lap_h2').innerText = lalu2.vol_lapangan ?? '-';

    document.getElementById('v_pus_kini').innerText = kini.vol_pusat ?? '-';
    document.getElementById('v_pus_h1').innerText = lalu1.vol_pusat ?? '-';
    document.getElementById('v_pus_h2').innerText = lalu2.vol_pusat ?? '-';

    document.getElementById('v_cet_kini').innerText = kini.vol_cetak ?? '-';
    document.getElementById('v_cet_h1').innerText = lalu1.vol_cetak ?? '-';
    document.getElementById('v_cet_h2').innerText = lalu2.vol_cetak ?? '-';

    document.getElementById('v_lalu_kini').innerText = info.vol_periode_lalu ?? '-';
    document.getElementById('v_lalu_h1').innerText = info.vol_periode_lalu_2 ?? '-';
    document.getElementById('v_lalu_h2').innerText = '-'; // Memori DB mentok di 2 bulan

    document.getElementById('t_bill_kini').innerText = formatRupiah(kini.bill_amount);
    document.getElementById('t_bill_h1').innerText = formatRupiah(lalu1.bill_amount);
    document.getElementById('t_bill_h2').innerText = formatRupiah(lalu2.bill_amount);

    document.getElementById('t_pay_kini').innerText = formatRupiah(kini.payment_amount);
    document.getElementById('t_pay_h1').innerText = formatRupiah(lalu1.payment_amount);
    document.getElementById('t_pay_h2').innerText = formatRupiah(lalu2.payment_amount);

    var myModal = new bootstrap.Modal(document.getElementById('modalCid'));
    myModal.show();
}

// Fungsi Simpan Catatan Desktop Tanpa Reload
function simpanCatatan(nomen, periode) {
    const catatan = document.getElementById('catatan_' + nomen).value;
    const alertMsg = document.getElementById('alert_' + nomen);
    
    fetch('/sbrs/save-catatan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nomen: nomen, periode: periode, catatan: catatan })
    })
    .then(response => response.json())
    .then(data => {
        if(data.status === 'success') {
            alertMsg.classList.remove('d-none');
            setTimeout(() => { alertMsg.classList.add('d-none'); }, 3000);
        } else {
            alert("Gagal menyimpan: " + data.message);
        }
    })
    .catch(error => console.error('Error:', error));
}
</script>
{% endblock %}
