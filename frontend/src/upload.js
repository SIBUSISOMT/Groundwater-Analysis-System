// Data Source Upload Dashboard
const _DUMMY_SOURCES = [
    { source_id: 1, filename: 'Sabie_Baseflow_2018-2022.xlsx',      category: 'BASEFLOW', subcatchment_name: 'Sabie',         uploaded_by: 'system', upload_date: '2023-03-15', total_records: 1824, processing_status: 'Completed', error_message: null },
    { source_id: 2, filename: 'Crocodile_Recharge_2019-2023.xlsx',  category: 'RECHARGE', subcatchment_name: 'Crocodile',     uploaded_by: 'system', upload_date: '2023-05-22', total_records: 2160, processing_status: 'Completed', error_message: null },
    { source_id: 3, filename: 'LowerKomati_GWL_2020-2023.xlsx',     category: 'GWLEVEL',  subcatchment_name: 'Lower Komati',  uploaded_by: 'system', upload_date: '2023-07-10', total_records: 1460, processing_status: 'Completed', error_message: null },
    { source_id: 4, filename: 'Ngwempisi_Baseflow_2021-2023.xlsx',  category: 'BASEFLOW', subcatchment_name: 'Ngwempisi',     uploaded_by: 'system', upload_date: '2023-09-01', total_records: 730,  processing_status: 'Completed', error_message: null },
    { source_id: 5, filename: 'Sand_Recharge_2018-2022.xlsx',       category: 'RECHARGE', subcatchment_name: 'Sand',          uploaded_by: 'system', upload_date: '2023-10-18', total_records: 1825, processing_status: 'Completed', error_message: null },
    { source_id: 6, filename: 'UpperKomati_GWL_2022-2023.xlsx',     category: 'GWLEVEL',  subcatchment_name: 'Upper Komati',  uploaded_by: 'system', upload_date: '2023-12-04', total_records: 365,  processing_status: 'Completed', error_message: null },
    { source_id: 7, filename: 'Assegai_Baseflow_2020-2023.xlsx',    category: 'BASEFLOW', subcatchment_name: 'Assegai',       uploaded_by: 'system', upload_date: '2024-01-09', total_records: 1095, processing_status: 'Completed', error_message: null },
];

class UploadDashboard {
    constructor(basicMode = false) {
        const _backend = (window.location.port === '5000' || window.location.port === '') ? '' : 'http://localhost:5000';
        this.apiBase   = `${_backend}/api`;
        this.basicMode = basicMode;
        this._dsSources       = [];
        this._dsPage          = 1;
        this._dsPageSize      = 15;
        this._previewSourceId = null;
        this._previewChanges  = new Map();
        this._previewSelected = new Set();
        this._previewRecords  = [];
        this.init();
    }

    async init() {
        this.setupEventListeners();
        if (this.basicMode) {
            this._applyBasicPlanMode();
            return;
        }
        await this.loadDataSources();
        this.showToast('Upload dashboard ready', 'success');
    }

    // ── Basic plan mode ──────────────────────────────────────────────────────

    _applyBasicPlanMode() {
        const content = document.getElementById('uploadPageContent');
        if (!content) return;

        // Insert upgrade banner at the very top
        const banner = document.createElement('div');
        banner.id = 'basicPlanBanner';
        banner.innerHTML = `
            <div class="flex items-start gap-4 bg-amber-50 border-2 border-amber-400 rounded-xl p-5 mb-6 shadow-sm">
                <div class="w-10 h-10 bg-amber-400 rounded-xl flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-lock text-white text-lg"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                        <h3 class="text-base font-bold text-amber-900">Basic Plan — Sample Data Only</h3>
                        <span class="px-2 py-0.5 text-xs font-bold bg-amber-400 text-amber-900 rounded-full uppercase tracking-wide">Basic</span>
                    </div>
                    <p class="text-sm text-amber-800 leading-relaxed">
                        The data shown below is <strong>generic sample data</strong> for demonstration purposes only.
                        It does not reflect your organisation's real groundwater records. Uploading custom data sources
                        and viewing live results requires a <strong>Pro plan</strong>.
                    </p>
                    <div class="mt-3 flex items-center gap-3">
                        <a href="mailto:admin@hydrocore.co.za?subject=Upgrade to Pro"
                           class="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg transition-all">
                            <i class="fas fa-arrow-up"></i>Upgrade to Pro
                        </a>
                        <span class="text-xs text-amber-700">Contact your administrator to unlock full access.</span>
                    </div>
                </div>
            </div>`;
        content.insertBefore(banner, content.firstChild);

        // Disable upload form with a locked overlay
        const uploadForm = content.querySelector('.bg-white.rounded-xl.shadow-sm.border.p-6.mb-6');
        if (uploadForm) {
            uploadForm.style.position = 'relative';
            uploadForm.style.overflow = 'hidden';
            const lockOverlay = document.createElement('div');
            lockOverlay.innerHTML = `
                <div style="position:absolute;inset:0;background:rgba(255,255,255,0.82);backdrop-filter:blur(2px);
                            z-index:10;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
                            border-radius:0.75rem;">
                    <i class="fas fa-lock text-amber-400" style="font-size:2rem;"></i>
                    <p style="font-size:0.875rem;font-weight:600;color:#92400e;">Upload disabled on Basic plan</p>
                    <p style="font-size:0.75rem;color:#b45309;">Upgrade to Pro to upload your own data sources.</p>
                </div>`;
            uploadForm.appendChild(lockOverlay.firstElementChild);
            uploadForm.querySelectorAll('input, select, button').forEach(el => el.disabled = true);
        }

        // Load dummy data into the table
        this._dsSources = _DUMMY_SOURCES;
        this._renderDataSourcesPage();
    }

    // ── Event listeners ──────────────────────────────────────────────────────

    setupEventListeners() {
        const on = (id, ev, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener(ev, fn);
        };

        on('refreshBtn', 'click', () => {
            if (this.basicMode) {
                this.showToast('Live data refresh is a Pro plan feature.', 'warning');
                return;
            }
            this.loadDataSources();
        });

        const dropZone  = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');

        if (dropZone && fileInput) {
            dropZone.addEventListener('click', () => {
                if (this.basicMode) { this.showToast('File upload requires a Pro plan.', 'warning'); return; }
                fileInput.click();
            });
            fileInput.addEventListener('change', e => {
                if (e.target.files[0]) this.handleFileUpload(e.target.files[0]);
            });
            dropZone.addEventListener('dragover', e => {
                e.preventDefault();
                if (!this.basicMode) dropZone.classList.add('border-blue-400', 'bg-blue-50');
            });
            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('border-blue-400', 'bg-blue-50');
            });
            dropZone.addEventListener('drop', e => {
                e.preventDefault();
                dropZone.classList.remove('border-blue-400', 'bg-blue-50');
                if (this.basicMode) { this.showToast('File upload requires a Pro plan.', 'warning'); return; }
                if (e.dataTransfer.files[0]) this.handleFileUpload(e.dataTransfer.files[0]);
            });
        }
    }

    // ── File upload ──────────────────────────────────────────────────────────

    async handleFileUpload(file) {
        const category     = document.getElementById('categorySelect').value;
        const subcatchment = document.getElementById('subcatchmentSelect').value;

        if (!category || !subcatchment) {
            this.showToast('Please select both category and subcatchment', 'error');
            return;
        }
        if (!file.name.match(/\.(xlsx|xls)$/i)) {
            this.showToast('Please select an Excel file (.xlsx or .xls)', 'error');
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            this.showToast('File size must be less than 16 MB', 'error');
            return;
        }

        this.showLoading('Uploading and processing file…');
        try {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('category', category);
            fd.append('subcatchment', subcatchment);

            const res    = await fetch(`${this.apiBase}/upload`, { method: 'POST', body: fd });
            const result = await res.json();

            if (!res.ok) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('You do not have permission to upload files. Only admins and analysts can upload data.');
                }
                throw new Error(result.error || 'Upload failed. Please check the file format and try again.');
            }

            this.showToast(`Uploaded! ${result.processed_records || 0} records processed`, 'success');

            document.getElementById('fileInput').value            = '';
            document.getElementById('categorySelect').value       = '';
            document.getElementById('subcatchmentSelect').value   = '';

            const dz = document.getElementById('dropZone');
            if (dz) dz.querySelector('p').textContent = 'Click or drag Excel file here';

            await this.loadDataSources();
        } catch (err) {
            console.error('Upload failed:', err);
            this.showToast(`Upload failed: ${err.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }

    // ── Data sources ─────────────────────────────────────────────────────────

    async loadDataSources() {
        try {
            const res = await fetch(`${this.apiBase}/sources`);
            if (!res.ok) {
                let msg;
                if (res.status === 401 || res.status === 403) {
                    msg = 'You do not have permission to view data sources. Please log in again or contact your administrator.';
                } else if (res.status === 500) {
                    msg = 'The server encountered an error loading data sources. Please try again or contact your administrator.';
                } else {
                    msg = `Unexpected error (${res.status}). Please refresh the page.`;
                }
                throw new Error(msg);
            }
            const data = await res.json();
            this._dsSources = data.sources || [];
            this._dsPage    = 1;
            this._renderDataSourcesPage();
        } catch (err) {
            console.error('Failed to load data sources:', err);
            const el = document.getElementById('dataSourcesTable');
            if (el) el.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <i class="fas fa-exclamation-triangle text-4xl mb-4 block"></i>
                    <p class="font-semibold text-lg">Could not load data sources</p>
                    <p class="text-sm mt-2 text-gray-600 max-w-md mx-auto">${err.message}</p>
                    <button onclick="app.loadDataSources()" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Try Again
                    </button>
                </div>`;
        }
    }

    _renderDataSourcesPage() {
        const container  = document.getElementById('dataSourcesTable');
        if (!container) return;

        const sources    = this._dsSources;
        const pageSize   = this._dsPageSize;
        const total      = sources.length;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));

        if (this._dsPage < 1)          this._dsPage = 1;
        if (this._dsPage > totalPages) this._dsPage = totalPages;

        const start = (this._dsPage - 1) * pageSize;
        const slice = sources.slice(start, start + pageSize);

        // Generic data badge shown on each row in basic mode
        const genericBadge = this.basicMode
            ? `<span class="ml-2 px-1.5 py-0.5 text-xs bg-amber-100 text-amber-700 border border-amber-300 rounded font-semibold" title="Sample data — not your organisation's records">Generic</span>`
            : '';

        if (total === 0) {
            container.innerHTML = `
                <div class="text-center py-12 text-gray-500">
                    <i class="fas fa-database text-4xl mb-4"></i>
                    <p class="font-semibold">No data sources found</p>
                    <p class="text-sm mt-2">Upload an Excel file above to get started</p>
                </div>`;
            return;
        }

        const rows = slice.map(s => `
            <tr class="hover:bg-gray-50">
                <td class="px-4 py-3 font-medium">
                    ${s.filename || 'Unknown'}${genericBadge}
                </td>
                <td class="px-4 py-3">
                    <span class="px-2 py-1 text-xs rounded ${
                        s.category === 'BASEFLOW' ? 'bg-blue-100 text-blue-800' :
                        s.category === 'RECHARGE' ? 'bg-green-100 text-green-800' :
                        s.category === 'GWLEVEL'  ? 'bg-purple-100 text-purple-800' :
                        'bg-gray-100 text-gray-800'}">
                        ${s.category || 'N/A'}
                    </span>
                </td>
                <td class="px-4 py-3">${s.subcatchment_name || 'N/A'}</td>
                <td class="px-4 py-3 text-sm text-gray-600">${s.uploaded_by || '—'}</td>
                <td class="px-4 py-3">${s.upload_date ? new Date(s.upload_date).toLocaleDateString() : 'N/A'}</td>
                <td class="px-4 py-3 text-center">
                    <span class="font-semibold">${(s.total_records || 0).toLocaleString()}</span>
                </td>
                <td class="px-4 py-3">
                    <span class="px-2 py-1 text-xs rounded font-semibold ${
                        s.processing_status === 'Completed' ? 'bg-green-100 text-green-800' :
                        s.processing_status === 'Failed'    ? 'bg-red-100 text-red-800' :
                        s.processing_status === 'Pending'   ? 'bg-yellow-100 text-yellow-800' :
                        'bg-gray-100 text-gray-800'}">
                        ${s.processing_status || 'Unknown'}
                    </span>
                    ${s.error_message ? `<div class="text-xs text-red-600 mt-1" title="${s.error_message}"><i class="fas fa-exclamation-circle"></i> Error</div>` : ''}
                </td>
                <td class="px-4 py-3 text-center">
                    ${this.basicMode
                        ? `<span class="text-xs text-gray-400 italic">Pro only</span>`
                        : `<div class="flex items-center justify-center gap-2">
                            <button onclick="app.openPreviewModal(${s.source_id}, '${(s.filename||'').replace(/'/g,"\\'")}', '${s.category||''}', '${(s.subcatchment_name||'').replace(/'/g,"\\'")}' )"
                                    class="text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-3 py-1 rounded transition-all"
                                    title="Preview &amp; edit records">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button onclick="app.deleteSource(${s.source_id})"
                                    class="text-red-600 hover:text-red-800 hover:bg-red-50 px-3 py-1 rounded transition-all"
                                    title="Delete this data source">
                                <i class="fas fa-trash"></i>
                            </button>
                          </div>`
                    }
                </td>
            </tr>`).join('');

        const prevDisabled = this._dsPage <= 1;
        const nextDisabled = this._dsPage >= totalPages;
        const pageButtons  = Array.from({ length: totalPages }, (_, i) => {
            const p = i + 1, active = p === this._dsPage;
            return `<button onclick="app._dsPage=${p};app._renderDataSourcesPage()"
                            class="px-3 py-1 text-sm rounded border ${active
                                ? 'bg-blue-600 text-white border-blue-600 font-semibold'
                                : 'border-gray-300 text-gray-600 hover:bg-gray-50'}">
                        ${p}
                    </button>`;
        }).join('');

        container.innerHTML = `
            ${this.basicMode ? `
            <div class="flex items-center gap-2 px-4 py-2 mb-3 bg-amber-50 border border-amber-300 rounded-lg text-amber-800 text-sm">
                <i class="fas fa-info-circle text-amber-500 flex-shrink-0"></i>
                <span>This table shows <strong>generic sample data</strong> for illustration only. Upgrade to Pro to view your organisation's real data sources.</span>
            </div>` : ''}
            <table class="w-full text-sm">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-4 py-3 text-left font-semibold">File Name</th>
                        <th class="px-4 py-3 text-left font-semibold">Category</th>
                        <th class="px-4 py-3 text-left font-semibold">Subcatchment</th>
                        <th class="px-4 py-3 text-left font-semibold">Uploaded By</th>
                        <th class="px-4 py-3 text-left font-semibold">Upload Date</th>
                        <th class="px-4 py-3 text-center font-semibold">Records</th>
                        <th class="px-4 py-3 text-left font-semibold">Status</th>
                        <th class="px-4 py-3 text-center font-semibold">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">${rows}</tbody>
            </table>
            <div class="flex items-center justify-between px-4 py-3 border-t bg-gray-50 text-sm text-gray-600">
                <span>Showing ${start + 1}–${Math.min(start + pageSize, total)} of ${total} source(s)${this.basicMode ? ' (sample)' : ''}</span>
                <div class="flex items-center gap-1">
                    <button onclick="app._dsPage > 1 && (app._dsPage--, app._renderDataSourcesPage())"
                            ${prevDisabled ? 'disabled' : ''}
                            class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed">
                        <i class="fas fa-chevron-left"></i>
                    </button>
                    ${pageButtons}
                    <button onclick="app._dsPage < ${totalPages} && (app._dsPage++, app._renderDataSourcesPage())"
                            ${nextDisabled ? 'disabled' : ''}
                            class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed">
                        <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            </div>`;
    }

    // ── Delete source ────────────────────────────────────────────────────────

    async deleteSource(sourceId) {
        if (this.basicMode) { this.showToast('Deleting data sources requires a Pro plan.', 'warning'); return; }
        if (!confirm('Delete this data source? All associated raw and processed data will also be removed.')) return;

        this.showLoading('Deleting source…');
        try {
            const res  = await fetch(`${this.apiBase}/sources/${sourceId}`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' } });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || `HTTP ${res.status}`);
            this.showToast('Data source deleted successfully', 'success');
            await this.loadDataSources();
        } catch (err) {
            console.error('Delete error:', err);
            this.showToast(`Failed to delete: ${err.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }

    // ── Preview / Edit Modal ─────────────────────────────────────────────────

    async openPreviewModal(sourceId, fileName, category, catchment) {
        if (this.basicMode) { this.showToast('Record preview requires a Pro plan.', 'warning'); return; }
        ensurePreviewModalExists();

        this._previewSourceId = sourceId;
        this._previewChanges  = new Map();
        this._previewSelected = new Set();

        document.getElementById('previewTitle').textContent    = fileName || `Source #${sourceId}`;
        document.getElementById('previewSubtitle').textContent = `${catchment || '—'} · ${(category || '').toUpperCase()} · Source ID: ${sourceId}`;
        document.getElementById('previewRecordCount').textContent = '';
        document.getElementById('previewChangeBadge').classList.add('hidden');
        document.getElementById('previewSaveBtn').disabled = true;

        const modal = document.getElementById('previewModal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        try {
            const res    = await fetch(`${this.apiBase}/sources/${sourceId}/records`);
            const result = await res.json();
            if (!result.success) throw new Error(result.error || 'Failed to load records');

            this._previewRecords = result.records;
            this._renderPreviewTable(result.records);
            document.getElementById('previewRecordCount').textContent = `${result.records.length} record(s)`;
        } catch (err) {
            document.getElementById('previewTableWrap').innerHTML = `
                <div class="text-center py-12 text-red-500">
                    <i class="fas fa-exclamation-circle text-3xl mb-3"></i>
                    <p class="font-semibold">Failed to load records</p>
                    <p class="text-sm mt-1">${err.message}</p>
                </div>`;
        }
    }

    closePreviewModal() {
        const modal = document.getElementById('previewModal');
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        this._previewChanges  = new Map();
        this._previewRecords  = [];
        this._previewSourceId = null;
    }

    _classifyZ(z) {
        if (z >= 0.5)  return { cls: 'Surplus',          fail: 0, sev: 0 };
        if (z >= -0.5) return { cls: 'Normal',            fail: 0, sev: 0 };
        if (z >= -1.0) return { cls: 'Moderate_Deficit',  fail: 1, sev: 1 };
        if (z >= -1.5) return { cls: 'Severe_Deficit',    fail: 1, sev: 2 };
        return                 { cls: 'Extreme_Deficit',   fail: 1, sev: 3 };
    }

    _clsBadge(cls) {
        const map = {
            'Surplus':          'bg-blue-100 text-blue-800',
            'Normal':           'bg-green-100 text-green-800',
            'Moderate_Deficit': 'bg-yellow-100 text-yellow-800',
            'Severe_Deficit':   'bg-orange-100 text-orange-800',
            'Extreme_Deficit':  'bg-red-100 text-red-800',
        };
        return `<span class="px-2 py-0.5 text-xs rounded font-semibold ${map[cls] || 'bg-gray-100 text-gray-700'}">${(cls||'').replace(/_/g,' ')}</span>`;
    }

    _renderPreviewTable(records) {
        if (!records || records.length === 0) {
            document.getElementById('previewTableWrap').innerHTML =
                '<p class="text-center py-10 text-gray-400">No records found for this source.</p>';
            return;
        }

        const rows = records.map(rec => {
            const changed  = this._previewChanges.has(rec.processed_id);
            const selected = this._previewSelected.has(rec.processed_id);
            const rowData  = changed ? this._previewChanges.get(rec.processed_id) : {};
            const isFail   = rec.is_failure === 1;
            const rowClass = selected ? 'bg-blue-50 ring-1 ring-inset ring-blue-300'
                           : changed  ? 'bg-yellow-50'
                           : isFail   ? 'bg-red-50'
                           : 'hover:bg-gray-50';

            const dateVal = rowData.measurement_date ?? rec.measurement_date ?? '';
            const valVal  = rowData.original_value !== undefined ? rowData.original_value : (rec.original_value ?? '');

            let dispZ = rec.standardized_value, dispCls = rec.classification;
            let dispFail = rec.is_failure, dispSev = rec.severity_level;
            if (changed && rowData.original_value !== undefined && rec.mean_value !== null && rec.std_deviation) {
                const std = rec.std_deviation || 1;
                dispZ = (parseFloat(rowData.original_value) - rec.mean_value) / std;
                const c = this._classifyZ(dispZ);
                dispCls = c.cls; dispFail = c.fail; dispSev = c.sev;
            }

            return `
            <tr class="${rowClass} transition-colors" id="prev-row-${rec.processed_id}">
                <td class="px-3 py-2 text-center">
                    <input type="checkbox" data-pid="${rec.processed_id}" ${selected ? 'checked' : ''}
                           onchange="app._onSelectRow(${rec.processed_id}, this.checked)"
                           class="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer">
                </td>
                <td class="px-3 py-2 text-center text-xs text-gray-400">${rec.processed_id}</td>
                <td class="px-3 py-2">
                    <input type="date" value="${dateVal}" data-pid="${rec.processed_id}" data-field="measurement_date"
                           onchange="app._onPreviewCellChange(this)"
                           class="w-full border border-transparent rounded px-1 py-0.5 text-sm focus:border-blue-400 focus:outline-none bg-transparent hover:border-gray-300">
                </td>
                <td class="px-3 py-2 text-xs text-gray-500">${rec.parameter_type || ''}</td>
                <td class="px-3 py-2">
                    <input type="number" value="${valVal}" step="any"
                           data-pid="${rec.processed_id}" data-field="original_value"
                           data-mean="${rec.mean_value ?? 0}" data-std="${rec.std_deviation ?? 1}"
                           onchange="app._onPreviewCellChange(this)"
                           class="w-28 border border-transparent rounded px-1 py-0.5 text-sm focus:border-blue-400 focus:outline-none bg-transparent hover:border-gray-300 text-right">
                </td>
                <td class="px-3 py-2 text-right text-sm font-mono" id="prev-z-${rec.processed_id}">
                    ${dispZ !== null && dispZ !== undefined ? dispZ.toFixed(4) : '—'}
                </td>
                <td class="px-3 py-2" id="prev-cls-${rec.processed_id}">${this._clsBadge(dispCls)}</td>
                <td class="px-3 py-2 text-center" id="prev-fail-${rec.processed_id}">
                    ${dispFail ? '<span class="text-red-600 font-bold text-xs">YES</span>' : '<span class="text-green-600 text-xs">No</span>'}
                </td>
                <td class="px-3 py-2 text-center text-sm" id="prev-sev-${rec.processed_id}">${dispSev ?? 0}</td>
                ${changed ? `<td class="px-3 py-2 text-center">
                    <button onclick="app._revertPreviewRow(${rec.processed_id})"
                            class="text-xs text-gray-400 hover:text-red-500" title="Undo this row">
                        <i class="fas fa-undo"></i>
                    </button></td>`
                : '<td class="px-3 py-2"></td>'}
            </tr>`;
        }).join('');

        const allSelected = records.length > 0 && records.every(r => this._previewSelected.has(r.processed_id));
        document.getElementById('previewTableWrap').innerHTML = `
            <table class="w-full text-sm border-collapse">
                <thead class="bg-gray-100 sticky top-0 z-10">
                    <tr>
                        <th class="px-3 py-2 text-center w-10">
                            <input type="checkbox" id="previewSelectAll" ${allSelected ? 'checked' : ''}
                                   onchange="app._onSelectAll(this.checked)"
                                   class="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer" title="Select all">
                        </th>
                        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 w-16">ID</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600">Date</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600">Parameter</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-600">Original Value</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-600">Z-Score (SDI)</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600">Classification</th>
                        <th class="px-3 py-2 text-center text-xs font-semibold text-gray-600">Failure</th>
                        <th class="px-3 py-2 text-center text-xs font-semibold text-gray-600">Severity</th>
                        <th class="px-3 py-2 w-8"></th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>`;
    }

    _onPreviewCellChange(input) {
        const pid   = parseInt(input.dataset.pid, 10);
        const field = input.dataset.field;
        const val   = input.value;
        const entry = this._previewChanges.get(pid) || {};
        entry[field] = field === 'original_value' ? parseFloat(val) : val;
        this._previewChanges.set(pid, entry);

        if (field === 'original_value') {
            const mean = parseFloat(input.dataset.mean || 0);
            const std  = parseFloat(input.dataset.std  || 1) || 1;
            const z    = (parseFloat(val) - mean) / std;
            const { cls, fail, sev } = this._classifyZ(z);
            const zEl   = document.getElementById(`prev-z-${pid}`);
            const clsEl = document.getElementById(`prev-cls-${pid}`);
            const fEl   = document.getElementById(`prev-fail-${pid}`);
            const sEl   = document.getElementById(`prev-sev-${pid}`);
            if (zEl)   zEl.textContent = z.toFixed(4);
            if (clsEl) clsEl.innerHTML = this._clsBadge(cls);
            if (fEl)   fEl.innerHTML   = fail ? '<span class="text-red-600 font-bold text-xs">YES</span>' : '<span class="text-green-600 text-xs">No</span>';
            if (sEl)   sEl.textContent = sev;
        }

        const row = document.getElementById(`prev-row-${pid}`);
        if (row) row.className = 'bg-yellow-50 transition-colors';
        this._refreshPreviewUI();
    }

    _revertPreviewRow(pid) {
        this._previewChanges.delete(pid);
        this._renderPreviewTable(this._previewRecords);
        this._refreshPreviewUI();
    }

    _onSelectRow(pid, checked) {
        if (checked) this._previewSelected.add(pid);
        else         this._previewSelected.delete(pid);
        const row = document.getElementById(`prev-row-${pid}`);
        if (row) {
            const changed = this._previewChanges.has(pid);
            const rec     = this._previewRecords.find(r => r.processed_id === pid);
            const isFail  = rec && rec.is_failure === 1;
            row.className = (checked  ? 'bg-blue-50 ring-1 ring-inset ring-blue-300'
                           : changed  ? 'bg-yellow-50'
                           : isFail   ? 'bg-red-50'
                           : 'hover:bg-gray-50') + ' transition-colors';
        }
        const allChk = document.getElementById('previewSelectAll');
        if (allChk && this._previewRecords) {
            allChk.checked = this._previewRecords.length > 0 &&
                this._previewRecords.every(r => this._previewSelected.has(r.processed_id));
            allChk.indeterminate = !allChk.checked && this._previewSelected.size > 0;
        }
        this._refreshPreviewUI();
    }

    _onSelectAll(checked) {
        if (!this._previewRecords) return;
        if (checked) this._previewRecords.forEach(r => this._previewSelected.add(r.processed_id));
        else         this._previewSelected.clear();
        this._renderPreviewTable(this._previewRecords);
        this._refreshPreviewUI();
    }

    _refreshPreviewUI() {
        const nChanges  = this._previewChanges ? this._previewChanges.size : 0;
        const nSelected = this._previewSelected ? this._previewSelected.size : 0;
        const saveBtn  = document.getElementById('previewSaveBtn');
        const badge    = document.getElementById('previewChangeBadge');
        const count    = document.getElementById('previewChangeCount');
        const delBtn   = document.getElementById('previewDeleteBtn');
        const delCount = document.getElementById('previewDeleteCount');
        if (saveBtn) saveBtn.disabled = nChanges === 0;
        if (badge)   badge.classList.toggle('hidden', nChanges === 0);
        if (count)   count.textContent = nChanges;
        if (delBtn)  { delBtn.disabled = nSelected === 0; if (delCount) delCount.textContent = nSelected; }
    }

    async deleteSelectedRecords() {
        if (!this._previewSelected || this._previewSelected.size === 0) return;
        const ids = Array.from(this._previewSelected);
        if (!confirm(`Delete ${ids.length} selected record(s)? This cannot be undone.`)) return;

        const delBtn = document.getElementById('previewDeleteBtn');
        if (delBtn) { delBtn.disabled = true; delBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Deleting…'; }

        try {
            const res = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`, {
                method:  'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ processed_ids: ids })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error || 'Delete failed');
            this.showToast(`${result.deleted} record(s) deleted`, 'success');

            this._previewSelected.clear();
            const fresh = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`);
            const freshData = await fresh.json();
            if (freshData.success) {
                this._previewRecords = freshData.records;
                this._renderPreviewTable(freshData.records);
                document.getElementById('previewRecordCount').textContent = `${freshData.records.length} record(s)`;
            }
            this._refreshPreviewUI();
            await this.loadDataSources();
        } catch (err) {
            this.showToast(`Delete failed: ${err.message}`, 'error');
        } finally {
            if (delBtn) {
                delBtn.disabled = (this._previewSelected.size === 0);
                delBtn.innerHTML = '<i class="fas fa-trash mr-2"></i>Delete Selected (<span id="previewDeleteCount">0</span>)';
            }
        }
    }

    async savePreviewChanges() {
        if (!this._previewChanges || this._previewChanges.size === 0) return;
        const records = Array.from(this._previewChanges.entries()).map(([pid, changes]) => ({ processed_id: pid, ...changes }));
        const saveBtn = document.getElementById('previewSaveBtn');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving…'; }

        try {
            const res = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`, {
                method:  'PUT',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ records })
            });
            const result = await res.json();
            if (!result.success) throw new Error(result.error || 'Save failed');
            this.showToast(`${result.updated} record(s) saved`, 'success');

            this._previewChanges = new Map();
            const fresh = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`);
            const freshData = await fresh.json();
            if (freshData.success) {
                this._previewRecords = freshData.records;
                this._renderPreviewTable(freshData.records);
            }
            this._refreshPreviewUI();
            await this.loadDataSources();
        } catch (err) {
            this.showToast(`Save failed: ${err.message}`, 'error');
        } finally {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.innerHTML = '<i class="fas fa-save mr-2"></i>Save Changes'; }
        }
    }

    // ── Utilities ────────────────────────────────────────────────────────────

    showLoading(message = 'Loading…') {
        const overlay = document.getElementById('loadingOverlay');
        const text    = document.getElementById('loadingText');
        if (overlay && text) {
            text.textContent = message;
            overlay.classList.remove('hidden');
            overlay.classList.add('flex');
        }
    }

    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) { overlay.classList.add('hidden'); overlay.classList.remove('flex'); }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `px-6 py-4 rounded-lg shadow-lg text-white ${
            type === 'success' ? 'bg-green-600' :
            type === 'error'   ? 'bg-red-600'   :
            type === 'warning' ? 'bg-amber-500'  : 'bg-blue-600'}`;
        toast.innerHTML = `<div class="flex items-center">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'lock' : 'info-circle'} mr-3"></i>
            <span>${message}</span>
        </div>`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
}

// ── Preview modal (lazily injected once) ────────────────────────────────────
function ensurePreviewModalExists() {
    if (document.getElementById('previewModal')) return;
    const el = document.createElement('div');
    el.innerHTML = `
    <div id="previewModal"
         class="fixed inset-0 bg-black bg-opacity-60 z-50 hidden items-center justify-center p-4"
         onclick="if(event.target===this) app.closePreviewModal()">
        <div class="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col">
            <div class="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-blue-600 to-indigo-600 rounded-t-xl">
                <div class="text-white">
                    <h3 class="text-xl font-bold" id="previewTitle">Data Source Records</h3>
                    <p class="text-blue-100 text-sm mt-0.5" id="previewSubtitle"></p>
                </div>
                <div class="flex items-center gap-3">
                    <span id="previewChangeBadge" class="hidden px-3 py-1 bg-yellow-400 text-yellow-900 text-xs font-bold rounded-full">
                        <i class="fas fa-pencil-alt mr-1"></i>
                        <span id="previewChangeCount">0</span> unsaved change(s)
                    </span>
                    <button onclick="app.closePreviewModal()" class="text-white hover:bg-white hover:bg-opacity-20 rounded-lg p-2 transition-all">
                        <i class="fas fa-times text-lg"></i>
                    </button>
                </div>
            </div>
            <div class="flex items-center gap-4 px-6 py-2 bg-gray-50 border-b text-xs text-gray-600">
                <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-blue-100 border border-blue-400 inline-block"></span> Selected for deletion</span>
                <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-yellow-200 border border-yellow-400 inline-block"></span> Edited (unsaved)</span>
                <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-red-100 border border-red-300 inline-block"></span> Failure record</span>
                <span class="text-gray-400">| Click any <strong>Date</strong> or <strong>Value</strong> cell to edit</span>
            </div>
            <div class="flex-1 overflow-auto px-6 py-3" id="previewTableWrap">
                <div class="flex items-center justify-center py-16 text-gray-400">
                    <i class="fas fa-spinner fa-spin text-3xl mr-3"></i> Loading records…
                </div>
            </div>
            <div class="flex items-center justify-between px-6 py-4 border-t bg-gray-50 rounded-b-xl">
                <div class="flex items-center gap-3">
                    <span class="text-sm text-gray-500" id="previewRecordCount"></span>
                    <button id="previewDeleteBtn" onclick="app.deleteSelectedRecords()" disabled
                            class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold text-sm">
                        <i class="fas fa-trash mr-2"></i>Delete Selected (<span id="previewDeleteCount">0</span>)
                    </button>
                </div>
                <div class="flex items-center gap-3">
                    <button onclick="app.closePreviewModal()" class="px-5 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition-all">Cancel</button>
                    <button id="previewSaveBtn" onclick="app.savePreviewChanges()" disabled
                            class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold">
                        <i class="fas fa-save mr-2"></i>Save Changes
                    </button>
                </div>
            </div>
        </div>
    </div>`;
    document.body.appendChild(el.firstElementChild);
}

let app;
document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('hydroAuthReady', e => {
        const user     = e.detail && e.detail.user;
        const isBasic  = !user || (user.plan || 'basic') === 'basic';
        app = new UploadDashboard(isBasic);
    });
});
