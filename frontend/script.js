class MobileAgentController {
    constructor() {
        this.backendUrl = 'http://localhost:50005'; // 后端服务地址
        this.frontendUrl = 'http://localhost:50006'; // 前端服务地址
        this.websocketUrl = 'ws://localhost:50005/ws'; // WebSocket地址
        this.isExecuting = false;
        this.executionStartTime = null;
        this.executionTimer = null;
        this.autoScroll = true;
        this.logCount = 0;
        this.stats = {
            totalActions: 0,
            successfulActions: 0,
            modelCalls: 0,
            screenshots: 0
        };
        
        this.initElements();
        this.bindEvents();
        this.checkConnection();
        this.startScreenshotPolling();
    }

    initElements() {
        // 获取DOM元素
        this.taskInput = document.getElementById('taskInput');
        this.executeBtn = document.getElementById('executeBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.refreshBtn = document.getElementById('refreshBtn');
        this.refreshScreenshotBtn = document.getElementById('refreshScreenshotBtn');
        this.autoScrollBtn = document.getElementById('autoScrollBtn');
        
        this.logContainer = document.getElementById('logContainer');
        this.currentScreenshot = document.getElementById('currentScreenshot');
        this.screenshotPlaceholder = document.getElementById('screenshotPlaceholder');
        this.screenshotTime = document.getElementById('screenshotTime');
        
        this.currentStatus = document.getElementById('currentStatus');
        this.executionTime = document.getElementById('executionTime');
        this.subtaskProgress = document.getElementById('subtaskProgress');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.connectionText = document.getElementById('connectionText');
        this.logCountEl = document.getElementById('logCount');  // 重命名为logCountEl
        
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.loadingMessage = document.getElementById('loadingMessage');
        
        // 统计元素
        this.totalActionsEl = document.getElementById('totalActions');
        this.successfulActionsEl = document.getElementById('successfulActions');
        this.modelCallsEl = document.getElementById('modelCalls');
        this.screenshotsEl = document.getElementById('screenshots');
    }

    bindEvents() {
        // 执行按钮
        this.executeBtn.addEventListener('click', () => this.executeTask());
        this.stopBtn.addEventListener('click', () => this.stopTask());
        this.clearBtn.addEventListener('click', () => this.clearLogs());
        this.refreshBtn.addEventListener('click', () => this.refreshConnection());
        this.refreshScreenshotBtn.addEventListener('click', () => this.refreshScreenshot());
        this.autoScrollBtn.addEventListener('click', () => this.toggleAutoScroll());

        // 预设指令按钮
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const instruction = e.target.dataset.instruction;
                this.taskInput.value = instruction;
            });
        });

        // 回车键执行
        this.taskInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.executeTask();
            }
        });
    }

    async checkConnection() {
        try {
            const response = await fetch(`${this.backendUrl}/ping`);
            if (response.ok) {
                this.updateConnectionStatus('success', '已连接');
            } else {
                this.updateConnectionStatus('error', '连接失败');
            }
        } catch (error) {
            this.updateConnectionStatus('error', '连接失败');
            console.error('Connection check failed:', error);
        }
    }

    updateConnectionStatus(status, text) {
        this.connectionStatus.className = `status-indicator status-${status}`;
        this.connectionText.textContent = text;
    }

    async executeTask() {
        const instruction = this.taskInput.value.trim();
        if (!instruction) {
            this.addLog('请输入任务指令', 'error');
            return;
        }

        if (this.isExecuting) {
            this.addLog('任务正在执行中，请等待完成', 'warning');
            return;
        }

        this.isExecuting = true;
        this.executionStartTime = Date.now();
        this.updateUIForExecution(true);
        this.clearLogs();
        this.resetStats();

        this.addLog(`开始执行任务: ${instruction}`, 'info');

        try {
            const response = await fetch(`${this.frontendUrl}/execute_task`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ instruction })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);
                            this.handleExecutionUpdate(data);
                        } catch (e) {
                            // 如果不是JSON，直接显示为日志
                            if (line.trim()) {
                                this.addLog(line.trim(), 'info');
                            }
                        }
                    }
                }
            }

        } catch (error) {
            this.addLog(`任务执行失败: ${error.message}`, 'error');
            console.error('Task execution failed:', error);
            this.isExecuting = false;
            this.updateUIForExecution(false);
        }
    }

    handleExecutionUpdate(data) {
        switch (data.type) {
            case 'log':
                this.addLog(data.message, data.level || 'info');
                break;
            case 'screenshot':
                this.updateScreenshot(data.path, data.timestamp);
                break;
            case 'status':
                this.updateStatus(data.status, data.progress);
                break;
            case 'progress':
                this.updateSubtaskProgress(data.current, data.total);
                break;
            case 'stats':
                this.updateStats(data.stats);
                break;
            case 'subtask':
                this.updateSubtaskProgress(data.current, data.total);
                break;
            case 'action':
                this.handleAction(data);
                break;
            case 'model_call':
                this.handleModelCall(data);
                break;
            case 'completion':
                this.handleCompletion(data);
                break;
            default:
                this.addLog(`未知更新类型: ${data.type}`, 'warning');
        }
    }

    handleAction(actionData) {
        this.stats.totalActions++;
        if (actionData.success) {
            this.stats.successfulActions++;
        }
        this.updateStatsDisplay();
        
        const actionText = `${actionData.action_type}: ${JSON.stringify(actionData.action_inputs)}`;
        this.addLog(actionText, actionData.success ? 'success' : 'error');
    }

    handleModelCall(modelData) {
        this.stats.modelCalls++;
        this.updateStatsDisplay();
        
        const modelText = `模型调用: ${modelData.model_name} (${modelData.call_type})`;
        this.addLog(modelText, 'info');
    }

    updateScreenshot(path, timestamp) {
        if (path) {
            this.currentScreenshot.src = `${this.backendUrl}/screenshot/${path}?t=${Date.now()}`;
            this.currentScreenshot.classList.remove('hidden');
            this.screenshotPlaceholder.classList.add('hidden');
            this.stats.screenshots++;
            this.updateStatsDisplay();
            
            if (timestamp) {
                this.screenshotTime.textContent = new Date(timestamp).toLocaleTimeString();
            }
        }
    }

    updateStatus(status, progress) {
        this.currentStatus.textContent = status;
        if (progress) {
            this.subtaskProgress.textContent = `${progress.current}/${progress.total}`;
        }
    }

    updateStats(stats) {
        this.stats = { ...this.stats, ...stats };
        this.updateStatsDisplay();
    }

    updateStatsDisplay() {
        this.totalActionsEl.textContent = this.stats.totalActions;
        this.successfulActionsEl.textContent = this.stats.successfulActions;
        this.modelCallsEl.textContent = this.stats.modelCalls;
        this.screenshotsEl.textContent = this.stats.screenshots;
    }

    updateSubtaskProgress(current, total) {
        this.subtaskProgress.textContent = `${current}/${total}`;
    }

    handleCompletion(data) {
        this.addLog(`任务完成！成功: ${data.completed}, 失败: ${data.failed}, 总计: ${data.total}`, 'success');
        this.isExecuting = false;
        this.updateUIForExecution(false);
    }

    updateUIForExecution(executing) {
        this.executeBtn.classList.toggle('hidden', executing);
        this.stopBtn.classList.toggle('hidden', !executing);
        this.taskInput.disabled = executing;
        
        if (executing) {
            this.startExecutionTimer();
        } else {
            this.stopExecutionTimer();
        }
    }

    startExecutionTimer() {
        this.executionTimer = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.executionStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            this.executionTime.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }

    stopExecutionTimer() {
        if (this.executionTimer) {
            clearInterval(this.executionTimer);
            this.executionTimer = null;
        }
    }

    async stopTask() {
        if (!this.isExecuting) return;

        try {
            await fetch(`${this.frontendUrl}/stop_task`, { method: 'POST' });
            this.addLog('任务已停止', 'warning');
        } catch (error) {
            this.addLog(`停止任务失败: ${error.message}`, 'error');
        } finally {
            this.isExecuting = false;
            this.updateUIForExecution(false);
        }
    }

    addLog(message, level = 'info') {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry mb-2 p-2 rounded ${this.getLogLevelClass(level)}`;
        
        const timestamp = new Date().toLocaleTimeString();
        const icon = this.getLogLevelIcon(level);
        
        logEntry.innerHTML = `
            <span class="text-gray-500 text-xs">${timestamp}</span>
            <i class="${icon} mr-2"></i>
            <span class="font-mono">${this.escapeHtml(message)}</span>
        `;
        
        this.logContainer.appendChild(logEntry);
        this.logCountEl.textContent = `${++this.logCount} 条日志`;
        
        if (this.autoScroll) {
            this.logContainer.scrollTop = this.logContainer.scrollHeight;
        }
    }

    getLogLevelClass(level) {
        const classes = {
            'info': 'bg-blue-50 text-blue-800',
            'success': 'bg-green-50 text-green-800',
            'warning': 'bg-yellow-50 text-yellow-800',
            'error': 'bg-red-50 text-red-800'
        };
        return classes[level] || classes.info;
    }

    getLogLevelIcon(level) {
        const icons = {
            'info': 'fas fa-info-circle',
            'success': 'fas fa-check-circle',
            'warning': 'fas fa-exclamation-triangle',
            'error': 'fas fa-times-circle'
        };
        return icons[level] || icons.info;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    clearLogs() {
        this.logContainer.innerHTML = `
            <div class="text-gray-500 text-center py-8">
                <i class="fas fa-terminal text-2xl mb-2"></i>
                <p>等待任务执行...</p>
            </div>
        `;
        this.logCountEl.textContent = '0 条日志';
        this.logCount = 0;  // 日志数量计数器
    }

    resetStats() {
        this.stats = {
            totalActions: 0,
            successfulActions: 0,
            modelCalls: 0,
            screenshots: 0
        };
        this.updateStatsDisplay();
    }

    async refreshConnection() {
        this.addLog('正在检查连接状态...', 'info');
        await this.checkConnection();
    }

    async refreshScreenshot() {
        try {
            const response = await fetch(`${this.backendUrl}/screenshot`);
            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                this.currentScreenshot.src = url;
                this.currentScreenshot.classList.remove('hidden');
                this.screenshotPlaceholder.classList.add('hidden');
                this.screenshotTime.textContent = new Date().toLocaleTimeString();
                this.addLog('截图已刷新', 'success');
            } else {
                this.addLog('获取截图失败', 'error');
            }
        } catch (error) {
            this.addLog(`刷新截图失败: ${error.message}`, 'error');
        }
    }

    toggleAutoScroll() {
        this.autoScroll = !this.autoScroll;
        this.autoScrollBtn.classList.toggle('bg-green-100', this.autoScroll);
        this.autoScrollBtn.classList.toggle('bg-gray-100', !this.autoScroll);
        this.autoScrollBtn.classList.toggle('text-green-700', this.autoScroll);
        this.autoScrollBtn.classList.toggle('text-gray-700', !this.autoScroll);
        
        const icon = this.autoScrollBtn.querySelector('i');
        icon.className = this.autoScroll ? 'fas fa-arrow-down mr-1' : 'fas fa-arrow-up mr-1';
        
        this.addLog(`自动滚动已${this.autoScroll ? '开启' : '关闭'}`, 'info');
    }

    startScreenshotPolling() {
        // 每5秒自动刷新一次截图
        setInterval(() => {
            if (!this.isExecuting) {
                this.refreshScreenshot();
            }
        }, 5000);
    }

    showLoading(message = '正在执行任务...') {
        this.loadingMessage.textContent = message;
        this.loadingOverlay.classList.remove('hidden');
    }

    hideLoading() {
        this.loadingOverlay.classList.add('hidden');
    }
}

// 初始化控制器
document.addEventListener('DOMContentLoaded', () => {
    window.agentController = new MobileAgentController();
}); 