   class AdvancedGroundwaterReports {
            constructor() {
                this.apiBase = 'http://localhost:5000/api';
                this.allData = [];
                this.filteredData = [];
                this.currentPage = 1;
                this.rowsPerPage = 25;
                this.charts = {};
                this.isFiltered = false;
                
                this.init();
            }
            
            async init() {
                this.setupEventListeners();
                await this.loadCatchments();
                await this.loadAllData();
                this.showToast('Reports system ready - Viewing all data', 'success');
            }
            
            setupEventListeners() {
                document.getElementById('viewAllBtn').addEventListener('click', () => this.viewAllData());
                document.getElementById('toggleFiltersBtn').addEventListener('click', () => this.toggleFilters());
                document.getElementById('applyFiltersBtn').addEventListener('click', () => this.applyFilters());
                document.getElementById('clearFiltersBtn').addEventListener('click', () => this.clearFilters());
                document.getElementById('refreshBtn').addEventListener('click', () => this.refresh());
                document.getElementById('printBtn').addEventListener('click', () => this.printReport());
                document.getElementById('exportPdfBtn').addEventListener('click', () => this.exportPDF());
                document.getElementById('exportExcelBtn').addEventListener('click', () => this.exportExcel());
                document.getElementById('searchInput').addEventListener('input', (e) => this.searchData(e.target.value));
                document.getElementById('rowsPerPage').addEventListener('change', (e) => this.changeRowsPerPage(e.target.value));
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
            
                async loadAllData() {
                    this.showLoading('Loading all groundwater data...');
                    try {
                        // Don't specify parameter - this loads ALL categories
                        const response = await fetch(`${this.apiBase}/data?limit=10000`);
                        const result = await response.json();
                        
                        this.allData = result.data || [];
                        this.filteredData = this.allData;
                        this.isFiltered = false;
                        
                        this.updateDisplay();
                        this.showToast(`Loaded ${this.allData.length} total records from all sub-catchments and parameters`, 'success');
                    } catch (error) {
                        this.showToast('Failed to load data', 'error');
                        console.error('Load error:', error);
                    } finally {
                        this.hideLoading();
                    }
                }
            
            async applyFilters() {
                const filters = {
                    catchment: document.getElementById('catchmentFilter').value,
                    parameter: document.getElementById('parameterFilter').value,
                    start_date: document.getElementById('startDateFilter').value,
                    end_date: document.getElementById('endDateFilter').value
                };
                
                const hasFilters = Object.values(filters).some(v => v !== '');
                
                if (!hasFilters) {
                    this.viewAllData();
                    return;
                }
                
                this.showLoading('Applying filters...');
                try {
                    const params = new URLSearchParams();
                    Object.entries(filters).forEach(([key, value]) => {
                        if (value) params.append(key, value);
                    });
                    
                    const response = await fetch(`${this.apiBase}/data?${params}&limit=10000`);
                    const result = await response.json();
                    
                    this.filteredData = result.data || [];
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
            
            viewAllData() {
                this.filteredData = this.allData;
                this.isFiltered = false;
                this.currentPage = 1;
                this.clearFilterInputs();
                this.updateDisplay();
                this.showToast('Viewing all data', 'info');
            }
            
            clearFilters() {
                this.clearFilterInputs();
                this.viewAllData();
            }
            
            clearFilterInputs() {
                document.getElementById('catchmentFilter').value = '';
                document.getElementById('parameterFilter').value = '';
                document.getElementById('startDateFilter').value = '';
                document.getElementById('endDateFilter').value = '';
                document.getElementById('activeFilters').innerHTML = '';
            }
            
            updateActiveFilters(filters) {
                const container = document.getElementById('activeFilters');
                container.innerHTML = '';
                
                Object.entries(filters).forEach(([key, value]) => {
                    if (value) {
                        const badge = document.createElement('span');
                        badge.className = 'filter-badge bg-blue-100 text-blue-800 text-xs px-3 py-1 rounded-full';
                        badge.textContent = `${key}: ${value}`;
                        container.appendChild(badge);
                    }
                });
            }
            
            updateDisplay() {
                this.updateSummaryCards();
                this.updateCharts();
                this.renderDataTable();
                this.updateRecordCount();
            }
            
            updateRecordCount() {
                const text = this.isFiltered ? 
                    `Showing ${this.filteredData.length} of ${this.allData.length} records (filtered)` :
                    `Showing all ${this.allData.length} records`;
                document.getElementById('recordCount').textContent = text;
            }
            
            updateSummaryCards() {
                const data = this.filteredData;
                
                // Total records
                document.getElementById('totalRecords').textContent = data.length.toLocaleString();
                
                // Failure rate
                const failures = data.filter(d => d.is_failure === 1).length;
                const rate = data.length > 0 ? ((failures / data.length) * 100).toFixed(1) : 0;
                document.getElementById('failureRate').textContent = rate + '%';
                
                // Active catchments
                const catchments = new Set(data.map(d => d.catchment_name));
                document.getElementById('activeCatchments').textContent = catchments.size;
                
                // Date range
                if (data.length > 0) {
                    const dates = data.map(d => new Date(d.measurement_date)).filter(d => !isNaN(d));
                    if (dates.length > 0) {
                        const minDate = new Date(Math.min(...dates)).toLocaleDateString();
                        const maxDate = new Date(Math.max(...dates)).toLocaleDateString();
                        document.getElementById('dateRange').textContent = `${minDate} - ${maxDate}`;
                    }
                }
            }
            
            updateCharts() {
            this.updateTimeSeriesChart();
            this.updateClassificationChart();
            this.updateCatchmentRecordsChart();
            this.updateFailureTrendsChart();
        }
            
            updateTimeSeriesChart() {
                const ctx = document.getElementById('timeSeriesChart');
                if (!ctx) return;
                
                if (this.charts.timeSeries) {
                    this.charts.timeSeries.destroy();
                }
                
                const sortedData = [...this.filteredData]
                    .filter(d => d.measurement_date && d.zscore !== null)
                    .sort((a, b) => new Date(a.measurement_date) - new Date(b.measurement_date));
                
                this.charts.timeSeries = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: sortedData.map(d => new Date(d.measurement_date).toLocaleDateString()),
                        datasets: [{
                            label: 'Z-Score',
                            data: sortedData.map(d => d.zscore),
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.4,
                            pointRadius: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: true }
                        },
                        scales: {
                            y: { 
                                title: { display: true, text: 'Z-Score' }
                            }
                        }
                    }
                });
            }

            updateCatchmentRecordsChart() {
    const ctx = document.getElementById('catchmentRecordsChart');
    if (!ctx) return;
    
    if (this.charts.catchmentRecords) {
        this.charts.catchmentRecords.destroy();
    }
    
    const catchmentData = {};
    this.filteredData.forEach(d => {
        const catchment = d.catchment_name;
        if (!catchmentData[catchment]) {
            catchmentData[catchment] = 0;
        }
        catchmentData[catchment]++;
    });
    
    const catchments = Object.keys(catchmentData);
    const counts = Object.values(catchmentData);
    
    this.charts.catchmentRecords = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: catchments,
            datasets: [{
                label: 'Total Records',
                data: counts,
                backgroundColor: '#3b82f6',
                borderColor: '#2563eb',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                title: {
                    display: true,
                    text: 'Records per Sub-Catchment'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Number of Records' }
                },
                x: {
                    title: { display: true, text: 'Sub-Catchment' }
                }
            }
        }
    });
}

updateFailureTrendsChart() {
    const ctx = document.getElementById('failureTrendsChart');
    if (!ctx) return;
    
    if (this.charts.failureTrends) {
        this.charts.failureTrends.destroy();
    }
    
    // Group by catchment and month/year, calculate failure rate
    const catchmentTrends = {};
    
    this.filteredData.forEach(d => {
        const catchment = d.catchment_name;
        if (!catchmentTrends[catchment]) {
            catchmentTrends[catchment] = {};
        }
        
        if (d.measurement_date) {
            const date = new Date(d.measurement_date);
            const monthYear = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
            
            if (!catchmentTrends[catchment][monthYear]) {
                catchmentTrends[catchment][monthYear] = {
                    total: 0,
                    failures: 0,
                    date: date
                };
            }
            
            catchmentTrends[catchment][monthYear].total++;
            if (d.is_failure === 1) {
                catchmentTrends[catchment][monthYear].failures++;
            }
        }
    });
    
    // Convert to datasets
    const datasets = [];
    const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#6366f1', '#14b8a6'];
    let colorIndex = 0;
    
    Object.keys(catchmentTrends).forEach(catchment => {
        const monthlyData = catchmentTrends[catchment];
        
        // Sort by date and calculate failure rates
        const data = Object.keys(monthlyData)
            .sort()
            .map(monthYear => {
                const stats = monthlyData[monthYear];
                const failureRate = stats.total > 0 ? (stats.failures / stats.total) * 100 : 0;
                return {
                    x: monthYear,
                    y: failureRate
                };
            });
        
        if (data.length > 0) {
            datasets.push({
                label: catchment,
                data: data,
                borderColor: colors[colorIndex % colors.length],
                backgroundColor: colors[colorIndex % colors.length] + '20',
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 6,
                fill: false,
                borderWidth: 2
            });
            
            colorIndex++;
        }
    });
    
    this.charts.failureTrends = new Chart(ctx, {
        type: 'line',
        data: { datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { 
                    display: true,
                    position: 'top'
                },
                title: {
                    display: true,
                    text: 'Failure Rate Trends by Sub-Catchment (%)'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(1)}%`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Failure Rate (%)' },
                    grid: { color: '#e5e7eb' },
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                },
                x: {
                    title: { display: true, text: 'Month' },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            }
        }
    });
}
            
            updateClassificationChart() {
                const ctx = document.getElementById('classificationChart');
                if (!ctx) return;
                
                if (this.charts.classification) {
                    this.charts.classification.destroy();
                }
                
                const counts = {
                    'Normal': 0,
                    'Moderate_Deficit': 0,
                    'Severe_Deficit': 0,
                    'Extreme_Deficit': 0,
                    'Surplus': 0
                };
                
                this.filteredData.forEach(d => {
                    if (counts.hasOwnProperty(d.classification)) {
                        counts[d.classification]++;
                    }
                });
                
                this.charts.classification = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: ['Normal', 'Moderate Deficit', 'Severe Deficit', 'Extreme Deficit', 'Surplus'],
                        datasets: [{
                            data: Object.values(counts),
                            backgroundColor: ['#22c55e', '#eab308', '#f97316', '#ef4444', '#3b82f6']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom' }
                        }
                    }
                });
            }
            
            renderDataTable() {
                const container = document.getElementById('dataTable');
                const data = this.filteredData;
                
                if (data.length === 0) {
                    container.innerHTML = '<div class="text-center py-8 text-gray-500">No data available</div>';
                    return;
                }
                
                const startIndex = (this.currentPage - 1) * this.rowsPerPage;
                const endIndex = this.rowsPerPage === 'all' ? data.length : startIndex + parseInt(this.rowsPerPage);
                const pageData = data.slice(startIndex, endIndex);
                
                const table = `
                    <table class="w-full text-sm">
                        <thead class="bg-gray-50 sticky top-0">
                            <tr>
                                <th class="px-4 py-3 text-left font-semibold">Date</th>
                                <th class="px-4 py-3 text-left font-semibold">Sub-Catchment</th>
                                <th class="px-4 py-3 text-left font-semibold">Parameter</th>
                                <th class="px-4 py-3 text-right font-semibold">Original Value</th>
                                <th class="px-4 py-3 text-right font-semibold">Z-Score</th>
                                <th class="px-4 py-3 text-left font-semibold">Classification</th>
                                <th class="px-4 py-3 text-center font-semibold">Status</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
                            ${pageData.map(row => `
                                <tr class="hover:bg-gray-50">
                                    <td class="px-4 py-3">${new Date(row.measurement_date).toLocaleDateString()}</td>
                                    <td class="px-4 py-3">${row.catchment_name || 'N/A'}</td>
                                    <td class="px-4 py-3">${row.category || 'N/A'}</td>
                                    <td class="px-4 py-3 text-right">${(row.original_value || 0).toFixed(2)}</td>
                                    <td class="px-4 py-3 text-right font-medium">${(row.zscore || 0).toFixed(3)}</td>
                                    <td class="px-4 py-3">
                                        <span class="px-2 py-1 text-xs rounded ${this.getClassificationColor(row.classification)}">
                                            ${(row.classification || 'Unknown').replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td class="px-4 py-3 text-center">
                                        ${row.is_failure ? 
                                            '<span class="text-red-600"><i class="fas fa-exclamation-circle"></i></span>' : 
                                            '<span class="text-green-600"><i class="fas fa-check-circle"></i></span>'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
                
                container.innerHTML = table;
                this.renderPagination();
            }
            
            getClassificationColor(classification) {
                const colors = {
                    'Normal': 'bg-green-100 text-green-800',
                    'Moderate_Deficit': 'bg-yellow-100 text-yellow-800',
                    'Severe_Deficit': 'bg-orange-100 text-orange-800',
                    'Extreme_Deficit': 'bg-red-100 text-red-800',
                    'Surplus': 'bg-blue-100 text-blue-800'
                };
                return colors[classification] || 'bg-gray-100 text-gray-800';
            }
            
            renderPagination() {
                const container = document.getElementById('pagination');
                if (this.rowsPerPage === 'all') {
                    container.innerHTML = '';
                    return;
                }
                
                const totalPages = Math.ceil(this.filteredData.length / this.rowsPerPage);
                const start = (this.currentPage - 1) * this.rowsPerPage + 1;
                const end = Math.min(this.currentPage * this.rowsPerPage, this.filteredData.length);
                
                container.innerHTML = `
                    <div class="text-sm text-gray-600">
                        Showing ${start}-${end} of ${this.filteredData.length} records
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="reports.goToPage(${this.currentPage - 1})" 
                                ${this.currentPage === 1 ? 'disabled' : ''}
                                class="px-3 py-1 border rounded ${this.currentPage === 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                            <i class="fas fa-chevron-left"></i> Prev
                        </button>
                        <span class="text-sm">Page ${this.currentPage} of ${totalPages}</span>
                        <button onclick="reports.goToPage(${this.currentPage + 1})" 
                                ${this.currentPage === totalPages ? 'disabled' : ''}
                                class="px-3 py-1 border rounded ${this.currentPage === totalPages ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'}">
                            Next <i class="fas fa-chevron-right"></i>
                        </button>
                    </div>
                `;
            }
            
            goToPage(page) {
                const totalPages = Math.ceil(this.filteredData.length / this.rowsPerPage);
                if (page >= 1 && page <= totalPages) {
                    this.currentPage = page;
                    this.renderDataTable();
                }
            }
            
            changeRowsPerPage(value) {
                this.rowsPerPage = value === 'all' ? 'all' : parseInt(value);
                this.currentPage = 1;
                this.renderDataTable();
            }
            
            searchData(query) {
                if (!query.trim()) {
                    this.filteredData = this.isFiltered ? this.filteredData : this.allData;
                } else {
                    const searchLower = query.toLowerCase();
                    const baseData = this.isFiltered ? this.filteredData : this.allData;
                    this.filteredData = baseData.filter(row => {
                        return Object.values(row).some(val => 
                            String(val).toLowerCase().includes(searchLower)
                        );
                    });
                }
                this.currentPage = 1;
                this.updateDisplay();
            }
            
            toggleFilters() {
                const panel = document.getElementById('filtersPanel');
                panel.classList.toggle('hidden');
            }
            
            async refresh() {
                await this.loadAllData();
                this.showToast('Data refreshed', 'success');
            }
            
          printReport() {
    // Hide all tables except current page data
    const originalRowsPerPage = this.rowsPerPage;
    this.rowsPerPage = 'all'; // Show all data
    this.renderDataTable();
    
    // Trigger print
    setTimeout(() => {
        window.print();
        
        // Restore pagination after print dialog closes
        setTimeout(() => {
            this.rowsPerPage = originalRowsPerPage;
            this.renderDataTable();
        }, 100);
    }, 500);
}
            

 async exportPDF() {
    console.log('=== PDF Export Started ===');
    this.showLoading('Preparing PDF report...');
    
    try {
        // Show all data
        const originalRowsPerPage = this.rowsPerPage;
        this.rowsPerPage = 'all';
        this.renderDataTable();
        
        // Wait for render
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Find container
        const container = document.querySelector('.container.mx-auto');
        if (!container) {
            throw new Error('Could not find content container');
        }
        
        console.log('Converting charts to images...');
        
        // Convert all Chart.js canvases to static images
        const chartCanvases = container.querySelectorAll('canvas');
        const chartImages = [];
        
        chartCanvases.forEach(canvas => {
            try {
                // Get the parent container
                const parent = canvas.parentElement;
                
                // Convert canvas to image
                const img = document.createElement('img');
                img.src = canvas.toDataURL('image/png');
                img.style.width = '100%';
                img.style.maxHeight = '400px';
                img.className = 'chart-image';
                
                // Store reference to restore later
                chartImages.push({
                    canvas: canvas,
                    parent: parent,
                    img: img
                });
                
                // Replace canvas with image
                parent.replaceChild(img, canvas);
            } catch (err) {
                console.warn('Failed to convert chart:', err);
            }
        });
        
        console.log(`Converted ${chartImages.length} charts to images`);
        
        // Wait a bit for images to settle
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Configure html2pdf
        const opt = {
            margin: [10, 10, 10, 10],
            filename: `groundwater_report_${new Date().toISOString().split('T')[0]}.pdf`,
            image: { 
                type: 'jpeg', 
                quality: 0.95
            },
            html2canvas: { 
                scale: 2,
                logging: false,
                useCORS: true,
                allowTaint: true,
                backgroundColor: '#ffffff',
                letterRendering: true
            },
            jsPDF: { 
                unit: 'mm', 
                format: 'a3',
                orientation: 'landscape'
            },
            pagebreak: {
                mode: ['avoid-all', 'css', 'legacy']
            }
        };
        
        this.showLoading('Generating PDF...');
        console.log('Starting PDF generation...');
        
        await html2pdf().set(opt).from(container).save();
        
        console.log('PDF generated successfully');
        
        // Restore canvases
        console.log('Restoring charts...');
        chartImages.forEach(item => {
            item.parent.replaceChild(item.canvas, item.img);
        });
        
        // Restore pagination
        this.rowsPerPage = originalRowsPerPage;
        this.renderDataTable();
        
        // Recreate charts since we replaced them
        this.updateCharts();
        
        this.showToast('PDF exported successfully', 'success');
        
    } catch (error) {
        console.error('PDF Error:', error);
        this.showToast('PDF export failed. Use Print button instead.', 'error');
        
        // Restore state
        if (this.rowsPerPage === 'all') {
            this.rowsPerPage = 25;
            this.renderDataTable();
        }
        
        // Offer fallback
        setTimeout(() => {
            const usePrint = confirm('PDF export failed. Would you like to use browser Print to PDF instead? (More reliable)');
            if (usePrint) {
                this.printReport();
            }
        }, 1000);
    } finally {
        this.hideLoading();
        console.log('=== PDF Export Ended ===');
    }
}

// Option 2: Browser Print (more reliable fallback)
// This is your existing printReport() - make sure it's working
            
            async exportExcel() {
                this.showLoading('Preparing Excel export...');
                
                try {
                    const filters = this.isFiltered ? this.getActiveFilters() : '';
                    const params = new URLSearchParams(filters);
                    
                    const response = await fetch(`${this.apiBase}/export?${params}`);
                    if (!response.ok) throw new Error('Export failed');
                    
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `groundwater_data_${new Date().toISOString().split('T')[0]}.xlsx`;
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
            
            getActiveFilters() {
                return {
                    catchment: document.getElementById('catchmentFilter').value,
                    parameter: document.getElementById('parameterFilter').value,
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
                
                const toast = document.createElement('div');
                toast.className = `${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg flex items-center justify-between min-w-[300px] transform transition-all duration-300 translate-x-full`;
                toast.innerHTML = `
                    <span class="text-sm font-medium">${message}</span>
                    <button onclick="this.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                
                container.appendChild(toast);
                setTimeout(() => toast.classList.remove('translate-x-full'), 100);
                setTimeout(() => {
                    if (toast.parentElement) {
                        toast.classList.add('translate-x-full');
                        setTimeout(() => toast.remove(), 300);
                    }
                }, 5000);
            }
        }
        
        // Initialize the system
        let reports;
        document.addEventListener('DOMContentLoaded', () => {
            reports = new AdvancedGroundwaterReports();
        });

        