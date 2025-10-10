// Failure Analysis Dashboard - failure-analysis.js
class FailureAnalysisDashboard {
    constructor() {
        this.apiBase = 'http://localhost:5000/api';
        this.allData = [];
        this.filteredData = [];
        this.currentPage = 1;
        this.rowsPerPage = 15;
        this.charts = {};
        this.isFiltered = false;
        
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadCatchments();
        await this.loadDataSources();
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
            const data = await response.json();
            
            const container = document.getElementById('dataSourcesTable');
            if (!container) return;
            
            if (!data.sources || data.sources.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <i class="fas fa-database text-4xl mb-4"></i>
                        <p>No data sources found</p>
                        <p class="text-sm mt-2">Upload an Excel file to get started</p>
                    </div>
                `;
                return;
            }
            
            const table = `
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
                    <tbody class="divide-y divide-gray-200">
                        ${data.sources.map(source => `
                            <tr class="hover:bg-gray-50">
                                <td class="px-4 py-3 font-medium">${source.file_name || 'Unknown'}</td>
                                <td class="px-4 py-3">${source.category || 'N/A'}</td>
                                <td class="px-4 py-3">${source.subcatchment || 'N/A'}</td>
                                <td class="px-4 py-3">${source.upload_date ? new Date(source.upload_date).toLocaleDateString() : 'N/A'}</td>
                                <td class="px-4 py-3">${(source.total_records || 0).toLocaleString()}</td>
                                <td class="px-4 py-3">
                                    <span class="px-2 py-1 text-xs rounded ${
                                        source.processing_status === 'Completed' ? 'bg-green-100 text-green-800' :
                                        source.processing_status === 'Failed' ? 'bg-red-100 text-red-800' :
                                        'bg-yellow-100 text-yellow-800'
                                    }">
                                        ${source.processing_status || 'Unknown'}
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <button onclick="app.deleteSource(${source.source_id})" class="text-red-600 hover:text-red-800" title="Delete">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
            
            container.innerHTML = table;
        } catch (error) {
            console.error('Failed to load data sources:', error);
        }
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
        if (!confirm('Are you sure you want to delete this data source?')) return;
        
        this.showLoading('Deleting source...');
        try {
            const response = await fetch(`${this.apiBase}/sources/${sourceId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error('Delete failed');
            
            this.showToast('Data source deleted successfully', 'success');
            await this.loadDataSources();
            await this.loadAllFailures();
        } catch (error) {
            this.showToast(`Failed to delete source: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async loadCatchments() {
        try {
            const response = await fetch(`${this.apiBase}/filter-options`);
            const data = await response.json();
            
            const select = document.getElementById('catchmentFilter');
            if (data.catchments) {
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
            const response = await fetch(`${this.apiBase}/failure-analysis`);
            const result = await response.json();
            
            this.allData = result.failure_analysis || [];
            this.filteredData = this.allData;
            this.isFiltered = false;
            this.currentPage = 1;
            
            this.updateDisplay();
            this.showToast(`Loaded ${this.allData.length} failure analysis records`, 'success');
        } catch (error) {
            this.showToast('Failed to load failure analysis', 'error');
            console.error('Load error:', error);
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
            
            const response = await fetch(`${this.apiBase}/failure-analysis?${params}`);
            const result = await response.json();
            
            this.filteredData = result.failure_analysis || [];
            
            if (filters.severity) {
                this.filteredData = this.filteredData.filter(record => 
                    record.severity_classification === filters.severity
                );
            }
            
            this.isFiltered = true;
            this.currentPage = 1;
            
            this.updateActiveFilters(filters);
            this.updateDisplay();
            this.showToast(`Filtered to ${this.filteredData.length} records`, 'success');
        } catch (error) {
            this.showToast('Filter application failed', 'error');
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
        const panel = document.getElementById('filtersPanel');
        panel.classList.toggle('hidden');
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
        
        const totalRecords = data.reduce((sum, r) => sum + (r.total_records || 0), 0);
        const totalFailures = data.reduce((sum, r) => sum + (r.total_failures || 0), 0);
        const overallRate = totalRecords > 0 ? ((totalFailures / totalRecords) * 100).toFixed(1) : '0.0';
        
        document.getElementById('summaryTotalRecords').textContent = totalRecords.toLocaleString();
        document.getElementById('summaryTotalFailures').textContent = totalFailures.toLocaleString();
        document.getElementById('summaryOverallRate').textContent = overallRate + '%';
        document.getElementById('summaryPeriods').textContent = data.length;
        
        const baseflowData = data.filter(r => r.category === 'BASEFLOW');
        const baseflowTotal = baseflowData.reduce((sum, r) => sum + (r.total_records || 0), 0);
        const baseflowFail = baseflowData.reduce((sum, r) => sum + (r.total_failures || 0), 0);
        const baseflowRate = baseflowTotal > 0 ? ((baseflowFail / baseflowTotal) * 100).toFixed(1) : '0.0';
        document.getElementById('baseflowRate').textContent = baseflowRate + '%';
        document.getElementById('baseflowRecords').textContent = `${baseflowFail.toLocaleString()}/${baseflowTotal.toLocaleString()} records`;
        
        const gwlevelData = data.filter(r => r.category === 'GWLEVEL');
        const gwlevelTotal = gwlevelData.reduce((sum, r) => sum + (r.total_records || 0), 0);
        const gwlevelFail = gwlevelData.reduce((sum, r) => sum + (r.total_failures || 0), 0);
        const gwlevelRate = gwlevelTotal > 0 ? ((gwlevelFail / gwlevelTotal) * 100).toFixed(1) : '0.0';
        document.getElementById('gwlevelRate').textContent = gwlevelRate + '%';
        document.getElementById('gwlevelRecords').textContent = `${gwlevelFail.toLocaleString()}/${gwlevelTotal.toLocaleString()} records`;
        
        const rechargeData = data.filter(r => r.category === 'RECHARGE');
        const rechargeTotal = rechargeData.reduce((sum, r) => sum + (r.total_records || 0), 0);
        const rechargeFail = rechargeData.reduce((sum, r) => sum + (r.total_failures || 0), 0);
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
                        <th class="px-4 py-3 text-left font-semibold">Date</th>
                        <th class="px-4 py-3 text-left font-semibold">Catchment</th>
                        <th class="px-4 py-3 text-left font-semibold">Parameter</th>
                        <th class="px-4 py-3 text-right font-semibold">Total Records</th>
                        <th class="px-4 py-3 text-right font-semibold">Failures</th>
                        <th class="px-4 py-3 text-right font-semibold">Failure Rate</th>
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
        const dateStr = `${row.month || ''}/${row.year || ''}`;
        const classificationColor = this.getClassificationColor(row.severity_classification);
        
        return `
            <tr class="hover:bg-gray-50">
                <td class="px-4 py-3">${dateStr}</td>
                <td class="px-4 py-3">${row.catchment_name || 'N/A'}</td>
                <td class="px-4 py-3">${row.category || 'N/A'}</td>
                <td class="px-4 py-3 text-right">${(row.total_records || 0).toLocaleString()}</td>
                <td class="px-4 py-3 text-right font-medium">${(row.total_failures || 0).toLocaleString()}</td>
                <td class="px-4 py-3 text-right">
                    <span class="px-2 py-1 text-xs rounded ${this.getFailureRateClass(row.failure_rate)}">
                        ${(row.failure_rate || 0).toFixed(1)}%
                    </span>
                </td>
                <td class="px-4 py-3">
                    <span class="px-2 py-1 text-xs rounded ${classificationColor}">
                        ${row.severity_classification || 'None'}
                    </span>
                </td>
                <td class="px-4 py-3 text-center">
                    ${row.total_failures > 0 ? 
                        '<span class="text-red-600"><i class="fas fa-exclamation-circle"></i></span>' : 
                        '<span class="text-green-600"><i class="fas fa-check-circle"></i></span>'}
                </td>
            </tr>
        `;
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
    
    showLoading(text) {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').classList.remove('hidden');
        document.getElementById('loadingOverlay').classList.add('flex');
    }
    
    hideLoading() {
        document.getElementById('loadingOverlay').classList.add('hidden');
        document.getElementById('loadingOverlay').classList.remove('flex');
    }
    
   showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };
    
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    
    // Handle multiline messages
    const formattedMessage = message.replace(/\n/g, '<br>');
    
    const toast = document.createElement('div');
    toast.className = `${colors[type]} text-white px-6 py-4 rounded-lg shadow-lg flex items-start justify-between min-w-[300px] max-w-[500px] transform transition-all duration-300 translate-x-full`;
    toast.innerHTML = `
        <div class="flex items-start flex-1">
            <i class="fas ${icons[type]} mr-3 mt-1"></i>
            <div class="text-sm font-medium leading-relaxed">${formattedMessage}</div>
        </div>
        <button onclick="this.parentElement.remove()" class="ml-4 text-white hover:text-gray-200 flex-shrink-0">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    container.appendChild(toast);
    setTimeout(() => toast.classList.remove('translate-x-full'), 100);
    
    // Longer timeout for error messages (10 seconds)
    const timeout = type === 'error' ? 10000 : 5000;
    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('translate-x-full');
            setTimeout(() => toast.remove(), 300);
        }
    }, timeout);
}
}

// Initialize the dashboard
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new FailureAnalysisDashboard();
});