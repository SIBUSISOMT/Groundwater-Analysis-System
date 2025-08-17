// Groundwater Analysis System Frontend
// Main JavaScript Application

class GroundwaterApp {
    constructor() {
        this.apiBase = 'http://localhost:5000/api';
        this.charts = {};
        this.currentData = null;
        this.currentMetrics = null;
        
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.checkApiHealth();
        await this.loadCatchments();
        await this.loadDataSources();
        this.initCharts();
    }
    
    setupEventListeners() {
        // File upload
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this.handleFileUpload(e.target.files[0]));
        
        // Drag and drop
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
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileUpload(files[0]);
            }
        });
        
        // Filters
        document.getElementById('applyFilters').addEventListener('click', () => this.applyFilters());
        document.getElementById('clearFilters').addEventListener('click', () => this.clearFilters());
        document.getElementById('exportData').addEventListener('click', () => this.exportData());
        
        // Modal controls
        document.getElementById('settingsBtn').addEventListener('click', () => this.showThresholdModal());
        document.getElementById('closeThresholdModal').addEventListener('click', () => this.hideThresholdModal());
        
        // Auto-refresh filters when parameter changes
        document.getElementById('parameterFilter').addEventListener('change', () => {
            if (this.currentData) {
                this.applyFilters();
            }
        });
    }
    
    async checkApiHealth() {
        try {
            const response = await fetch(`${this.apiBase}/health`);
            const data = await response.json();
            
            const statusEl = document.getElementById('healthStatus');
            if (data.status === 'healthy') {
                statusEl.innerHTML = '<div class="w-3 h-3 bg-green-400 rounded-full mr-2"></div><span class="text-sm">Connected</span>';
            } else {
                statusEl.innerHTML = '<div class="w-3 h-3 bg-red-400 rounded-full mr-2"></div><span class="text-sm">Error</span>';
            }
        } catch (error) {
            console.error('Health check failed:', error);
            const statusEl = document.getElementById('healthStatus');
            statusEl.innerHTML = '<div class="w-3 h-3 bg-red-400 rounded-full mr-2"></div><span class="text-sm">Offline</span>';
        }
    }
    
    async loadCatchments() {
        try {
            const response = await fetch(`${this.apiBase}/catchments`);
            const data = await response.json();
            
            const select = document.getElementById('catchmentFilter');
            select.innerHTML = '<option value="">All Catchments</option>';
            
            if (data.catchments) {
                data.catchments.forEach(catchment => {
                    const option = document.createElement('option');
                    option.value = catchment.catchment_name;
                    option.textContent = `${catchment.catchment_name} (${catchment.total_records || 0} records)`;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load catchments:', error);
            this.showMessage('Failed to load catchments', 'error');
        }
    }
    
    async loadDataSources() {
        try {
            const response = await fetch(`${this.apiBase}/sources`);
            const data = await response.json();
            
            const container = document.getElementById('dataSourcesTable');
            
            if (!data.sources || data.sources.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-8">No data sources available. Upload an Excel file to get started.</p>';
                return;
            }
            
            const table = this.createDataSourcesTable(data.sources);
            container.innerHTML = table;
            
        } catch (error) {
            console.error('Failed to load data sources:', error);
            this.showMessage('Failed to load data sources', 'error');
        }
    }
    
    createDataSourcesTable(sources) {
        let html = `
            <table class="w-full text-sm">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-4 py-2 text-left">File Name</th>
                        <th class="px-4 py-2 text-left">Upload Date</th>
                        <th class="px-4 py-2 text-left">Size (KB)</th>
                        <th class="px-4 py-2 text-left">Records</th>
                        <th class="px-4 py-2 text-left">Status</th>
                        <th class="px-4 py-2 text-left">Date Range</th>
                        <th class="px-4 py-2 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        sources.forEach(source => {
            const statusClass = source.processing_status === 'Completed' ? 'text-green-600' : 
                              source.processing_status === 'Failed' ? 'text-red-600' : 'text-yellow-600';
            
            const dateRange = source.date_range_start && source.date_range_end ? 
                `${source.date_range_start} to ${source.date_range_end}` : 'N/A';
            
            html += `
                <tr class="border-b hover:bg-gray-50">
                    <td class="px-4 py-2">${source.file_name}</td>
                    <td class="px-4 py-2">${new Date(source.upload_date).toLocaleDateString()}</td>
                    <td class="px-4 py-2">${source.file_size_kb || 0}</td>
                    <td class="px-4 py-2">${source.processed_records || 0}</td>
                    <td class="px-4 py-2 ${statusClass}">${source.processing_status}</td>
                    <td class="px-4 py-2">${dateRange}</td>
                    <td class="px-4 py-2">
                        <button onclick="app.viewSource(${source.source_id})" class="text-blue-600 hover:text-blue-800 mr-2">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button onclick="app.deleteSource(${source.source_id})" class="text-red-600 hover:text-red-800">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        return html;
    }
    
    async handleFileUpload(file) {
        if (!file) return;
        
        if (!file.name.match(/\.(xlsx|xls)$/)) {
            this.showMessage('Please select an Excel file (.xlsx or .xls)', 'error');
            return;
        }
        
        if (file.size > 16 * 1024 * 1024) {
            this.showMessage('File size must be less than 16MB', 'error');
            return;
        }
        
        this.showLoading('Uploading and processing file...');
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`${this.apiBase}/upload`, {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.error || 'Upload failed');
            }
            
            this.showMessage(`File uploaded successfully! ${result.processed_records} records processed.`, 'success');
            
            // Refresh data
            await this.loadCatchments();
            await this.loadDataSources();
            await this.applyFilters();
            
        } catch (error) {
            console.error('Upload failed:', error);
            this.showMessage(error.message || 'Upload failed', 'error');
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
        
        this.showLoading('Loading data...');
        
        try {
            // Load processed data
            const dataParams = new URLSearchParams();
            Object.keys(filters).forEach(key => {
                if (filters[key]) dataParams.append(key, filters[key]);
            });
            
            const dataResponse = await fetch(`${this.apiBase}/data?${dataParams}`);
            const dataResult = await dataResponse.json();
            
            if (!dataResponse.ok) {
                throw new Error(dataResult.error || 'Failed to load data');
            }
            
            this.currentData = dataResult.data;
            
            // Load performance metrics
            const metricsParams = new URLSearchParams();
            Object.keys(filters).forEach(key => {
                if (filters[key] && key !== 'start_date' && key !== 'end_date') {
                    metricsParams.append(key, filters[key]);
                }
            });
            
            const metricsResponse = await fetch(`${this.apiBase}/metrics?${metricsParams}`);
            const metricsResult = await metricsResponse.json();
            
            if (metricsResponse.ok) {
                this.currentMetrics = metricsResult.metrics;
                this.updateMetricsDisplay();
            }
            
            // Load failure analysis
            const failureParams = new URLSearchParams();
            if (filters.catchment) failureParams.append('catchment', filters.catchment);
            if (filters.start_date) failureParams.append('start_date', filters.start_date);
            if (filters.end_date) failureParams.append('end_date', filters.end_date);
            
            const failureResponse = await fetch(`${this.apiBase}/failure-analysis?${failureParams}`);
            const failureResult = await failureResponse.json();
            
            if (failureResponse.ok) {
                this.updateFailureAnalysis(failureResult.failure_analysis);
            }
            
            // Update charts
            this.updateCharts();
            
            this.showMessage('Data loaded successfully', 'success');
            
        } catch (error) {
            console.error('Failed to apply filters:', error);
            this.showMessage(error.message || 'Failed to load data', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    clearFilters() {
        document.getElementById('catchmentFilter').value = '';
        document.getElementById('parameterFilter').value = 'GWR';
        document.getElementById('startDateFilter').value = '';
        document.getElementById('endDateFilter').value = '';
        
        this.currentData = null;
        this.currentMetrics = null;
        
        // Clear charts
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });
        this.initCharts();
        
        // Clear metrics
        document.getElementById('reliabilityMetric').textContent = '-';
        document.getElementById('resilienceMetric').textContent = '-';
        document.getElementById('vulnerabilityMetric').textContent = '-';
        document.getElementById('sustainabilityMetric').textContent = '-';
        
        // Clear failure analysis
        document.getElementById('failureAnalysisTable').innerHTML = 
            '<p class="text-gray-500 text-center py-8">No failure analysis data available. Please upload and process data first.</p>';
    }
    
    updateMetricsDisplay() {
        if (!this.currentMetrics || this.currentMetrics.length === 0) {
            return;
        }
        
        // Calculate average metrics across all catchments
        const avgMetrics = {
            reliability: 0,
            resilience: 0,
            vulnerability: 0,
            sustainability: 0
        };
        
        this.currentMetrics.forEach(metric => {
            avgMetrics.reliability += metric.reliability || 0;
            avgMetrics.resilience += metric.resilience || 0;
            avgMetrics.vulnerability += metric.vulnerability || 0;
            avgMetrics.sustainability += metric.sustainability || 0;
        });
        
        const count = this.currentMetrics.length;
        Object.keys(avgMetrics).forEach(key => {
            avgMetrics[key] = (avgMetrics[key] / count).toFixed(3);
        });
        
        document.getElementById('reliabilityMetric').textContent = avgMetrics.reliability;
        document.getElementById('resilienceMetric').textContent = avgMetrics.resilience;
        document.getElementById('vulnerabilityMetric').textContent = avgMetrics.vulnerability;
        document.getElementById('sustainabilityMetric').textContent = avgMetrics.sustainability;
    }
    
    updateFailureAnalysis(failureData) {
        const container = document.getElementById('failureAnalysisTable');
        
        if (!failureData || failureData.length === 0) {
            container.innerHTML = '<p class="text-gray-500 text-center py-8">No failure analysis data available.</p>';
            return;
        }
        
        let html = `
            <table class="w-full text-sm">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-4 py-2 text-left">Catchment</th>
                        <th class="px-4 py-2 text-left">Year</th>
                        <th class="px-4 py-2 text-left">Month</th>
                        <th class="px-4 py-2 text-left">Total Records</th>
                        <th class="px-4 py-2 text-left">GWR Failures</th>
                        <th class="px-4 py-2 text-left">GWL Failures</th>
                        <th class="px-4 py-2 text-left">GWB Failures</th>
                        <th class="px-4 py-2 text-left">Failure Rate</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        failureData.forEach(row => {
            const totalFailures = (row.gwr_failures || 0) + (row.gwl_failures || 0) + (row.gwb_failures || 0);
            const failureRate = row.total_records > 0 ? 
                ((totalFailures / (row.total_records * 3)) * 100).toFixed(1) : '0.0';
            
            html += `
                <tr class="border-b hover:bg-gray-50">
                    <td class="px-4 py-2">${row.catchment_name}</td>
                    <td class="px-4 py-2">${row.year}</td>
                    <td class="px-4 py-2">${row.month}</td>
                    <td class="px-4 py-2">${row.total_records}</td>
                    <td class="px-4 py-2">${row.gwr_failures || 0}</td>
                    <td class="px-4 py-2">${row.gwl_failures || 0}</td>
                    <td class="px-4 py-2">${row.gwb_failures || 0}</td>
                    <td class="px-4 py-2">${failureRate}%</td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        container.innerHTML = html;
    }
    
    initCharts() {
        // Initialize empty charts
        this.initTimeSeriesChart();
        this.initClassificationChart();
    }
    
    initTimeSeriesChart() {
        const ctx = document.getElementById('timeSeriesChart').getContext('2d');
        
        if (this.charts.timeSeries) {
            this.charts.timeSeries.destroy();
        }
        
        this.charts.timeSeries = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Original Values',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4
                }, {
                    label: 'Z-scores',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.4,
                    yAxisID: 'y1'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Original Values'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Z-scores'
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Date'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true
                    },
                    title: {
                        display: true,
                        text: 'Time Series Analysis'
                    }
                }
            }
        });
    }
    
    initClassificationChart() {
        const ctx = document.getElementById('classificationChart').getContext('2d');
        
        if (this.charts.classification) {
            this.charts.classification.destroy();
        }
        
        this.charts.classification = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        '#3b82f6',  // Surplus
                        '#22c55e',  // Normal
                        '#eab308',  // Moderate
                        '#f97316',  // Severe
                        '#ef4444'   // Extreme
                    ],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    title: {
                        display: true,
                        text: 'Classification Distribution'
                    }
                }
            }
        });
    }
    
    updateCharts() {
        if (!this.currentData || this.currentData.length === 0) {
            return;
        }
        
        // Update time series chart
        this.updateTimeSeriesChart();
        
        // Update classification chart
        this.updateClassificationChart();
    }
    
    updateTimeSeriesChart() {
        if (!this.charts.timeSeries) return;
        
        const sortedData = this.currentData.sort((a, b) => new Date(a.measurement_date) - new Date(b.measurement_date));
        
        const labels = sortedData.map(item => new Date(item.measurement_date).toLocaleDateString());
        const originalValues = sortedData.map(item => item.original_value);
        const zScores = sortedData.map(item => item.zscore);
        
        this.charts.timeSeries.data.labels = labels;
        this.charts.timeSeries.data.datasets[0].data = originalValues;
        this.charts.timeSeries.data.datasets[1].data = zScores;
        
        // Update dataset labels based on parameter
        const parameter = document.getElementById('parameterFilter').value;
        const parameterLabels = {
            'GWR': 'Groundwater Recharge (mm)',
            'GWL': 'Groundwater Level (m)',
            'GWB': 'Groundwater Baseflow (m³/s)'
        };
        
        this.charts.timeSeries.data.datasets[0].label = parameterLabels[parameter];
        
        this.charts.timeSeries.update();
    }
    
    updateClassificationChart() {
        if (!this.charts.classification) return;
        
        // Count classifications
        const classificationCounts = {
            'Surplus': 0,
            'Normal': 0,
            'Moderate_Deficit': 0,
            'Severe_Deficit': 0,
            'Extreme_Deficit': 0
        };
        
        this.currentData.forEach(item => {
            if (item.classification && classificationCounts.hasOwnProperty(item.classification)) {
                classificationCounts[item.classification]++;
            }
        });
        
        const labels = Object.keys(classificationCounts).map(key => 
            key.replace('_', ' ').replace('Deficit', 'Deficit')
        );
        const data = Object.values(classificationCounts);
        
        this.charts.classification.data.labels = labels;
        this.charts.classification.data.datasets[0].data = data;
        
        this.charts.classification.update();
    }
    
    async exportData() {
        const filters = {
            catchment: document.getElementById('catchmentFilter').value,
            parameter: document.getElementById('parameterFilter').value,
            start_date: document.getElementById('startDateFilter').value,
            end_date: document.getElementById('endDateFilter').value
        };
        
        const params = new URLSearchParams();
        Object.keys(filters).forEach(key => {
            if (filters[key]) params.append(key, filters[key]);
        });
        
        try {
            this.showLoading('Preparing export...');
            
            const response = await fetch(`${this.apiBase}/export?${params}`);
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Export failed');
            }
            
            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `groundwater_analysis_${new Date().toISOString().split('T')[0]}.xlsx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            this.showMessage('Data exported successfully', 'success');
            
        } catch (error) {
            console.error('Export failed:', error);
            this.showMessage(error.message || 'Export failed', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async viewSource(sourceId) {
        // Set filters to show data from this source
        document.getElementById('catchmentFilter').value = '';
        document.getElementById('parameterFilter').value = 'GWR';
        document.getElementById('startDateFilter').value = '';
        document.getElementById('endDateFilter').value = '';
        
        try {
            const response = await fetch(`${this.apiBase}/data?source_id=${sourceId}`);
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.error || 'Failed to load source data');
            }
            
            this.currentData = result.data;
            this.updateCharts();
            
            this.showMessage(`Viewing data from source ID ${sourceId}`, 'info');
            
        } catch (error) {
            console.error('Failed to view source:', error);
            this.showMessage(error.message || 'Failed to load source data', 'error');
        }
    }
    
    async deleteSource(sourceId) {
        if (!confirm('Are you sure you want to delete this data source? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBase}/sources/${sourceId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to delete source');
            }
            
            await this.loadDataSources();
            await this.loadCatchments();
            
            this.showMessage('Data source deleted successfully', 'success');
            
        } catch (error) {
            console.error('Failed to delete source:', error);
            this.showMessage(error.message || 'Failed to delete source', 'error');
        }
    }
    
    showThresholdModal() {
        document.getElementById('thresholdModal').classList.remove('hidden');
        document.getElementById('thresholdModal').classList.add('flex');
    }
    
    hideThresholdModal() {
        document.getElementById('thresholdModal').classList.add('hidden');
        document.getElementById('thresholdModal').classList.remove('flex');
    }
    
    showLoading(message = 'Loading...') {
        document.getElementById('loadingText').textContent = message;
        document.getElementById('loadingOverlay').style.display = 'flex';
    }
    
    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
    
    showMessage(message, type = 'info') {
        const container = document.getElementById('messageContainer');
        
        const messageEl = document.createElement('div');
        messageEl.className = `mb-4 p-4 rounded-lg shadow-lg transition-all duration-300 transform translate-x-full`;
        
        const colors = {
            success: 'bg-green-100 text-green-800 border border-green-200',
            error: 'bg-red-100 text-red-800 border border-red-200',
            warning: 'bg-yellow-100 text-yellow-800 border border-yellow-200',
            info: 'bg-blue-100 text-blue-800 border border-blue-200'
        };
        
        messageEl.className += ` ${colors[type] || colors.info}`;
        messageEl.innerHTML = `
            <div class="flex items-center justify-between">
                <span>${message}</span>
                <button class="ml-4 text-lg font-bold opacity-70 hover:opacity-100" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;
        
        container.appendChild(messageEl);
        
        // Animate in
        setTimeout(() => {
            messageEl.classList.remove('translate-x-full');
        }, 100);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (messageEl.parentElement) {
                messageEl.classList.add('translate-x-full');
                setTimeout(() => {
                    if (messageEl.parentElement) {
                        messageEl.remove();
                    }
                }, 300);
            }
        }, 5000);
    }
}

// Initialize the application
const app = new GroundwaterApp();