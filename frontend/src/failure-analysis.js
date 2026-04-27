// Failure Analysis Dashboard - failure-analysis.js
class FailureAnalysisDashboard {
    constructor() {
        const _backend = (window.location.port === '5000' || window.location.port === '') ? '' : 'http://localhost:5000';
        this.apiBase = `${_backend}/api`;
        this.allData = [];
        this.filteredData = [];
        this.currentPage = 1;
        this.rowsPerPage = 15;
        this.charts = {};
        this.isFiltered = false;
        this._dsSources = [];
        this._dsPage    = 1;
        this._dsPageSize = 15;
        
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadCatchments();
        await this.loadAllFailures();
        this.showToast('Failure Analysis Dashboard ready', 'success');
    }
    
    setupEventListeners() {
        const addListener = (id, event, handler) => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener(event, handler);
            } else {
                console.warn(`Element with id '${id}' not found`);
            }
        };
        
        addListener('viewAllBtn', 'click', () => this.loadAllFailures());
        addListener('toggleFiltersBtn', 'click', () => this.toggleFilters());
        addListener('applyFiltersBtn', 'click', () => this.applyFilters());
        addListener('clearFiltersBtn', 'click', () => this.clearFilters());
        addListener('refreshBtn', 'click', () => this.refresh());
        addListener('exportExcelBtn', 'click', () => this.exportExcel());
        addListener('exportPdfBtn', 'click', () => this.exportPDF());
        addListener('printBtn', 'click', () => window.print());
        addListener('searchInput', 'input', (e) => this.searchData(e.target.value));
        addListener('rowsPerPage', 'change', (e) => this.changeRowsPerPage(e.target.value));
        
        // Toggle upload form
        const toggleUploadBtn = document.getElementById('toggleUploadBtn');
        if (toggleUploadBtn) {
            toggleUploadBtn.addEventListener('click', () => {
                const uploadForm = document.getElementById('uploadFormSection');
                const icon = toggleUploadBtn.querySelector('i');
                if (uploadForm.classList.contains('hidden')) {
                    uploadForm.classList.remove('hidden');
                    icon.classList.remove('fa-chevron-down');
                    icon.classList.add('fa-chevron-up');
                    toggleUploadBtn.innerHTML = '<i class="fas fa-chevron-up mr-1"></i>Hide Upload Form';
                } else {
                    uploadForm.classList.add('hidden');
                    icon.classList.remove('fa-chevron-up');
                    icon.classList.add('fa-chevron-down');
                    toggleUploadBtn.innerHTML = '<i class="fas fa-chevron-down mr-1"></i>Show Upload Form';
                }
            });
        }
        
        // Upload functionality
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        
        if (!dropZone || !fileInput) {
            console.warn('Upload elements not found');
            return;
        }
        
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => {
            if (e.target.files[0]) this.handleFileUpload(e.target.files[0]);
        });
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('border-blue-400', 'bg-blue-50');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('border-blue-400', 'bg-blue-50');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('border-blue-400', 'bg-blue-50');
            if (e.dataTransfer.files[0]) this.handleFileUpload(e.dataTransfer.files[0]);
        });
    }
    
async handleFileUpload(file) {
    const category = document.getElementById('categorySelect').value;
    const subcatchment = document.getElementById('subcatchmentSelect').value;
    
    if (!category || !subcatchment) {
        this.showToast('Please select both category and subcatchment', 'error');
        return;
    }
    
    if (!file.name.match(/\.(xlsx|xls)$/)) {
        this.showToast('Please select an Excel file (.xlsx or .xls)', 'error');
        return;
    }
    
    if (file.size > 16 * 1024 * 1024) {
        this.showToast('File size must be less than 16MB', 'error');
        return;
    }
    
    this.showLoading('Uploading and processing file...');
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);
        formData.append('subcatchment', subcatchment);
        
        const response = await fetch(`${this.apiBase}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Upload failed');
        }
        
        // Log the full result for debugging
        console.log('Upload result:', result);
        
        this.showToast(`File uploaded! ${result.processed_records || 0} records processed`, 'success');
        
        // Reload data sources and failure analysis
        await this.loadDataSources();
        await this.loadAllFailures();
        
        // Clear file input
        document.getElementById('fileInput').value = '';
        
    } catch (error) {
        console.error('Upload failed:', error);
        this.showToast(`Upload failed: ${error.message}`, 'error');
    } finally {
        this.hideLoading();
    }
}

async loadDataSources() {
    try {
        const response = await fetch(`${this.apiBase}/sources`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Here are the data sources loaded:', data);

        this._dsSources = data.sources || [];
        this._dsPage    = 1;   // reset to first page on fresh load
        this._renderDataSourcesPage();

    } catch (error) {
        console.error('Failed to load data sources:', error);
        const container = document.getElementById('dataSourcesTable');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-8 text-red-500">
                    <i class="fas fa-exclamation-triangle text-4xl mb-4"></i>
                    <p class="font-semibold">Failed to load data sources</p>
                    <p class="text-sm mt-2">${error.message}</p>
                    <button onclick="app.loadDataSources()" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Retry
                    </button>
                </div>
            `;
        }
    }
}

_renderDataSourcesPage() {
    const container = document.getElementById('dataSourcesTable');
    if (!container) return;

    const sources   = this._dsSources;
    const pageSize  = this._dsPageSize;
    const page      = this._dsPage;
    const total     = sources.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    // Clamp page
    if (page < 1)           this._dsPage = 1;
    if (page > totalPages)  this._dsPage = totalPages;

    const start   = (this._dsPage - 1) * pageSize;
    const slice   = sources.slice(start, start + pageSize);

    if (total === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fas fa-database text-4xl mb-4"></i>
                <p>No data sources found</p>
                <p class="text-sm mt-2">Upload an Excel file to get started</p>
            </div>`;
        return;
    }

    const rows = slice.map(source => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-3 font-medium">${source.filename || 'Unknown'}</td>
            <td class="px-4 py-3">
                <span class="px-2 py-1 text-xs rounded ${
                    source.category === 'BASEFLOW' ? 'bg-blue-100 text-blue-800' :
                    source.category === 'RECHARGE' ? 'bg-green-100 text-green-800' :
                    source.category === 'GWLEVEL'  ? 'bg-purple-100 text-purple-800' :
                    'bg-gray-100 text-gray-800'
                }">
                    ${source.category || 'N/A'}
                </span>
            </td>
            <td class="px-4 py-3">${source.subcatchment_name || 'N/A'}</td>
            <td class="px-4 py-3">${source.upload_date ? new Date(source.upload_date).toLocaleDateString() : 'N/A'}</td>
            <td class="px-4 py-3 text-center">
                <span class="font-semibold">${(source.total_records || 0).toLocaleString()}</span>
            </td>
            <td class="px-4 py-3">
                <span class="px-2 py-1 text-xs rounded font-semibold ${
                    source.processing_status === 'Completed' ? 'bg-green-100 text-green-800' :
                    source.processing_status === 'Failed'    ? 'bg-red-100 text-red-800' :
                    source.processing_status === 'Pending'   ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-800'
                }">
                    ${source.processing_status || 'Unknown'}
                </span>
                ${source.error_message ? `
                    <div class="text-xs text-red-600 mt-1" title="${source.error_message}">
                        <i class="fas fa-exclamation-circle"></i> Error
                    </div>` : ''}
            </td>
            <td class="px-4 py-3 text-center">
                <div class="flex items-center justify-center gap-2">
                    <button
                        onclick="app.openPreviewModal(${source.source_id}, '${(source.filename||'').replace(/'/g,"\\'")}', '${source.category||''}', '${(source.subcatchment_name||'').replace(/'/g,"\\'")}' )"
                        class="text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-3 py-1 rounded transition-all"
                        title="Preview & edit records">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button
                        onclick="app.deleteSource(${source.source_id})"
                        class="text-red-600 hover:text-red-800 hover:bg-red-50 px-3 py-1 rounded transition-all"
                        title="Delete this data source">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>`).join('');

    // Build pagination buttons
    const prevDisabled = this._dsPage <= 1;
    const nextDisabled = this._dsPage >= totalPages;

    const pageButtons = Array.from({ length: totalPages }, (_, i) => {
        const p = i + 1;
        const active = p === this._dsPage;
        return `<button onclick="app._dsSources && (app._dsPage=${p}, app._renderDataSourcesPage())"
                        class="px-3 py-1 text-sm rounded border ${active
                            ? 'bg-blue-600 text-white border-blue-600 font-semibold'
                            : 'border-gray-300 text-gray-600 hover:bg-gray-50'}">
                    ${p}
                </button>`;
    }).join('');

    container.innerHTML = `
        <table class="w-full text-sm">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-4 py-3 text-left font-semibold">File Name</th>
                    <th class="px-4 py-3 text-left font-semibold">Category</th>
                    <th class="px-4 py-3 text-left font-semibold">Subcatchment</th>
                    <th class="px-4 py-3 text-left font-semibold">Upload Date</th>
                    <th class="px-4 py-3 text-left font-semibold">Records</th>
                    <th class="px-4 py-3 text-left font-semibold">Status</th>
                    <th class="px-4 py-3 text-center font-semibold">Actions</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">${rows}</tbody>
        </table>
        <div class="flex items-center justify-between px-4 py-3 border-t bg-gray-50 text-sm text-gray-600">
            <span>Showing ${start + 1}–${Math.min(start + pageSize, total)} of ${total} source(s)</span>
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

  printReport() {
    const originalRowsPerPage = this.rowsPerPage;
    this.rowsPerPage = 1000; // Show more data
    this.renderTable();
    
    setTimeout(() => {
        window.print();
        setTimeout(() => {
            this.rowsPerPage = originalRowsPerPage;
            this.renderTable();
        }, 100);
    }, 500);
    }
    
async deleteSource(sourceId) {
    if (!confirm('Are you sure you want to delete this data source? This will also delete all associated raw and processed data.')) {
        return;
    }
    
    this.showLoading('Deleting source...');
    
    try {
        const response = await fetch(`${this.apiBase}/sources/${sourceId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        
        if (!data.success) {
            throw new Error(data.error || 'Delete failed');
        }
        
        this.showToast('Data source deleted successfully', 'success');
        
        // Reload data sources table
        await this.loadDataSources();
        
        // Optionally reload other data
        if (typeof this.loadAllFailures === 'function') {
            await this.loadAllFailures();
        }
        
    } catch (error) {
        console.error('Delete error:', error);
        this.showToast(`Failed to delete source: ${error.message}`, 'error');
    } finally {
        this.hideLoading();
    }
}


async uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const categorySelect = document.getElementById('categorySelect');
    const subcatchmentSelect = document.getElementById('subcatchmentSelect');
    
    if (!fileInput.files || fileInput.files.length === 0) {
        this.showToast('Please select a file', 'error');
        return;
    }
    
    const category = categorySelect.value;
    const subcatchment = subcatchmentSelect.value;
    
    if (!category) {
        this.showToast('Please select a category', 'error');
        return;
    }
    
    if (!subcatchment) {
        this.showToast('Please select a subcatchment', 'error');
        return;
    }
    
    const file = fileInput.files[0];
    
    // Validate file type
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
        this.showToast('Please select an Excel file (.xlsx or .xls)', 'error');
        return;
    }
    
    this.showLoading(`Uploading ${file.name}...`);
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);
        formData.append('subcatchment', subcatchment);
        
        const response = await fetch(`${this.apiBase}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        
        if (!data.success) {
            throw new Error(data.error || 'Upload failed');
        }
        
        this.showToast(`File uploaded successfully! Processed ${data.records_processed || 0} records.`, 'success');
        
        // Reset form
        fileInput.value = '';
        categorySelect.value = '';
        subcatchmentSelect.value = '';
        
        // Reload data sources
        await this.loadDataSources();
        
        // Optionally reload other data
        if (typeof this.loadAllFailures === 'function') {
            await this.loadAllFailures();
        }
        
    } catch (error) {
        console.error('Upload error:', error);
        this.showToast(`Upload failed: ${error.message}`, 'error');
    } finally {
        this.hideLoading();
    }
}

    
async loadCatchments() {
    try {
        const response = await fetch(`${this.apiBase}/filter-options`);
        const data = await response.json();
        
        const select = document.getElementById('catchmentFilter');
        if (data.catchments && select) {
            data.catchments.forEach(catchment => {
                const option = document.createElement('option');
                option.value = catchment;
                option.textContent = catchment;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load catchments:', error);
    }
}
    
async loadAllFailures() {
    this.showLoading('Loading comprehensive failure analysis...');
    try {
        console.log('Loading failure analysis from /api/failure-analysis...');
        const response = await fetch(`${this.apiBase}/failure-analysis`);
        const result = await response.json();
        
        console.log('Failure analysis response:', result);
        
        if (result.success) {
            // Use consistent field name: failure_analysis
            this.allData = result.failure_analysis || result.analysis || [];
            this.filteredData = this.allData;
            this.isFiltered = false;
            this.currentPage = 1;
            
            this.updateDisplay();
            this.showToast(`Loaded ${this.allData.length} failure analysis records`, 'success');
        } else {
            this.allData = [];
            this.filteredData = [];
            this.updateDisplay();
            this.showToast('No failure analysis data available', 'info');
        }
    } catch (error) {
        this.showToast('Failed to load failure analysis', 'error');
        console.error('Load error:', error);
        this.allData = [];
        this.filteredData = [];
        this.updateDisplay();
    } finally {
        this.hideLoading();
    }
}
    
async applyFilters() {
    const filters = {
        catchment: document.getElementById('catchmentFilter').value,
        category: document.getElementById('categoryFilter').value,
        start_date: document.getElementById('startDateFilter').value,
        end_date: document.getElementById('endDateFilter').value,
        severity: document.getElementById('severityFilter').value
    };
    
    const hasFilters = Object.values(filters).some(v => v !== '');
    
    if (!hasFilters) {
        this.loadAllFailures();
        return;
    }
    
    this.showLoading('Applying filters...');
    try {
        const params = new URLSearchParams();
        if (filters.catchment) params.append('catchment', filters.catchment);
        if (filters.category) params.append('category', filters.category);
        if (filters.start_date) params.append('start_date', filters.start_date);
        if (filters.end_date) params.append('end_date', filters.end_date);
        
        console.log('Applying filters with params:', params.toString());
        
        const response = await fetch(`${this.apiBase}/failure-analysis?${params}`);
        const result = await response.json();
        
        console.log('Filter response:', result);
        
        // Use consistent field name
        let filteredResults = result.failure_analysis || result.analysis || [];
        
        // Additional severity filter (client-side)
        if (filters.severity) {
            filteredResults = filteredResults.filter(record => {
                const rate = record.failure_rate || 0;
                if (filters.severity === 'Critical') return rate > 50;
                if (filters.severity === 'High') return rate > 30 && rate <= 50;
                if (filters.severity === 'Moderate') return rate > 15 && rate <= 30;
                if (filters.severity === 'Low') return rate > 0 && rate <= 15;
                if (filters.severity === 'None') return rate === 0;
                return true;
            });
        }
        
        this.filteredData = filteredResults;
        this.isFiltered = true;
        this.currentPage = 1;
        
        this.updateActiveFilters(filters);
        this.updateDisplay();
        this.showToast(`Filtered to ${this.filteredData.length} records`, 'success');
    } catch (error) {
        this.showToast('Filter application failed: ' + error.message, 'error');
        console.error('Filter error:', error);
    } finally {
        this.hideLoading();
    }
}
    
    updateActiveFilters(filters) {
        const container = document.getElementById('activeFiltersContainer');
        container.innerHTML = '';
        
        Object.entries(filters).forEach(([key, value]) => {
            if (value) {
                const chip = document.createElement('div');
                chip.className = 'filter-chip';
                chip.innerHTML = `
                    ${key}: ${value}
                    <i class="fas fa-times ml-2 cursor-pointer" onclick="app.removeFilter('${key}')"></i>
                `;
                container.appendChild(chip);
            }
        });
    }
    
    removeFilter(filterKey) {
        const filterMap = {
            'catchment': 'catchmentFilter',
            'category': 'categoryFilter',
            'start_date': 'startDateFilter',
            'end_date': 'endDateFilter',
            'severity': 'severityFilter'
        };
        
        const elementId = filterMap[filterKey];
        if (elementId) {
            document.getElementById(elementId).value = '';
            this.applyFilters();
        }
    }
    
    clearFilters() {
        document.getElementById('catchmentFilter').value = '';
        document.getElementById('categoryFilter').value = '';
        document.getElementById('startDateFilter').value = '';
        document.getElementById('endDateFilter').value = '';
        document.getElementById('severityFilter').value = '';
        document.getElementById('activeFiltersContainer').innerHTML = '';
        this.loadAllFailures();
    }
    
toggleFilters() {
    console.log('Toggle filters clicked');
    const panel = document.getElementById('filtersPanel');
    if (!panel) {
        console.warn('Filter panel not found - check HTML has #filtersPanel element');
        return;
    }
    
    console.log('Current hidden status:', panel.classList.contains('hidden'));
    
    // Toggle the hidden class
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        panel.style.display = 'block';
    } else {
        panel.classList.add('hidden');
        panel.style.display = 'none';
    }
    
    console.log('After toggle hidden status:', panel.classList.contains('hidden'));
}
    
    updateDisplay() {
        this.updateSummaryCards();
        this.updateSummaryStatistics();
        this.renderTable();
    }
    
    updateSummaryCards() {
        const data = this.filteredData;
        
        document.getElementById('totalPeriods').textContent = data.length;
        
        const baseflowRecords = data
            .filter(record => record.category === 'BASEFLOW')
            .reduce((sum, record) => sum + (record.total_records || 0), 0);
        document.getElementById('totalBaseflow').textContent = baseflowRecords.toLocaleString();
        
        const rechargeRecords = data
            .filter(record => record.category === 'RECHARGE')
            .reduce((sum, record) => sum + (record.total_records || 0), 0);
        document.getElementById('totalRecharge').textContent = rechargeRecords.toLocaleString();
        
        const gwlevelRecords = data
            .filter(record => record.category === 'GWLEVEL')
            .reduce((sum, record) => sum + (record.total_records || 0), 0);
        document.getElementById('totalGWLevel').textContent = gwlevelRecords.toLocaleString();
    }
    
updateSummaryStatistics() {
    const data = this.filteredData;
    
    if (data.length === 0) {
        document.getElementById('summaryTotalRecords').textContent = '0';
        document.getElementById('summaryTotalFailures').textContent = '0';
        document.getElementById('summaryOverallRate').textContent = '0%';
        document.getElementById('summaryPeriods').textContent = '0';
        document.getElementById('baseflowRate').textContent = '0%';
        document.getElementById('baseflowRecords').textContent = '0/0 records';
        document.getElementById('gwlevelRate').textContent = '0%';
        document.getElementById('gwlevelRecords').textContent = '0/0 records';
        document.getElementById('rechargeRate').textContent = '0%';
        document.getElementById('rechargeRecords').textContent = '0/0 records';
        return;
    }
    
    // Calculate totals from API response
    const totalRecords = data.reduce((sum, r) => sum + (r.total || r.total_records || 0), 0);
    const totalFailures = data.reduce((sum, r) => sum + (r.failures || r.total_failures || 0), 0);
    const overallRate = totalRecords > 0 ? ((totalFailures / totalRecords) * 100).toFixed(1) : '0.0';
    
    console.log('Stats - Total:', totalRecords, 'Failures:', totalFailures, 'Rate:', overallRate);
    
    document.getElementById('summaryTotalRecords').textContent = totalRecords.toLocaleString();
    document.getElementById('summaryTotalFailures').textContent = totalFailures.toLocaleString();
    document.getElementById('summaryOverallRate').textContent = overallRate + '%';
    document.getElementById('summaryPeriods').textContent = data.length;
    
    // By category - handle both parameter and category field names
    const baseflowData = data.filter(r => (r.parameter || r.category || '').toUpperCase() === 'BASEFLOW');
    const baseflowTotal = baseflowData.reduce((sum, r) => sum + (r.total || r.total_records || 0), 0);
    const baseflowFail = baseflowData.reduce((sum, r) => sum + (r.failures || r.total_failures || 0), 0);
    const baseflowRate = baseflowTotal > 0 ? ((baseflowFail / baseflowTotal) * 100).toFixed(1) : '0.0';
    document.getElementById('baseflowRate').textContent = baseflowRate + '%';
    document.getElementById('baseflowRecords').textContent = `${baseflowFail.toLocaleString()}/${baseflowTotal.toLocaleString()} records`;
    
    const gwlevelData = data.filter(r => (r.parameter || r.category || '').toUpperCase() === 'GWLEVEL');
    const gwlevelTotal = gwlevelData.reduce((sum, r) => sum + (r.total || r.total_records || 0), 0);
    const gwlevelFail = gwlevelData.reduce((sum, r) => sum + (r.failures || r.total_failures || 0), 0);
    const gwlevelRate = gwlevelTotal > 0 ? ((gwlevelFail / gwlevelTotal) * 100).toFixed(1) : '0.0';
    document.getElementById('gwlevelRate').textContent = gwlevelRate + '%';
    document.getElementById('gwlevelRecords').textContent = `${gwlevelFail.toLocaleString()}/${gwlevelTotal.toLocaleString()} records`;
    
    const rechargeData = data.filter(r => (r.parameter || r.category || '').toUpperCase() === 'RECHARGE');
    const rechargeTotal = rechargeData.reduce((sum, r) => sum + (r.total || r.total_records || 0), 0);
    const rechargeFail = rechargeData.reduce((sum, r) => sum + (r.failures || r.total_failures || 0), 0);
    const rechargeRate = rechargeTotal > 0 ? ((rechargeFail / rechargeTotal) * 100).toFixed(1) : '0.0';
    document.getElementById('rechargeRate').textContent = rechargeRate + '%';
    document.getElementById('rechargeRecords').textContent = `${rechargeFail.toLocaleString()}/${rechargeTotal.toLocaleString()} records`;
}
    
    renderTable() {
        const container = document.getElementById('tableContainer');
        const data = this.filteredData;
        
        if (data.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12 text-gray-500">
                    <i class="fas fa-inbox text-4xl mb-4"></i>
                    <p>No failure analysis records found</p>
                    <p class="text-sm mt-2">Click "Load All Failures" to retrieve data</p>
                </div>
            `;
            return;
        }
        
        const startIndex = (this.currentPage - 1) * this.rowsPerPage;
        const endIndex = startIndex + parseInt(this.rowsPerPage);
        const pageData = data.slice(startIndex, endIndex);
        
        const table = `
            <table class="w-full text-sm">
                <thead class="bg-gray-50 sticky top-0">
                    <tr>
                        <th class="px-4 py-3 text-left font-semibold">Catchment</th>
                        <th class="px-4 py-3 text-left font-semibold">Parameter</th>
                        <th class="px-4 py-3 text-right font-semibold">Total Records</th>
                        <th class="px-4 py-3 text-right font-semibold">Failures</th>
                        <th class="px-4 py-3 text-right font-semibold">Failure Rate</th>
                        <th class="px-4 py-3 text-right font-semibold">Avg Severity</th>
                        <th class="px-4 py-3 text-left font-semibold">Classification</th>
                        <th class="px-4 py-3 text-center font-semibold">Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">
                    ${pageData.map(row => this.renderTableRow(row)).join('')}
                </tbody>
            </table>
        `;
        
        container.innerHTML = table;
        this.renderPagination();
    }
    
renderTableRow(row) {
    const failureRate = (row.failure_rate || 0);
    const avgSeverity = row.avg_severity || 0;

    return `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-3">${row.catchment || 'N/A'}</td>
            <td class="px-4 py-3">
                <span class="px-2 py-1 text-xs rounded ${this.getCategoryBadgeClass((row.parameter || row.category || '').toUpperCase())}">
                    ${row.parameter || row.category || 'N/A'}
                </span>
            </td>
            <td class="px-4 py-3 text-right">${(row.total || row.total_records || 0).toLocaleString()}</td>
            <td class="px-4 py-3 text-right font-medium">${(row.failures || row.total_failures || 0).toLocaleString()}</td>
            <td class="px-4 py-3 text-right">
                <span class="px-2 py-1 text-xs rounded ${this.getFailureRateClass(failureRate)}">
                    ${failureRate.toFixed(1)}%
                </span>
            </td>
            <td class="px-4 py-3 text-right">
                <span class="px-2 py-1 text-xs rounded ${this.getSeverityClass(avgSeverity)}">
                    ${avgSeverity.toFixed(2)}
                </span>
            </td>
            <td class="px-4 py-3">
                <span class="px-2 py-1 text-xs rounded ${this.getSeverityClass(failureRate)}">
                    ${failureRate > 50 ? 'Critical' : failureRate > 30 ? 'High' : failureRate > 15 ? 'Moderate' : failureRate > 0 ? 'Low' : 'None'}
                </span>
            </td>
            <td class="px-4 py-3 text-center">
                ${row.failures > 0 || failureRate > 0 ?
                    '<span class="text-red-600"><i class="fas fa-exclamation-circle"></i></span>' :
                    '<span class="text-green-600"><i class="fas fa-check-circle"></i></span>'}
            </td>
        </tr>
    `;
}

// Add helper method for severity class
getSeverityClass(failureRate) {
    if (failureRate > 50) return 'bg-red-100 text-red-800';
    if (failureRate > 30) return 'bg-orange-100 text-orange-800';
    if (failureRate > 15) return 'bg-yellow-100 text-yellow-800';
    if (failureRate > 0) return 'bg-blue-100 text-blue-800';
    return 'bg-green-100 text-green-800';
}
    
    getClassificationColor(classification) {
        const colors = {
            'Critical': 'bg-red-100 text-red-800',
            'High': 'bg-orange-100 text-orange-800',
            'Moderate': 'bg-yellow-100 text-yellow-800',
            'Low': 'bg-blue-100 text-blue-800',
            'None': 'bg-green-100 text-green-800'
        };
        return colors[classification] || 'bg-gray-100 text-gray-800';
    }
    
    getFailureRateClass(rate) {
        if (rate > 50) return 'bg-red-100 text-red-800';
        if (rate > 30) return 'bg-orange-100 text-orange-800';
        if (rate > 15) return 'bg-yellow-100 text-yellow-800';
        if (rate > 0) return 'bg-blue-100 text-blue-800';
        return 'bg-green-100 text-green-800';
    }
    
    
    getCategoryBadgeClass(category) {
        const classes = {
            'BASEFLOW': 'bg-blue-100 text-blue-800',
            'RECHARGE': 'bg-green-100 text-green-800',
            'GWLEVEL': 'bg-purple-100 text-purple-800'
        };
        return classes[category] || 'bg-gray-100 text-gray-800';
    }
    
    getSeverityColor(severity) {
        const colors = {
            'Critical': '#ef4444',
            'High': '#f97316',
            'Moderate': '#eab308',
            'Low': '#3b82f6',
            'None': '#22c55e'
        };
        return colors[severity] || '#6b7280';
    }
    
    getFailureRateColor(rate) {
        if (rate > 50) return '#ef4444';
        if (rate > 30) return '#f97316';
        if (rate > 15) return '#eab308';
        if (rate > 0) return '#3b82f6';
        return '#22c55e';
    }
    
    renderPagination() {
        const container = document.getElementById('paginationContainer');
        const totalPages = Math.ceil(this.filteredData.length / this.rowsPerPage);
        
        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }
        
        const start = (this.currentPage - 1) * this.rowsPerPage + 1;
        const end = Math.min(this.currentPage * this.rowsPerPage, this.filteredData.length);
        
        container.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="text-sm text-gray-600">
                    Showing ${start}-${end} of ${this.filteredData.length} records
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="app.goToPage(${this.currentPage - 1})" 
                            ${this.currentPage === 1 ? 'disabled' : ''}
                            class="px-4 py-2 border rounded ${this.currentPage === 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                        <i class="fas fa-chevron-left mr-1"></i> Previous
                    </button>
                    <span class="text-sm px-3">Page ${this.currentPage} of ${totalPages}</span>
                    <button onclick="app.goToPage(${this.currentPage + 1})" 
                            ${this.currentPage === totalPages ? 'disabled' : ''}
                            class="px-4 py-2 border rounded ${this.currentPage === totalPages ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                        Next <i class="fas fa-chevron-right ml-1"></i>
                    </button>
                </div>
            </div>
        `;
    }
    
    goToPage(page) {
        const totalPages = Math.ceil(this.filteredData.length / this.rowsPerPage);
        if (page >= 1 && page <= totalPages) {
            this.currentPage = page;
            this.renderTable();
        }
    }
    
    changeRowsPerPage(value) {
        this.rowsPerPage = parseInt(value);
        this.currentPage = 1;
        this.renderTable();
    }
    
    searchData(query) {
        if (!query.trim()) {
            this.filteredData = this.allData;
        } else {
            const searchLower = query.toLowerCase();
            this.filteredData = this.allData.filter(row => {
                return Object.values(row).some(val => 
                    String(val).toLowerCase().includes(searchLower)
                );
            });
        }
        this.currentPage = 1;
        this.updateDisplay();
    }
    
    async refresh() {
        await this.loadAllFailures();
        this.showToast('Data refreshed', 'success');
    }
    
    async exportExcel() {
        this.showLoading('Preparing Excel export...');
        
        try {
            const filters = this.getActiveFilters();
            const params = new URLSearchParams(filters);
            
            const response = await fetch(`${this.apiBase}/export-enhanced?${params}`);
            if (!response.ok) throw new Error('Export failed');
            
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `failure_analysis_${new Date().toISOString().split('T')[0]}.xlsx`;
            a.click();
            URL.revokeObjectURL(url);
            
            this.showToast('Excel file downloaded', 'success');
        } catch (error) {
            this.showToast('Excel export failed', 'error');
            console.error('Excel error:', error);
        } finally {
            this.hideLoading();
        }
    }

    // PDF EXPORT FEATURE
    async exportPDF() {
        this.showToast('PDF export feature coming soon', 'info');
    }
    
    getActiveFilters() {
        return {
            catchment: document.getElementById('catchmentFilter').value,
            category: document.getElementById('categoryFilter').value,
            start_date: document.getElementById('startDateFilter').value,
            end_date: document.getElementById('endDateFilter').value
        };
    }
    
showLoading(message = 'Loading...') {
    const overlay = document.getElementById('loadingOverlay');
    const text = document.getElementById('loadingText');
    if (overlay && text) {
        text.textContent = message;
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    }
}
    
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('hidden');
            overlay.classList.remove('flex');
        }
    }

showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `px-6 py-4 rounded-lg shadow-lg text-white animate-slide-down ${
        type === 'success' ? 'bg-green-600' :
        type === 'error' ? 'bg-red-600' :
        type === 'warning' ? 'bg-yellow-600' :
        'bg-blue-600'
    }`;
    
    toast.innerHTML = `
        <div class="flex items-center">
            <i class="fas fa-${
                type === 'success' ? 'check-circle' :
                type === 'error' ? 'exclamation-circle' :
                type === 'warning' ? 'exclamation-triangle' :
                'info-circle'
            } mr-3"></i>
            <span>${message}</span>
        </div>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

    // ── PREVIEW MODAL ────────────────────────────────────────────────────────

    async openPreviewModal(sourceId, fileName, category, catchment) {
        ensurePreviewModalExists();

        this._previewSourceId = sourceId;
        this._previewChanges  = new Map();   // processed_id → {measurement_date, original_value}
        this._previewSelected = new Set();   // selected processed_ids for deletion

        // Header info
        document.getElementById('previewTitle').textContent   = fileName || `Source #${sourceId}`;
        document.getElementById('previewSubtitle').textContent =
            `${catchment || '—'} · ${(category || '').toUpperCase()} · Source ID: ${sourceId}`;
        document.getElementById('previewRecordCount').textContent = '';
        document.getElementById('previewChangeBadge').classList.add('hidden');
        document.getElementById('previewSaveBtn').disabled = true;

        // Show modal
        const modal = document.getElementById('previewModal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        // Fetch records
        try {
            const res    = await fetch(`${this.apiBase}/sources/${sourceId}/records`);
            const result = await res.json();

            if (!result.success) throw new Error(result.error || 'Failed to load records');

            this._previewRecords = result.records;
            this._renderPreviewTable(result.records);
            document.getElementById('previewRecordCount').textContent =
                `${result.records.length} record(s)`;
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
        // Must mirror sp_ProcessRawData thresholds exactly
        if (z >= 0.5)   return { cls: 'Surplus',          fail: 0, sev: 0 };
        if (z >= -0.5)  return { cls: 'Normal',            fail: 0, sev: 0 };
        if (z >= -1.0)  return { cls: 'Moderate_Deficit',  fail: 1, sev: 1 };
        if (z >= -1.5)  return { cls: 'Severe_Deficit',    fail: 1, sev: 2 };
        return             { cls: 'Extreme_Deficit',    fail: 1, sev: 3 };
    }

    _clsBadge(cls) {
        const map = {
            'Surplus':           'bg-blue-100 text-blue-800',
            'Normal':            'bg-green-100 text-green-800',
            'Moderate_Deficit':  'bg-yellow-100 text-yellow-800',
            'Severe_Deficit':    'bg-orange-100 text-orange-800',
            'Extreme_Deficit':   'bg-red-100 text-red-800',
        };
        return `<span class="px-2 py-0.5 text-xs rounded font-semibold ${map[cls] || 'bg-gray-100 text-gray-700'}">
                    ${(cls||'').replace(/_/g,' ')}
                </span>`;
    }

    _renderPreviewTable(records) {
        if (!records || records.length === 0) {
            document.getElementById('previewTableWrap').innerHTML =
                '<p class="text-center py-10 text-gray-400">No records found for this source.</p>';
            return;
        }

        const rows = records.map(rec => {
            const changed   = this._previewChanges.has(rec.processed_id);
            const selected  = this._previewSelected.has(rec.processed_id);
            const rowData   = changed ? this._previewChanges.get(rec.processed_id) : {};
            const isFail    = rec.is_failure === 1;
            const rowClass  = selected  ? 'bg-blue-50 ring-1 ring-inset ring-blue-300'
                            : changed   ? 'bg-yellow-50'
                            : isFail    ? 'bg-red-50'
                            : 'hover:bg-gray-50';

            const dateVal  = rowData.measurement_date ?? rec.measurement_date ?? '';
            const valVal   = rowData.original_value   !== undefined
                             ? rowData.original_value : (rec.original_value ?? '');

            // Compute preview z-score for display when row is dirty
            let dispZ   = rec.standardized_value;
            let dispCls = rec.classification;
            let dispFail = rec.is_failure;
            let dispSev  = rec.severity_level;
            if (changed && rowData.original_value !== undefined &&
                rec.mean_value !== null && rec.std_deviation) {
                const std = rec.std_deviation || 1;
                dispZ = (parseFloat(rowData.original_value) - rec.mean_value) / std;
                const c = this._classifyZ(dispZ);
                dispCls = c.cls; dispFail = c.fail; dispSev = c.sev;
            }

            return `
            <tr class="${rowClass} transition-colors" id="prev-row-${rec.processed_id}">
                <td class="px-3 py-2 text-center">
                    <input type="checkbox"
                           data-pid="${rec.processed_id}"
                           ${selected ? 'checked' : ''}
                           onchange="app._onSelectRow(${rec.processed_id}, this.checked)"
                           class="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer">
                </td>
                <td class="px-3 py-2 text-center text-xs text-gray-400">${rec.processed_id}</td>
                <td class="px-3 py-2">
                    <input type="date"
                           value="${dateVal}"
                           data-pid="${rec.processed_id}"
                           data-field="measurement_date"
                           onchange="app._onPreviewCellChange(this)"
                           class="w-full border border-transparent rounded px-1 py-0.5 text-sm focus:border-blue-400 focus:outline-none bg-transparent hover:border-gray-300">
                </td>
                <td class="px-3 py-2 text-xs text-gray-500">${rec.parameter_type || ''}</td>
                <td class="px-3 py-2">
                    <input type="number"
                           value="${valVal}"
                           step="any"
                           data-pid="${rec.processed_id}"
                           data-field="original_value"
                           data-mean="${rec.mean_value ?? 0}"
                           data-std="${rec.std_deviation ?? 1}"
                           onchange="app._onPreviewCellChange(this)"
                           class="w-28 border border-transparent rounded px-1 py-0.5 text-sm focus:border-blue-400 focus:outline-none bg-transparent hover:border-gray-300 text-right">
                </td>
                <td class="px-3 py-2 text-right text-sm font-mono" id="prev-z-${rec.processed_id}">
                    ${dispZ !== null && dispZ !== undefined ? dispZ.toFixed(4) : '—'}
                </td>
                <td class="px-3 py-2" id="prev-cls-${rec.processed_id}">
                    ${this._clsBadge(dispCls)}
                </td>
                <td class="px-3 py-2 text-center" id="prev-fail-${rec.processed_id}">
                    ${dispFail ? '<span class="text-red-600 font-bold text-xs">YES</span>'
                               : '<span class="text-green-600 text-xs">No</span>'}
                </td>
                <td class="px-3 py-2 text-center text-sm" id="prev-sev-${rec.processed_id}">
                    ${dispSev ?? 0}
                </td>
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
                            <input type="checkbox"
                                   id="previewSelectAll"
                                   ${allSelected ? 'checked' : ''}
                                   onchange="app._onSelectAll(this.checked)"
                                   class="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer"
                                   title="Select all">
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

        // Start or update the change entry for this row
        const entry = this._previewChanges.get(pid) || {};
        entry[field] = field === 'original_value' ? parseFloat(val) : val;
        this._previewChanges.set(pid, entry);

        // Live-update derived display columns (Z-score, classification, failure, severity)
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
            if (fEl)   fEl.innerHTML   = fail
                ? '<span class="text-red-600 font-bold text-xs">YES</span>'
                : '<span class="text-green-600 text-xs">No</span>';
            if (sEl)   sEl.textContent = sev;
        }

        // Highlight the row
        const row = document.getElementById(`prev-row-${pid}`);
        if (row) row.className = 'bg-yellow-50 transition-colors';

        // Update badge + button state
        this._refreshPreviewUI();
    }

    _revertPreviewRow(pid) {
        this._previewChanges.delete(pid);
        // Re-render to restore the original values for that row
        this._renderPreviewTable(this._previewRecords);
        this._refreshPreviewUI();
    }

    _onSelectRow(pid, checked) {
        if (checked) {
            this._previewSelected.add(pid);
        } else {
            this._previewSelected.delete(pid);
        }
        // Update row highlight without full re-render
        const row = document.getElementById(`prev-row-${pid}`);
        if (row) {
            const changed = this._previewChanges.has(pid);
            const rec = this._previewRecords.find(r => r.processed_id === pid);
            const isFail = rec && rec.is_failure === 1;
            row.className = (checked         ? 'bg-blue-50 ring-1 ring-inset ring-blue-300'
                            : changed        ? 'bg-yellow-50'
                            : isFail         ? 'bg-red-50'
                            : 'hover:bg-gray-50') + ' transition-colors';
        }
        // Update select-all checkbox state
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
        if (checked) {
            this._previewRecords.forEach(r => this._previewSelected.add(r.processed_id));
        } else {
            this._previewSelected.clear();
        }
        // Re-render to reflect new selection state
        this._renderPreviewTable(this._previewRecords);
        this._refreshPreviewUI();
    }

    _refreshPreviewUI() {
        const nChanges  = this._previewChanges ? this._previewChanges.size : 0;
        const nSelected = this._previewSelected ? this._previewSelected.size : 0;

        const saveBtn   = document.getElementById('previewSaveBtn');
        const badge     = document.getElementById('previewChangeBadge');
        const count     = document.getElementById('previewChangeCount');
        const delBtn    = document.getElementById('previewDeleteBtn');
        const delCount  = document.getElementById('previewDeleteCount');

        if (saveBtn) saveBtn.disabled = nChanges === 0;
        if (badge)  badge.classList.toggle('hidden', nChanges === 0);
        if (count)  count.textContent = nChanges;
        if (delBtn) {
            delBtn.disabled = nSelected === 0;
            if (delCount) delCount.textContent = nSelected;
        }
    }

    async deleteSelectedRecords() {
        if (!this._previewSelected || this._previewSelected.size === 0) return;

        const ids = Array.from(this._previewSelected);
        const confirmed = confirm(`Delete ${ids.length} selected record(s)? This cannot be undone.`);
        if (!confirmed) return;

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

            // Clear selection and refresh
            this._previewSelected.clear();
            const fresh = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`);
            const freshData = await fresh.json();
            if (freshData.success) {
                this._previewRecords = freshData.records;
                this._renderPreviewTable(freshData.records);
                document.getElementById('previewRecordCount').textContent =
                    `${freshData.records.length} record(s)`;
            }
            this._refreshPreviewUI();

            // Refresh the failure analysis tables in background
            await this.loadDataSources();
            await this.loadAllFailures();

        } catch (err) {
            this.showToast(`Delete failed: ${err.message}`, 'error');
            console.error('deleteSelectedRecords error:', err);
        } finally {
            if (delBtn) {
                delBtn.disabled = (this._previewSelected.size === 0);
                delBtn.innerHTML = '<i class="fas fa-trash mr-2"></i>Delete Selected (<span id="previewDeleteCount">0</span>)';
            }
        }
    }

    async savePreviewChanges() {
        if (!this._previewChanges || this._previewChanges.size === 0) return;

        const records = Array.from(this._previewChanges.entries()).map(([pid, changes]) => ({
            processed_id: pid,
            ...changes
        }));

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

            this.showToast(`${result.updated} record(s) saved successfully`, 'success');

            // Clear change tracking and re-render with fresh data from server
            this._previewChanges = new Map();
            const fresh = await fetch(`${this.apiBase}/sources/${this._previewSourceId}/records`);
            const freshData = await fresh.json();
            if (freshData.success) {
                this._previewRecords = freshData.records;
                this._renderPreviewTable(freshData.records);
            }
            this._refreshPreviewUI();

            // Auto-refresh the failure analysis dashboard in the background
            await this.loadDataSources();
            await this.loadAllFailures();

        } catch (err) {
            this.showToast(`Save failed: ${err.message}`, 'error');
            console.error('savePreviewChanges error:', err);
        } finally {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.innerHTML = '<i class="fas fa-save mr-2"></i>Save Changes'; }
        }
    }

}

// ─────────────────────────────────────────────────────────────────────────────
// PREVIEW / EDIT MODAL
// ─────────────────────────────────────────────────────────────────────────────

// Inject the modal markup once into the page (called lazily)
function ensurePreviewModalExists() {
    if (document.getElementById('previewModal')) return;
    const el = document.createElement('div');
    el.innerHTML = `
    <div id="previewModal"
         class="fixed inset-0 bg-black bg-opacity-60 z-50 hidden items-center justify-center p-4"
         onclick="if(event.target===this) app.closePreviewModal()">
        <div class="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col">

            <!-- Header -->
            <div class="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-blue-600 to-indigo-600 rounded-t-xl">
                <div class="text-white">
                    <h3 class="text-xl font-bold" id="previewTitle">Data Source Records</h3>
                    <p class="text-blue-100 text-sm mt-0.5" id="previewSubtitle"></p>
                </div>
                <div class="flex items-center gap-3">
                    <span id="previewChangeBadge"
                          class="hidden px-3 py-1 bg-yellow-400 text-yellow-900 text-xs font-bold rounded-full">
                        <i class="fas fa-pencil-alt mr-1"></i>
                        <span id="previewChangeCount">0</span> unsaved change(s)
                    </span>
                    <button onclick="app.closePreviewModal()"
                            class="text-white hover:bg-white hover:bg-opacity-20 rounded-lg p-2 transition-all">
                        <i class="fas fa-times text-lg"></i>
                    </button>
                </div>
            </div>

            <!-- Legend bar -->
            <div class="flex items-center gap-4 px-6 py-2 bg-gray-50 border-b text-xs text-gray-600">
                <span class="flex items-center gap-1">
                    <span class="w-3 h-3 rounded bg-blue-100 border border-blue-400 inline-block"></span> Selected for deletion
                </span>
                <span class="flex items-center gap-1">
                    <span class="w-3 h-3 rounded bg-yellow-200 border border-yellow-400 inline-block"></span> Edited row (unsaved)
                </span>
                <span class="flex items-center gap-1">
                    <span class="w-3 h-3 rounded bg-red-100 border border-red-300 inline-block"></span> Failure record
                </span>
                <span class="text-gray-400">| Click any <strong>Date</strong> or <strong>Value</strong> cell to edit</span>
            </div>

            <!-- Table -->
            <div class="flex-1 overflow-auto px-6 py-3" id="previewTableWrap">
                <div class="flex items-center justify-center py-16 text-gray-400">
                    <i class="fas fa-spinner fa-spin text-3xl mr-3"></i> Loading records…
                </div>
            </div>

            <!-- Footer -->
            <div class="flex items-center justify-between px-6 py-4 border-t bg-gray-50 rounded-b-xl">
                <div class="flex items-center gap-3">
                    <span class="text-sm text-gray-500" id="previewRecordCount"></span>
                    <button id="previewDeleteBtn"
                            onclick="app.deleteSelectedRecords()"
                            disabled
                            class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold text-sm">
                        <i class="fas fa-trash mr-2"></i>Delete Selected (<span id="previewDeleteCount">0</span>)
                    </button>
                </div>
                <div class="flex items-center gap-3">
                    <button onclick="app.closePreviewModal()"
                            class="px-5 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition-all">
                        Cancel
                    </button>
                    <button id="previewSaveBtn"
                            onclick="app.savePreviewChanges()"
                            disabled
                            class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold">
                        <i class="fas fa-save mr-2"></i>Save Changes
                    </button>
                </div>
            </div>
        </div>
    </div>`;
    document.body.appendChild(el.firstElementChild);
}

// Initialize the dashboard
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new FailureAnalysisDashboard();
});