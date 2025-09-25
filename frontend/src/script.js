class AIEnhancedGroundwaterSystem {
    constructor() {
        this.apiEndpoints = [
            'http://localhost:5000/api',
            'http://127.0.0.1:5000/api'
        ];
        this.apiBase = this.apiEndpoints[0];
        this.charts = {};
        this.currentData = null;
        this.isLoading = false;
        this.initialized = false;
        this.diagnostics = new DiagnosticsPanel();
        this.aiAssistant = new AdvancedAIAssistant(this); // UPDATED: Advanced AI Assistant
        
        this.init();
    }
    
    async init() {
        if (this.initialized) return;
        
        try {
            this.diagnostics.log('Initializing AI-enhanced system', 'info');
            this.setupEventListeners();
            
            const apiAvailable = await this.testApiConnectivity();
            
            if (apiAvailable) {
                await this.loadInitialData();
                this.initializeCharts();
                this.diagnostics.log('AI system ready', 'good');
                this.showMessage('AI-Enhanced Groundwater Analysis System initialized successfully', 'success');
            } else {
                this.diagnostics.log('API server not responding', 'bad');
                this.showMessage('Backend server not responding. Please check if the server is running.', 'error');
            }
            
            this.initialized = true;
        } catch (error) {
            this.diagnostics.log(`Initialization failed: ${error.message}`, 'bad');
            this.showMessage('System initialization failed', 'error');
        }
    }
    
    async testApiConnectivity() {
        for (const endpoint of this.apiEndpoints) {
            try {
                this.diagnostics.log(`Testing ${endpoint}`, 'info');
                const response = await fetch(`${endpoint}/health`, { 
                    method: 'GET',
                    timeout: 5000 
                });
                
                if (response.ok) {
                    this.apiBase = endpoint;
                    this.diagnostics.log(`Connected to ${endpoint}`, 'good');
                    this.updateConnectionStatus('connected');
                    return true;
                }
            } catch (error) {
                this.diagnostics.log(`${endpoint} failed: ${error.message}`, 'warning');
            }
        }
        
        this.updateConnectionStatus('failed');
        return false;
    }
    
    updateConnectionStatus(status) {
        const indicator = document.getElementById('statusIndicator');
        const text = document.getElementById('statusText');
        
        if (!indicator || !text) return;
        
        switch (status) {
            case 'connected':
                indicator.className = 'w-3 h-3 bg-green-400 rounded-full mr-2';
                text.textContent = 'AI System Online';
                break;
            case 'failed':
                indicator.className = 'w-3 h-3 bg-red-400 rounded-full mr-2';
                text.textContent = 'System Offline';
                break;
            default:
                indicator.className = 'w-3 h-3 bg-yellow-400 rounded-full mr-2';
                text.textContent = 'Connecting...';
        }
    }
    
    setupEventListeners() {
        // File upload
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        
        if (dropZone && fileInput) {
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
        
        // Filter buttons
        const applyBtn = document.getElementById('applyFilters');
        const clearBtn = document.getElementById('clearFilters');
        const exportBtn = document.getElementById('exportData');
        const refreshBtn = document.getElementById('refreshBtn');
        const aiAnalysisBtn = document.getElementById('getAIAnalysis');
        const aiInsightsBtn = document.getElementById('aiInsightsBtn');
        
        if (applyBtn) applyBtn.addEventListener('click', () => this.applyFilters());
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearFilters());
        if (exportBtn) exportBtn.addEventListener('click', () => this.exportData());
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshData());
        if (aiAnalysisBtn) aiAnalysisBtn.addEventListener('click', () => this.getAIAnalysis());
        if (aiInsightsBtn) aiInsightsBtn.addEventListener('click', () => this.toggleAIInsights());
        
        // AI Chat setup
        this.aiAssistant.setupEventListeners();
        
        // Modal controls
        const closeMethodologyBtn = document.getElementById('closeMethodologyModal');
        if (closeMethodologyBtn) closeMethodologyBtn.addEventListener('click', () => this.hideMethodologyModal());
        
        // Diagnostics toggle
        const toggleBtn = document.getElementById('toggleDiagnostics');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const panel = document.getElementById('diagnosticPanel');
                if (panel.style.display === 'none') {
                    panel.style.display = 'block';
                    toggleBtn.textContent = 'Hide';
                } else {
                    panel.style.display = 'none';
                    toggleBtn.textContent = 'Show';
                }
            });
        }
    }
    
    async makeApiRequest(endpoint, options = {}) {
        try {
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return response;
        } catch (error) {
            this.diagnostics.log(`API request failed: ${endpoint} - ${error.message}`, 'bad');
            throw error;
        }
    }
    
    async loadInitialData() {
        try {
            this.diagnostics.log('Loading initial data', 'info');
            await Promise.all([
                this.loadCatchments(),
                this.loadDataSources()
            ]);
            this.diagnostics.log('Initial data loaded', 'good');
        } catch (error) {
            this.diagnostics.log(`Initial data loading failed: ${error.message}`, 'warning');
        }
    }
    
    async loadCatchments() {
        try {
            const response = await this.makeApiRequest('/catchments');
            const data = await response.json();
            
            const select = document.getElementById('catchmentFilter');
            if (select && data.catchments) {
                select.innerHTML = '<option value="">All Catchments</option>';
                data.catchments.forEach(catchment => {
                    const option = document.createElement('option');
                    option.value = catchment.catchment_name || '';
                    option.textContent = `${catchment.catchment_name} (${catchment.total_records || 0} records)`;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            this.diagnostics.log(`Failed to load catchments: ${error.message}`, 'warning');
        }
    }
    
    async loadDataSources() {
        try {
            const response = await this.makeApiRequest('/sources');
            const data = await response.json();
            
            const container = document.getElementById('dataSourcesTable');
            if (!container) return;
            
            if (!data.sources || data.sources.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <i class="fas fa-database text-4xl mb-4"></i>
                        <p>No data sources found</p>
                        <p class="text-sm">Upload an Excel file to get started with AI analysis</p>
                    </div>
                `;
                return;
            }
            
            this.renderDataSourcesTable(data.sources, container);
        } catch (error) {
            this.diagnostics.log(`Failed to load data sources: ${error.message}`, 'warning');
        }
    }
    
    renderDataSourcesTable(sources, container) {
        const table = `
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-2 text-left">File Name</th>
                            <th class="px-4 py-2 text-left">Upload Date</th>
                            <th class="px-4 py-2 text-left">Records</th>
                            <th class="px-4 py-2 text-left">Status</th>
                            <th class="px-4 py-2 text-left">AI Score</th>
                            <th class="px-4 py-2 text-left">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sources.map(source => `
                            <tr class="border-b hover:bg-gray-50">
                                <td class="px-4 py-2">${source.file_name || 'Unknown'}</td>
                                <td class="px-4 py-2">${source.upload_date ? new Date(source.upload_date).toLocaleDateString() : 'N/A'}</td>
                                <td class="px-4 py-2">${source.processed_records || 0}</td>
                                <td class="px-4 py-2">
                                    <span class="px-2 py-1 text-xs rounded ${
                                        source.processing_status === 'Completed' ? 'bg-green-100 text-green-800' :
                                        source.processing_status === 'Failed' ? 'bg-red-100 text-red-800' :
                                        'bg-yellow-100 text-yellow-800'
                                    }">
                                        ${source.processing_status || 'Unknown'}
                                    </span>
                                </td>
                                <td class="px-4 py-2">
                                    <div class="flex items-center">
                                        <div class="w-2 h-2 rounded-full ${
                                            source.processing_status === 'Completed' ? 'bg-green-400' : 
                                            source.processing_status === 'Failed' ? 'bg-red-400' : 'bg-yellow-400'
                                        } mr-2"></div>
                                        <span class="text-xs">${
                                            source.processing_status === 'Completed' ? 'Good' : 
                                            source.processing_status === 'Failed' ? 'Poor' : 'Processing'
                                        }</span>
                                    </div>
                                </td>
                                <td class="px-4 py-2">
                                    <button onclick="app.viewSource(${source.source_id})" class="text-blue-600 hover:text-blue-800 mr-2" title="View">
                                        <i class="fas fa-eye"></i>
                                    </button>
                                    <button onclick="app.getSourceAIAnalysis(${source.source_id})" class="text-purple-600 hover:text-purple-800 mr-2" title="AI Analysis">
                                        <i class="fas fa-brain"></i>
                                    </button>
                                    <button onclick="app.deleteSource(${source.source_id})" class="text-red-600 hover:text-red-800" title="Delete">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = table;
    }

    // ENHANCED FILE UPLOAD WITH AI INTEGRATION
    async handleFileUpload(file) {
        if (!file || this.isLoading) return;
        
        const category = document.getElementById('categorySelect')?.value;
        const subcatchment = document.getElementById('subcatchmentSelect')?.value;
        
        if (!category || !subcatchment) {
            this.showMessage('Please select both category and subcatchment before uploading', 'error');
            return;
        }
        
        if (!file.name.match(/\.(xlsx|xls)$/)) {
            this.showMessage('Please select an Excel file (.xlsx or .xls)', 'error');
            return;
        }
        
        if (file.size > 16 * 1024 * 1024) {
            this.showMessage('File size must be less than 16MB', 'error');
            return;
        }
        
        this.isLoading = true;
        this.showLoading('Analyzing and uploading file with AI enhancement...');
        this.diagnostics.log(`AI analyzing upload: ${file.name}`, 'info');
        
        // Show upload analysis panel
        const analysisPanel = document.getElementById('uploadAnalysis');
        const analysisContent = document.getElementById('uploadAnalysisContent');
        if (analysisPanel && analysisContent) {
            analysisPanel.classList.remove('hidden');
            analysisContent.innerHTML = '<div class="loading-dots text-blue-700">AI analyzing data quality and structure</div>';
        }
        
        try {
            // First, analyze the file with AI
            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', category);
            formData.append('subcatchment', subcatchment);
            
            // Try to get AI analysis first
            let aiAnalysisResult = null;
            try {
                const aiResponse = await fetch(`${this.apiBase}/ai/analyze-upload`, {
                    method: 'POST',
                    body: formData
                });
                
                if (aiResponse.ok) {
                    aiAnalysisResult = await aiResponse.json();
                    this.displayUploadAnalysis(aiAnalysisResult);
                    this.diagnostics.log('AI upload analysis completed', 'good');
                }
            } catch (aiError) {
                this.diagnostics.log(`AI analysis failed: ${aiError.message}`, 'warning');
                if (analysisContent) {
                    analysisContent.innerHTML = '<div class="text-yellow-700"><i class="fas fa-exclamation-triangle mr-2"></i>AI analysis unavailable - proceeding with standard upload</div>';
                }
            }
            
            // Create new FormData for actual upload (can't reuse the same FormData)
            const uploadFormData = new FormData();
            uploadFormData.append('file', file);
            uploadFormData.append('category', category);
            uploadFormData.append('subcatchment', subcatchment);
            
            // Proceed with normal upload
            const response = await fetch(`${this.apiBase}/upload`, {
                method: 'POST',
                body: uploadFormData
            });
            
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.error || 'Upload failed');
            }
            
            this.diagnostics.log(`Upload successful: ${result.processed_records || 0} records`, 'good');
            
            // Enhanced success message with AI insights
            let successMessage = `File uploaded successfully! ${result.processed_records || 0} records processed.`;
            if (aiAnalysisResult && aiAnalysisResult.data_quality_score) {
                successMessage += ` Data quality: ${aiAnalysisResult.data_quality_score}`;
            }
            
            this.showMessage(successMessage, 'success');
            
            // Store upload info for AI context
            localStorage.setItem('lastUploadTime', new Date().toISOString());
            
            // Notify AI about successful upload
            if (result.processed_records > 0) {
                this.aiAssistant.onDataUploaded({
                    fileName: file.name,
                    recordsProcessed: result.processed_records,
                    category: category,
                    subcatchment: subcatchment,
                    dataQuality: aiAnalysisResult?.data_quality_score || 'Unknown',
                    aiInsights: aiAnalysisResult?.insights || null,
                    recommendations: aiAnalysisResult?.recommendations || []
                });
            }
            
            // Auto-generate AI insights after successful upload
            setTimeout(() => {
                if (this.currentData && this.currentData.length > 0) {
                    this.getAIAnalysis();
                }
            }, 1500);
            
            // Refresh data sources and catchments
            await Promise.all([
                this.loadDataSources(),
                this.loadCatchments()
            ]);
            
            // Clear file input
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.value = '';
            
        } catch (error) {
            this.diagnostics.log(`Upload failed: ${error.message}`, 'bad');
            this.showMessage(`Upload failed: ${error.message}`, 'error');
            
            // Enhanced error explanation with AI help
            if (analysisContent) {
                analysisContent.innerHTML = `
                    <div class="text-red-700">
                        <i class="fas fa-exclamation-triangle mr-2"></i>
                        Upload failed: ${error.message}
                    </div>
                    <button onclick="app.aiAssistant.explainError('Upload failed: ${error.message.replace(/'/g, "\\'")}', {file: '${file.name}', category: '${category}', subcatchment: '${subcatchment}'})" 
                            class="text-blue-600 hover:text-blue-800 text-sm mt-2 block">
                        <i class="fas fa-robot mr-1"></i>Get AI help with this error
                    </button>
                `;
            }
            
            // Ask AI to help with the error
            setTimeout(() => {
                this.aiAssistant.explainError(`Upload failed: ${error.message}`, {
                    file: file.name,
                    category: category,
                    subcatchment: subcatchment,
                    fileSize: file.size,
                    timestamp: new Date().toISOString()
                });
            }, 1000);
            
        } finally {
            this.isLoading = false;
            this.hideLoading();
            
            // Hide upload analysis panel after a delay
            setTimeout(() => {
                if (analysisPanel) {
                    analysisPanel.classList.add('hidden');
                }
            }, 10000);
        }
    }

    // ENHANCED APPLY FILTERS WITH AI INTEGRATION
    async applyFilters() {
        if (this.isLoading) return;
        
        const filters = {
            catchment: document.getElementById('catchmentFilter')?.value || '',
            parameter: document.getElementById('parameterFilter')?.value || 'RECHARGE',
            start_date: document.getElementById('startDateFilter')?.value || '',
            end_date: document.getElementById('endDateFilter')?.value || ''
        };
        
        this.isLoading = true;
        this.showLoading('Loading data with AI-enhanced analysis...');
        this.diagnostics.log('Applying filters with AI enhancement', 'info');
        
        // Clear previous AI insights
        const aiPanel = document.getElementById('aiInsightsPanel');
        if (aiPanel) {
            aiPanel.classList.add('hidden');
        }
        
        try {
            // Build query parameters
            const params = new URLSearchParams();
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.append(key, value);
            });
            
            // Fetch data from API
            const response = await this.makeApiRequest(`/data?${params}`);
            const result = await response.json();
            
            this.currentData = result.data || [];
            this.diagnostics.log(`Loaded ${this.currentData.length} records`, 'good');
            
            // Update charts and metrics
            this.updateCharts();
            await Promise.all([
                this.loadMetrics(filters),
                this.loadFailureAnalysis(filters)
            ]);
            
            // Calculate failure rate for AI context
            const failureRate = this.calculateCurrentFailureRate();
            const failureCount = this.currentData.filter(d => d.is_failure === 1).length;
            
            // Enhanced success message with data insights
            let message = `Loaded ${this.currentData.length} records`;
            if (this.currentData.length > 0) {
                message += ` with ${failureRate.toFixed(1)}% failure rate`;
                
                // Add context about data quality
                if (failureRate > 30) {
                    message += ' (High stress detected)';
                } else if (failureRate > 15) {
                    message += ' (Moderate concerns)';
                } else {
                    message += ' (Good performance)';
                }
            }
            
            this.showMessage(message, 'success');
            
            // Notify AI about filter application with detailed context
            if (this.currentData && this.currentData.length > 0) {
                const dataInsights = this.generateDataInsights();
                
                this.aiAssistant.onFiltersApplied({
                    filters: filters,
                    resultCount: this.currentData.length,
                    failureRate: failureRate,
                    failureCount: failureCount,
                    dateRange: this.getDataDateRange(),
                    catchments: this.getUniqueCatchments(),
                    parameters: this.getUniqueParameters(),
                    dataInsights: dataInsights,
                    timestamp: new Date().toISOString()
                });
                
                // Auto-generate AI analysis if significant data is loaded
                if (this.currentData.length > 10) {
                    setTimeout(() => {
                        this.getAIAnalysis();
                    }, 2000);
                }
            } else {
                // No data found - AI can help explain why
                setTimeout(() => {
                    this.aiAssistant.sendMessage(`I applied filters but got no data. Can you help me understand why and suggest what to try next? My filters were: ${JSON.stringify(filters, null, 2)}`);
                }, 1000);
            }
            
        } catch (error) {
            this.diagnostics.log(`Filter application failed: ${error.message}`, 'bad');
            this.showMessage(`Failed to load data: ${error.message}`, 'error');
            
            // Clear current data and charts
            this.currentData = [];
            this.updateCharts();
            this.clearMetrics();
            this.clearFailureAnalysis();
            
            // AI assistance with filter errors
            setTimeout(() => {
                this.aiAssistant.explainError(`Filter application failed: ${error.message}`, {
                    filters: filters,
                    timestamp: new Date().toISOString(),
                    context: 'data_filtering'
                });
            }, 1500);
            
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    // HELPER FUNCTIONS FOR AI INTEGRATION
    calculateCurrentFailureRate() {
        if (!this.currentData || this.currentData.length === 0) return 0;
        const failures = this.currentData.filter(d => d.is_failure === 1).length;
        return (failures / this.currentData.length) * 100;
    }

    generateDataInsights() {
        if (!this.currentData || this.currentData.length === 0) return {};
        
        const insights = {
            totalRecords: this.currentData.length,
            failureAnalysis: {},
            temporalCoverage: {},
            severityAnalysis: {}
        };
        
        // Failure analysis
        const failures = this.currentData.filter(d => d.is_failure === 1);
        insights.failureAnalysis = {
            count: failures.length,
            rate: (failures.length / this.currentData.length) * 100,
            severity: failures.length > 0 ? 'high' : 'low'
        };
        
        // Temporal coverage
        if (this.currentData.length > 0 && this.currentData[0].measurement_date) {
            const dates = this.currentData.map(d => new Date(d.measurement_date)).filter(d => !isNaN(d));
            if (dates.length > 0) {
                insights.temporalCoverage = {
                    startDate: new Date(Math.min(...dates)).toISOString().split('T')[0],
                    endDate: new Date(Math.max(...dates)).toISOString().split('T')[0],
                    timeSpan: Math.ceil((Math.max(...dates) - Math.min(...dates)) / (1000 * 60 * 60 * 24))
                };
            }
        }
        
        // Severity analysis
        const classifications = {};
        this.currentData.forEach(d => {
            if (d.classification) {
                classifications[d.classification] = (classifications[d.classification] || 0) + 1;
            }
        });
        insights.severityAnalysis = classifications;
        
        return insights;
    }

    getDataDateRange() {
        if (!this.currentData || this.currentData.length === 0) return null;
        
        const dates = this.currentData
            .map(d => d.measurement_date)
            .filter(date => date)
            .map(date => new Date(date))
            .filter(date => !isNaN(date))
            .sort((a, b) => a - b);
        
        if (dates.length === 0) return null;
        
        return {
            start: dates[0].toISOString().split('T')[0],
            end: dates[dates.length - 1].toISOString().split('T')[0],
            span_days: Math.ceil((dates[dates.length - 1] - dates[0]) / (1000 * 60 * 60 * 24))
        };
    }

    getUniqueCatchments() {
        if (!this.currentData) return [];
        return [...new Set(this.currentData.map(d => d.catchment_name).filter(c => c))];
    }

    getUniqueParameters() {
        if (!this.currentData) return [];
        return [...new Set(this.currentData.map(d => d.parameter_type).filter(p => p))];
    }

    displayUploadAnalysis(analysis) {
        const content = document.getElementById('uploadAnalysisContent');
        if (!content || !analysis.insights) return;
        
        const quality = analysis.insights.data_quality || {};
        const recommendations = analysis.recommendations || [];
        const columnAnalysis = analysis.insights.column_analysis || {};
        const temporalAnalysis = analysis.insights.temporal_analysis || {};
        
        content.innerHTML = `
            <div class="space-y-4">
                <div class="flex items-center justify-between">
                    <span class="font-medium">AI Data Quality Score:</span>
                    <span class="px-3 py-1 rounded-full text-sm font-medium ${
                        quality.quality_score === 'Good' ? 'bg-green-100 text-green-800' :
                        quality.quality_score === 'Fair' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-red-100 text-red-800'
                    }">${quality.quality_score || 'Analyzing...'}</span>
                </div>
                
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div class="space-y-1">
                        <div><span class="font-medium">Records:</span> ${quality.total_rows || 0}</div>
                        <div><span class="font-medium">Columns:</span> ${quality.total_columns || 0}</div>
                        <div><span class="font-medium">Missing Data:</span> ${(quality.missing_data_percentage || 0).toFixed(1)}%</div>
                    </div>
                    <div class="space-y-1">
                        <div><span class="font-medium">Duplicates:</span> ${quality.duplicate_rows || 0}</div>
                        <div><span class="font-medium">Empty Rows:</span> ${quality.empty_rows || 0}</div>
                        ${temporalAnalysis.has_date_column ? 
                            `<div><span class="font-medium">Date Range:</span> ${temporalAnalysis.total_time_points || 0} points</div>` : 
                            '<div class="text-orange-600"><i class="fas fa-exclamation-triangle mr-1"></i>No date column detected</div>'
                        }
                    </div>
                </div>
                
                ${columnAnalysis.missing_columns && columnAnalysis.missing_columns.length > 0 ? `
                    <div class="bg-orange-50 border border-orange-200 rounded p-3">
                        <div class="text-sm font-medium text-orange-800 mb-1">Missing Expected Columns:</div>
                        <div class="text-sm text-orange-700">${columnAnalysis.missing_columns.join(', ')}</div>
                    </div>
                ` : ''}
                
                                ${recommendations.length > 0 ? `
                    <div class="bg-blue-50 border border-blue-200 rounded p-3">
                        <div class="text-sm font-medium text-blue-800 mb-2">AI Recommendations:</div>
                        <ul class="text-sm space-y-1 text-blue-700">
                            ${recommendations.slice(0, 4).map(rec => `<li>• ${rec}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                
                <div class="flex items-center justify-between pt-2 border-t border-gray-200">
                    <button onclick="app.aiAssistant.explainUploadAnalysis()" 
                            class="text-blue-600 hover:text-blue-800 text-sm font-medium">
                        <i class="fas fa-brain mr-1"></i>Ask AI for detailed analysis
                    </button>
                    <div class="text-xs text-gray-500">
                        Powered by AI • ${new Date().toLocaleTimeString()}
                    </div>
                </div>
            </div>
        `;
    }

    // ENHANCED AI INTEGRATION METHODS
    async explainMetric(metricName) {
        const message = `Can you explain the ${metricName} metric in detail? How is it calculated and what does it mean for my specific groundwater system?`;
        this.aiAssistant.openChat();
        setTimeout(() => {
            this.aiAssistant.sendMessage(message);
        }, 500);
    }

    async askAIAboutChart(chartType) {
        let message;
        if (chartType === 'timeSeries') {
            message = "Looking at my time series chart, what patterns do you see? What do these trends tell us about the groundwater system's health over time?";
        } else if (chartType === 'classification') {
            message = "Can you interpret my classification distribution chart? What does this tell us about the overall system performance and what should I be concerned about?";
        }
        
        this.aiAssistant.openChat();
        setTimeout(() => {
            this.aiAssistant.sendMessage(message);
        }, 500);
    }

    async getSourceAIAnalysis(sourceId) {
        this.showLoading('Getting AI analysis for data source...');
        
        try {
            // Load the source data first
            const response = await this.makeApiRequest(`/data?source_id=${sourceId}`);
            const result = await response.json();
            
            if (result.data && result.data.length > 0) {
                // Get AI analysis
                const analysisResponse = await fetch(`${this.apiBase}/ai/analyze-data`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        data: result.data,
                        filters: { source_id: sourceId }
                    })
                });
                
                if (analysisResponse.ok) {
                    const analysis = await analysisResponse.json();
                    this.displaySourceAnalysis(sourceId, analysis);
                } else {
                    throw new Error('AI analysis unavailable');
                }
            } else {
                this.showMessage('No data available for this source', 'warning');
            }
            
        } catch (error) {
            this.showMessage(`AI analysis failed: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }

    displaySourceAnalysis(sourceId, analysis) {
        // Create a modal or panel to show source-specific analysis
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.innerHTML = `
            <div class="bg-white p-6 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-96 overflow-y-auto">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg font-semibold">AI Analysis - Source ${sourceId}</h3>
                    <button onclick="this.parentElement.parentElement.parentElement.remove()" class="text-gray-400 hover:text-gray-600">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="space-y-4">
                    ${analysis.insights && analysis.insights.length > 0 ? `
                        <div>
                            <h4 class="font-medium mb-2">Key Insights</h4>
                            ${analysis.insights.map(insight => `
                                <div class="ai-insight-item ai-insight-${insight.category} mb-2">
                                    <p class="text-sm">${insight.message}</p>
                                    <p class="text-xs text-gray-600 mt-1">${insight.recommendation}</p>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                    
                    ${analysis.recommendations && analysis.recommendations.length > 0 ? `
                        <div>
                            <h4 class="font-medium mb-2">Recommendations</h4>
                            <ul class="text-sm space-y-1 text-gray-700">
                                ${analysis.recommendations.map(rec => `<li>• ${rec}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                    
                    <button onclick="app.aiAssistant.discussSourceAnalysis(${sourceId})" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        <i class="fas fa-comments mr-1"></i>Discuss with AI
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }

    async getAIAnalysis() {
        if (!this.currentData || this.currentData.length === 0) {
            this.showMessage('No data available for AI analysis. Please apply filters first.', 'warning');
            return;
        }
        
        this.showLoading('AI analyzing your data...');
        
        try {
            const filters = {
                catchment: document.getElementById('catchmentFilter')?.value || '',
                parameter: document.getElementById('parameterFilter')?.value || 'RECHARGE',
                start_date: document.getElementById('startDateFilter')?.value || '',
                end_date: document.getElementById('endDateFilter')?.value || ''
            };
            
            const response = await fetch(`${this.apiBase}/ai/analyze-data`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: this.currentData,
                    filters: filters
                })
            });
            
            if (response.ok) {
                const analysis = await response.json();
                this.displayAIAnalysis(analysis);
                this.showMessage('AI analysis completed', 'success');
            } else {
                throw new Error('AI analysis service unavailable');
            }
            
        } catch (error) {
            this.diagnostics.log(`AI analysis failed: ${error.message}`, 'warning');
            this.showRuleBasedAnalysis();
            this.showMessage('Using rule-based analysis (AI service unavailable)', 'info');
        } finally {
            this.hideLoading();
        }
    }

    displayAIAnalysis(analysis) {
        const panel = document.getElementById('aiInsightsPanel');
        const content = document.getElementById('aiInsightsContent');
        
        if (!panel || !content) return;
        
        panel.classList.remove('hidden');
        
        const insights = analysis.insights || [];
        const recommendations = analysis.recommendations || [];
        
        // Calculate basic failure statistics for display
        const failureCount = this.currentData.filter(d => d.is_failure === 1).length;
        const failureRate = ((failureCount / this.currentData.length) * 100).toFixed(1);
        
        content.innerHTML = `
            <div class="space-y-4">
                <div class="ai-insight-item ai-insight-${failureRate > 30 ? 'critical' : failureRate > 15 ? 'warning' : 'info'}">
                    <h4 class="font-medium">System Performance Analysis</h4>
                    <p class="text-sm mt-1">Failure rate: ${failureRate}% (${failureCount} of ${this.currentData.length} records)</p>
                    <p class="text-xs text-gray-600 mt-1">
                        ${failureRate > 30 ? 'High failure rate indicates significant system stress' :
                          failureRate > 15 ? 'Moderate failure rate suggests potential issues' :
                          'Relatively stable system performance'}
                    </p>
                </div>
                
                ${insights.length > 0 ? `
                    <div>
                        <h4 class="font-medium mb-2">AI Insights</h4>
                        ${insights.map(insight => `
                            <div class="ai-insight-item ai-insight-${insight.category || 'info'} mb-2">
                                <p class="text-sm">${insight.message}</p>
                                <p class="text-xs text-gray-600 mt-1">${insight.recommendation}</p>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
                
                ${recommendations.length > 0 ? `
                    <div>
                        <h4 class="font-medium mb-2">Recommendations</h4>
                        <ul class="text-sm space-y-1 text-gray-700">
                            ${recommendations.map(rec => `<li>• ${rec}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                
                <div class="text-sm text-gray-600">
                    <p><i class="fas fa-info-circle mr-2"></i>AI-powered analysis based on your current data. For more insights, chat with the AI assistant.</p>
                </div>
                
                <button onclick="app.aiAssistant.openChat()" class="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">
                    <i class="fas fa-comments mr-1"></i>Ask AI Assistant
                </button>
            </div>
        `;
    }

    showRuleBasedAnalysis() {
        if (!this.currentData || this.currentData.length === 0) return;
        
        const failureCount = this.currentData.filter(d => d.is_failure === 1).length;
        const failureRate = ((failureCount / this.currentData.length) * 100).toFixed(1);
        
        const panel = document.getElementById('aiInsightsPanel');
        const content = document.getElementById('aiInsightsContent');
        
        if (!panel || !content) return;
        
        panel.classList.remove('hidden');
        
        content.innerHTML = `
            <div class="space-y-4">
                <div class="ai-insight-item ai-insight-${failureRate > 30 ? 'critical' : failureRate > 15 ? 'warning' : 'info'}">
                    <h4 class="font-medium">System Performance Analysis</h4>
                    <p class="text-sm mt-1">Failure rate: ${failureRate}% (${failureCount} of ${this.currentData.length} records)</p>
                    <p class="text-xs text-gray-600 mt-1">
                        ${failureRate > 30 ? 'High failure rate indicates significant system stress' :
                          failureRate > 15 ? 'Moderate failure rate suggests potential issues' :
                          'Relatively stable system performance'}
                    </p>
                </div>
                
                <div class="text-sm text-gray-600">
                    <p><i class="fas fa-info-circle mr-2"></i>Rule-based analysis active. For advanced AI insights, ensure AI service is available.</p>
                </div>
                
                <button onclick="app.aiAssistant.openChat()" class="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">
                    <i class="fas fa-comments mr-1"></i>Ask AI Assistant
                </button>
            </div>
        `;
    }

    toggleAIInsights() {
        const panel = document.getElementById('aiInsightsPanel');
        if (panel) {
            panel.classList.toggle('hidden');
        }
    }

    // REST OF EXISTING METHODS (loadMetrics, updateCharts, etc.)
    async loadMetrics(filters) {
        try {
            const params = new URLSearchParams();
            if (filters.catchment) params.append('catchment', filters.catchment);
            if (filters.parameter) params.append('parameter', filters.parameter);
            
            const response = await this.makeApiRequest(`/metrics?${params}`);
            const result = await response.json();
            
            this.updateMetricsDisplay(result.metrics || []);
        } catch (error) {
            this.diagnostics.log(`Metrics loading failed: ${error.message}`, 'warning');
        }
    }
    
    updateMetricsDisplay(metrics) {
        const metricIds = ['reliabilityMetric', 'resilienceMetric', 'vulnerabilityMetric', 'sustainabilityMetric'];
        
        if (!metrics || metrics.length === 0) {
            metricIds.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '-';
            });
            return;
        }
        
        const avgMetrics = { reliability: 0, resilience: 0, vulnerability: 0, sustainability: 0 };
        let count = 0;
        
        metrics.forEach(metric => {
            if (metric) {
                avgMetrics.reliability += metric.reliability || 0;
                avgMetrics.resilience += metric.resilience || 0;
                avgMetrics.vulnerability += metric.vulnerability || 0;
                avgMetrics.sustainability += metric.sustainability || 0;
                count++;
            }
        });
        
        if (count > 0) {
            Object.keys(avgMetrics).forEach(key => {
                avgMetrics[key] = (avgMetrics[key] / count).toFixed(3);
            });
            
            document.getElementById('reliabilityMetric').textContent = avgMetrics.reliability;
            document.getElementById('resilienceMetric').textContent = avgMetrics.resilience;
            document.getElementById('vulnerabilityMetric').textContent = avgMetrics.vulnerability;
            document.getElementById('sustainabilityMetric').textContent = avgMetrics.sustainability;
        }
    }
    
    async loadFailureAnalysis(filters) {
        try {
            const params = new URLSearchParams();
            if (filters.catchment) params.append('catchment', filters.catchment);
            if (filters.start_date) params.append('start_date', filters.start_date);
            if (filters.end_date) params.append('end_date', filters.end_date);
            
            const response = await this.makeApiRequest(`/failure-analysis?${params}`);
            const result = await response.json();
            
            this.updateFailureAnalysisTable(result.failure_analysis || []);
        } catch (error) {
            this.diagnostics.log(`Failure analysis failed: ${error.message}`, 'warning');
        }
    }
    
    updateFailureAnalysisTable(data) {
        const container = document.getElementById('failureAnalysisTable');
        if (!container) return;
        
        if (!data || data.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-exclamation-triangle text-4xl mb-4"></i>
                    <p>No failure analysis data available</p>
                </div>
            `;
            return;
        }
        
        const table = `
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-2 text-left">Catchment</th>
                            <th class="px-4 py-2 text-left">Year</th>
                            <th class="px-4 py-2 text-left">Month</th>
                            <th class="px-4 py-2 text-left">Total Records</th>
                            <th class="px-4 py-2 text-left">Failures</th>
                            <th class="px-4 py-2 text-left">Failure Rate</th>
                            <th class="px-4 py-2 text-left">AI Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(row => {
                            const totalFailures = (row.gwr_failures || 0) + (row.gwl_failures || 0) + (row.gwb_failures || 0);
                            const rate = row.total_records > 0 ? ((totalFailures / row.total_records) * 100).toFixed(1) : '0.0';
                            return `
                                <tr class="border-b hover:bg-gray-50">
                                    <td class="px-4 py-2">${row.catchment_name || 'Unknown'}</td>
                                    <td class="px-4 py-2">${row.year || 'N/A'}</td>
                                    <td class="px-4 py-2">${row.month || 'N/A'}</td>
                                    <td class="px-4 py-2">${row.total_records || 0}</td>
                                    <td class="px-4 py-2">${totalFailures}</td>
                                    <td class="px-4 py-2">${rate}%</td>
                                    <td class="px-4 py-2">
                                        <button onclick="app.aiAssistant.analyzeFailurePeriod('${row.catchment_name}', ${row.year}, ${row.month})" 
                                                class="text-purple-600 hover:text-purple-800 text-xs">
                                            <i class="fas fa-brain mr-1"></i>Analyze
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = table;
    }
    
    initializeCharts() {
        try {
            this.initTimeSeriesChart();
            this.initClassificationChart();
            this.diagnostics.log('Charts initialized', 'good');
        } catch (error) {
            this.diagnostics.log(`Chart initialization failed: ${error.message}`, 'bad');
        }
    }
    
    initTimeSeriesChart() {
        const canvas = document.getElementById('timeSeriesChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
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
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Original Values' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: 'Z-scores' },
                        grid: { drawOnChartArea: false }
                    }
                },
                plugins: {
                    title: { display: true, text: 'Time Series Analysis' }
                }
            }
        });
    }
    
    initClassificationChart() {
        const canvas = document.getElementById('classificationChart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        if (this.charts.classification) {
            this.charts.classification.destroy();
        }
        
        this.charts.classification = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444'],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: 'Classification Distribution' },
                    legend: { position: 'bottom' }
                }
            }
        });
    }
    
    updateCharts() {
        if (!this.currentData || this.currentData.length === 0) {
            this.clearCharts();
            return;
        }
        
        try {
            this.updateTimeSeriesChart();
            this.updateClassificationChart();
        } catch (error) {
            this.diagnostics.log(`Chart update failed: ${error.message}`, 'warning');
        }
    }
    
    updateTimeSeriesChart() {
        if (!this.charts.timeSeries || !this.currentData) return;
        
        const sortedData = [...this.currentData]
            .filter(item => item.measurement_date)
            .sort((a, b) => new Date(a.measurement_date) - new Date(b.measurement_date));
        
        const labels = sortedData.map(item => new Date(item.measurement_date).toLocaleDateString());
        const originalValues = sortedData.map(item => item.original_value);
        const zScores = sortedData.map(item => item.zscore);
        
        this.charts.timeSeries.data.labels = labels;
        this.charts.timeSeries.data.datasets[0].data = originalValues;
        this.charts.timeSeries.data.datasets[1].data = zScores;
        this.charts.timeSeries.update();
    }
    
    updateClassificationChart() {
        if (!this.charts.classification || !this.currentData) return;
        
        const counts = { 'Surplus': 0, 'Normal': 0, 'Moderate_Deficit': 0, 'Severe_Deficit': 0, 'Extreme_Deficit': 0 };
        
        this.currentData.forEach(item => {
            if (counts.hasOwnProperty(item.classification)) {
                counts[item.classification]++;
            }
        });
        
        const labels = Object.keys(counts).map(key => key.replace('_', ' '));
        const data = Object.values(counts);
        
        this.charts.classification.data.labels = labels;
        this.charts.classification.data.datasets[0].data = data;
        this.charts.classification.update();
    }
    
    clearCharts() {
        if (this.charts.timeSeries) {
            this.charts.timeSeries.data.labels = [];
            this.charts.timeSeries.data.datasets[0].data = [];
            this.charts.timeSeries.data.datasets[1].data = [];
            this.charts.timeSeries.update();
        }
        
        if (this.charts.classification) {
            this.charts.classification.data.labels = [];
            this.charts.classification.data.datasets[0].data = [];
            this.charts.classification.update();
        }
    }
    
    clearFilters() {
        if (this.isLoading) return;
        
        const elements = ['catchmentFilter', 'startDateFilter', 'endDateFilter'];
        elements.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        
        const paramFilter = document.getElementById('parameterFilter');
        if (paramFilter) paramFilter.value = 'RECHARGE';
        
        this.currentData = null;
        this.clearCharts();
        this.clearMetrics();
        this.clearFailureAnalysis();
        
        // Hide AI insights
        const aiPanel = document.getElementById('aiInsightsPanel');
        if (aiPanel) aiPanel.classList.add('hidden');
        
        this.showMessage('Filters cleared', 'info');
        this.diagnostics.log('Filters cleared', 'info');
    }
    
    clearMetrics() {
        const metricIds = ['reliabilityMetric', 'resilienceMetric', 'vulnerabilityMetric', 'sustainabilityMetric'];
        metricIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = '-';
        });
    }
    
    clearFailureAnalysis() {
        const container = document.getElementById('failureAnalysisTable');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-exclamation-triangle text-4xl mb-4"></i>
                    <p>No failure analysis data available</p>
                </div>
            `;
        }
    }
    
    async refreshData() {
        if (this.isLoading) return;
        
        this.diagnostics.log('Refreshing data', 'info');
        await this.loadInitialData();
        this.showMessage('Data refreshed', 'success');
    }
    
    async exportData() {
        if (this.isLoading) return;
        
        try {
            this.showLoading('Preparing export...');
            const response = await this.makeApiRequest('/export');
            
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `groundwater_analysis_${new Date().toISOString().split('T')[0]}.xlsx`;
            a.click();
            URL.revokeObjectURL(url);
            
            this.showMessage('Data exported successfully', 'success');
        } catch (error) {
            this.showMessage(`Export failed: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async viewSource(sourceId) {
        if (this.isLoading) return;
        
        try {
            this.showLoading('Loading source data...');
            const response = await this.makeApiRequest(`/data?source_id=${sourceId}`);
            const result = await response.json();
            
            this.currentData = result.data || [];
            this.updateCharts();
            this.showMessage(`Viewing ${this.currentData.length} records from source ${sourceId}`, 'info');
        } catch (error) {
            this.showMessage(`Failed to load source data: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async deleteSource(sourceId) {
        if (this.isLoading || !confirm('Are you sure you want to delete this data source?')) return;
        
        try {
            this.showLoading('Deleting source...');
            await this.makeApiRequest(`/sources/${sourceId}`, { method: 'DELETE' });
            
            await this.loadDataSources();
            await this.loadCatchments();
            this.showMessage('Data source deleted successfully', 'success');
        } catch (error) {
            this.showMessage(`Failed to delete source: ${error.message}`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    showLoading(message = 'Loading...') {
        const overlay = document.getElementById('loadingOverlay');
        const text = document.getElementById('loadingText');
        
        if (text) text.textContent = message;
        if (overlay) overlay.classList.remove('hidden');
    }
    
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.add('hidden');
    }
    
    showMessage(message, type = 'info') {
        const container = document.getElementById('messageContainer');
        if (!container) return;
        
        const colors = {
            success: 'bg-green-100 border-green-400 text-green-700',
            error: 'bg-red-100 border-red-400 text-red-700',
            warning: 'bg-yellow-100 border-yellow-400 text-yellow-700',
            info: 'bg-blue-100 border-blue-400 text-blue-700'
        };
        
        const messageEl = document.createElement('div');
        messageEl.className = `mb-3 p-3 rounded border ${colors[type] || colors.info}`;
        messageEl.innerHTML = `
            <div class="flex justify-between items-center">
                <span class="text-sm">${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-lg font-bold opacity-70 hover:opacity-100">&times;</button>
            </div>
        `;
        
        container.appendChild(messageEl);
        
        setTimeout(() => {
            if (messageEl.parentElement) {
                messageEl.remove();
            }
        }, 5000);
    }
    
    hideMethodologyModal() {
        const modal = document.getElementById('methodologyModal');
        if (modal) {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
        }
    }
}

// ADVANCED AI ASSISTANT CLASS - COMPLETE IMPLEMENTATION
class AdvancedAIAssistant {
    constructor(mainApp) {
        this.app = mainApp;
        this.conversationHistory = [];
        this.conversationContext = {};
        this.isTyping = false;
        this.userId = this.generateUserId();
        this.currentConversationId = null;
        this.contextUpdateInterval = null;
        
        // Enhanced AI capabilities
        this.memoryCapabilities = {
            shortTerm: [], // Last 10 interactions
            longTerm: {}, // Persistent preferences and learnings
            contextual: {} // Current session context
        };
        
        this.thinkingPatterns = {
            analytical: true,
            creative: true,
            contextAware: true,
            followUp: true
        };
    }
    
    generateUserId() {
        return 'user_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }
    
    setupEventListeners() {
        // Enhanced event listeners with context awareness
        const aiFab = document.getElementById('aiFab');
        const chatContainer = document.getElementById('aiChatContainer');
        const closeChatBtn = document.getElementById('closeChatBtn');
        const sendChatBtn = document.getElementById('sendChatBtn');
        const chatInput = document.getElementById('aiChatInput');
        
        if (aiFab) {
            aiFab.addEventListener('click', () => this.toggleChat());
        }
        
        if (closeChatBtn) {
            closeChatBtn.addEventListener('click', () => this.closeChat());
        }
        
        if (sendChatBtn) {
            sendChatBtn.addEventListener('click', () => this.sendCurrentMessage());
        }
        
        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendCurrentMessage();
                }
            });
            
            // Smart suggestions as user types
            chatInput.addEventListener('input', (e) => {
                this.handleInputChange(e.target.value);
            });
        }
        
        // Auto-update context every 30 seconds when chat is active
        this.startContextUpdates();
    }
    
    handleInputChange(value) {
        // Provide smart suggestions as user types
        if (value.length > 10) {
            this.showSmartSuggestions(value);
        }
    }
    
    showSmartSuggestions(partialMessage) {
        // Analyze partial message and show relevant suggestions
        const suggestions = this.generateSmartSuggestions(partialMessage);
        if (suggestions.length > 0) {
            this.displayInputSuggestions(suggestions);
        }
    }
    
    generateSmartSuggestions(partialMessage) {
        const msg = partialMessage.toLowerCase();
        const suggestions = [];
        
        // Context-aware suggestions
        if (this.app.currentData && this.app.currentData.length > 0) {
            if (msg.includes('why') && msg.includes('fail')) {
                suggestions.push('Why are failures happening in my data?');
            }
            if (msg.includes('how') && msg.includes('improve')) {
                suggestions.push('How can I improve the reliability of this system?');
            }
            if (msg.includes('what') && msg.includes('mean')) {
                suggestions.push('What does this pattern mean for water management?');
            }
            if (msg.includes('compare')) {
                suggestions.push('Compare my results with industry benchmarks');
            }
        }
        
        // Methodology suggestions
        if (msg.includes('explain') || msg.includes('formula')) {
            suggestions.push('Explain the sustainability index calculation');
            suggestions.push('How is the z-score computed for my data?');
        }
        
        // Follow-up suggestions based on conversation history
        if (this.conversationHistory.length > 0) {
            const lastAiMessage = this.conversationHistory[this.conversationHistory.length - 1];
            if (lastAiMessage && lastAiMessage.sender === 'ai') {
                if (lastAiMessage.message.includes('reliability')) {
                    suggestions.push('Tell me more about reliability factors');
                }
                if (lastAiMessage.message.includes('failure')) {
                    suggestions.push('What specific actions should I take?');
                }
            }
        }
        
        return suggestions.slice(0, 3);
    }
    
    displayInputSuggestions(suggestions) {
        // Create or update suggestion dropdown
        let suggestionBox = document.getElementById('aiSuggestionBox');
        if (!suggestionBox) {
            suggestionBox = document.createElement('div');
            suggestionBox.id = 'aiSuggestionBox';
            suggestionBox.className = 'absolute bottom-full left-0 right-0 bg-white border rounded-lg shadow-lg mb-2 max-h-32 overflow-y-auto z-10';
            
            const chatInput = document.getElementById('aiChatInput');
            chatInput.parentElement.style.position = 'relative';
            chatInput.parentElement.appendChild(suggestionBox);
        }
        
        suggestionBox.innerHTML = suggestions.map(suggestion => `
            <div class="px-3 py-2 hover:bg-blue-50 cursor-pointer text-sm border-b last:border-b-0" 
                 onclick="window.app.aiAssistant.selectSuggestion('${suggestion}')">
                ${suggestion}
            </div>
        `).join('');
        
        suggestionBox.style.display = 'block';
        
        // Hide suggestions after 5 seconds or on outside click
        setTimeout(() => {
            if (suggestionBox) suggestionBox.style.display = 'none';
        }, 5000);
    }
    
    selectSuggestion(suggestion) {
        const chatInput = document.getElementById('aiChatInput');
        const suggestionBox = document.getElementById('aiSuggestionBox');
        
        if (chatInput) {
            chatInput.value = suggestion;
            chatInput.focus();
        }
        
        if (suggestionBox) {
            suggestionBox.style.display = 'none';
        }
    }
    
    startContextUpdates() {
        // Automatically update AI context with current app state
        this.contextUpdateInterval = setInterval(() => {
            if (this.isChatActive()) {
                this.updateAIContext();
            }
        }, 600000); // Every 10 minutes
    }
    
    isChatActive() {
        const chatContainer = document.getElementById('aiChatContainer');
        return chatContainer && chatContainer.style.display === 'flex';
    }
    
    async updateAIContext() {
        try {
            const contextData = this.gatherCurrentContext();
            
            await fetch(`${this.app.apiBase}/ai/context`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: this.userId,
                    context: contextData
                })
            });
            
            console.log('AI context updated automatically');
        } catch (error) {
            console.warn('Failed to update AI context:', error);
        }
    }
    
    gatherCurrentContext() {
        return {
            data: this.app.currentData,
            charts: {
                visible: Object.keys(this.app.charts || {}),
                hasData: this.app.currentData && this.app.currentData.length > 0
            },
            filters: {
                catchment: document.getElementById('catchmentFilter')?.value || '',
                parameter: document.getElementById('parameterFilter')?.value || '',
                dateRange: {
                    start: document.getElementById('startDateFilter')?.value || '',
                    end: document.getElementById('endDateFilter')?.value || ''
                }
            },
            userActions: {
                lastUpload: this.getLastUploadTime(),
                viewingSource: this.getCurrentViewingSource(),
                activeTab: this.getActiveTab()
            },
            systemState: {
                initialized: this.app.initialized,
                loading: this.app.isLoading,
                errors: this.getRecentErrors()
            }
        };
    }
    
    getLastUploadTime() {
        return localStorage.getItem('lastUploadTime') || null;
    }
    
    getCurrentViewingSource() {
        return this.app.currentSourceId || null;
    }
    
    getActiveTab() {
        const activeElements = document.querySelectorAll('.tab-active, .bg-blue-600');
        return activeElements.length > 0 ? activeElements[0].textContent : 'dashboard';
    }
    
    getRecentErrors() {
        return this.app.diagnostics ? 
            this.app.diagnostics.logs.filter(log => log.level === 'bad').slice(-3) : [];
    }
    
    toggleChat() {
        const chatContainer = document.getElementById('aiChatContainer');
        const fab = document.getElementById('aiFab');
        
        if (chatContainer && fab) {
            if (chatContainer.style.display === 'none' || !chatContainer.style.display) {
                this.openChat();
            } else {
                this.closeChat();
            }
        }
    }
    
    openChat() {
        const chatContainer = document.getElementById('aiChatContainer');
        const fab = document.getElementById('aiFab');
        
        if (chatContainer && fab) {
            chatContainer.style.display = 'flex';
            fab.style.display = 'none';
            
            // Update context immediately when opening
            this.updateAIContext();
            
            // Show contextual welcome message if first time opening
            if (this.conversationHistory.length === 0) {
                this.showContextualWelcome();
            }
            
            // Focus on input
            const chatInput = document.getElementById('aiChatInput');
            if (chatInput) {
                setTimeout(() => chatInput.focus(), 100);
            }
        }
    }
    
    showContextualWelcome() {
        let welcomeMessage = "Hello! I'm your AI assistant for groundwater analysis. ";
        
        if (this.app.currentData && this.app.currentData.length > 0) {
            const dataCount = this.app.currentData.length;
            const failureCount = this.app.currentData.filter(d => d.is_failure === 1).length;
            const failureRate = ((failureCount / dataCount) * 100).toFixed(1);
            
            welcomeMessage += `I can see you have ${dataCount} data points loaded with a ${failureRate}% failure rate. What would you like to understand about your groundwater system?`;
        } else {
            welcomeMessage += "I can help you understand groundwater analysis methodology, interpret your data, and provide insights. What questions do you have?";
        }
        
        this.addMessage(welcomeMessage, 'ai', 'welcome');
    }
    
    closeChat() {
        const chatContainer = document.getElementById('aiChatContainer');
        const fab = document.getElementById('aiFab');
        
        if (chatContainer && fab) {
            chatContainer.style.display = 'none';
            fab.style.display = 'flex';
            
            // Hide any suggestion boxes
            const suggestionBox = document.getElementById('aiSuggestionBox');
            if (suggestionBox) {
                suggestionBox.style.display = 'none';
            }
        }
    }
    
    sendCurrentMessage() {
        const input = document.getElementById('aiChatInput');
        if (input && input.value.trim()) {
            this.sendMessage(input.value.trim());
            input.value = '';
            
            // Hide suggestion box
            const suggestionBox = document.getElementById('aiSuggestionBox');
            if (suggestionBox) {
                suggestionBox.style.display = 'none';
            }
        }
    }
    
    async sendMessage(message) {
        if (this.isTyping) return;
        
        // Add user message immediately
        this.addMessage(message, 'user');
        this.showAdvancedTypingIndicator();
        
        // Store in conversation history
        this.conversationHistory.push({
            message,
            sender: 'user',
            timestamp: new Date(),
            context: this.gatherCurrentContext()
        });
        
        try {
            const contextData = this.gatherCurrentContext();
            
            // Call advanced AI endpoint
            const response = await fetch(`${this.app.apiBase}/ai/chat-advanced`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    user_id: this.userId,
                    context: contextData
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                this.hideAdvancedTypingIndicator();
                this.handleAdvancedResponse(result);
            } else {
                throw new Error(`AI service error: ${response.status}`);
            }
            
        } catch (error) {
            this.hideAdvancedTypingIndicator();
            console.error('Advanced AI error:', error);
            this.handleAIError(message, error);
        }
    }
    
    handleAdvancedResponse(result) {
        // Add AI response with enhanced features
        this.addMessage(result.content, 'ai', result.type || 'conversational');
        
        // Store in conversation history
        this.conversationHistory.push({
            message: result.content,
            sender: 'ai',
            timestamp: new Date(),
            type: result.type,
            suggestions: result.suggestions,
            contextActions: result.context_actions
        });
        
        // Handle follow-up suggestions
        if (result.suggestions && result.suggestions.length > 0) {
            this.showFollowUpSuggestions(result.suggestions);
        }
        
        // Handle context actions
        if (result.context_actions && result.context_actions.length > 0) {
            this.handleContextActions(result.context_actions);
        }
        
        // Update memory capabilities
        this.updateMemoryCapabilities(result);
    }
    
    showFollowUpSuggestions(suggestions) {
        const messagesContainer = document.getElementById('aiChatMessages');
        if (!messagesContainer) return;
        
        const suggestionsEl = document.createElement('div');
        suggestionsEl.className = 'ai-message mt-2';
        suggestionsEl.innerHTML = `
            <div class="flex flex-wrap gap-2 mt-2">
                <span class="text-xs text-gray-500 w-full mb-1">Suggested follow-ups:</span>
                ${suggestions.map(suggestion => `
                    <button onclick="window.app.aiAssistant.sendMessage('${suggestion}')" 
                            class="bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs px-3 py-1 rounded-full border border-blue-200 transition-colors">
                        ${suggestion}
                    </button>
                `).join('')}
            </div>
        `;
        
        messagesContainer.appendChild(suggestionsEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Auto-remove suggestions after 30 seconds
        setTimeout(() => {
            if (suggestionsEl.parentElement) {
                suggestionsEl.remove();
            }
        }, 30000);
    }
    
    handleContextActions(actions) {
        actions.forEach(action => {
            switch (action) {
                case 'update_charts':
                    this.app.updateCharts();
                    break;
                case 'show_upload_section':
                    this.scrollToSection('uploadSection');
                    break;
                case 'enable_export':
                    this.highlightExportButton();
                    break;
            }
        });
    }
    
    scrollToSection(sectionId) {
        const section = document.getElementById(sectionId);
        if (section) {
            section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            section.classList.add('highlight-section');
            setTimeout(() => section.classList.remove('highlight-section'), 3000);
        }
    }
    
    highlightExportButton() {
        const exportBtn = document.getElementById('exportData');
        if (exportBtn) {
            exportBtn.classList.add('pulse-animation');
            setTimeout(() => exportBtn.classList.remove('pulse-animation'), 3000);
        }
    }
    
    updateMemoryCapabilities(result) {
        this.memoryCapabilities.shortTerm.push({
            timestamp: new Date(),
            topic: this.extractMainTopic(result.content),
            type: result.type,
            userSatisfaction: 'pending'
        });
        
        if (this.memoryCapabilities.shortTerm.length > 10) {
            this.memoryCapabilities.shortTerm.shift();
        }
        
        this.memoryCapabilities.contextual.lastResponseType = result.type;
        this.memoryCapabilities.contextual.lastTopic = this.extractMainTopic(result.content);
    }
    
    extractMainTopic(content) {
        const topics = ['reliability', 'resilience', 'vulnerability', 'sustainability', 
                       'failure', 'drought', 'analysis', 'data', 'methodology'];
        
        const contentLower = content.toLowerCase();
        for (const topic of topics) {
            if (contentLower.includes(topic)) {
                return topic;
            }
        }
        return 'general';
    }
    
    handleAIError(originalMessage, error) {
        console.error('AI Error:', error);
        
        let errorMessage = "I encountered an issue processing your request. ";
        
        if (error.message.includes('network') || error.message.includes('fetch')) {
            errorMessage += "It seems there's a connectivity issue. Let me try to help with what I know locally.";
            const localResponse = this.generateEnhancedLocalResponse(originalMessage);
            this.addMessage(localResponse, 'ai', 'offline');
        } else {
            errorMessage += "Could you please rephrase your question? I'm here to help with your groundwater analysis.";
            this.addMessage(errorMessage, 'ai', 'error');
        }
        
        this.showRecoverySuggestions();
    }
    
    generateEnhancedLocalResponse(message) {
        const msg = message.toLowerCase();
        
        if (this.app.currentData && this.app.currentData.length > 0) {
            const df = this.app.currentData;
            const failureCount = df.filter(d => d.is_failure === 1).length;
            const failureRate = ((failureCount / df.length) * 100).toFixed(1);
            
            if (msg.includes('failure') || msg.includes('problem')) {
                return `Looking at your current data, you have ${failureCount} failures out of ${df.length} records (${failureRate}% failure rate). ${failureRate > 25 ? 'This indicates significant system stress that requires attention.' : 'This is within manageable levels but should be monitored.'}`;
            }
            
            if (msg.includes('improve') || msg.includes('better')) {
                if (failureRate > 20) {
                    return `With a ${failureRate}% failure rate, I'd recommend: 1) Investigate the timing of failures for patterns, 2) Consider adaptive management strategies, 3) Examine correlation with seasonal factors. Would you like me to help analyze any of these aspects?`;
                } else {
                    return `Your system shows good performance with ${failureRate}% failure rate. Consider monitoring trends over time and maintaining current management practices.`;
                }
            }
            
            if (msg.includes('reliability')) {
                const reliability = ((df.length - failureCount) / df.length).toFixed(3);
                return `Based on your data, the reliability is approximately ${reliability}. ${reliability > 0.8 ? 'This indicates good system performance.' : 'This suggests room for improvement in system management.'}`;
            }
        }
        
        if (msg.includes('z-score') || msg.includes('zscore')) {
            return "The Z-score formula (Z = (X - μ) / σ) standardizes your data values. It shows how many standard deviations each measurement is from the average. Values below -1.0 typically indicate drought conditions in groundwater systems.";
        }
        
        if (msg.includes('sustainability')) {
            return "The Sustainability Index combines reliability, resilience, and vulnerability (S = R × γ × (1 - V)). Higher values indicate better overall system health. It's the most comprehensive metric for evaluating groundwater system performance.";
        }
        
        return "While I'm working with limited connectivity, I can still help you understand groundwater analysis concepts and interpret your data patterns. What specific aspect would you like to explore?";
    }
    
    showRecoverySuggestions() {
        const suggestions = [
            "Try asking about your current data",
            "Ask for methodology explanations", 
            "Request help with data interpretation"
        ];
        
        setTimeout(() => {
            this.showFollowUpSuggestions(suggestions);
        }, 1000);
    }
    
    showAdvancedTypingIndicator() {
        this.isTyping = true;
        const messagesContainer = document.getElementById('aiChatMessages');
        if (!messagesContainer) return;
        
        const typingEl = document.createElement('div');
        typingEl.id = 'advancedTypingIndicator';
        typingEl.className = 'ai-message';
        typingEl.innerHTML = `
            <div class="flex items-start gap-2">
                <i class="fas fa-brain text-blue-600 mt-1 animate-pulse"></i>
                <div class="flex-1">
                    <div class="text-xs text-gray-500 mb-1">AI is thinking...</div>
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                    <div class="text-xs text-gray-400 mt-1">Analyzing your data and context</div>
                </div>
            </div>
        `;
        
        messagesContainer.appendChild(typingEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    hideAdvancedTypingIndicator() {
        this.isTyping = false;
        const typingEl = document.getElementById('advancedTypingIndicator');
        if (typingEl) {
            typingEl.remove();
        }
    }
    
    addMessage(message, sender, type = 'conversational') {
        const messagesContainer = document.getElementById('aiChatMessages');
        if (!messagesContainer) return;
        
        const messageEl = document.createElement('div');
        messageEl.className = sender === 'user' ? 'user-message' : 'ai-message';
        
        if (sender === 'user') {
            messageEl.innerHTML = `<p class="text-sm">${message}</p>`;
        } else {
            const typeIcons = {
                'methodology': 'fas fa-book',
                'data_analysis': 'fas fa-chart-line', 
                'recommendation': 'fas fa-lightbulb',
                'troubleshooting': 'fas fa-wrench',
                'welcome': 'fas fa-hand-wave',
                'offline': 'fas fa-wifi-slash',
                'error': 'fas fa-exclamation-triangle',
                'conversational': 'fas fa-brain'
            };
            
            const icon = typeIcons[type] || typeIcons.conversational;
            const typeColor = type === 'error' ? 'text-red-600' : 
                             type === 'offline' ? 'text-yellow-600' : 
                             type === 'recommendation' ? 'text-green-600' : 'text-blue-600';
            
            messageEl.innerHTML = `
                <div class="flex items-start gap-2">
                    <i class="${icon} ${typeColor} mt-1"></i>
                    <div class="flex-1">
                        <p class="text-sm">${this.formatMessage(message)}</p>
                        ${type === 'offline' ? '<p class="text-xs text-gray-500 mt-1">Offline response - Limited connectivity</p>' : ''}
                        ${type === 'welcome' ? '<p class="text-xs text-blue-500 mt-1">Ready to assist with your groundwater analysis</p>' : ''}
                    </div>
                </div>
            `;
        }
        
        messagesContainer.appendChild(messageEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    formatMessage(message) {
        let formatted = message;
        
        const technicalTerms = {
            'Z-score': '<span class="font-semibold text-blue-600">Z-score</span>',
            'reliability': '<span class="font-semibold text-green-600">reliability</span>',
            'resilience': '<span class="font-semibold text-purple-600">resilience</span>',
            'vulnerability': '<span class="font-semibold text-orange-600">vulnerability</span>',
            'sustainability': '<span class="font-semibold text-indigo-600">sustainability</span>'
        };
        
        Object.entries(technicalTerms).forEach(([term, replacement]) => {
            const regex = new RegExp(`\\b${term}\\b`, 'gi');
            formatted = formatted.replace(regex, replacement);
        });
        
        formatted = formatted.replace(/\b\d+\.?\d*%/g, '<span class="font-semibold text-gray-800">        this.contextUpdate</span>');
        formatted = formatted.replace(/([A-Z] = [^.]+)/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm">$1</code>');
        
        return formatted;
    }
    
    // Public methods called by main app
    onDataUploaded(uploadResult) {
        if (this.isChatActive()) {
            setTimeout(() => {
                this.sendMessage(`I just uploaded new data. Can you analyze what this means for my groundwater system?`);
            }, 2000);
        }
    }
    
    onFiltersApplied(filterData) {
        this.conversationContext.lastFilterUpdate = {
            timestamp: new Date(),
            filters: filterData,
            dataCount: filterData.resultCount
        };
        
        if (this.isChatActive()) {
            const contextMessage = `I've applied new filters and now have ${filterData.resultCount} records. What insights can you provide?`;
            this.pendingContextMessage = contextMessage;
        }
    }
    
    async explainError(errorMessage, context = {}) {
        this.openChat();
        setTimeout(() => {
            this.sendMessage(`I encountered this error: "${errorMessage}". Can you help me understand what went wrong and how to fix it?`);
        }, 500);
    }
    
    async explainUploadAnalysis() {
        this.openChat();
        setTimeout(() => {
            this.sendMessage("Can you explain the upload analysis results and what they mean for my data quality?");
        }, 500);
    }
    
    async discussSourceAnalysis(sourceId) {
        this.openChat();
        setTimeout(() => {
            this.sendMessage(`I'd like to discuss the AI analysis results for data source ${sourceId}. What are the key takeaways?`);
        }, 500);
    }
    
    async analyzeFailurePeriod(catchment, year, month) {
        this.openChat();
        setTimeout(() => {
            this.sendMessage(`Can you analyze the failure patterns for ${catchment} in ${month}/${year} and suggest what might have caused them?`);
        }, 500);
    }
    
    destroy() {
        if (this.contextUpdateInterval) {
            clearInterval(this.contextUpdateInterval);
        }
    }
}

// DIAGNOSTICS PANEL CLASS
class DiagnosticsPanel {
    constructor() {
        this.logs = [];
        this.maxLogs = 15;
    }
    
    log(message, level = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const icons = { good: '✅', bad: '❌', warning: '⚠️', info: 'ℹ️' };
        
        this.logs.push({
            timestamp,
            message,
            level,
            icon: icons[level] || icons.info
        });
        
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }
        
        this.updateDisplay();
        console.log(`[${timestamp}] ${level.toUpperCase()}: ${message}`);
    }
    
    updateDisplay() {
        const panel = document.getElementById('diagnostics');
        if (!panel) return;
        
        panel.innerHTML = this.logs.map(log => 
            `<div class="text-xs mb-1 ${this.getStatusClass(log.level)}">
                [${log.timestamp}] ${log.icon} ${log.message}
            </div>`
        ).join('');
    }
    
    getStatusClass(level) {
        return level === 'good' ? 'status-good' :
               level === 'bad' ? 'status-bad' :
               level === 'warning' ? 'status-warning' :
               'status-info';
    }
}

// INITIALIZE THE APPLICATION
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.app = new AIEnhancedGroundwaterSystem();
    } catch (error) {
        console.error('Failed to initialize AI-enhanced application:', error);
        document.body.innerHTML += `
            <div class="fixed top-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded z-50 max-w-md">
                <strong>Initialization Error:</strong> ${error.message}
            </div>
        `;
    }
});

// Global error handling
window.addEventListener('error', (event) => {
    console.error('JavaScript Error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled Promise Rejection:', event.reason);
    event.preventDefault();
});