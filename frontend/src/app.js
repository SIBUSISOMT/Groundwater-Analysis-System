// Groundwater Analysis System Frontend - Fixed Version
// Main JavaScript Application with Better Loading Management

class GroundwaterApp {
    constructor() {
        this.apiBase = 'http://localhost:5000/api';
        this.charts = {};
        this.currentData = null;
        this.currentMetrics = null;
        this.retryAttempts = 3;
        this.retryDelay = 1000;
        this.isLoading = false; // Track loading state
        this.initialized = false; // Track initialization state
        
        this.init();
    }
    
    async init() {
        if (this.initialized) {
            console.warn('App already initialized');
            return;
        }
        
        try {
            this.showMessage('Initializing application...', 'info');
            this.setupEventListeners();
            
            // Only do initial health check - don't reload everything repeatedly
            const isHealthy = await this.checkApiHealth();
            
            if (isHealthy) {
                await this.loadInitialData();
                this.initCharts();
                this.showMessage('Application ready', 'success');
            } else {
                this.showMessage('Backend server is not responding. Please start the server and refresh.', 'warning');
            }
            
            this.initialized = true;
            
        } catch (error) {
            console.error('Initialization failed:', error);
            this.showMessage('System initialization failed. Please refresh the page.', 'error');
        }
    }
    
    async loadInitialData() {
        // Load data only once during initialization
        try {
            await this.loadCatchments();
            await this.loadDataSources();
        } catch (error) {
            console.error('Failed to load initial data:', error);
            // Don't fail completely, just show warning
            this.showMessage('Some initial data could not be loaded', 'warning');
        }
    }
    
    setupEventListeners() {
        // File upload
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        
        if (fileInput && dropZone) {
            dropZone.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handleFileUpload(e.target.files[0]);
                }
            });
            
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
        }
        
        // Filters - prevent multiple rapid calls
        const applyFiltersBtn = document.getElementById('applyFilters');
        const clearFiltersBtn = document.getElementById('clearFilters');
        const exportDataBtn = document.getElementById('exportData');
        
        if (applyFiltersBtn) {
            applyFiltersBtn.addEventListener('click', this.debounce(() => this.applyFilters(), 500));
        }
        if (clearFiltersBtn) clearFiltersBtn.addEventListener('click', () => this.clearFilters());
        if (exportDataBtn) exportDataBtn.addEventListener('click', () => this.exportData());
        
        // Modal controls
        const settingsBtn = document.getElementById('settingsBtn');
        const closeModalBtn = document.getElementById('closeThresholdModal');
        
        if (settingsBtn) settingsBtn.addEventListener('click', () => this.showThresholdModal());
        if (closeModalBtn) closeModalBtn.addEventListener('click', () => this.hideThresholdModal());
        
        // Parameter change - debounced
        const parameterFilter = document.getElementById('parameterFilter');
        if (parameterFilter) {
            parameterFilter.addEventListener('change', this.debounce(() => {
                if (this.currentData && !this.isLoading) {
                    this.applyFilters();
                }
            }, 300));
        }
    }
    
    // Debounce function to prevent rapid API calls
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    async makeApiCall(endpoint, options = {}) {
        // Prevent concurrent calls to same endpoint
        const requestKey = `${endpoint}:${JSON.stringify(options)}`;
        if (this.activeRequests?.has(requestKey)) {
            console.warn('Duplicate request blocked:', requestKey);
            throw new Error('Request already in progress');
        }
        
        if (!this.activeRequests) {
            this.activeRequests = new Set();
        }
        
        this.activeRequests.add(requestKey);
        
        try {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout: 30000, // 30 second timeout
                ...options
            };
            
            let lastError = null;
            
            for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), defaultOptions.timeout);
                    
                    const response = await fetch(`${this.apiBase}${endpoint}`, {
                        ...defaultOptions,
                        signal: controller.signal
                    });
                    
                    clearTimeout(timeoutId);
                    
                    // If successful or client error, return the response
                    if (response.ok || response.status < 500) {
                        return response;
                    }
                    
                    // For server errors, retry
                    lastError = new Error(`Server error: ${response.status}`);
                    
                } catch (error) {
                    lastError = error;
                    
                    // Don't retry for certain errors
                    if (error.name === 'AbortError' || error.message.includes('NetworkError')) {
                        break;
                    }
                    
                    console.warn(`API call attempt ${attempt} failed:`, error.message);
                }
                
                // Wait before retrying (except on last attempt)
                if (attempt < this.retryAttempts) {
                    await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt));
                }
            }
            
            throw lastError || new Error('API call failed after all retries');
            
        } finally {
            this.activeRequests.delete(requestKey);
        }
    }
   
    
    async loadCatchments() {
        try {
            const response = await this.makeApiCall('/catchments');
            
            if (!response.ok) {
                throw new Error(`Failed to load catchments: ${response.status}`);
            }
            
            const data = await response.json();
            
            const select = document.getElementById('catchmentFilter');
            if (select) {
                select.innerHTML = '<option value="">All Catchments</option>';
                
                if (data.catchments && Array.isArray(data.catchments)) {
                    data.catchments.forEach(catchment => {
                        const option = document.createElement('option');
                        option.value = catchment.catchment_name || '';
                        option.textContent = `${catchment.catchment_name || 'Unknown'} (${catchment.total_records || 0} records)`;
                        select.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load catchments:', error);
            // Don't show error message for initial load failures
            if (this.initialized) {
                this.showMessage('Failed to load catchments', 'warning');
            }
        }
    }
    
    async loadDataSources() {
        try {
            const response = await this.makeApiCall('/sources');
            
            if (!response.ok) {
                throw new Error(`Failed to load data sources: ${response.status}`);
            }
            
            const data = await response.json();
            
            const container = document.getElementById('dataSourcesTable');
            if (!container) return;
            
            if (!data.sources || !Array.isArray(data.sources) || data.sources.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-8">No data sources available. Upload an Excel file to get started.</p>';
                return;
            }
            
            const table = this.createDataSourcesTable(data.sources);
            container.innerHTML = table;
            
        } catch (error) {
            console.error('Failed to load data sources:', error);
            const container = document.getElementById('dataSourcesTable');
            if (container && this.initialized) {
                container.innerHTML = '<p class="text-red-500 text-center py-8">Failed to load data sources. Please refresh the page.</p>';
                this.showMessage('Failed to load data sources', 'error');
            }
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
            
            const fileName = source.file_name || 'Unknown';
            const uploadDate = source.upload_date ? new Date(source.upload_date).toLocaleDateString() : 'Unknown';
            
            html += `
                <tr class="border-b hover:bg-gray-50">
                    <td class="px-4 py-2" title="${fileName}">${fileName.length > 50 ? fileName.substring(0, 47) + '...' : fileName}</td>
                    <td class="px-4 py-2">${uploadDate}</td>
                    <td class="px-4 py-2">${source.file_size_kb || 0}</td>
                    <td class="px-4 py-2">${source.processed_records || 0}</td>
                    <td class="px-4 py-2 ${statusClass}">${source.processing_status || 'Unknown'}</td>
                    <td class="px-4 py-2">${dateRange}</td>
                    <td class="px-4 py-2">
                        <button onclick="app.viewSource(${source.source_id})" class="text-blue-600 hover:text-blue-800 mr-2" title="View Data">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button onclick="app.deleteSource(${source.source_id})" class="text-red-600 hover:text-red-800" title="Delete Source">
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
        if (!file || this.isLoading) return;

        // Get selected category and subcatchment
        const category = this.getElementValue('categorySelect');
        const subcatchment = this.getElementValue('subcatchmentSelect');

        if (!category || !subcatchment) {
            this.showMessage('Please select both category and subcatchment before uploading.', 'error');
            return;
        }

        // Validate file
        if (!file.name.match(/\.(xlsx|xls)$/)) {
            this.showMessage('Please select an Excel file (.xlsx or .xls)', 'error');
            return;
        }
        
        if (file.size > 16 * 1024 * 1024) {
            this.showMessage('File size must be less than 16MB', 'error');
            return;
        }
        
        this.isLoading = true;
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
                throw new Error(result.error || result.message || 'Upload failed');
            }

            // Only refresh after successful upload and processing
            this.showMessage(`File uploaded successfully! ${result.processed_records || 0} records processed.`, 'success');
            await this.loadDataSources();
            await this.loadCatchments();

        } catch (error) {
            console.error('Upload failed:', error);
            this.showMessage(`Upload failed: ${error.message}`, 'error');
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }
    
    async applyFilters() {
        if (this.isLoading) {
            console.warn('Already loading, skipping filter application');
            return;
        }
        
        const filters = {
            catchment: this.getElementValue('catchmentFilter'),
            parameter: this.getElementValue('parameterFilter', 'GWR'),
            start_date: this.getElementValue('startDateFilter'),
            end_date: this.getElementValue('endDateFilter')
        };
        
        this.isLoading = true;
        this.showLoading('Loading data...');
        
        try {
            // Load processed data
            const dataParams = new URLSearchParams();
            Object.keys(filters).forEach(key => {
                if (filters[key]) dataParams.append(key, filters[key]);
            });
            
            const dataResponse = await this.makeApiCall(`/data?${dataParams}`);
            
            if (!dataResponse.ok) {
                const errorData = await dataResponse.json();
                throw new Error(errorData.error || `HTTP ${dataResponse.status}: Failed to load data`);
            }
            
            const dataResult = await dataResponse.json();
            this.currentData = dataResult.data || [];
            
            // Load metrics (non-blocking)
            this.loadMetrics(filters).catch(error => {
                console.warn('Failed to load metrics:', error);
            });
            
            // Load failure analysis (non-blocking)
            this.loadFailureAnalysis(filters).catch(error => {
                console.warn('Failed to load failure analysis:', error);
            });
            
            // Update charts
            this.updateCharts();
            
            this.showMessage(`Data loaded successfully (${this.currentData.length} records)`, 'success');
            
        } catch (error) {
            console.error('Failed to apply filters:', error);
            this.showMessage(`Failed to load data: ${error.message}`, 'error');
            
            // Clear current data on error
            this.currentData = [];
            this.updateCharts();
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }
    
    async loadMetrics(filters) {
        try {
            const metricsParams = new URLSearchParams();
            if (filters.catchment) metricsParams.append('catchment', filters.catchment);
            if (filters.parameter) metricsParams.append('parameter', filters.parameter);
            
            const metricsResponse = await this.makeApiCall(`/metrics?${metricsParams}`);
            if (metricsResponse.ok) {
                const metricsResult = await metricsResponse.json();
                this.currentMetrics = metricsResult.metrics || [];
                this.updateMetricsDisplay();
            }
        } catch (error) {
            console.warn('Metrics loading failed:', error);
        }
    }
    
    async loadFailureAnalysis(filters) {
        try {
            const failureParams = new URLSearchParams();
            if (filters.catchment) failureParams.append('catchment', filters.catchment);
            if (filters.start_date) failureParams.append('start_date', filters.start_date);
            if (filters.end_date) failureParams.append('end_date', filters.end_date);
            
            const failureResponse = await this.makeApiCall(`/failure-analysis?${failureParams}`);
            if (failureResponse.ok) {
                const failureResult = await failureResponse.json();
                this.updateFailureAnalysis(failureResult.failure_analysis || []);
            }
        } catch (error) {
            console.warn('Failure analysis loading failed:', error);
        }
    }
    
    clearFilters() {
        if (this.isLoading) return;
        
        const catchmentFilter = document.getElementById('catchmentFilter');
        const parameterFilter = document.getElementById('parameterFilter');
        const startDateFilter = document.getElementById('startDateFilter');
        const endDateFilter = document.getElementById('endDateFilter');
        
        if (catchmentFilter) catchmentFilter.value = '';
        if (parameterFilter) parameterFilter.value = 'GWR';
        if (startDateFilter) startDateFilter.value = '';
        if (endDateFilter) endDateFilter.value = '';
        
        this.currentData = null;
        this.currentMetrics = null;
        
        // Clear charts
        Object.values(this.charts).forEach(chart => {
            if (chart) {
                try {
                    chart.destroy();
                } catch (e) {
                    console.warn('Error destroying chart:', e);
                }
            }
        });
        this.initCharts();
        
        // Clear metrics
        this.clearMetricsDisplay();
        
        // Clear failure analysis
        const failureTable = document.getElementById('failureAnalysisTable');
        if (failureTable) {
            failureTable.innerHTML = '<p class="text-gray-500 text-center py-8">No failure analysis data available. Please upload and process data first.</p>';
        }
        
        this.showMessage('Filters cleared', 'info');
    }
    
    clearMetricsDisplay() {
        const metrics = ['reliabilityMetric', 'resilienceMetric', 'vulnerabilityMetric', 'sustainabilityMetric'];
        metrics.forEach(metricId => {
            const element = document.getElementById(metricId);
            if (element) element.textContent = '-';
        });
    }
    
    updateMetricsDisplay() {
        if (!this.currentMetrics || !Array.isArray(this.currentMetrics) || this.currentMetrics.length === 0) {
            return;
        }
        
        // Calculate average metrics across all catchments
        const avgMetrics = {
            reliability: 0,
            resilience: 0,
            vulnerability: 0,
            sustainability: 0
        };
        
        let validCount = 0;
        
        this.currentMetrics.forEach(metric => {
            if (metric && typeof metric === 'object') {
                avgMetrics.reliability += metric.reliability || 0;
                avgMetrics.resilience += metric.resilience || 0;
                avgMetrics.vulnerability += metric.vulnerability || 0;
                avgMetrics.sustainability += metric.sustainability || 0;
                validCount++;
            }
        });
        
        if (validCount > 0) {
            Object.keys(avgMetrics).forEach(key => {
                avgMetrics[key] = (avgMetrics[key] / validCount).toFixed(3);
            });
            
            const reliabilityEl = document.getElementById('reliabilityMetric');
            const resilienceEl = document.getElementById('resilienceMetric');
            const vulnerabilityEl = document.getElementById('vulnerabilityMetric');
            const sustainabilityEl = document.getElementById('sustainabilityMetric');
            
            if (reliabilityEl) reliabilityEl.textContent = avgMetrics.reliability;
            if (resilienceEl) resilienceEl.textContent = avgMetrics.resilience;
            if (vulnerabilityEl) vulnerabilityEl.textContent = avgMetrics.vulnerability;
            if (sustainabilityEl) sustainabilityEl.textContent = avgMetrics.sustainability;
        }
    }
    
    updateFailureAnalysis(failureData) {
        const container = document.getElementById('failureAnalysisTable');
        if (!container) return;
        
        if (!failureData || !Array.isArray(failureData) || failureData.length === 0) {
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
            const totalRecords = row.total_records || 0;
            const failureRate = totalRecords > 0 ? 
                ((totalFailures / (totalRecords * 3)) * 100).toFixed(1) : '0.0';
            
            html += `
                <tr class="border-b hover:bg-gray-50">
                    <td class="px-4 py-2">${row.catchment_name || 'Unknown'}</td>
                    <td class="px-4 py-2">${row.year || 'N/A'}</td>
                    <td class="px-4 py-2">${row.month || 'N/A'}</td>
                    <td class="px-4 py-2">${totalRecords}</td>
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
        // Initialize empty charts with error handling
        try {
            this.initTimeSeriesChart();
        } catch (error) {
            console.error('Failed to initialize time series chart:', error);
        }
        
        try {
            this.initClassificationChart();
        } catch (error) {
            console.error('Failed to initialize classification chart:', error);
        }
    }
    
    initTimeSeriesChart() {
        const canvas = document.getElementById('timeSeriesChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (this.charts.timeSeries) {
            try {
                this.charts.timeSeries.destroy();
            } catch (e) {
                console.warn('Error destroying existing chart:', e);
            }
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
                    tension: 0.4,
                    pointRadius: 2
                }, {
                    label: 'Z-scores',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.4,
                    yAxisID: 'y1',
                    pointRadius: 2
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
        const canvas = document.getElementById('classificationChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (this.charts.classification) {
            try {
                this.charts.classification.destroy();
            } catch (e) {
                console.warn('Error destroying existing chart:', e);
            }
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
        if (!this.currentData || !Array.isArray(this.currentData) || this.currentData.length === 0) {
            return;
        }
        
        try {
            this.updateTimeSeriesChart();
        } catch (error) {
            console.error('Failed to update time series chart:', error);
        }
        
        try {
            this.updateClassificationChart();
        } catch (error) {
            console.error('Failed to update classification chart:', error);
        }
    }
    
    updateTimeSeriesChart() {
        if (!this.charts.timeSeries || !this.currentData) return;
        
        const sortedData = [...this.currentData]
            .filter(item => item.measurement_date)
            .sort((a, b) => new Date(a.measurement_date) - new Date(b.measurement_date));
        
        const labels = sortedData.map(item => {
            const date = new Date(item.measurement_date);
            return isNaN(date.getTime()) ? 'Invalid Date' : date.toLocaleDateString();
        });
        
        const originalValues = sortedData.map(item => 
            typeof item.original_value === 'number' ? item.original_value : null
        );
        
        const zScores = sortedData.map(item => 
            typeof item.zscore === 'number' ? item.zscore : null
        );
        
        this.charts.timeSeries.data.labels = labels;
        this.charts.timeSeries.data.datasets[0].data = originalValues;
        this.charts.timeSeries.data.datasets[1].data = zScores;
        
        // Update dataset labels based on parameter
        const parameterFilter = document.getElementById('parameterFilter');
        const parameter = parameterFilter ? parameterFilter.value : 'GWR';
        
        const parameterLabels = {
            'GWR': 'Groundwater Recharge (mm)',
            'GWL': 'Groundwater Level (m)',
            'GWB': 'Groundwater Baseflow (m³/s)'
        };
        
        this.charts.timeSeries.data.datasets[0].label = parameterLabels[parameter] || 'Original Values';
        
        this.charts.timeSeries.update();
    }
    
    updateClassificationChart() {
        if (!this.charts.classification || !this.currentData) return;
        
        // Count classifications
        const classificationCounts = {
            'Surplus': 0,
            'Normal': 0,
            'Moderate_Deficit': 0,
            'Severe_Deficit': 0,
            'Extreme_Deficit': 0
        };
        
        this.currentData.forEach(item => {
            const classification = item.classification;
            if (classification && classificationCounts.hasOwnProperty(classification)) {
                classificationCounts[classification]++;
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
        if (this.isLoading) return;
        
        const filters = {
            catchment: this.getElementValue('catchmentFilter'),
            parameter: this.getElementValue('parameterFilter'),
            start_date: this.getElementValue('startDateFilter'),
            end_date: this.getElementValue('endDateFilter')
        };
        
        const params = new URLSearchParams();
        Object.keys(filters).forEach(key => {
            if (filters[key]) params.append(key, filters[key]);
        });
        
        try {
            this.showLoading('Preparing export...');
            
            const response = await this.makeApiCall(`/export?${params}`);
            
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
            this.showMessage(`Export failed: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async viewSource(sourceId) {
        if (!sourceId || this.isLoading) {
            this.showMessage('Invalid source ID or system is busy', 'error');
            return;
        }
        
        try {
            this.showLoading('Loading source data...');
            
            const response = await this.makeApiCall(`/data?source_id=${sourceId}`);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Failed to load source data (HTTP ${response.status})`);
            }
            
            const result = await response.json();
            
            if (!result.data || !Array.isArray(result.data)) {
                throw new Error('No data available for this source');
            }
            
            // Reset filters to show all data from this source
            const catchmentFilter = document.getElementById('catchmentFilter');
            const parameterFilter = document.getElementById('parameterFilter');
            const startDateFilter = document.getElementById('startDateFilter');
            const endDateFilter = document.getElementById('endDateFilter');
            
            if (catchmentFilter) catchmentFilter.value = '';
            if (parameterFilter) parameterFilter.value = 'GWR';
            if (startDateFilter) startDateFilter.value = '';
            if (endDateFilter) endDateFilter.value = '';
            
            this.currentData = result.data;
            this.updateCharts();
            
            this.showMessage(`Viewing ${result.data.length} records from source ID ${sourceId}`, 'info');
            
        } catch (error) {
            console.error('Failed to view source:', error);
            this.showMessage(`Failed to load source data: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
   
}

// Global error handler for unhandled promise rejections
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    if (window.app) {
        window.app.showMessage('An unexpected error occurred. Please refresh the page.', 'error');
    }
    event.preventDefault();
});

// Global error handler for JavaScript errors
window.addEventListener('error', function(event) {
    console.error('JavaScript error:', event.error);
    if (window.app) {
        window.app.showMessage('A JavaScript error occurred. Please refresh the page.', 'error');
    }
});

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    try {
        // Only initialize once
        if (window.app) {
            console.warn('App already exists, skipping initialization');
            return;
        }
        
        window.app = new GroundwaterApp();
        
        // Add global reference for debugging
        if (typeof window !== 'undefined') {
            window.groundwaterApp = window.app;
        }
        
    } catch (error) {
        console.error('Failed to initialize application:', error);
        document.body.innerHTML += `
            <div class="fixed top-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded z-50">
                <strong>Application Error:</strong> Failed to initialize. Please refresh the page.
            </div>
        `;
    }
});

// Prevent multiple initializations
let appInitialized = false;

// Export for module usage if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GroundwaterApp;
}