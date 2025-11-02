<template>
  <div class="complete-simulation-advanced">
    <!-- 功能模式选择 -->
    <div class="mode-selector">
      <button 
        v-for="mode in modes" 
        :key="mode.value"
        :class="['mode-btn', { active: activeMode === mode.value }]"
        @click="activeMode = mode.value"
      >
        {{ mode.label }}
      </button>
    </div>

    <!-- 主要功能区 -->
    <div class="main-content">
      
      <!-- 拓扑设置模式 -->
      <div v-if="activeMode === 'topology'" class="feature-panel">
        <div class="panel-header">
          <h3>拓扑设置</h3>
          <p>配置网络拓扑参数</p>
        </div>
        
        <div class="input-section">
          <div class="input-group">
            <label>TOR交换机数量：</label>
            <input v-model.number="topology.torSwitches" type="number" min="1" placeholder="例如: 8">
          </div>
          <div class="input-group">
            <label>Spine交换机数量：</label>
            <input v-model.number="topology.spineSwitches" type="number" min="1" placeholder="例如: 4">
          </div>
          
          <div class="button-group">
            <button class="btn btn-primary" @click="generateTopology" :disabled="isGeneratingTopology">
              {{ isGeneratingTopology ? '生成中...' : '生成拓扑' }}
            </button>
            <button class="btn btn-secondary" @click="visualizeTopology" :disabled="!topologyGenerated">
              可视化拓扑
            </button>
          </div>
          
          <div v-if="topologyResult" class="result-box success">
            <p><strong>拓扑已生成</strong></p>
            <p>文件: leaf-spine.txt</p>
          </div>
        </div>
      </div>

      <!-- 负载设置模式 -->
      <div v-if="activeMode === 'load'" class="feature-panel">
        <div class="panel-header">
          <h3>负载设置</h3>
          <p>配置网络负载参数</p>
        </div>
        
        <div class="input-section">
          <div class="input-group">
            <label>节点数量：</label>
            <input v-model.number="load.host_num" type="number" min="1" placeholder="例如: 64">
          </div>
          <div class="input-group">
            <label>消息长度：</label>
            <input v-model="load.msg_len" type="text" placeholder="例如: 32*(1024)">
          </div>
          <div class="input-group">
            <label>DP值：</label>
            <input v-model.number="load.dp" type="number" min="1" placeholder="例如: 8">
          </div>
          
          <div class="button-group">
            <button class="btn btn-primary" @click="generateLoad" :disabled="isGeneratingLoad">
              {{ isGeneratingLoad ? '生成中...' : '生成负载' }}
            </button>
            <button class="btn btn-secondary" @click="viewLoadFiles">
              查看负载文件
            </button>
          </div>
          
          <div v-if="loadResult" class="result-box success">
            <p><strong>负载已生成</strong></p>
            <p>{{ loadResult.message }}</p>
          </div>
        </div>
      </div>

      <!-- 拓扑切分模式 -->
      <div v-if="activeMode === 'cut'" class="feature-panel">
        <div class="panel-header">
          <h3>拓扑切分</h3>
          <p>执行通信树拓扑切分</p>
        </div>
        
        <div class="input-section">
          <div class="input-group">
            <label>输出目录：</label>
            <input v-model="treeCut.output_dir" type="text" placeholder="TreeGroup">
          </div>
          
          <div class="button-group">
            <button class="btn btn-primary" @click="performTreeCut" :disabled="isCutting">
              {{ isCutting ? '切分中...' : '开始切分' }}
            </button>
            <button class="btn btn-secondary" @click="viewCutResults">
              查看切分结果
            </button>
          </div>
          
          <div v-if="cutResult" class="result-box success">
            <p><strong>切分完成</strong></p>
            <p>树组数量: {{ cutResult.tree_groups }}</p>
            <p>输出目录: {{ cutResult.output_directory }}</p>
          </div>
        </div>
      </div>

      <!-- 仿真控制模式 -->
      <div v-if="activeMode === 'simulation'" class="feature-panel">
        <div class="panel-header">
          <h3>仿真控制</h3>
          <p>配置并启动网络仿真</p>
        </div>
        
        <div class="input-section">
          <div class="switch-group">
            <label>开启切分 (TASKNUM):</label>
            <label class="switch">
              <input type="checkbox" v-model="simulation.enableCut">
              <span class="slider"></span>
            </label>
            <span class="switch-label">{{ simulation.enableCut ? 'TASKNUM=4' : 'TASKNUM=1' }}</span>
          </div>

          <div class="switch-group">
            <label>开启混合粒度:</label>
            <label class="switch">
              <input type="checkbox" v-model="simulation.enableMixedGranularity">
              <span class="slider"></span>
            </label>
            <span class="switch-label">{{ simulation.enableMixedGranularity ? '已开启' : '已关闭' }}</span>
          </div>

          <div class="input-group">
            <label>LLM模型：</label>
            <select v-model="simulation.llmModel">
              <option value="deepseek">DeepSeek</option>
              <option value="gpt">GPT</option>
              <option value="llama">LLaMa</option>
            </select>
          </div>

          <div class="input-group">
            <label>仿真时间（秒）：</label>
            <input v-model.number="simulation.time" type="number" min="1" placeholder="例如: 10">
          </div>
          
          <div class="button-group">
            <button class="btn btn-primary" @click="startSimulation" :disabled="simulationStatus.is_running">
              启动仿真
            </button>
            <button class="btn btn-danger" @click="stopSimulation" :disabled="!simulationStatus.is_running">
              停止仿真
            </button>
            <button class="btn btn-secondary" @click="checkStatus">
              查看状态
            </button>
          </div>
          
          <div v-if="simulationStatus.is_running" class="status-indicator running">
            <span class="status-dot"></span>
            仿真运行中... (ID: {{ simulationStatus.simulation_id }})
          </div>
          <div v-else class="status-indicator idle">
            <span class="status-dot"></span>
            仿真空闲
          </div>
        </div>
      </div>

      <!-- 稳态监控模式 -->
      <div v-if="activeMode === 'monitor'" class="feature-panel">
        <div class="panel-header">
          <h3>稳态监控</h3>
          <p>监控仿真稳态状态</p>
        </div>
        
        <div class="input-section">
          <div class="button-group">
            <button class="btn btn-primary" @click="checkSteadyState">
              检查稳态
            </button>
            <button class="btn btn-secondary" @click="startAutoMonitor" :disabled="autoMonitoring">
              {{ autoMonitoring ? '监控中...' : '自动监控' }}
            </button>
            <button class="btn btn-secondary" @click="stopAutoMonitor" :disabled="!autoMonitoring">
              停止监控
            </button>
          </div>
          
          <div v-if="steadyStateInfo" class="result-box">
            <p><strong>稳态状态:</strong> {{ steadyStateInfo.is_steady ? '已进入稳态' : '未进入稳态' }}</p>
            <p>检查时间: {{ new Date(steadyStateInfo.timestamp * 1000).toLocaleTimeString() }}</p>
          </div>
        </div>
      </div>

      <!-- 结果分析模式 -->
      <div v-if="activeMode === 'analysis'" class="feature-panel">
        <div class="panel-header">
          <h3>结果分析</h3>
          <p>分析仿真结果数据</p>
        </div>
        
        <div class="input-section">
          <div class="input-group">
            <label>分析类型：</label>
            <select v-model="analysis.type">
              <option value="all">全部</option>
              <option value="fct">FCT分析</option>
              <option value="performance">性能分析</option>
            </select>
          </div>
          
          <div class="button-group">
            <button class="btn btn-primary" @click="analyzeResults" :disabled="isAnalyzing">
              {{ isAnalyzing ? '分析中...' : '开始分析' }}
            </button>
          </div>
          
          <div v-if="analysisResult" class="result-box">
            <h4>分析结果</h4>
            <pre>{{ JSON.stringify(analysisResult, null, 2) }}</pre>
          </div>
        </div>
      </div>

    </div>

    <!-- 统一的模态框 -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>{{ modal.title }}</h2>
          <button class="close-button" @click="closeModal">×</button>
        </div>
        <div class="modal-body">
          <div v-if="modal.type === 'image'">
            <img :src="modal.imageUrl" style="max-width: 100%; height: auto;">
          </div>
          <div v-else-if="modal.type === 'files'">
            <ul class="file-list">
              <li v-for="file in modal.files" :key="file.path" @click="readFile(file.path, file.is_dir)">
                <strong>{{ file.is_dir ? '[DIR]' : '[FILE]' }}</strong> {{ file.name }}
                <span v-if="!file.is_dir" style="opacity: 0.5; margin-left: 10px; font-size: 12px;">
                  ({{ (file.size / 1024).toFixed(2) }} KB)
                </span>
              </li>
            </ul>
          </div>
          <div v-else-if="modal.type === 'content'">
            <pre style="max-height: 500px; overflow: auto;">{{ modal.content }}</pre>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="closeModal">关闭</button>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-toast" @click="errorMessage = ''">
      <svg viewBox="0 0 1024 1024" width="20" height="20">
        <path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z" fill="currentColor"/>
        <path d="M464 688a48 48 0 1 0 96 0 48 48 0 1 0-96 0zm8-304v184c0 4.4 3.6 8 8 8h64c4.4 0 8-3.6 8-8V384c0-4.4-3.6-8-8-8h-64c-4.4 0-8 3.6-8 8z" fill="currentColor"/>
      </svg>
      {{ errorMessage }}
    </div>
  </div>
</template>

<script>
export default {
  name: 'CompleteSimulationAdvanced',
  props: {
    apiUrl: {
      type: String,
      default: 'http://localhost:8000'
    }
  },
  data() {
    return {
      activeMode: 'topology',
      modes: [
        { value: 'topology', label: '拓扑设置' },
        { value: 'load', label: '负载设置' },
        { value: 'cut', label: '拓扑切分' },
        { value: 'simulation', label: '仿真控制' },
        { value: 'monitor', label: '稳态监控' },
        { value: 'analysis', label: '结果分析' }
      ],
      
      // 拓扑相关
      topology: {
        torSwitches: 8,
        spineSwitches: 4
      },
      topologyResult: null,
      topologyGenerated: false,
      isGeneratingTopology: false,
      
      // 负载相关
      load: {
        host_num: 64,
        msg_len: '32*(1024)',
        dp: 8,
        device: 0,
        forward: 1
      },
      loadResult: null,
      isGeneratingLoad: false,
      
      // 切分相关
      treeCut: {
        output_dir: 'TreeGroup'
      },
      cutResult: null,
      isCutting: false,
      
      // 仿真相关
      simulation: {
        enableCut: true,
        enableMixedGranularity: true,
        llmModel: 'deepseek',
        time: 10
      },
      simulationStatus: {
        is_running: false,
        simulation_id: null
      },
      
      // 稳态监控
      steadyStateInfo: null,
      autoMonitoring: false,
      monitorInterval: null,
      
      // 分析相关
      analysis: {
        type: 'all'
      },
      analysisResult: null,
      isAnalyzing: false,
      
      // 模态框
      showModal: false,
      modal: {
        title: '',
        type: 'content',
        content: '',
        imageUrl: '',
        files: []
      },
      
      errorMessage: ''
    }
  },
  methods: {
    // ========== 拓扑设置 ==========
    async generateTopology() {
      this.isGeneratingTopology = true
      try {
        const response = await fetch(`${this.apiUrl}/generate-topology`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            torSwitches: this.topology.torSwitches,
            spineSwitches: this.topology.spineSwitches
          })
        })
        
        const result = await response.json()
        if (result.success) {
          this.topologyResult = result
          this.topologyGenerated = true
        } else {
          throw new Error(result.message || '拓扑生成失败')
        }
      } catch (error) {
        this.showError(error.message)
      } finally {
        this.isGeneratingTopology = false
      }
    },
    
    async visualizeTopology() {
      try {
        await fetch(`${this.apiUrl}/visualize-topology`, { method: 'POST' })
        
        this.modal = {
          title: '拓扑可视化',
          type: 'image',
          imageUrl: `${this.apiUrl}/get-topology-image?t=${Date.now()}`
        }
        this.showModal = true
      } catch (error) {
        this.showError('拓扑可视化失败')
      }
    },
    
    // ========== 负载设置 ==========
    async generateLoad() {
      this.isGeneratingLoad = true
      try {
        const response = await fetch(`${this.apiUrl}/generate-load`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.load)
        })
        
        const result = await response.json()
        if (result.success) {
          this.loadResult = result
        } else {
          throw new Error(result.message || '负载生成失败')
        }
      } catch (error) {
        this.showError(error.message)
      } finally {
        this.isGeneratingLoad = false
      }
    },
    
    async viewLoadFiles() {
      await this.listDirectory('rdma_result')
    },
    
    // ========== 拓扑切分 ==========
    async performTreeCut() {
      this.isCutting = true
      try {
        const response = await fetch(`${this.apiUrl}/tree-cut`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            output_dir: this.treeCut.output_dir
          })
        })
        
        const result = await response.json()
        if (result.success) {
          this.cutResult = result
        } else {
          throw new Error(result.message || '切分失败')
        }
      } catch (error) {
        this.showError(error.message)
      } finally {
        this.isCutting = false
      }
    },
    
    async viewCutResults() {
      await this.listDirectory(this.treeCut.output_dir)
    },
    
    // ========== 仿真控制 ==========
    async startSimulation() {
      try {
        await fetch(`${this.apiUrl}/start-steady-state-monitor`, { method: 'POST' })
        
        const response = await fetch(`${this.apiUrl}/run-simulation`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_num: this.simulation.enableCut ? 4 : 1,
            llm_model: this.simulation.llmModel,
            enable_mixed_granularity: this.simulation.enableMixedGranularity,
            simulation_time: this.simulation.time
          })
        })
        
        const result = await response.json()
        if (result.success) {
          this.simulationStatus.is_running = true
          this.simulationStatus.simulation_id = result.simulation_id
        }
      } catch (error) {
        this.showError('仿真启动失败')
      }
    },
    
    async stopSimulation() {
      try {
        await fetch(`${this.apiUrl}/stop-simulation`, { method: 'POST' })
        await fetch(`${this.apiUrl}/stop-steady-state-monitor`, { method: 'POST' })
        this.simulationStatus.is_running = false
      } catch (error) {
        this.showError('仿真停止失败')
      }
    },
    
    async checkStatus() {
      try {
        const response = await fetch(`${this.apiUrl}/simulation-status`)
        const status = await response.json()
        this.simulationStatus = status
      } catch (error) {
        this.showError('状态获取失败')
      }
    },
    
    // ========== 稳态监控 ==========
    async checkSteadyState() {
      try {
        const response = await fetch(`${this.apiUrl}/steady-state-monitor`)
        this.steadyStateInfo = await response.json()
      } catch (error) {
        this.showError('稳态检查失败')
      }
    },
    
    startAutoMonitor() {
      this.autoMonitoring = true
      this.monitorInterval = setInterval(() => {
        this.checkSteadyState()
        this.checkStatus()
      }, 2000)
    },
    
    stopAutoMonitor() {
      this.autoMonitoring = false
      if (this.monitorInterval) {
        clearInterval(this.monitorInterval)
      }
    },
    
    // ========== 结果分析 ==========
    async analyzeResults() {
      this.isAnalyzing = true
      try {
        const response = await fetch(`${this.apiUrl}/analyze-results`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysis_type: this.analysis.type })
        })
        
        this.analysisResult = await response.json()
      } catch (error) {
        this.showError('分析失败')
      } finally {
        this.isAnalyzing = false
      }
    },
    
    // ========== 文件浏览 ==========
    async listDirectory(path) {
      try {
        const response = await fetch(`${this.apiUrl}/list-files?directory=${encodeURIComponent(path)}`)
        const result = await response.json()
        
        this.modal = {
          title: `目录: ${path}`,
          type: 'files',
          files: result.files,
          currentPath: path
        }
        this.showModal = true
      } catch (error) {
        this.showError('目录读取失败')
      }
    },
    
    async readFile(filePath, isDir) {
      if (isDir) {
        await this.listDirectory(filePath)
      } else {
        try {
          const response = await fetch(`${this.apiUrl}/read-file?file_path=${encodeURIComponent(filePath)}`)
          const result = await response.json()
          
          this.modal = {
            title: filePath,
            type: 'content',
            content: result.content
          }
          this.showModal = true
        } catch (error) {
          this.showError('文件读取失败')
        }
      }
    },
    
    // ========== 工具方法 ==========
    closeModal() {
      this.showModal = false
    },
    
    showError(message) {
      this.errorMessage = message
      setTimeout(() => {
        this.errorMessage = ''
      }, 3000)
    }
  },
  
  beforeUnmount() {
    this.stopAutoMonitor()
  }
}
</script>

<style scoped>
.complete-simulation-advanced {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

/* 模式选择器 */
.mode-selector {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.mode-btn {
  flex: 1;
  min-width: 140px;
  padding: 12px 20px;
  border: 2px solid #e8e8e8;
  background: white;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 14px;
  font-weight: 500;
  color: #666;
}

.mode-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

.mode-btn.active {
  border-color: #667eea;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

/* 功能面板 */
.feature-panel {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.panel-header {
  margin-bottom: 20px;
  border-bottom: 2px solid #667eea;
  padding-bottom: 12px;
}

.panel-header h3 {
  color: #333;
  margin-bottom: 8px;
  font-size: 20px;
}

.panel-header p {
  color: #666;
  font-size: 14px;
}

/* 输入区域 */
.input-section {
  max-width: 600px;
}

.input-group {
  margin-bottom: 16px;
}

.input-group label {
  display: block;
  margin-bottom: 6px;
  color: #666;
  font-size: 14px;
  font-weight: 500;
}

.input-group input,
.input-group select {
  width: 100%;
  padding: 10px 12px;
  border: 2px solid #e8e8e8;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.input-group input:focus,
.input-group select:focus {
  outline: none;
  border-color: #667eea;
}

/* 开关组 */
.switch-group {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.4s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: #667eea;
}

input:checked + .slider:before {
  transform: translateX(24px);
}

.switch-label {
  color: #667eea;
  font-weight: 500;
  font-size: 14px;
}

/* 按钮组 */
.button-group {
  display: flex;
  gap: 12px;
  margin: 20px 0;
  flex-wrap: wrap;
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
  background: #e8e8e8;
  color: #333;
}

.btn-secondary:hover:not(:disabled) {
  background: #d4d4d4;
}

.btn-danger {
  background: #ff4d4f;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #cf1322;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 结果框 */
.result-box {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
  border-left: 4px solid #667eea;
}

.result-box.success {
  border-left-color: #52c41a;
  background: #f6ffed;
}

.result-box h4 {
  margin-bottom: 8px;
  color: #333;
}

.result-box p {
  margin: 4px 0;
  color: #666;
  font-size: 14px;
}

.result-box pre {
  background: #282c34;
  color: #abb2bf;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
  margin-top: 8px;
}

/* 状态指示器 */
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 6px;
  margin-top: 16px;
  font-weight: 500;
}

.status-indicator.running {
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.status-indicator.idle {
  background: #f9fafb;
  color: #666;
  border: 1px solid #e8e8e8;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 900px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e8e8e8;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #333;
}

.close-button {
  background: none;
  border: none;
  cursor: pointer;
  color: #666;
  font-size: 28px;
  line-height: 1;
  padding: 0;
  width: 32px;
  height: 32px;
  transition: all 0.2s;
}

.close-button:hover {
  background: #f5f5f5;
  border-radius: 4px;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: flex-end;
}

/* 文件列表 */
.file-list {
  list-style: none;
  padding: 0;
}

.file-list li {
  padding: 12px;
  border-bottom: 1px solid #e8e8e8;
  cursor: pointer;
  transition: background 0.2s;
}

.file-list li:hover {
  background: #f9fafb;
}

/* 错误提示 */
.error-toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #ff4d4f;
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(255, 77, 79, 0.4);
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 2000;
  cursor: pointer;
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translate(-50%, -20px);
  }
  to {
    opacity: 1;
    transform: translate(-50%, 0);
  }
}

/* 响应式 */
@media (max-width: 768px) {
  .mode-selector {
    flex-direction: column;
  }
  
  .mode-btn {
    min-width: 100%;
  }
  
  .button-group {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }
}
</style>

