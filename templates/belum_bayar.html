{% extends "base.html" %}
{% block content %}
<div class="container-fluid px-3 pb-5">
    <div class="pt-4 mb-3">
        <h4 class="fw-bold mb-0">Tugas Lapangan</h4>
        <p class="text-muted small">Daftar pelanggan berdasarkan rute petugas</p>
    </div>

    <div class="card border-0 shadow-sm rounded-4 mb-4">
        <div class="card-body p-3">
            <label class="small fw-bold mb-2"><i class="fas fa-filter me-1"></i> Filter Petugas Lapangan:</label>
            <select id="filter-petugas" class="form-select border-0 bg-light py-2 shadow-none" onchange="loadData()">
                <option value="all">-- Semua Petugas --</option>
            </select>
            <div id="petugas-status" class="mt-2 small"></div>
        </div>
    </div>

    <div id="list-container" class="row g-2">
        <div class="col-12 text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="text-muted small mt-2">Memuat data...</p>
        </div>
    </div>
</div>

<div class="modal fade" id="modalKunjungan" tabindex="-1" data-bs-backdrop="static">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content border-0 rounded-4 shadow-lg">
            <form id="form-kunjungan">
                <div class="modal-header border-0 pb-0">
                    <h5 class="modal-title fw-bold text-primary">Input Hasil Kunjungan</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="p-3 bg-light rounded-4 mb-3 border-start border-primary border-4">
                        <div id="m-nama" class="fw-bold h6 mb-1"></div>
                        <div id="m-nomen" class="small text-muted"></div>
                        <div id="m-petugas-info" class="badge bg-primary-subtle text-primary mt-2"></div>
                        <input type="hidden" name="nomen" id="in-nomen">
                        <input type="hidden" name="nama_pelanggan" id="in-nama">
                        <input type="hidden" name="nominal_val" id="in-nominal">
                        <input type="hidden" name="petugas" id="in-petugas-name">
                    </div>

                    <div class="mb-3">
                        <label class="small fw-bold">Nomor HP Pelanggan *</label>
                        <input type="number" name="no_hp" class="form-control" placeholder="08..." required>
                    </div>

                    <div class="mb-3">
                        <label class="small fw-bold">Foto Lokasi (Kamera) *</label>
                        <input type="file" name="foto" class="form-control" accept="image/*" capture="camera" required>
                    </div>

                    <div class="mb-3">
                        <label class="small fw-bold">Status Kunjungan *</label>
                        <select name="keterangan" id="sel-status" class="form-select" required onchange="toggleJanji()">
                            <option value="">-- Pilih Status --</option>
                            <option value="Segera Bayar">Segera Bayar</option>
                            <option value="Janji Bayar">Janji Bayar</option>
                            <option value="Rumah Kosong">Rumah Kosong (RKS)</option>
                            <option value="Pasang Stiker">Pasang Stiker</option>
                        </select>
                    </div>

                    <div id="div-janji" class="mb-3 d-none">
                        <label class="small fw-bold text-danger">Tanggal Janji Bayar</label>
                        <input type="date" name="janji_bayar_dt" class="form-control">
                    </div>

                    <div class="mb-3">
                        <label class="small fw-bold">Catatan Lapangan</label>
                        <textarea name="catatan" class="form-control" rows="2" required></textarea>
                    </div>

                    <button type="submit" class="btn btn-primary w-100 rounded-3 py-3 fw-bold">
                        SIMPAN & KIRIM WA <i class="fab fa-whatsapp ms-1"></i>
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
    const modal = new bootstrap.Modal(document.getElementById('modalKunjungan'));

    async function loadPetugasDropdown() {
        try {
            const res = await fetch('/api/belum-bayar/petugas-tabs');
            const list = await res.json();
            const select = document.getElementById('filter-petugas');
            const statusDiv = document.getElementById('petugas-status');
            
            // Clear existing options (kecuali "Semua Petugas")
            select.innerHTML = '<option value="all">-- Semua Petugas --</option>';
            
            if (list && list.length > 0) {
                list.forEach(nama => {
                    const opt = document.createElement('option');
                    opt.value = nama; 
                    opt.innerText = nama;
                    select.appendChild(opt);
                });
                statusDiv.innerHTML = `<span class="badge bg-success-subtle text-success"><i class="fas fa-check-circle me-1"></i>${list.length} Petugas Aktif</span>`;
            } else {
                statusDiv.innerHTML = `
                    <div class="alert alert-warning rounded-3 p-2 mb-0">
                        <i class="fas fa-exclamation-triangle me-1"></i> 
                        <strong>Tidak ada data petugas!</strong><br>
                        <small>
                            • Pastikan file Rute sudah diupload<br>
                            • Periksa kolom PETUGAS tidak kosong/NaN<br>
                            • <a href="/upload" class="alert-link">Upload file Rute sekarang</a>
                        </small>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading petugas:', error);
            document.getElementById('petugas-status').innerHTML = `
                <div class="alert alert-danger rounded-3 p-2 mb-0">
                    <i class="fas fa-times-circle me-1"></i> Gagal memuat data petugas
                </div>
            `;
        }
    }

    async function loadData() {
        const p = document.getElementById('filter-petugas').value;
        const container = document.getElementById('list-container');
        
        // Loading state
        container.innerHTML = `
            <div class="col-12 text-center py-5">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="text-muted small mt-2">Memuat data pelanggan...</p>
            </div>
        `;
        
        try {
            const res = await fetch(`/api/belum-bayar/list?petugas=${p}`);
            const data = await res.json();
            
            if(data.length === 0) {
                container.innerHTML = `
                    <div class="col-12">
                        <div class="card border-0 shadow-sm rounded-4 p-4 text-center">
                            <i class="fas fa-clipboard-check text-success mb-3" style="font-size: 3rem; opacity: 0.3;"></i>
                            <h5 class="fw-bold text-muted">Tidak Ada Data</h5>
                            <p class="text-muted small mb-3">
                                ${p === 'all' ? 
                                    'Semua pelanggan sudah dikunjungi atau belum ada data MC.' : 
                                    `Semua pelanggan rute <strong>${p}</strong> sudah dikunjungi.`
                                }
                            </p>
                            <div class="d-flex gap-2 justify-content-center">
                                <a href="/upload" class="btn btn-primary btn-sm rounded-pill px-4">
                                    <i class="fas fa-upload me-1"></i> Upload Data MC
                                </a>
                                <button onclick="location.reload()" class="btn btn-outline-secondary btn-sm rounded-pill px-4">
                                    <i class="fas fa-sync me-1"></i> Refresh
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                return;
            }

            container.innerHTML = data.map(item => `
                <div class="col-12 col-md-6">
                    <div class="card border-0 shadow-sm rounded-4 mb-1" onclick="openReport('${item.nomen}', '${item.nama}', '${item.nominal}', '${item.nama_petugas}')">
                        <div class="card-body p-3">
                            <div class="d-flex justify-content-between align-items-start">
                                <div style="max-width: 70%;">
                                    <div class="fw-bold text-truncate">${item.nama}</div>
                                    <div class="small text-muted">${item.nomen} | ${item.pcez}</div>
                                    <div class="mt-2">
                                        <span class="badge ${item.nama_petugas === 'Belum Diatur' ? 'bg-warning-subtle text-warning' : 'bg-info-subtle text-info'} border border-info-subtle">
                                            <i class="fas fa-user-tag me-1"></i> ${item.nama_petugas}
                                        </span>
                                    </div>
                                </div>
                                <div class="text-end">
                                    <div class="text-danger fw-bold small">Rp ${item.nominal.toLocaleString()}</div>
                                    <div class="badge bg-light text-dark mt-1">Blok: ${item.block}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('Error loading data:', error);
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-danger rounded-4">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        <strong>Error!</strong> Gagal memuat data pelanggan.
                        <button onclick="loadData()" class="btn btn-sm btn-outline-danger float-end">
                            <i class="fas fa-redo me-1"></i> Coba Lagi
                        </button>
                    </div>
                </div>
            `;
        }
    }

    function openReport(nomen, nama, nominal, petugas) {
        document.getElementById('m-nama').innerText = nama;
        document.getElementById('m-nomen').innerText = nomen;
        document.getElementById('m-petugas-info').innerText = "Petugas Rute: " + petugas;
        document.getElementById('in-nomen').value = nomen;
        document.getElementById('in-nama').value = nama;
        document.getElementById('in-nominal').value = nominal;
        document.getElementById('in-petugas-name').value = petugas;
        modal.show();
    }

    function toggleJanji() {
        const s = document.getElementById('sel-status').value;
        document.getElementById('div-janji').classList.toggle('d-none', s !== 'Janji Bayar');
    }

    document.getElementById('form-kunjungan').onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        
        Swal.fire({ 
            title: 'Menyimpan Laporan...', 
            allowOutsideClick: false, 
            didOpen: () => Swal.showLoading() 
        });

        try {
            const res = await fetch('/api/belum-bayar/simpan-kunjungan', { method: 'POST', body: fd });
            const resData = await res.json();

            if(resData.status === 'success') {
                const fotoLink = `${window.location.origin}/uploads/kunjungan/${resData.filename}`;
                const waMsg = `*LAPORAN HASIL KUNJUNGAN*%0A` +
                              `---------------------------%0A` +
                              `👷 *Petugas:* ${fd.get('petugas')}%0A` +
                              `🏠 *Pelanggan:* ${document.getElementById('m-nama').innerText}%0A` +
                              `🆔 *Nomen:* ${fd.get('nomen')}%0A` +
                              `📝 *Hasil:* ${fd.get('keterangan')}%0A` +
                              `💬 *Catatan:* ${fd.get('catatan')}%0A%0A` +
                              `📸 *Link Foto:* ${fotoLink}%0A%0A` +
                              `© _Sunter Pro - Khoirul Anwar_`;
                
                Swal.fire('Berhasil!', 'Laporan telah disimpan.', 'success').then(() => {
                    window.open(`https://wa.me/?text=${waMsg}`, '_blank');
                    location.reload();
                });
            } else {
                throw new Error(resData.error || 'Gagal menyimpan');
            }
        } catch(err) {
            Swal.fire('Error', err.message, 'error');
        }
    };

    // Inisialisasi saat halaman load
    window.onload = () => {
        loadPetugasDropdown();
        loadData();
    };
</script>
{% endblock %}
