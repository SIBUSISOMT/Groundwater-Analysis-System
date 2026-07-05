/**
 * water_quality.js — HydroCore Water Quality Module
 * Handles all client-side logic for the /water_quality.html page.
 */

class WaterQualityApp {
    constructor() {
        const _backend      = window.HC_BACKEND_URL;
        this._apiBase       = _backend;
        this._currentTab    = 'overview';
        this._stations      = [];
        this._filteredSt    = [];
        this._indicators    = [];
        this._readingsPage  = 1;
        this._readingsTotal = 0;
        this._uploadFile    = null;
        this._chartEC       = null;
        this._chartTrend    = null;
        this._chartRadar    = null;
        this._radarReqSeq   = 0;  // guards against overlapping _buildRadarChart() calls racing on the same canvas
        this._trendReqSeq   = 0;  // same guard for loadTrend()/_buildTrendChart()
        this._matrixReqSeq  = 0;  // same guard for loadComplianceMatrix()
        this._readingsReqSeq = 0; // same guard for loadReadings() (rapid Prev/Next clicks)
        this._leafletMap    = null;
        this._markers       = [];
        this._tooltip       = document.getElementById('wq-tooltip');
    }

    // ── Bootstrap ─────────────────────────────────────────────────────────────

    async init() {
        await Promise.all([
            this.loadDashboard(),
            this.loadStations(),
            this.loadIndicators(),
        ]);
        this._initLeafletMap();
        this._populateAnalyticsSelects();
        this._populateAlertSelects();
        this.switchTab('overview');
    }

    _authHeaders() {
        return { 'Content-Type': 'application/json' };
    }

    async _fetch(url, opts = {}) {
        const fullUrl  = url.startsWith('http') ? url : `${this._apiBase}${url}`;
        const defaults = { headers: this._authHeaders() };
        if (opts.body && !(opts.body instanceof FormData)) {
            opts.headers = { ...defaults.headers, ...(opts.headers || {}) };
        } else {
            // multipart: let browser set Content-Type boundary
            const h = { ...defaults.headers };
            delete h['Content-Type'];
            opts.headers = { ...h, ...(opts.headers || {}) };
        }
        const res = await fetch(fullUrl, { ...defaults, ...opts });
        return res;
    }

    // ── Tab management ────────────────────────────────────────────────────────

    switchTab(tab) {
        ['overview', 'stations', 'analysis', 'upload', 'analytics', 'alerts', 'wsp', 'diagnostics'].forEach(t => {
            const el = document.getElementById(`tab-${t}`);
            if (el) el.style.display = t === tab ? '' : 'none';
            const btn = document.querySelector(`.wq-tab[data-tab="${t}"]`);
            if (btn) {
                btn.classList.toggle('active', t === tab);
                btn.style.color = t === tab ? '#22d3ee' : '#d1d5db';
            }
        });
        this._currentTab = tab;
        if (tab === 'analysis' && this._indicators.length) {
            this._populateAnalysisStations();
            this.loadAnalysis();
            this.loadTrend();
        }
        if (tab === 'stations') {
            this._renderStationTable(this._filteredSt);
        }
        if (tab === 'analytics') {
            this._populateAnalyticsSelects();
            this.loadAnalytics();
        }
        if (tab === 'alerts') {
            this._populateAlertSelects();
            this.loadAlertConfigs();
            this.loadAlertLog();
        }
        if (tab === 'wsp') {
            this._populateRiskStationSelect();
            this.loadRiskRegister();
            this.loadCorrectiveActions();
        }
        if (tab === 'diagnostics') {
            this._populateDiagnosticsStationSelect();
            this.loadDiagnosticsTab();
        }
    }

    // ── Dashboard ─────────────────────────────────────────────────────────────

    async loadDashboard() {
        try {
            const res = await this._fetch('/api/wq/dashboard');
            if (!res.ok) return;
            const data = await res.json();
            if (!data.success) return;

            const k = data.kpis;
            this._setText('kpi-stations',   k.total_stations ?? '—');
            this._setText('kpi-readings',    k.total_readings ?? '—');
            this._setText('kpi-meas',        k.total_measured ?? '—');
            if (k.latest_date) {
                this._setText('kpi-latest', `latest: ${k.latest_date}`);
            }
            if (k.compliance_rate !== null && k.compliance_rate !== undefined) {
                const el = document.getElementById('kpi-compliance-val');
                if (el) {
                    el.textContent = `${k.compliance_rate}%`;
                    el.style.color = k.compliance_rate >= 90 ? '#0d9488'
                                   : k.compliance_rate >= 70 ? '#d97706'
                                   : '#ef4444';
                }
                this._setText('kpi-meas-sub', `${k.compliant_count} of ${k.total_measured} compliant`);
            }

            this._renderAlerts(data.alerts || []);
            if ((data.ec_trend || []).length) {
                this._buildECChart(data.ec_trend);
            }
        } catch (e) {
            console.error('WQ dashboard load error', e);
        }
    }

    _renderAlerts(alerts) {
        const container = document.getElementById('alert-list');
        if (!container) return;
        if (!alerts.length) {
            container.innerHTML = '<p class="text-sm text-gray-400 text-center py-4"><i class="fas fa-check-circle text-teal-400 mr-2"></i>No compliance alerts in the last 30 days.</p>';
            return;
        }
        container.innerHTML = alerts.map(a => `
            <div class="flex items-center gap-4 py-3 border-b border-gray-50 last:border-0">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                     style="background:#fef2f2;">
                    <i class="fas fa-exclamation-triangle text-rose-500 text-sm"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="text-sm font-semibold text-gray-800 truncate">${this._esc(a.station)}</div>
                    <div class="text-xs text-gray-500">${this._esc(a.indicator)}${a.unit ? ` (${this._esc(a.unit)})` : ''} — ${this._esc(String(a.date))}</div>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="text-sm font-bold text-gray-800">${a.value !== null ? a.value : '—'}</span>
                    <span class="alert-badge ${a.flag === 'ABOVE' ? 'above' : 'below'}">
                        <i class="fas fa-arrow-${a.flag === 'ABOVE' ? 'up' : 'down'} text-xs"></i>
                        ${a.flag}
                    </span>
                </div>
            </div>
        `).join('');
    }

    _buildECChart(series) {
        const ctx = document.getElementById('chart-ec-trend');
        if (!ctx) return;
        if (this._chartEC) { this._chartEC.destroy(); this._chartEC = null; }

        const labels = series.map(p => p.date);
        const values = series.map(p => p.value);

        this._chartEC = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg EC (mS/m)',
                        data: values,
                        borderColor: '#0891b2',
                        backgroundColor: 'rgba(8,145,178,.12)',
                        borderWidth: 2.5,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#0891b2',
                        pointRadius: 4,
                        pointHoverRadius: 7,
                    },
                    {
                        label: 'Limit (70 mS/m)',
                        data: Array(labels.length).fill(70),
                        borderColor: '#f43f5e',
                        borderDash: [6, 4],
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'top', labels: { font: { size: 11 } } },
                    tooltip: { mode: 'index', intersect: false },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    // ── Leaflet Map ──────────────────────────────────────────────────────────

    _initLeafletMap() {
        const el = document.getElementById('wq-station-map');
        if (!el || this._leafletMap) return;
        this._leafletMap = L.map('wq-station-map', { zoomControl: true, scrollWheelZoom: false })
            .setView([-26.0, 31.0], 6);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors', maxZoom: 18,
        }).addTo(this._leafletMap);
        this._updateMapMarkers();
    }

    _updateMapMarkers() {
        if (!this._leafletMap) return;
        this._markers.forEach(m => m.remove());
        this._markers = [];
        const positioned = this._stations.filter(s => s.lat && s.lng);
        positioned.forEach(s => {
            const color = s.reading_count > 0 ? '#14b8a6' : '#9ca3af';
            const icon = L.divIcon({
                html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,.3);"></div>`,
                className: '', iconSize: [14, 14],
            });
            const m = L.marker([s.lat, s.lng], { icon })
                .addTo(this._leafletMap)
                .bindPopup(`<strong>${this._esc(s.name)}</strong><br><span style="font-size:.75rem;color:#64748b;">${this._esc(s.code)} · ${s.reading_count} reading(s)</span>`);
            this._markers.push(m);
        });
        if (positioned.length > 1) {
            const group = L.featureGroup(this._markers);
            this._leafletMap.fitBounds(group.getBounds().pad(0.3));
        }
    }

    // ── Stations ─────────────────────────────────────────────────────────────

    async loadStations() {
        try {
            const res = await this._fetch('/api/wq/stations');
            if (!res.ok) return;
            const data = await res.json();
            if (!data.success) return;
            this._stations    = data.stations || [];
            this._filteredSt  = [...this._stations];
            const label = document.getElementById('station-count-label');
            if (label) label.textContent = `${this._stations.length} station(s) registered`;
            if (this._currentTab === 'stations') this._renderStationTable(this._filteredSt);
            this._updateMapMarkers();
        } catch (e) {
            console.error('WQ loadStations error', e);
        }
    }

    filterStations(query) {
        const q = query.toLowerCase();
        this._filteredSt = q
            ? this._stations.filter(s =>
                s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q)
              )
            : [...this._stations];
        this._renderStationTable(this._filteredSt);
    }

    _renderStationTable(stations) {
        const tbody = document.getElementById('station-table-body');
        if (!tbody) return;
        if (!stations.length) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-10 text-gray-400 text-sm">
                <i class="fas fa-map-marker-alt mr-2"></i>No stations found. Add one to get started.</td></tr>`;
            return;
        }
        tbody.innerHTML = stations.map(s => `
            <tr class="hover:bg-gray-50 transition-colors" style="border-bottom:1px solid #f8fafc;">
                <td class="px-5 py-4">
                    <span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-bold"
                          style="background:#ecfeff;color:#0891b2;">${this._esc(s.code)}</span>
                </td>
                <td class="px-5 py-4">
                    <div class="text-sm font-semibold text-gray-800">${this._esc(s.name)}</div>
                    ${s.description ? `<div class="text-xs text-gray-400 truncate max-w-xs">${this._esc(s.description)}</div>` : ''}
                </td>
                <td class="px-5 py-4 text-xs text-gray-500">
                    ${s.lat !== null ? `${s.lat.toFixed(4)}, ${s.lng.toFixed(4)}` : '<span class="text-gray-300">—</span>'}
                </td>
                <td class="px-5 py-4 text-sm font-semibold text-gray-700">${s.reading_count}</td>
                <td class="px-5 py-4">
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold
                                 ${s.active ? 'text-teal-700' : 'text-gray-500'}"
                          style="${s.active ? 'background:#ccfbf1;' : 'background:#f1f5f9;'}">
                        <i class="fas fa-circle text-[8px]"></i>
                        ${s.active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td class="px-5 py-4 text-right">
                    <div class="flex justify-end gap-1">
                        <button title="Edit" onclick="WQ.openStationModal(${JSON.stringify(s)})"
                                class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-cyan-600 hover:bg-cyan-50 transition-all text-sm">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button title="Delete" onclick="WQ.deleteStation(${s.id}, '${this._esc(s.name)}')"
                                class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all text-sm">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    openStationModal(station = null) {
        document.getElementById('station-modal-title').textContent = station ? 'Edit Station' : 'Add Station';
        document.getElementById('station-edit-id').value = station ? station.id : '';
        document.getElementById('station-code').value     = station ? station.code : '';
        document.getElementById('station-name').value     = station ? station.name : '';
        document.getElementById('station-desc').value     = station ? (station.description || '') : '';
        document.getElementById('station-lat').value      = station && station.lat !== null ? station.lat : '';
        document.getElementById('station-lng').value      = station && station.lng !== null ? station.lng : '';
        document.getElementById('station-aquifer-type').value = station && station.aquifer_type ? station.aquifer_type : '';
        document.getElementById('station-depth').value     = station && station.depth_m !== null && station.depth_m !== undefined ? station.depth_m : '';
        const activeRow = document.getElementById('station-active-row');
        const activeCb  = document.getElementById('station-active');
        if (station) {
            activeRow.style.display = '';
            activeCb.checked = station.active;
            document.getElementById('station-code').disabled = true;
        } else {
            activeRow.style.display = 'none';
            document.getElementById('station-code').disabled = false;
        }
        document.getElementById('station-modal').style.display = 'flex';
    }

    closeStationModal() {
        document.getElementById('station-modal').style.display = 'none';
    }

    async saveStation(e) {
        e.preventDefault();
        const id       = document.getElementById('station-edit-id').value;
        const isEdit   = !!id;
        const depthRaw = document.getElementById('station-depth').value;
        const payload = {
            code:        document.getElementById('station-code').value.trim(),
            name:        document.getElementById('station-name').value.trim(),
            description: document.getElementById('station-desc').value.trim() || null,
            lat:         parseFloat(document.getElementById('station-lat').value) || null,
            lng:         parseFloat(document.getElementById('station-lng').value) || null,
            aquifer_type: document.getElementById('station-aquifer-type').value || null,
            // depthRaw !== '' guard (not `|| null`) so a legitimate depth of 0m (surface station) isn't silently dropped
            depth_m:     depthRaw !== '' && !isNaN(parseFloat(depthRaw)) ? parseFloat(depthRaw) : null,
            active:      isEdit ? document.getElementById('station-active').checked : true,
        };
        try {
            const res = await this._fetch(
                isEdit ? `/api/wq/stations/${id}` : '/api/wq/stations',
                { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(payload) }
            );
            const data = await res.json();
            if (data.success) {
                this.closeStationModal();
                await this.loadStations();
                this._populateAnalysisStations();
            } else {
                alert(data.error || 'Failed to save station.');
            }
        } catch (err) {
            alert('Network error: ' + err.message);
        }
    }

    async deleteStation(id, name) {
        if (!confirm(`Delete station "${name}"? This cannot be undone.`)) return;
        try {
            const res  = await this._fetch(`/api/wq/stations/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                await this.loadStations();
            } else {
                alert(data.error || 'Could not delete station.');
            }
        } catch (err) {
            alert('Network error: ' + err.message);
        }
    }

    // ── Indicators ────────────────────────────────────────────────────────────

    async loadIndicators() {
        try {
            const res = await this._fetch('/api/wq/indicators');
            if (!res.ok) return;
            const data = await res.json();
            if (data.success) {
                this._indicators = data.indicators || [];
                this._populateIndicatorSelect();
            }
        } catch (e) {
            console.error('WQ loadIndicators error', e);
        }
    }

    _populateIndicatorSelect() {
        const sel = document.getElementById('analysis-indicator');
        if (!sel || !this._indicators.length) return;
        sel.innerHTML = this._indicators.map(i =>
            `<option value="${this._esc(i.code)}">${this._esc(i.name)}</option>`
        ).join('');
    }

    _populateAnalysisStations() {
        const sel = document.getElementById('analysis-station');
        if (!sel) return;
        sel.innerHTML = '<option value="">All stations</option>' +
            this._stations.map(s =>
                `<option value="${s.id}">${this._esc(s.name)}</option>`
            ).join('');
    }

    // ── Analysis ─────────────────────────────────────────────────────────────

    async loadAnalysis() {
        this._readingsPage = 1;
        await Promise.all([this.loadComplianceMatrix(), this.loadReadings()]);
        this.loadTrend();
    }

    onStandardChange() {
        // The Standard toggle sits on the same filter bar as the radar snapshot, so both
        // must refresh together — previously only the matrix listened for this change.
        this.loadComplianceMatrix();
        this._buildRadarChart();
    }

    async loadComplianceMatrix() {
        const myReq    = ++this._matrixReqSeq;
        const station  = document.getElementById('analysis-station')?.value;
        const standard = document.getElementById('analysis-standard')?.value || 'sans241';
        const dateFrom = document.getElementById('analysis-from')?.value;
        const dateTo   = document.getElementById('analysis-to')?.value;
        const params   = new URLSearchParams({ limit: 10, standard });
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);

        try {
            const res  = await this._fetch(`/api/wq/compliance?${params}`);
            const data = await res.json();
            if (myReq !== this._matrixReqSeq) return;
            if (!data.success) return;
            this._renderMatrix(data.cols || [], data.rows || []);
        } catch (e) {
            console.error('WQ compliance matrix error', e);
        }
    }

    _renderMatrix(cols, rows) {
        const wrap = document.getElementById('compliance-matrix-wrap');
        if (!wrap) return;
        if (!cols.length || !rows.length) {
            wrap.innerHTML = '<p class="text-center text-gray-400 text-sm py-8">No readings to display. Upload data to see the compliance matrix.</p>';
            return;
        }

        const colHeaders = cols.map(c => `
            <th style="writing-mode:vertical-rl;transform:rotate(180deg);min-width:40px;font-size:.65rem;font-weight:600;color:#64748b;padding:.3rem .2rem;white-space:nowrap;">
                ${this._esc(String(c.date).slice(0, 10))}<br>
                <span style="color:#94a3b8;font-weight:400;">${this._esc(c.station)}</span>
            </th>
        `).join('');

        const bodyRows = rows.map(r => {
            const cells = r.cells.map((cell, ci) => {
                if (!cell) {
                    return `<td class="px-0.5 py-0.5"><div class="matrix-cell no-data" title="No data"></div></td>`;
                }
                const cls = cell.not_assessed ? 'not-assessed'
                          : cell.compliant === null ? 'no-standard'
                          : cell.compliant ? 'compliant'
                          : 'violation';
                const tip = cell.not_assessed
                    ? `${r.indicator.name}: not assessed under this standard (requires site-specific baseline data)`
                    : `${r.indicator.name}: ${cell.value !== null ? cell.value : '—'}${r.indicator.unit ? ' ' + r.indicator.unit : ''}${cell.flag ? ' [' + cell.flag + ']' : ''}`;
                return `<td class="px-0.5 py-0.5">
                    <div class="matrix-cell ${cls}"
                         data-tip="${this._esc(tip)}"
                         onmouseenter="WQ.showTip(event)"
                         onmouseleave="WQ.hideTip()">
                    </div>
                </td>`;
            }).join('');
            return `<tr>
                <td class="ind-label">${this._esc(r.indicator.name)}${r.indicator.unit ? ` <span style="color:#94a3b8;font-weight:400;">(${r.indicator.unit})</span>` : ''}</td>
                ${cells}
            </tr>`;
        }).join('');

        wrap.innerHTML = `
            <table class="matrix-table">
                <thead>
                    <tr>
                        <th style="min-width:140px;"></th>
                        ${colHeaders}
                    </tr>
                </thead>
                <tbody>${bodyRows}</tbody>
            </table>
        `;
    }

    async loadReadings() {
        const myReq    = ++this._readingsReqSeq;
        const station  = document.getElementById('analysis-station')?.value;
        const dateFrom = document.getElementById('analysis-from')?.value;
        const dateTo   = document.getElementById('analysis-to')?.value;
        const params   = new URLSearchParams({ page: this._readingsPage, per_page: 10 });
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);

        try {
            const res  = await this._fetch(`/api/wq/readings?${params}`);
            const data = await res.json();
            if (myReq !== this._readingsReqSeq) return;
            if (!data.success) return;
            this._readingsTotal = data.total || 0;
            this._renderReadingsTable(data.readings || []);
            const totalPages = Math.ceil(this._readingsTotal / 10) || 1;
            this._setText('readings-page-label', `Page ${this._readingsPage} of ${totalPages}`);
            const prev = document.getElementById('readings-prev');
            const next = document.getElementById('readings-next');
            if (prev) prev.disabled = this._readingsPage <= 1;
            if (next) next.disabled = this._readingsPage >= totalPages;
        } catch (e) {
            console.error('WQ loadReadings error', e);
        }
    }

    readingsPage(delta) {
        const totalPages = Math.ceil(this._readingsTotal / 10) || 1;
        const next = this._readingsPage + delta;
        if (next < 1 || next > totalPages) return;
        this._readingsPage = next;
        this.loadReadings();
    }

    _renderReadingsTable(readings) {
        const tbody = document.getElementById('readings-table-body');
        if (!tbody) return;
        if (!readings.length) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-10 text-gray-400 text-sm">No readings found for the selected filters.</td></tr>`;
            return;
        }
        tbody.innerHTML = readings.map(r => {
            const violationBadge = r.fails > 0
                ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-rose-50 text-rose-600">
                       <i class="fas fa-exclamation-circle text-[10px]"></i>${r.fails}
                   </span>`
                : `<span class="text-xs text-teal-600 font-semibold">✓ Clean</span>`;
            return `
                <tr class="hover:bg-gray-50 transition-colors" style="border-bottom:1px solid #f8fafc;">
                    <td class="px-5 py-3.5 text-sm font-mono font-semibold text-gray-800">${this._esc(String(r.date).slice(0, 10))}</td>
                    <td class="px-5 py-3.5">
                        <div class="text-sm font-semibold text-gray-800">${this._esc(r.station)}</div>
                        <div class="text-xs text-gray-400 font-mono">${this._esc(r.station_code)}</div>
                    </td>
                    <td class="px-5 py-3.5 text-sm text-gray-600">${r.meas_count}</td>
                    <td class="px-5 py-3.5">${violationBadge}</td>
                    <td class="px-5 py-3.5 text-xs text-gray-400 truncate max-w-xs">${r.source_file ? this._esc(r.source_file) : '—'}</td>
                    <td class="px-5 py-3.5 text-right">
                        <div class="flex justify-end gap-1">
                            <button title="View measurements" onclick="WQ.viewReading(${r.id}, '${this._esc(String(r.date).slice(0,10))}', '${this._esc(r.station)}')"
                                    class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-cyan-600 hover:bg-cyan-50 transition-all text-sm">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button title="Delete" onclick="WQ.deleteReading(${r.id})"
                                    class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all text-sm">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async viewReading(id, date, station) {
        const modal = document.getElementById('reading-detail-modal');
        const body  = document.getElementById('reading-detail-body');
        const title = document.getElementById('reading-modal-title');
        if (!modal || !body) return;
        title.textContent = `${station} — ${date}`;
        body.innerHTML = '<p class="text-center text-gray-400 py-8"><i class="fas fa-spinner fa-spin mr-2"></i>Loading…</p>';
        modal.style.display = 'flex';
        try {
            const res  = await this._fetch(`/api/wq/readings/${id}/measurements`);
            const data = await res.json();
            if (!data.success) { body.innerHTML = '<p class="text-red-500 text-sm">Failed to load.</p>'; return; }
            const rows = (data.measurements || []).filter(m => m.value !== null);
            if (!rows.length) {
                body.innerHTML = '<p class="text-gray-400 text-sm text-center py-6">No measurements recorded for this reading.</p>';
                return;
            }
            body.innerHTML = `
                <div class="grid grid-cols-2 gap-2">
                    ${rows.map(m => {
                        const cls = m.compliant === null ? 'border-gray-200 bg-gray-50'
                                  : m.compliant ? 'border-teal-200 bg-teal-50'
                                  : 'border-rose-200 bg-rose-50';
                        const icon = m.compliant === null ? '' : m.compliant
                            ? '<i class="fas fa-check-circle text-teal-500 text-xs ml-1"></i>'
                            : '<i class="fas fa-times-circle text-rose-500 text-xs ml-1"></i>';
                        return `
                            <div class="rounded-xl border p-3 ${cls}">
                                <div class="text-xs text-gray-500 font-semibold">${this._esc(m.name)}${m.unit ? ` (${this._esc(m.unit)})` : ''}</div>
                                <div class="text-lg font-bold text-gray-900 mt-0.5 flex items-center">
                                    ${m.value !== null ? m.value : '—'}${icon}
                                </div>
                                ${m.upper_std !== null || m.lower_std !== null ? `
                                    <div class="text-xs text-gray-400">
                                        Standard: ${m.lower_std !== null ? `≥${m.lower_std}` : ''}${m.upper_std !== null ? `≤${m.upper_std}` : ''}
                                    </div>` : ''}
                                ${m.flag ? `<span class="text-xs font-bold ${m.flag === 'ABOVE' ? 'text-rose-600' : 'text-amber-600'}">${m.flag}</span>` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        } catch (e) {
            body.innerHTML = '<p class="text-red-500 text-sm">Network error loading measurements.</p>';
        }
    }

    async deleteReading(id) {
        if (!confirm('Delete this reading event and all its measurements? This cannot be undone.')) return;
        try {
            const res  = await this._fetch(`/api/wq/readings/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                this.loadReadings();
                this.loadComplianceMatrix();
            } else {
                alert(data.error || 'Could not delete reading.');
            }
        } catch (err) {
            alert('Network error: ' + err.message);
        }
    }

    // ── Trend chart ───────────────────────────────────────────────────────────

    async loadTrend() {
        const myReq = ++this._trendReqSeq;
        const station   = document.getElementById('analysis-station')?.value;
        const indicator = document.getElementById('analysis-indicator')?.value || 'EC';
        const dateFrom  = document.getElementById('analysis-from')?.value;
        const dateTo    = document.getElementById('analysis-to')?.value;

        const params = new URLSearchParams({ indicator });
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);

        try {
            const res  = await this._fetch(`/api/wq/trend?${params}`);
            const data = await res.json();
            // Drop stale responses from a filter change that's since been superseded —
            // otherwise an out-of-order network reply can silently render outdated data.
            if (myReq !== this._trendReqSeq) return;
            if (!data.success) return;

            const subtitle = document.getElementById('trend-subtitle');
            const ind = this._indicators.find(i => i.code === indicator);
            const indName = ind ? ind.name : indicator;
            const unit    = data.unit || '';
            if (subtitle) subtitle.textContent = `${indName}${unit ? ` (${unit})` : ''} — ${data.series.length} data points`;

            this._buildTrendChart(data.series, indName, unit, data.upper_std, data.lower_std);
            this._buildRadarChart();
        } catch (e) {
            console.error('WQ trend error', e);
        }
    }

    _buildTrendChart(series, name, unit, upperStd, lowerStd) {
        const ctx = document.getElementById('chart-indicator-trend');
        if (!ctx) return;
        if (this._chartTrend) { this._chartTrend.destroy(); this._chartTrend = null; }

        const labels   = series.map(p => p.date);
        const values   = series.map(p => p.value);
        const datasets = [
            {
                label: `${name}${unit ? ` (${unit})` : ''}`,
                data: values,
                borderColor: '#0d9488',
                backgroundColor: 'rgba(13,148,136,.1)',
                borderWidth: 2.5,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: series.map(p =>
                    p.compliant === false ? '#f43f5e' : '#0d9488'
                ),
                pointRadius: 5,
                pointHoverRadius: 8,
            },
        ];
        if (upperStd !== null && upperStd !== undefined) {
            datasets.push({
                label: `Limit (${upperStd})`,
                data: Array(labels.length).fill(upperStd),
                borderColor: '#f43f5e', borderDash: [5, 4], borderWidth: 1.5,
                fill: false, tension: 0, pointRadius: 0,
            });
        }
        if (lowerStd !== null && lowerStd !== undefined) {
            datasets.push({
                label: `Min (${lowerStd})`,
                data: Array(labels.length).fill(lowerStd),
                borderColor: '#f59e0b', borderDash: [5, 4], borderWidth: 1.5,
                fill: false, tension: 0, pointRadius: 0,
            });
        }

        this._chartTrend = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'top', labels: { font: { size: 10 } } },
                    tooltip: { mode: 'index', intersect: false },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 45, minRotation: 30 } },
                    y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    async _buildRadarChart() {
        const ctx = document.getElementById('chart-radar');
        if (!ctx || !this._indicators.length) return;

        // Station/standard/date/indicator can all trigger this within the same tick (e.g.
        // onStandardChange + loadTrend's own call both fire it). Without this guard, two
        // overlapping calls can both pass the "nothing to destroy yet" check before either
        // has created its chart, then both try to bind a new Chart.js instance to the same
        // canvas — Chart.js throws "Canvas is already in use" (confirmed live in testing).
        const myReq = ++this._radarReqSeq;

        // Use the latest reading's first available measurement values, normalised by the
        // CURRENTLY SELECTED standard's upper limit (SANS upper_std, or TWQR twqr_upper) —
        // keeps this chart consistent with the Compliance Matrix's standard toggle, which
        // sits on the same filter bar. Defaults to the true latest reading; when a date
        // range is set, restricts to the latest reading within that window.
        const station  = document.getElementById('analysis-station')?.value;
        const standard = document.getElementById('analysis-standard')?.value || 'sans241';
        const dateFrom = document.getElementById('analysis-from')?.value;
        const dateTo   = document.getElementById('analysis-to')?.value;
        const params   = new URLSearchParams({ limit: 1, standard });
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);

        this._setText('radar-subtitle', standard === 'twqr'
            ? 'Normalised % of TWQR upper limit (DWAF Vol 7)'
            : 'Normalised % of SANS 241 upper limit');

        try {
            const res  = await this._fetch(`/api/wq/compliance?${params}`);
            const data = await res.json();
            // A newer call has started since we began awaiting — drop this stale response
            // rather than let it clobber (or race to create a chart alongside) the result
            // of a filter change the user made after this one.
            if (myReq !== this._radarReqSeq) return;
            if (!data.success || !data.rows.length) return;

            const col0 = 0;
            const labels = [];
            const values = [];
            const colors = [];

            data.rows.forEach(row => {
                const cell = row.cells[col0];
                if (!cell || cell.value === null || cell.not_assessed) return;
                const ind = this._indicators.find(i => i.code === row.indicator.code);
                if (!ind) return;
                const upperLimit = standard === 'twqr' ? ind.twqr_upper : ind.upper_std;
                // Use an explicit null/undefined check, NOT a falsy check — some real
                // SANS 241 limits are legitimately 0 (e.g. E. coli/Total Coliform's
                // zero-tolerance requirement), and `!upperLimit` would silently drop
                // those safety-critical indicators from the chart entirely.
                if (upperLimit === null || upperLimit === undefined) return;
                labels.push(row.indicator.code);
                // A zero-tolerance limit can't be expressed as "% of limit" (division
                // by zero) — represent it as a binary full-scale violation (150%) on
                // any detection, or fully compliant (0%) otherwise.
                const pct = upperLimit > 0
                    ? Math.min((cell.value / upperLimit) * 100, 150)
                    : (cell.value > 0 ? 150 : 0);
                values.push(pct);
                colors.push(cell.compliant === false ? 'rgba(244,63,94,.7)' : 'rgba(13,148,136,.7)');
            });

            if (!labels.length) return;

            // Destroy whatever chart is actually bound to this canvas right now (via Chart.js's
            // own registry, not just our own possibly-stale `this._chartRadar` reference) —
            // the defensive check that actually prevents the "already in use" crash.
            const existing = Chart.getChart(ctx);
            if (existing) existing.destroy();

            this._chartRadar = new Chart(ctx, {
                type: 'radar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Latest reading (% of limit)',
                        data: values,
                        borderColor: '#0891b2',
                        backgroundColor: 'rgba(8,145,178,.15)',
                        pointBackgroundColor: colors,
                        borderWidth: 2,
                        pointRadius: 5,
                    }],
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => `${ctx.raw.toFixed(1)}% of limit`,
                            },
                        },
                    },
                    scales: {
                        r: {
                            ticks: { font: { size: 9 }, stepSize: 25 },
                            pointLabels: { font: { size: 10 } },
                            suggestedMin: 0,
                            suggestedMax: 100,
                        },
                    },
                },
            });
        } catch (e) {
            console.error('WQ radar chart error', e);
        }
    }

    // ── Upload ────────────────────────────────────────────────────────────────

    handleDrop(e) {
        e.preventDefault();
        document.getElementById('wq-upload-zone').classList.remove('dragover');
        const file = e.dataTransfer?.files?.[0];
        if (file) this._setUploadFile(file);
    }

    handleFileSelect(input) {
        const file = input.files?.[0];
        if (file) this._setUploadFile(file);
    }

    _setUploadFile(file) {
        this._uploadFile = file;
        const zone = document.getElementById('wq-upload-zone');
        if (zone) {
            zone.innerHTML = `
                <i class="fas fa-file-excel text-3xl mb-2" style="color:#0d9488;"></i>
                <p class="text-sm font-semibold text-gray-700">${this._esc(file.name)}</p>
                <p class="text-xs text-gray-400 mt-1">${(file.size / 1024).toFixed(1)} KB — ready to upload</p>
            `;
        }
        const btn = document.getElementById('wq-upload-btn');
        if (btn) btn.disabled = false;
    }

    async submitUpload() {
        if (!this._uploadFile) return;
        const btn     = document.getElementById('wq-upload-btn');
        const result  = document.getElementById('wq-upload-result');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Uploading…'; }
        if (result) result.classList.add('hidden');

        const fd = new FormData();
        fd.append('file', this._uploadFile);

        try {
            const res  = await this._fetch('/api/wq/upload', { method: 'POST', body: fd });
            const data = await res.json();

            if (result) {
                result.classList.remove('hidden');
                if (data.success) {
                    result.innerHTML = `
                        <div class="rounded-xl p-4" style="background:#f0fdf4;border:1px solid #bbf7d0;">
                            <div class="flex items-center gap-2 mb-2">
                                <i class="fas fa-check-circle text-teal-600"></i>
                                <span class="text-sm font-bold text-teal-800">Upload complete</span>
                            </div>
                            <div class="text-xs text-teal-700">
                                <span class="font-semibold">${data.inserted}</span> reading(s) inserted/updated.
                                ${data.skipped > 0 ? `<span class="ml-2 text-amber-700">${data.skipped} row(s) skipped.</span>` : ''}
                            </div>
                            ${data.errors && data.errors.length ? `
                                <details class="mt-2">
                                    <summary class="text-xs text-amber-700 cursor-pointer font-semibold">View ${data.errors.length} warning(s)</summary>
                                    <ul class="mt-1 space-y-0.5">
                                        ${data.errors.map(e => `<li class="text-xs text-gray-600">· ${this._esc(e)}</li>`).join('')}
                                    </ul>
                                </details>` : ''}
                        </div>`;
                    this._uploadFile = null;
                    const zone = document.getElementById('wq-upload-zone');
                    if (zone) zone.innerHTML = `<i class="fas fa-file-excel text-4xl mb-3" style="color:#0d9488;"></i><p class="text-sm font-semibold text-gray-700">Drag &amp; drop your Excel file here</p><p class="text-xs text-gray-400 mt-1">or click to browse · .xlsx only</p>`;
                    await this.loadDashboard();
                } else {
                    result.innerHTML = `
                        <div class="rounded-xl p-4" style="background:#fef2f2;border:1px solid #fecaca;">
                            <div class="flex items-center gap-2">
                                <i class="fas fa-exclamation-circle text-rose-500"></i>
                                <span class="text-sm font-bold text-rose-800">Upload failed</span>
                            </div>
                            <p class="text-xs text-rose-700 mt-1">${this._esc(data.error || 'Unknown error')}</p>
                        </div>`;
                }
            }
        } catch (e) {
            if (result) {
                result.classList.remove('hidden');
                result.innerHTML = `<div class="rounded-xl p-4 bg-red-50 border border-red-200 text-xs text-red-700">Network error: ${this._esc(e.message)}</div>`;
            }
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-upload mr-2"></i>Upload File'; }
        }
    }

    downloadTemplate() {
        this._fetch('/api/wq/template')
        .then(r => r.blob())
        .then(blob => {
            const url = URL.createObjectURL(blob);
            const a   = document.createElement('a');
            a.href    = url;
            a.download = 'water_quality_upload_template.xlsx';
            a.click();
            URL.revokeObjectURL(url);
        })
        .catch(e => alert('Could not download template: ' + e.message));
    }

    // ── Export ────────────────────────────────────────────────────────────────

    exportData() {
        const station  = document.getElementById('analysis-station')?.value;
        const dateFrom = document.getElementById('analysis-from')?.value;
        const dateTo   = document.getElementById('analysis-to')?.value;
        const params   = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);

        this._fetch(`/api/wq/export?${params}`)
            .then(r => r.blob())
            .then(blob => {
                const url = URL.createObjectURL(blob);
                const a   = document.createElement('a');
                a.href    = url;
                a.download = `wq_export_${new Date().toISOString().slice(0,10)}.xlsx`;
                a.click();
                URL.revokeObjectURL(url);
            })
            .catch(e => alert('Export failed: ' + e.message));
    }

    // ── Tooltip ───────────────────────────────────────────────────────────────

    showTip(e) {
        const tip  = this._tooltip;
        const text = e.currentTarget.dataset.tip;
        if (!tip || !text) return;
        tip.textContent = text;
        tip.classList.add('visible');
        const move = ev => { tip.style.left = (ev.clientX + 12) + 'px'; tip.style.top = (ev.clientY - 10) + 'px'; };
        e.currentTarget._tipMove = move;
        window.addEventListener('mousemove', move);
    }

    hideTip() {
        if (this._tooltip) this._tooltip.classList.remove('visible');
    }

    // ── Analytics ─────────────────────────────────────────────────────────────

    _populateAnalyticsSelects() {
        ['ana-station', 'alert-station-sel'].forEach(id => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const current = sel.value;
            sel.innerHTML = '<option value="">All stations</option>' + this._stations.map(s =>
                `<option value="${s.id}">${this._esc(s.name)}</option>`
            ).join('');
            if (current) sel.value = current;
        });
    }

    _populateAlertSelects() {
        const sel = document.getElementById('alert-indicator-sel');
        if (!sel) return;
        sel.innerHTML = '<option value="">Select indicator…</option>' +
            this._indicators.map(i =>
                `<option value="${i.id}">${this._esc(i.name)}</option>`
            ).join('');
        this._populateAnalyticsSelects();
    }

    async loadAnalytics() {
        const station   = document.getElementById('ana-station')?.value;
        const dateFrom  = document.getElementById('ana-from')?.value;
        const dateTo    = document.getElementById('ana-to')?.value;
        const indicator = document.getElementById('ana-indicator')?.value || 'EC';

        // Mann-Kendall, LSI and Pollution Load are single-station time-series stats —
        // combining multiple rivers into one trend line would be scientifically
        // meaningless. When "All stations" is selected, these three fall back to the
        // first available station rather than showing nothing until the user picks
        // one explicitly; every other widget below shows real org-wide data by
        // default and only narrows when a specific station is chosen.
        const trendStation = station || (this._stations[0]?.id ?? '');
        const autoSelected = !station && !!trendStation;
        const trendStationName = this._stations.find(s => String(s.id) === String(trendStation))?.name || '';

        await Promise.all([
            this._loadWQI(station, dateFrom, dateTo),
            this._loadBlueDrop(dateFrom, dateTo),
            this._loadMannKendall(trendStation, indicator, dateFrom, dateTo, trendStationName, autoSelected),
            this._loadLSI(trendStation, dateFrom, dateTo, trendStationName, autoSelected),
            this._loadPiper(station, dateFrom, dateTo),
            this._loadStiff(station, dateFrom, dateTo),
            this._loadEutrophication(station, dateFrom, dateTo),
            this._loadAMD(station, dateFrom, dateTo),
            this._loadSeasonal(station, dateFrom, dateTo),
            this._loadPollutionLoad(trendStation, indicator, dateFrom, dateTo, trendStationName, autoSelected),
        ]);
    }

    // ── WQI ──────────────────────────────────────────────────────────────────

    async _loadWQI(station, dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/wqi?${params}`);
            const data = await res.json();
            if (!data.success || !data.wqi.wqi_score) {
                this._setText('wqi-gauge-score', '—');
                this._setText('wqi-gauge-cat', data.wqi?.category || 'No data');
                return;
            }
            const w = data.wqi;
            const arc = document.getElementById('wqi-arc');
            if (arc) {
                const pct   = w.wqi_score / 100;
                const total = 204;
                arc.setAttribute('stroke-dashoffset', String(Math.round(total - total * pct)));
            }
            this._setText('wqi-gauge-score', w.wqi_score);
            this._setText('wqi-gauge-cat', w.category);
            this._setText('wqi-f1', w.F1 !== null ? `${w.F1}%` : '—');
            this._setText('wqi-f2', w.F2 !== null ? `${w.F2}%` : '—');
            this._setText('wqi-f3', w.F3 !== null ? w.F3.toFixed(1) : '—');
            this._setText('wqi-detail',
                `${w.n_total_tests} approved tests · ${w.n_failed_tests} failures · ${w.n_variables} variables`);
        } catch (e) {
            console.error('WQI error', e);
        }
    }

    // ── Blue Drop ─────────────────────────────────────────────────────────────

    async _loadBlueDrop(dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/blue-drop?${params}`);
            const data = await res.json();
            if (!data.success) return;
            const bd = data.blue_drop;
            if (!bd || bd.overall_score === null) {
                this._setText('bd-grade', 'Insufficient data');
                this._setText('bd-sub', 'Need approved measurements');
                return;
            }
            const ring = document.getElementById('bd-ring-fill');
            if (ring) {
                const circumference = 239;
                ring.setAttribute('stroke-dashoffset', String(Math.round(circumference - circumference * bd.overall_score / 100)));
                ring.setAttribute('stroke', bd.achieves_blue_drop ? '#0891b2' : '#f59e0b');
            }
            this._setText('bd-score-txt', bd.overall_score);
            this._setText('bd-grade', bd.grade);
            this._setText('bd-sub', bd.achieves_blue_drop ? '✓ Blue Drop achieved' : 'Below Blue Drop threshold (95%)');
            const bdBreak = document.getElementById('bd-breakdown');
            if (bdBreak && bd.breakdown) {
                bdBreak.innerHTML = Object.entries(bd.breakdown).map(([cat, v]) => `
                    <div class="flex justify-between items-center py-0.5">
                        <span class="text-gray-500 capitalize">${cat.replace(/_/g,' ')}</span>
                        <span class="font-semibold ${v.score >= 95 ? 'text-teal-600' : v.score >= 75 ? 'text-amber-600' : 'text-rose-500'}">
                            ${v.score}%
                        </span>
                    </div>`).join('');
            }
        } catch (e) {
            console.error('Blue Drop error', e);
        }
    }

    // ── Mann-Kendall ──────────────────────────────────────────────────────────

    async _loadMannKendall(station, indicator, dateFrom, dateTo, stationName = '', autoSelected = false) {
        const params = new URLSearchParams({ station_id: station, indicator });
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/mann-kendall?${params}`);
            const data = await res.json();
            if (!data.success) return;
            const mk = data.mann_kendall;
            const panel = document.getElementById('mk-panel');
            if (!panel) return;
            const trendLower = (mk.trend || 'no trend').toLowerCase();
            const badgeCls   = trendLower.includes('increasing') ? 'increasing'
                             : trendLower.includes('decreasing') ? 'decreasing'
                             : 'no-trend';
            const icon = trendLower.includes('increasing') ? 'arrow-up'
                       : trendLower.includes('decreasing') ? 'arrow-down'
                       : 'minus';
            const autoNote = autoSelected && stationName
                ? `<div class="text-xs text-cyan-700 mb-2"><i class="fas fa-map-marker-alt mr-1"></i>Showing ${this._esc(stationName)} — pick a station above to switch (trends can't be combined across rivers).</div>`
                : '';
            panel.innerHTML = mk.n < 4 ? `${autoNote}<p class="text-gray-400 text-xs text-center py-4">Insufficient data (n=${mk.n}, need ≥ 4).</p>` : `
                ${autoNote}
                <div class="flex items-center justify-between mb-4">
                    <span class="mk-trend-badge ${badgeCls}">
                        <i class="fas fa-${icon}"></i> ${mk.trend}
                    </span>
                    <span class="text-xs text-gray-400 ml-2">n = ${mk.n} · p = ${mk.p_value}</span>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div class="p-3 rounded-xl bg-gray-50">
                        <div class="text-xs text-gray-400 mb-1">Z statistic</div>
                        <div class="text-base font-bold text-gray-800">${mk.Z !== null ? mk.Z.toFixed(4) : '—'}</div>
                    </div>
                    <div class="p-3 rounded-xl bg-gray-50">
                        <div class="text-xs text-gray-400 mb-1">Sen's Slope</div>
                        <div class="text-base font-bold text-gray-800">${mk.sen_slope_per_year !== null ? mk.sen_slope_per_year.toFixed(4) + '/yr' : '—'}</div>
                    </div>
                    <div class="p-3 rounded-xl bg-gray-50">
                        <div class="text-xs text-gray-400 mb-1">S statistic</div>
                        <div class="text-base font-bold text-gray-800">${mk.S !== null ? mk.S : '—'}</div>
                    </div>
                    <div class="p-3 rounded-xl bg-gray-50">
                        <div class="text-xs text-gray-400 mb-1">Significant?</div>
                        <div class="text-base font-bold ${mk.is_significant ? 'text-teal-600' : 'text-gray-400'}">${mk.is_significant ? 'Yes (α=0.05)' : 'No'}</div>
                    </div>
                </div>
            `;
        } catch (e) {
            console.error('MK error', e);
        }
    }

    // ── LSI / RSI ─────────────────────────────────────────────────────────────

    _chartLSI = null;
    _lsiReqSeq = 0;

    async _loadLSI(station, dateFrom, dateTo, stationName = '', autoSelected = false) {
        const myReq = ++this._lsiReqSeq;
        const params = new URLSearchParams({ station_id: station });
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/lsi?${params}`);
            const data = await res.json();
            if (myReq !== this._lsiReqSeq) return;
            if (!data.success) return;
            const series = data.lsi_series.filter(r => r.LSI !== undefined && r.LSI !== null);
            const panel  = document.getElementById('lsi-panel');
            const autoNote = autoSelected && stationName
                ? `<div class="text-xs text-cyan-700 mb-2"><i class="fas fa-map-marker-alt mr-1"></i>Showing ${this._esc(stationName)} — pick a station above to switch.</div>`
                : '';
            if (!series.length) {
                if (panel) panel.innerHTML = `${autoNote}<p class="text-gray-400 text-xs text-center py-4">Requires pH, TDS/EC, Ca, and Alkalinity measurements.</p>`;
                return;
            }
            const latest = series[series.length - 1];
            if (panel) {
                const lsiColor = latest.LSI > 0.5 ? '#0d9488' : latest.LSI > 0 ? '#f59e0b' : latest.LSI < -0.5 ? '#ef4444' : '#64748b';
                panel.innerHTML = `
                    ${autoNote}
                    <div class="grid grid-cols-2 gap-3 mb-3">
                        <div class="p-3 rounded-xl bg-gray-50 text-center">
                            <div class="text-xs text-gray-400 mb-1">Latest LSI</div>
                            <div class="text-xl font-bold" style="color:${lsiColor}">${latest.LSI.toFixed(3)}</div>
                            <div class="text-xs text-gray-500 mt-1">${latest.lsi_class}</div>
                        </div>
                        <div class="p-3 rounded-xl bg-gray-50 text-center">
                            <div class="text-xs text-gray-400 mb-1">Ryznar (RSI)</div>
                            <div class="text-xl font-bold text-gray-800">${latest.RSI.toFixed(3)}</div>
                            <div class="text-xs text-gray-500 mt-1">${latest.rsi_class}</div>
                        </div>
                    </div>
                    <div class="lsi-bar-track">
                        <div class="lsi-bar-fill" style="
                            background:${lsiColor};
                            width:${Math.min(100, Math.max(0, (latest.LSI + 3) / 6 * 100)).toFixed(1)}%;
                        "></div>
                    </div>
                    <div class="flex justify-between text-xs text-gray-400 mt-1">
                        <span>Corrosive (-3)</span>
                        <span style="font-weight:600;">0</span>
                        <span>Scale (+3)</span>
                    </div>`;
            }
            // Chart
            const ctx = document.getElementById('chart-lsi-trend');
            if (ctx) {
                const existing = Chart.getChart(ctx);
                if (existing) existing.destroy();
                this._chartLSI = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: series.map(r => r.date),
                        datasets: [
                            { label: 'LSI', data: series.map(r => r.LSI), borderColor: '#0891b2', borderWidth: 2, tension: 0.4, fill: false, pointRadius: 4 },
                            { label: 'RSI baseline (6.5)', data: Array(series.length).fill(6.5), borderColor: '#f43f5e', borderDash: [5,3], borderWidth: 1.2, pointRadius: 0, fill: false },
                        ],
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { position: 'top', labels: { font: { size: 10 } } } },
                        scales: { x: { grid: { display: false }, ticks: { font: { size: 9 } } }, y: { ticks: { font: { size: 9 } } } },
                    },
                });
            }
        } catch (e) {
            console.error('LSI error', e);
        }
    }

    // ── Piper Diagram (pure SVG) ───────────────────────────────────────────────

    async _loadPiper(station, dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (station)  params.append('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/piper?${params}`);
            const data = await res.json();
            const wrap = document.getElementById('piper-svg-wrap');
            if (!wrap) return;
            if (!data.success || !data.points.length) {
                wrap.innerHTML = '<p class="text-gray-400 text-sm text-center py-6">Requires Ca, Mg, Na/K, HCO3, Cl, SO4 approved measurements.</p>';
                return;
            }
            wrap.innerHTML = this._renderPiperSVG(data.points);
        } catch (e) {
            console.error('Piper error', e);
        }
    }

    _ternaryToXY(a, b, c, x0, y0, size) {
        // a+b+c must sum to 100; a = bottom-left, b = bottom-right, c = top
        const pct_a = a / 100, pct_b = b / 100, pct_c = c / 100;
        const px = x0 + pct_b * size + pct_c * size * 0.5;
        const py = y0 - pct_c * size * Math.sin(Math.PI / 3);
        return { x: px, y: py };
    }

    _renderPiperSVG(points) {
        const W = 680, H = 500;
        const T = 200; // triangle side length

        // Left triangle (cations): bottom-left=Ca, bottom-right=NaK, top=Mg
        const cLx = 60, cLy = 420;
        // Right triangle (anions): bottom-left=HCO3, bottom-right=Cl, top=SO4
        const aLx = 380, aLy = 420;
        // Diamond centre
        const dCx = 340, dCy = 220;

        const trianglePoints = (x0, y0, sz) => {
            const p1 = `${x0},${y0}`;
            const p2 = `${x0 + sz},${y0}`;
            const p3 = `${x0 + sz * 0.5},${y0 - sz * Math.sin(Math.PI / 3)}`;
            return `${p1} ${p2} ${p3}`;
        };

        const catPoints   = trianglePoints(cLx, cLy, T);
        const anionPoints = trianglePoints(aLx, aLy, T);

        // Diamond: 4 vertices (top, right, bottom, left)
        const dTop   = { x: dCx,        y: dCy - T * Math.sin(Math.PI / 3) * 0.85 };
        const dRight = { x: dCx + T * 0.6, y: dCy };
        const dBot   = { x: dCx,        y: dCy + T * Math.sin(Math.PI / 3) * 0.85 };
        const dLeft  = { x: dCx - T * 0.6, y: dCy };
        const diamondPts = `${dTop.x},${dTop.y} ${dRight.x},${dRight.y} ${dBot.x},${dBot.y} ${dLeft.x},${dLeft.y}`;

        const COLORS = ['#0891b2','#14b8a6','#f59e0b','#8b5cf6','#ef4444','#10b981','#f97316'];

        const dots = points.map((p, i) => {
            // Cation position: x=NaK%, y via barycentric (Ca, Mg, NaK)
            const catPos = this._ternaryToXY(p.pct_Ca, p.pct_NaK, p.pct_Mg, cLx, cLy, T);
            // Anion position: x=Cl%, via (HCO3, Cl, SO4)
            const anPos  = this._ternaryToXY(p.pct_HCO3, p.pct_Cl, p.pct_SO4, aLx, aLy, T);
            // Diamond: project from both triangles
            const dX = dLeft.x + (p.x_diamond / 100) * (dRight.x - dLeft.x);
            const dY = dBot.y  - (p.y_diamond / 100) * (dBot.y   - dTop.y);
            const color = COLORS[i % COLORS.length];
            const tip = `${this._esc(p.station)} (${p.date})\n${p.water_type}`;
            return `
                <circle cx="${catPos.x.toFixed(1)}" cy="${catPos.y.toFixed(1)}" r="5" fill="${color}" opacity="0.85" stroke="white" stroke-width="1">
                    <title>${tip}</title></circle>
                <circle cx="${anPos.x.toFixed(1)}" cy="${anPos.y.toFixed(1)}" r="5" fill="${color}" opacity="0.85" stroke="white" stroke-width="1">
                    <title>${tip}</title></circle>
                <circle cx="${dX.toFixed(1)}" cy="${dY.toFixed(1)}" r="6" fill="${color}" opacity="0.9" stroke="white" stroke-width="1.5">
                    <title>${tip}</title></circle>
            `;
        }).join('');

        const labelStyle = 'font-size:10px;font-family:Arial;fill:#64748b;';

        return `
        <svg viewBox="0 0 ${W} ${H}" style="max-height:460px;width:100%;" xmlns="http://www.w3.org/2000/svg">
            <!-- Cation triangle -->
            <polygon points="${catPoints}" fill="#ecfeff" stroke="#0891b2" stroke-width="1.5"/>
            <text x="${cLx + T*0.5}" y="${cLy + 18}" text-anchor="middle" style="${labelStyle}font-weight:700;">Cations</text>
            <text x="${cLx - 12}" y="${cLy + 4}" text-anchor="end" style="${labelStyle}">Ca²⁺</text>
            <text x="${cLx + T + 12}" y="${cLy + 4}" text-anchor="start" style="${labelStyle}">Na⁺+K⁺</text>
            <text x="${cLx + T*0.5}" y="${cLy - T*Math.sin(Math.PI/3) - 8}" text-anchor="middle" style="${labelStyle}">Mg²⁺</text>

            <!-- Anion triangle -->
            <polygon points="${anionPoints}" fill="#f0fdf4" stroke="#0d9488" stroke-width="1.5"/>
            <text x="${aLx + T*0.5}" y="${aLy + 18}" text-anchor="middle" style="${labelStyle}font-weight:700;">Anions</text>
            <text x="${aLx - 12}" y="${aLy + 4}" text-anchor="end" style="${labelStyle}">HCO₃⁻</text>
            <text x="${aLx + T + 12}" y="${aLy + 4}" text-anchor="start" style="${labelStyle}">Cl⁻</text>
            <text x="${aLx + T*0.5}" y="${aLy - T*Math.sin(Math.PI/3) - 8}" text-anchor="middle" style="${labelStyle}">SO₄²⁻</text>

            <!-- Diamond -->
            <polygon points="${diamondPts}" fill="#fefce8" stroke="#f59e0b" stroke-width="1.5"/>
            <text x="${dCx}" y="${dTop.y - 8}" text-anchor="middle" style="${labelStyle}font-weight:700;">Na+K / SO₄</text>
            <text x="${dCx}" y="${dBot.y + 16}" text-anchor="middle" style="${labelStyle}font-weight:700;">Ca+Mg / HCO₃</text>

            <!-- Data points -->
            ${dots}

            <!-- Title -->
            <text x="${W/2}" y="24" text-anchor="middle" style="font-size:13px;font-weight:700;font-family:Arial;fill:#0f172a;">Piper Diagram — Major Ion Chemistry</text>
        </svg>`;
    }

    // ── Stiff Diagrams ────────────────────────────────────────────────────────

    async _loadStiff(station, dateFrom, dateTo) {
        const params = new URLSearchParams({ limit: 5 });
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/stiff?${params}`);
            const data = await res.json();
            const wrap = document.getElementById('stiff-svg-wrap');
            if (!wrap) return;
            if (!data.success || !data.diagrams.length) {
                wrap.innerHTML = '<p class="text-gray-400 text-sm py-4">No data for Stiff diagrams.</p>';
                return;
            }
            wrap.innerHTML = data.diagrams.map(d => this._renderStiffSVG(d)).join('');
        } catch (e) {
            console.error('Stiff error', e);
        }
    }

    _renderStiffSVG(d) {
        const W = 220, H = 140;
        const cx = W / 2, armH = 32, armCount = 3;
        const maxMeq = d.max_meq || 1;
        const maxPx  = 80;

        const arms = d.arms.map((arm, i) => {
            const y     = 28 + i * armH;
            const leftW = Math.min((arm.cat_meq / maxMeq) * maxPx, maxPx);
            const rightW= Math.min((arm.an_meq  / maxMeq) * maxPx, maxPx);
            return { y, leftW, rightW, cation: arm.cation, anion: arm.anion,
                     cat_meq: arm.cat_meq, an_meq: arm.an_meq };
        });

        const polyLeft  = arms.map((a, i) => `${(cx - a.leftW).toFixed(1)},${a.y.toFixed(1)}`);
        const polyRight = arms.map((a, i) => `${(cx + a.rightW).toFixed(1)},${a.y.toFixed(1)}`);
        const polyPts   = [...polyLeft, ...[...polyRight].reverse()].join(' ');

        const armLines = arms.map(a => `
            <line x1="${cx}" y1="${a.y}" x2="${(cx - a.leftW).toFixed(1)}" y2="${a.y}" stroke="#94a3b8" stroke-width="1"/>
            <line x1="${cx}" y1="${a.y}" x2="${(cx + a.rightW).toFixed(1)}" y2="${a.y}" stroke="#94a3b8" stroke-width="1"/>
            <text x="${(cx - a.leftW - 3).toFixed(1)}" y="${(a.y + 4).toFixed(1)}" text-anchor="end" font-size="8" fill="#64748b">${a.cation}</text>
            <text x="${(cx + a.rightW + 3).toFixed(1)}" y="${(a.y + 4).toFixed(1)}" font-size="8" fill="#64748b">${a.anion}</text>
        `).join('');

        const label = this._esc(d.label || `${d.station} — ${d.date}`);
        return `
            <div style="text-align:center;">
                <svg viewBox="0 0 ${W} ${H}" width="${W}" style="overflow:visible;" xmlns="http://www.w3.org/2000/svg">
                    <line x1="${cx}" y1="10" x2="${cx}" y2="${H - 20}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3,3"/>
                    <polygon points="${polyPts}" fill="rgba(8,145,178,.25)" stroke="#0891b2" stroke-width="1.5"/>
                    ${armLines}
                    <text x="${cx}" y="${H - 6}" text-anchor="middle" font-size="8" font-weight="700" fill="#0f172a">${label}</text>
                </svg>
            </div>
        `;
    }

    // ── Eutrophication ────────────────────────────────────────────────────────

    async _loadEutrophication(station, dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/eutrophication?${params}`);
            const data = await res.json();
            const panel = document.getElementById('tsi-panel');
            if (!panel) return;
            const series = (data.eutrophication || []).filter(r => r.tsi_overall !== null);
            if (!series.length) {
                panel.innerHTML = '<p class="text-gray-400 text-xs text-center py-6">Requires TP, Chlorophyll-a, or Secchi depth measurements.</p>';
                return;
            }
            const latest = series[series.length - 1];
            const trophicCls = latest.trophic_class === 'Oligotrophic' ? 'oligo'
                             : latest.trophic_class === 'Mesotrophic'  ? 'meso'
                             : latest.trophic_class === 'Eutrophic'    ? 'eutro'
                             : 'hyper';
            panel.innerHTML = `
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <div class="text-3xl font-black text-gray-900">${latest.tsi_overall}</div>
                        <div class="text-xs text-gray-400">Carlson TSI — ${this._esc(latest.station || '')} (${latest.date})</div>
                    </div>
                    <span class="trophic-pill ${trophicCls}">
                        <i class="fas fa-water text-xs"></i> ${latest.trophic_class}
                    </span>
                </div>
                <div class="grid grid-cols-3 gap-2 text-center">
                    ${latest.tsi_tp !== null ? `<div class="p-2 rounded-lg bg-gray-50"><div class="text-xs text-gray-400">TSI-TP</div><div class="font-bold text-gray-700">${latest.tsi_tp}</div></div>` : ''}
                    ${latest.tsi_chl !== null ? `<div class="p-2 rounded-lg bg-gray-50"><div class="text-xs text-gray-400">TSI-Chl</div><div class="font-bold text-gray-700">${latest.tsi_chl}</div></div>` : ''}
                    ${latest.tsi_sd !== null ? `<div class="p-2 rounded-lg bg-gray-50"><div class="text-xs text-gray-400">TSI-SD</div><div class="font-bold text-gray-700">${latest.tsi_sd}</div></div>` : ''}
                </div>
                <div class="mt-3 text-xs text-gray-400">
                    Scale: &lt;40 Oligotrophic · 40–50 Mesotrophic · 50–70 Eutrophic · &gt;70 Hypereutrophic
                </div>
            `;
        } catch (e) {
            console.error('Eutrophication error', e);
        }
    }

    // ── AMD ───────────────────────────────────────────────────────────────────

    async _loadAMD(station, dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res   = await this._fetch(`/api/wq/analytics/amd?${params}`);
            const data  = await res.json();
            const panel = document.getElementById('amd-panel');
            if (!panel) return;
            const results = data.amd || [];
            if (!results.length) {
                panel.innerHTML = '<p class="text-gray-400 text-xs text-center py-6">No AMD indicator data available.</p>';
                return;
            }
            const riskCounts = { None: 0, Low: 0, Moderate: 0, High: 0 };
            results.forEach(r => { riskCounts[r.amd_risk] = (riskCounts[r.amd_risk] || 0) + 1; });
            const latest = results[results.length - 1];
            const riskCls = latest.amd_risk === 'None' ? 'none'
                          : latest.amd_risk === 'Low'  ? 'low'
                          : latest.amd_risk === 'Moderate' ? 'moderate'
                          : 'high';
            const flagsHtml = latest.amd_flags.map(f => `
                <div class="flex justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                    <span class="text-gray-600 font-semibold">${f.indicator}</span>
                    <span class="text-rose-600 font-bold">${f.value}</span>
                    <span class="text-gray-400">&gt; ${f.threshold}</span>
                </div>`).join('');
            panel.innerHTML = `
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <div class="text-xs text-gray-400">Latest Reading — ${this._esc(latest.station || '')} (${latest.date})</div>
                        <div class="text-xs text-gray-500 mt-1">${latest.amd_flags.length} AMD indicator(s) triggered</div>
                    </div>
                    <span class="amd-pill ${riskCls}">
                        <i class="fas fa-radiation text-xs"></i> ${latest.amd_risk} Risk
                    </span>
                </div>
                ${flagsHtml || '<div class="text-xs text-gray-400 py-2">No AMD thresholds breached in latest reading.</div>'}
                <div class="mt-3 grid grid-cols-4 gap-1 text-xs text-center">
                    ${Object.entries(riskCounts).map(([r, n]) => `
                        <div class="p-1.5 rounded bg-gray-50"><div class="font-bold text-gray-700">${n}</div><div class="text-gray-400">${r}</div></div>
                    `).join('')}
                </div>
            `;
        } catch (e) {
            console.error('AMD error', e);
        }
    }

    // ── Seasonal ──────────────────────────────────────────────────────────────

    async _loadSeasonal(station, dateFrom, dateTo) {
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res   = await this._fetch(`/api/wq/analytics/seasonal?${params}`);
            const data  = await res.json();
            const panel = document.getElementById('seasonal-panel');
            if (!panel) return;
            const rows = data.seasonal || [];
            if (!rows.length) {
                panel.innerHTML = '<p class="text-gray-400 text-xs text-center py-6">No seasonal data available.</p>';
                return;
            }
            const maxAll = rows.reduce((m, r) => {
                const w = r.wet?.mean || 0;
                const d = r.dry?.mean || 0;
                return Math.max(m, w, d);
            }, 1);
            panel.innerHTML = rows.slice(0, 10).map(r => {
                const wm = r.wet?.mean, dm = r.dry?.mean;
                if (wm === null && dm === null) return '';
                const wPct = wm !== null ? Math.min(100, (wm / maxAll) * 100) : 0;
                const dPct = dm !== null ? Math.min(100, (dm / maxAll) * 100) : 0;
                return `
                    <div class="mb-3">
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-xs font-semibold text-gray-700">${this._esc(r.code)}</span>
                            <span class="text-xs text-gray-400">${r.unit || ''}</span>
                        </div>
                        <div class="seasonal-bar">
                            <span class="s-label text-blue-500 font-semibold">Wet</span>
                            <div class="s-track"><div class="s-fill wet" style="width:${wPct.toFixed(1)}%"></div></div>
                            <span class="text-xs text-gray-600 w-14 text-right">${wm !== null ? wm.toFixed(3) : '—'}</span>
                        </div>
                        <div class="seasonal-bar">
                            <span class="s-label text-amber-500 font-semibold">Dry</span>
                            <div class="s-track"><div class="s-fill dry" style="width:${dPct.toFixed(1)}%"></div></div>
                            <span class="text-xs text-gray-600 w-14 text-right">${dm !== null ? dm.toFixed(3) : '—'}</span>
                        </div>
                    </div>`;
            }).join('');
        } catch (e) {
            console.error('Seasonal error', e);
        }
    }

    // ── Pollution Load ────────────────────────────────────────────────────────

    _chartLoad = null;
    _loadReqSeq = 0;

    async _loadPollutionLoad(station, indicator, dateFrom, dateTo, stationName = '', autoSelected = false) {
        const myReq = ++this._loadReqSeq;
        const params = new URLSearchParams({ station_id: station, indicator });
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/pollution-load?${params}`);
            const data = await res.json();
            if (myReq !== this._loadReqSeq) return;
            const panel = document.getElementById('load-panel');
            const ctx   = document.getElementById('chart-load-trend');
            if (!data.success) return;
            const series = (data.series || []).filter(r => r.load_kg_day !== null);
            const autoNote = autoSelected && stationName
                ? `<div class="text-xs text-cyan-700 mb-2"><i class="fas fa-map-marker-alt mr-1"></i>Showing ${this._esc(stationName)} — pick a station above to switch.</div>`
                : '';
            if (!series.length) {
                if (panel) panel.innerHTML = `${autoNote}<p class="text-gray-400 text-xs text-center">No flow rate data. Add flow_rate_m3s to readings to compute load.</p>`;
                if (ctx) { const existing = Chart.getChart(ctx); if (existing) existing.destroy(); }
                return;
            }
            if (ctx) {
                const existing = Chart.getChart(ctx);
                if (existing) existing.destroy();
                this._chartLoad = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: series.map(r => r.date),
                        datasets: [{
                            label: `${indicator} Load (kg/day)`,
                            data: series.map(r => r.load_kg_day),
                            backgroundColor: 'rgba(8,145,178,.7)',
                            borderColor: '#0891b2',
                            borderWidth: 1.5,
                            borderRadius: 4,
                        }],
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
                        scales: { x: { grid: { display: false }, ticks: { font: { size: 9 } } }, y: { ticks: { font: { size: 9 } } } },
                    },
                });
            }
            if (panel) panel.innerHTML = `${autoNote}<div class="text-xs text-gray-400 mt-1">${series.length} readings with flow data · indicator: ${this._esc(indicator)}</div>`;
        } catch (e) {
            console.error('Pollution load error', e);
        }
    }

    // ── Alert Config ─────────────────────────────────────────────────────────

    async loadAlertConfigs() {
        try {
            const res  = await this._fetch('/api/wq/alerts/config');
            const data = await res.json();
            const list = document.getElementById('alert-config-list');
            if (!list) return;
            if (!data.success || !(data.configs || []).length) {
                list.innerHTML = '<p class="text-gray-400 text-xs text-center py-4">No alert rules configured.</p>';
                return;
            }
            list.innerHTML = data.configs.map(c => `
                <div class="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                    <div>
                        <div class="text-xs font-semibold text-gray-800">${this._esc(c.indicator)} — ${this._esc(c.threshold_type)} ${c.threshold_value}${c.unit ? ' ' + c.unit : ''}</div>
                        <div class="text-xs text-gray-400">${this._esc(c.station)} · ${c.alert_email || ''} ${c.alert_whatsapp || ''}</div>
                    </div>
                    <button onclick="WQ.deleteAlertConfig(${c.id})"
                            class="text-xs text-rose-400 hover:text-rose-600 px-2 py-1 rounded-lg hover:bg-rose-50 transition-all">
                        <i class="fas fa-times"></i>
                    </button>
                </div>`).join('');
        } catch (e) {
            console.error('Alert configs error', e);
        }
    }

    async createAlertConfig() {
        const indicatorId = document.getElementById('alert-indicator-sel')?.value;
        const stationId   = document.getElementById('alert-station-sel')?.value || null;
        const threshType  = document.getElementById('alert-type-sel')?.value;
        const threshVal   = parseFloat(document.getElementById('alert-threshold')?.value);
        const email       = document.getElementById('alert-email')?.value.trim() || null;
        const whatsapp    = document.getElementById('alert-whatsapp')?.value.trim() || null;
        const msg         = document.getElementById('alert-config-msg');

        if (!indicatorId) { alert('Please select an indicator.'); return; }
        if (isNaN(threshVal)) { alert('Please enter a valid threshold value.'); return; }
        if (!email && !whatsapp) { alert('At least one of email or WhatsApp number is required.'); return; }

        try {
            const res  = await this._fetch('/api/wq/alerts/config', {
                method: 'POST',
                body:   JSON.stringify({ indicator_id: parseInt(indicatorId), station_id: stationId ? parseInt(stationId) : null,
                    threshold_type: threshType, threshold_value: threshVal, alert_email: email, alert_whatsapp: whatsapp }),
            });
            const data = await res.json();
            if (msg) {
                msg.classList.remove('hidden');
                if (data.success) {
                    msg.style.color = '#0d9488';
                    msg.textContent = 'Alert rule created successfully.';
                    await this.loadAlertConfigs();
                } else {
                    msg.style.color = '#ef4444';
                    msg.textContent = data.error || 'Failed to create rule.';
                }
            }
        } catch (e) {
            if (msg) { msg.classList.remove('hidden'); msg.style.color = '#ef4444'; msg.textContent = 'Network error.'; }
        }
    }

    async deleteAlertConfig(id) {
        if (!confirm('Delete this alert rule?')) return;
        try {
            const res  = await this._fetch(`/api/wq/alerts/config/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) await this.loadAlertConfigs();
            else alert(data.error || 'Could not delete rule.');
        } catch (e) { alert('Network error.'); }
    }

    async loadAlertLog() {
        try {
            const res  = await this._fetch('/api/wq/alerts/log');
            const data = await res.json();
            const list = document.getElementById('alert-log-list');
            if (!list) return;
            if (!data.success || !(data.logs || []).length) {
                list.innerHTML = '<p class="text-gray-400 text-xs text-center py-4">No alerts dispatched yet.</p>';
                return;
            }
            list.innerHTML = data.logs.map(l => `
                <div class="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0">
                    <div class="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
                         style="${l.channel === 'email' ? 'background:#ede9fe;' : 'background:#d1fae5;'}">
                        <i class="fas fa-${l.channel === 'email' ? 'envelope' : 'comment-dots'} text-xs"
                           style="color:${l.channel === 'email' ? '#7c3aed' : '#059669'};"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="text-xs font-semibold text-gray-800 truncate">${this._esc(l.indicator)} at ${this._esc(l.station)}</div>
                        <div class="text-xs text-gray-400">${this._esc(l.recipient)} · ${String(l.dispatched_at).slice(0,16)}</div>
                    </div>
                    <span class="text-xs font-bold px-2 py-0.5 rounded-full ${l.status === 'sent' ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}">${l.status}</span>
                </div>`).join('');
        } catch (e) {
            console.error('Alert log error', e);
        }
    }

    // ── Water Safety Plan: Risk Register + Corrective Actions ────────────────

    _populateRiskStationSelect() {
        const sel = document.getElementById('risk-station-sel');
        if (!sel) return;
        sel.innerHTML = '<option value="">Org-wide hazard</option>' +
            this._stations.map(s => `<option value="${s.id}">${this._esc(s.name)}</option>`).join('');
    }

    _riskBadge(score) {
        if (score >= 15) return { label: 'Critical', cls: 'background:#fee2e2;color:#991b1b;' };
        if (score >= 8)  return { label: 'High',     cls: 'background:#ffedd5;color:#9a3412;' };
        if (score >= 4)  return { label: 'Medium',   cls: 'background:#fef9c3;color:#854d0e;' };
        return                  { label: 'Low',      cls: 'background:#d1fae5;color:#065f46;' };
    }

    async loadRiskRegister() {
        const list = document.getElementById('risk-register-list');
        if (!list) return;
        try {
            const res  = await this._fetch('/api/wq/risk-register');
            const data = await res.json();
            if (!data.success || !(data.risks || []).length) {
                list.innerHTML = '<p class="text-gray-400 text-xs text-center py-4">No risks logged yet. Click "Add Risk" to start your risk register.</p>';
                return;
            }
            list.innerHTML = `
                <table class="w-full text-xs">
                    <thead><tr class="text-left text-gray-400 border-b border-gray-100">
                        <th class="py-2 pr-2">Hazard</th><th class="py-2 pr-2">Risk</th>
                        <th class="py-2 pr-2">Control Measure</th><th class="py-2 pr-2">Responsible</th>
                        <th class="py-2 pr-2">Status</th><th class="py-2"></th>
                    </tr></thead>
                    <tbody>
                        ${data.risks.map(r => {
                            const badge = this._riskBadge(r.risk_score);
                            return `<tr class="border-b border-gray-50">
                                <td class="py-2 pr-2 font-medium text-gray-800">${this._esc(r.hazard_description)}</td>
                                <td class="py-2 pr-2"><span class="px-2 py-0.5 rounded-full text-xs font-bold" style="${badge.cls}">${badge.label} (${r.risk_score})</span></td>
                                <td class="py-2 pr-2 text-gray-500">${this._esc(r.control_measure || '—')}</td>
                                <td class="py-2 pr-2 text-gray-500">${this._esc(r.responsible_person || '—')}</td>
                                <td class="py-2 pr-2">
                                    <select onchange="WQ.updateRiskStatus(${r.risk_id}, this.value)" class="border border-gray-200 rounded px-1 py-0.5 text-xs">
                                        <option value="open" ${r.status==='open'?'selected':''}>Open</option>
                                        <option value="mitigated" ${r.status==='mitigated'?'selected':''}>Mitigated</option>
                                        <option value="closed" ${r.status==='closed'?'selected':''}>Closed</option>
                                    </select>
                                </td>
                                <td class="py-2 text-right"><button onclick="WQ.deleteRisk(${r.risk_id})" class="text-gray-300 hover:text-red-500"><i class="fas fa-trash"></i></button></td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>`;
        } catch (e) {
            console.error('Risk register load error', e);
        }
    }

    openRiskModal() {
        document.getElementById('risk-form').reset();
        document.getElementById('risk-form-msg').classList.add('hidden');
        document.getElementById('risk-modal').style.display = 'flex';
    }

    closeRiskModal() {
        document.getElementById('risk-modal').style.display = 'none';
    }

    async saveRisk(e) {
        e.preventDefault();
        const payload = {
            hazard_description:   document.getElementById('risk-hazard').value.trim(),
            hazard_source:        document.getElementById('risk-source').value.trim() || null,
            station_id:           document.getElementById('risk-station-sel').value || null,
            likelihood:           parseInt(document.getElementById('risk-likelihood').value, 10),
            severity:             parseInt(document.getElementById('risk-severity').value, 10),
            control_measure:      document.getElementById('risk-control').value.trim() || null,
            monitoring_frequency: document.getElementById('risk-freq').value.trim() || null,
            responsible_person:   document.getElementById('risk-responsible').value.trim() || null,
        };
        const msg = document.getElementById('risk-form-msg');
        try {
            const res  = await this._fetch('/api/wq/risk-register', { method: 'POST', body: JSON.stringify(payload) });
            const data = await res.json();
            if (data.success) {
                this.closeRiskModal();
                await this.loadRiskRegister();
            } else {
                msg.textContent = data.error || 'Failed to save risk.';
                msg.className = 'text-xs font-semibold text-red-500';
            }
        } catch (err) {
            msg.textContent = 'Network error: ' + err.message;
            msg.className = 'text-xs font-semibold text-red-500';
        }
    }

    async updateRiskStatus(riskId, status) {
        try {
            await this._fetch(`/api/wq/risk-register/${riskId}`, { method: 'PUT', body: JSON.stringify({ status }) });
            await this.loadRiskRegister();
        } catch (e) { alert('Network error.'); }
    }

    async deleteRisk(riskId) {
        if (!confirm('Delete this risk entry?')) return;
        try {
            const res  = await this._fetch(`/api/wq/risk-register/${riskId}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) await this.loadRiskRegister();
            else alert(data.error || 'Could not delete.');
        } catch (e) { alert('Network error.'); }
    }

    async loadCorrectiveActions() {
        const list   = document.getElementById('capa-list');
        const status = document.getElementById('capa-status-filter')?.value;
        if (!list) return;
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        try {
            const res  = await this._fetch(`/api/wq/corrective-actions?${params}`);
            const data = await res.json();
            if (!data.success || !(data.actions || []).length) {
                list.innerHTML = '<p class="text-gray-400 text-xs text-center py-4">No corrective actions logged.</p>';
                return;
            }
            const statusColors = {
                open: 'background:#fee2e2;color:#991b1b;', in_progress: 'background:#fef9c3;color:#854d0e;',
                closed: 'background:#d1fae5;color:#065f46;', overdue: 'background:#fecaca;color:#7f1d1d;',
            };
            list.innerHTML = `
                <table class="w-full text-xs">
                    <thead><tr class="text-left text-gray-400 border-b border-gray-100">
                        <th class="py-2 pr-2">Description</th><th class="py-2 pr-2">Assigned To</th>
                        <th class="py-2 pr-2">Due</th><th class="py-2 pr-2">Status</th><th class="py-2">Source</th>
                    </tr></thead>
                    <tbody>
                        ${data.actions.map(a => `
                            <tr class="border-b border-gray-50">
                                <td class="py-2 pr-2 text-gray-700">${this._esc(a.description)}</td>
                                <td class="py-2 pr-2 text-gray-500">${this._esc(a.assigned_to || '—')}</td>
                                <td class="py-2 pr-2 text-gray-500">${a.due_date || '—'}</td>
                                <td class="py-2 pr-2">
                                    <select onchange="WQ.updateActionStatus(${a.action_id}, this.value)" class="border border-gray-200 rounded px-1 py-0.5 text-xs" style="${statusColors[a.status] || ''}">
                                        <option value="open" ${a.status==='open'?'selected':''}>Open</option>
                                        <option value="in_progress" ${a.status==='in_progress'?'selected':''}>In Progress</option>
                                        <option value="closed" ${a.status==='closed'?'selected':''}>Closed</option>
                                        <option value="overdue" ${a.status==='overdue'?'selected':''}>Overdue</option>
                                    </select>
                                </td>
                                <td class="py-2 text-gray-400">${a.auto_generated ? '<i class="fas fa-robot" title="Auto-generated from a compliance violation"></i>' : 'Manual'}</td>
                            </tr>`).join('')}
                    </tbody>
                </table>`;
        } catch (e) {
            console.error('Corrective actions load error', e);
        }
    }

    async updateActionStatus(actionId, status) {
        try {
            await this._fetch(`/api/wq/corrective-actions/${actionId}`, { method: 'PUT', body: JSON.stringify({ status }) });
            await this.loadCorrectiveActions();
        } catch (e) { alert('Network error.'); }
    }

    async exportWSP() {
        try {
            const res = await this._fetch('/api/wq/wsp/export');
            if (!res.ok) { alert('Export failed.'); return; }
            const blob = await res.blob();
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href = url; a.download = 'water_safety_plan_export.xlsx';
            document.body.appendChild(a); a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Network error: ' + e.message);
        }
    }

    // ── Diagnostics ───────────────────────────────────────────────────────────

    _populateDiagnosticsStationSelect() {
        const sel = document.getElementById('diag-station');
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">All stations</option>' +
            this._stations.map(s => `<option value="${s.id}">${this._esc(s.name)}</option>`).join('');
        if (current) sel.value = current;
    }

    async loadDiagnosticsTab() {
        const station  = document.getElementById('diag-station')?.value;
        const dateFrom = document.getElementById('diag-from')?.value;
        const dateTo   = document.getElementById('diag-to')?.value;
        await Promise.all([
            this.loadDiagnostics(station, dateFrom, dateTo),
            this.loadMultiUseCompliance(station, dateFrom, dateTo),
            this.loadEcosystemHealth(station, dateFrom, dateTo),
        ]);
    }

    _confidenceBadge(pct) {
        if (pct >= 70) return { label: 'High confidence', cls: 'background:#fee2e2;color:#991b1b;' };
        if (pct >= 40) return { label: 'Moderate confidence', cls: 'background:#ffedd5;color:#9a3412;' };
        return { label: 'Low confidence', cls: 'background:#f1f5f9;color:#475569;' };
    }

    _diagReqSeq = 0;

    async loadDiagnostics(station, dateFrom, dateTo) {
        const myReq = ++this._diagReqSeq;
        const panel = document.getElementById('diag-findings-panel');
        if (!panel) return;
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/diagnostics?${params}`);
            const data = await res.json();
            if (myReq !== this._diagReqSeq) return;
            this.renderDiagnosticFindings(data.findings || []);
        } catch (e) {
            console.error('Diagnostics error', e);
            panel.innerHTML = '<p class="text-rose-500 text-xs text-center py-6">Failed to load diagnostic findings.</p>';
        }
    }

    renderDiagnosticFindings(findings) {
        const panel = document.getElementById('diag-findings-panel');
        if (!panel) return;
        if (!findings.length) {
            panel.innerHTML = '<p class="text-gray-400 text-xs text-center py-6">No contamination-source findings for this station/date range — either no evaluable signals were present, or nothing crossed the 15% confidence floor.</p>';
            return;
        }
        panel.innerHTML = findings.map(f => {
            const badge = this._confidenceBadge(f.confidence_pct);
            const signalsHtml = (f.matched_signals || []).map(s => `
                <div class="flex justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                    <span class="text-gray-600">${this._esc(s.signal)}</span>
                    <span class="text-gray-400 text-right" style="max-width:60%;">${this._esc(s.detail || '')}</span>
                </div>`).join('');
            const modifiersHtml = (f.contextual_modifiers || []).length ? `
                <div class="mt-2 pt-2 border-t border-gray-50 text-xs text-cyan-700">
                    <i class="fas fa-map-marker-alt mr-1"></i>
                    ${(f.contextual_modifiers || []).map(m => this._esc(m.detail || '')).join(' ')}
                </div>` : '';
            return `
                <div class="p-3 rounded-xl mb-3 last:mb-0" style="background:#f8fafc;border:1px solid #f1f5f9;">
                    <div class="flex items-center justify-between mb-1">
                        <div class="text-sm font-bold text-gray-800">${this._esc(f.source_label)}</div>
                        <span class="px-2 py-0.5 rounded-full text-xs font-bold" style="${badge.cls}">${f.confidence_pct}% · ${badge.label}</span>
                    </div>
                    <div class="text-xs text-gray-400 mb-2">${this._esc(f.station)} · ${f.date}</div>
                    <div class="text-xs text-gray-600 mb-2">${this._esc(f.explanation_text || '')}</div>
                    <details class="text-xs">
                        <summary class="text-gray-400 cursor-pointer select-none">Matched signals (${(f.matched_signals || []).length})</summary>
                        <div class="mt-1">${signalsHtml}</div>
                    </details>
                    ${modifiersHtml}
                </div>`;
        }).join('');
    }

    _muReqSeq = 0;

    async loadMultiUseCompliance(station, dateFrom, dateTo) {
        const myReq = ++this._muReqSeq;
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/multi-use-compliance?${params}`);
            const data = await res.json();
            if (myReq !== this._muReqSeq) return;
            if (!data.success) return;
            this.renderIrrigationPanel(data.irrigation || []);
            this.renderLivestockPanel(data.livestock || []);
            this.renderAquaculturePanel(data.aquaculture || []);
        } catch (e) {
            console.error('Multi-use compliance error', e);
        }
    }

    renderIrrigationPanel(rows) {
        const panel = document.getElementById('fitness-irrigation-panel');
        if (!panel) return;
        if (!rows.length) {
            panel.innerHTML = '<p class="text-gray-400 text-xs py-4">No readings available.</p>';
            return;
        }
        const latest = rows[rows.length - 1];
        const restrictionCls = latest.overall_restriction_class === 'severe' ? 'text-rose-600'
                              : latest.overall_restriction_class === 'slight_moderate' ? 'text-amber-600'
                              : 'text-teal-600';
        panel.innerHTML = `
            <div class="text-xs text-gray-400 mb-2">${this._esc(latest.station || '')} · ${latest.date}</div>
            <div class="p-2 rounded-lg mb-2" style="background:#f8fafc;">
                <div class="flex justify-between text-xs mb-0.5"><span class="text-gray-500">SAR</span><span class="font-bold text-gray-700">${latest.sar_result.sar ?? '—'}</span></div>
                <div class="text-xs text-gray-400">${this._esc(latest.sar_class.effect_description)}</div>
            </div>
            <div class="p-2 rounded-lg" style="background:#f8fafc;">
                <div class="flex justify-between text-xs mb-0.5"><span class="text-gray-500">EC band</span><span class="font-bold text-gray-700">${this._esc(latest.ec_class.band || '—')}</span></div>
                <div class="text-xs text-gray-400">${this._esc(latest.ec_class.management_note)}</div>
            </div>
            <div class="mt-2 text-xs font-bold ${restrictionCls}">Overall: ${latest.overall_restriction_class.replace('_', '/')}</div>
        `;
    }

    renderLivestockPanel(rows) {
        const panel = document.getElementById('fitness-livestock-panel');
        if (!panel) return;
        if (!rows.length) {
            panel.innerHTML = '<p class="text-gray-400 text-xs py-4">No readings available.</p>';
            return;
        }
        const latest = rows[rows.length - 1];
        const species = Object.entries(latest.by_species || {});
        if (!species.length) {
            panel.innerHTML = `<div class="text-xs text-gray-400 mb-2">${this._esc(latest.station || '')} · ${latest.date}</div><p class="text-gray-400 text-xs py-2">No TDS reading available for this date.</p>`;
            return;
        }
        const sevColor = r => r === 0 ? '#0d9488' : r === 1 ? '#84cc16' : r === 2 ? '#f59e0b' : r === 3 ? '#f97316' : '#dc2626';
        panel.innerHTML = `
            <div class="text-xs text-gray-400 mb-2">${this._esc(latest.station || '')} · ${latest.date}</div>
            ${species.map(([sp, v]) => `
                <div class="flex items-center justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                    <span class="text-gray-600">${this._esc(sp)}</span>
                    <span class="w-3 h-3 rounded-full inline-block" style="background:${sevColor(v.severity_rating)};" title="${this._esc(v.band_label)}"></span>
                </div>`).join('')}
            <div class="mt-2 text-xs text-gray-500">Most restrictive: <span class="font-bold">${this._esc(latest.most_restrictive_species || '—')}</span></div>
        `;
    }

    renderAquaculturePanel(rows) {
        const panel = document.getElementById('fitness-aquaculture-panel');
        if (!panel) return;
        if (!rows.length) {
            panel.innerHTML = '<p class="text-gray-400 text-xs py-4">No readings available.</p>';
            return;
        }
        const latest = rows[rows.length - 1];
        const flagCls = latest.overall_flag === 'suitable' ? 'text-teal-600'
                       : latest.overall_flag === 'caution' ? 'text-amber-600' : 'text-rose-600';
        const violations = (latest.per_indicator || []).filter(p => p.status !== 'within');
        panel.innerHTML = `
            <div class="text-xs text-gray-400 mb-2">${this._esc(latest.station || '')} · ${latest.date} · hardness: ${this._esc(latest.hardness_class)}</div>
            <div class="text-xs font-bold ${flagCls} mb-2">Overall: ${latest.overall_flag}</div>
            ${violations.length ? violations.map(p => `
                <div class="flex justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                    <span class="text-gray-600">${this._esc(p.indicator_code)}</span>
                    <span class="text-rose-500 font-semibold">${p.measured_val} ${this._esc(p.unit || '')} (${p.status})</span>
                </div>`).join('') : '<p class="text-gray-400 text-xs py-1">No DWAF Vol 6 threshold exceedances.</p>'}
        `;
    }

    _ecoReqSeq = 0;

    async loadEcosystemHealth(station, dateFrom, dateTo) {
        const myReq = ++this._ecoReqSeq;
        const params = new URLSearchParams();
        if (station)  params.set('station_id', station);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo)   params.set('date_to', dateTo);
        try {
            const res  = await this._fetch(`/api/wq/analytics/ecosystem-health?${params}`);
            const data = await res.json();
            if (myReq !== this._ecoReqSeq) return;
            if (!data.success) return;
            this.renderEcosystemHealthGauge(data.ecosystem_health);
        } catch (e) {
            console.error('Ecosystem health error', e);
        }
    }

    renderEcosystemHealthGauge(eco) {
        if (!eco || eco.overall_score === null) {
            this._setText('eco-grade', 'Insufficient data');
            this._setText('eco-sub', 'Need TWQR-assessed measurements');
            this._setText('eco-score-txt', '—');
            return;
        }
        const ring = document.getElementById('eco-ring-fill');
        if (ring) {
            const circumference = 239;
            ring.setAttribute('stroke-dashoffset', String(Math.round(circumference - circumference * eco.overall_score / 100)));
            ring.setAttribute('stroke', eco.achieves_target ? '#0891b2' : eco.overall_score >= 50 ? '#f59e0b' : '#dc2626');
        }
        this._setText('eco-score-txt', eco.overall_score);
        this._setText('eco-grade', eco.grade);
        this._setText('eco-sub', `${eco.n_variables} variable(s) assessed`);
        const breakEl = document.getElementById('eco-breakdown');
        if (breakEl && eco.breakdown) {
            breakEl.innerHTML = eco.breakdown.map(b => `
                <div class="flex justify-between items-center py-0.5">
                    <span class="text-gray-500">${this._esc(b.indicator_name || b.indicator_code)} <span class="text-gray-300">(${b.measured_val})</span></span>
                    <span class="font-semibold ${b.score >= 90 ? 'text-teal-600' : b.score >= 50 ? 'text-amber-600' : 'text-rose-500'}">
                        ${b.score}%
                    </span>
                </div>`).join('');
        }
    }

    // ── Utilities ─────────────────────────────────────────────────────────────

    _setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
}

// ── Entry point ───────────────────────────────────────────────────────────────
const WQ = new WaterQualityApp();

document.addEventListener('DOMContentLoaded', () => {
    // Wait for HydroAuth to finish its refresh cycle before making any API calls.
    // Running WQ.init() on DOMContentLoaded races with HydroAuth.init() — both
    // call _doRefresh() concurrently, the second one gets 401 on the rotated token.
    document.addEventListener('hydroAuthReady', ({ detail }) => {
        const role = detail && detail.user ? detail.user.role : '';
        document.querySelectorAll('[data-show-for-role="admin"]').forEach(el => {
            if (role === 'admin') el.style.display = '';
        });
        WQ.init().catch(console.error);
    }, { once: true });
});
