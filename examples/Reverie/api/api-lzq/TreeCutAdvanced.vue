<template>
  <div class="tree-cut-advanced">
    <!-- 输入模式选择 -->
    <div class="mode-selector">
      <button 
        v-for="mode in modes" 
        :key="mode.value"
        :class="['mode-btn', { active: inputMode === mode.value }]"
        @click="inputMode = mode.value"
      >
        <svg class="icon" viewBox="0 0 1024 1024" width="18" height="18" v-html="mode.icon"></svg>
        {{ mode.label }}
      </button>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <!-- 模式 1: 使用示例数据 -->
      <div v-if="inputMode === 'example'" class="input-panel">
        <div class="panel-header">
          <h3>📦 使用示例数据</h3>
          <p>直接使用 API 提供的示例通信树数据</p>
        </div>
        <div class="example-preview">
          <pre>{{ exampleDataPreview }}</pre>
        </div>
      </div>

      <!-- 模式 2: 从 URL 加载 -->
      <div v-if="inputMode === 'url'" class="input-panel">
        <div class="panel-header">
          <h3>🔗 从 URL 加载 JSON</h3>
          <p>输入文件服务器上 JSON 文件的 URL 地址</p>
        </div>
        <div class="url-input-group">
          <input 
            v-model="jsonUrl" 
            type="text" 
            class="url-input"
            placeholder="例如: http://localhost:8000/tree_data.json"
            @keyup.enter="loadFromUrl"
          />
          <button class="btn btn-primary" @click="loadFromUrl" :disabled="!jsonUrl || isLoadingUrl">
            <span v-if="!isLoadingUrl">加载</span>
            <span v-else>加载中...</span>
          </button>
        </div>
        <div v-if="urlLoadError" class="error-message">{{ urlLoadError }}</div>
        <div v-if="urlLoadSuccess" class="success-message">✓ 成功加载 JSON 数据</div>
        <div v-if="loadedJsonData" class="loaded-preview">
          <h4>已加载的数据预览:</h4>
          <pre>{{ JSON.stringify(loadedJsonData, null, 2).substring(0, 500) }}...</pre>
        </div>
      </div>

      <!-- 模式 3: 上传 JSON 文件 -->
      <div v-if="inputMode === 'file'" class="input-panel">
        <div class="panel-header">
          <h3>📁 上传 JSON 文件</h3>
          <p>从本地选择 JSON 文件上传</p>
        </div>
        <div class="file-upload-area" @drop.prevent="handleFileDrop" @dragover.prevent>
          <input 
            ref="fileInput"
            type="file" 
            accept=".json"
            style="display: none"
            @change="handleFileSelect"
          />
          <div class="upload-box" @click="$refs.fileInput.click()">
            <svg class="upload-icon" viewBox="0 0 1024 1024" width="48" height="48">
              <path d="M544 224v384h-64V224H320l192-192 192 192H544z m-256 512h448v64H288v-64z" fill="currentColor"/>
            </svg>
            <p v-if="!uploadedFile">点击或拖拽文件到此处上传</p>
            <p v-else class="file-name">{{ uploadedFile.name }}</p>
          </div>
        </div>
        <div v-if="uploadedJsonData" class="loaded-preview">
          <h4>已上传的数据预览:</h4>
          <pre>{{ JSON.stringify(uploadedJsonData, null, 2).substring(0, 500) }}...</pre>
        </div>
      </div>

      <!-- 模式 4: 在线输入 -->
      <div v-if="inputMode === 'manual'" class="input-panel">
        <div class="panel-header">
          <h3>✏️ 在线输入</h3>
          <p>手动输入通信树的节点和边信息</p>
        </div>
        
        <!-- 节点输入 -->
        <div class="manual-section">
          <h4>节点列表</h4>
          <div class="node-list">
            <div v-for="(node, index) in manualNodes" :key="index" class="node-item">
              <div class="node-fields">
                <input v-model="node.name" placeholder="节点名称" class="field-input" />
                <select v-model="node.type" class="field-select">
                  <option value="">选择类型</option>
                  <option value="Root">Root</option>
                  <option value="DP">DP</option>
                  <option value="PP">PP</option>
                  <option value="TP">TP</option>
                </select>
                <input v-model.number="node.layer" type="number" placeholder="层级" class="field-input small" />
                <input v-model="node.nodes_passed" placeholder="经过节点 (逗号分隔)" class="field-input" />
                <label class="checkbox-label">
                  <input v-model="node.isBurr" type="checkbox" />
                  毛刺节点
                </label>
                <button class="btn-remove" @click="removeNode(index)">删除</button>
              </div>
            </div>
          </div>
          <button class="btn btn-secondary" @click="addNode">+ 添加节点</button>
        </div>

        <!-- 边输入 -->
        <div class="manual-section">
          <h4>边列表</h4>
          <div class="edge-list">
            <div v-for="(edge, index) in manualEdges" :key="index" class="edge-item">
              <input v-model="edge.from_node" placeholder="起始节点" class="field-input" />
              <span class="arrow">→</span>
              <input v-model="edge.to_node" placeholder="目标节点" class="field-input" />
              <button class="btn-remove" @click="removeEdge(index)">删除</button>
            </div>
          </div>
          <button class="btn btn-secondary" @click="addEdge">+ 添加边</button>
        </div>

        <!-- JSON 预览 -->
        <div class="manual-preview">
          <h4>JSON 预览:</h4>
          <pre>{{ JSON.stringify(getManualTreeData(), null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- 输出目录配置 -->
    <div class="config-section">
      <label class="config-label">
        <span>输出目录:</span>
        <input v-model="outputDir" class="config-input" placeholder="TreeGroup" />
      </label>
    </div>

    <!-- 操作按钮 -->
    <div class="action-buttons">
      <button 
        class="cut-button" 
        @click="performCut"
        :disabled="isLoading || !canPerformCut"
      >
        <span v-if="!isLoading">
          <svg class="icon" viewBox="0 0 1024 1024" width="20" height="20">
            <path d="M512 85.333333c235.648 0 426.666667 191.018667 426.666667 426.666667s-191.018667 426.666667-426.666667 426.666667S85.333333 747.648 85.333333 512 276.352 85.333333 512 85.333333z m0 85.333334a341.333333 341.333333 0 1 0 0 682.666666 341.333333 341.333333 0 0 0 0-682.666666z m42.666667 170.666666v213.333334h213.333333v85.333333h-213.333333v213.333333h-85.333334v-213.333333H256v-85.333333h213.333333V341.333333h85.333334z" fill="currentColor"/>
          </svg>
          开始拓扑切分
        </span>
        <span v-else>
          <svg class="loading-icon" viewBox="0 0 1024 1024" width="20" height="20">
            <path d="M512 74.667C270.933 74.667 74.667 270.933 74.667 512S270.933 949.333 512 949.333 949.333 753.067 949.333 512H874.667c0 200.298-162.368 362.667-362.667 362.667S149.333 712.299 149.333 512 311.701 149.333 512 149.333V74.667z" fill="currentColor"/>
          </svg>
          切分中...
        </span>
      </button>
      <button class="btn btn-secondary" @click="resetInput">重置</button>
    </div>

    <!-- 结果弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>拓扑切分结果</h2>
          <button class="close-button" @click="closeModal">×</button>
        </div>
        <div class="modal-body">
          <div v-if="cutResult" class="result-summary">
            <div class="summary-item">
              <span class="label">切分状态：</span>
              <span :class="['value', cutResult.success ? 'success' : 'error']">
                {{ cutResult.success ? '✓ 成功' : '✗ 失败' }}
              </span>
            </div>
            <div class="summary-item">
              <span class="label">树组数量：</span>
              <span class="value highlight">{{ cutResult.tree_groups }}</span>
            </div>
            <div class="summary-item">
              <span class="label">输出目录：</span>
              <span class="value">{{ cutResult.output_directory }}</span>
            </div>
            <div class="summary-item message">
              <span class="label">消息：</span>
              <span class="value">{{ cutResult.message }}</span>
            </div>
          </div>

          <div v-if="cutResult && cutResult.result_files.length > 0" class="files-section">
            <h3>生成的文件 ({{ cutResult.result_files.length }})</h3>
            <div class="files-list">
              <div v-for="(file, index) in cutResult.result_files" :key="index" class="file-item">
                <svg class="file-icon" viewBox="0 0 1024 1024" width="16" height="16">
                  <path d="M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.5-3.4-16.7-9.4-22.7zM790.2 326H602V137.8L790.2 326z m1.8 562H232V136h302v216a42 42 0 0 0 42 42h216v494z" fill="currentColor"/>
                </svg>
                <span class="file-path">{{ file }}</span>
              </div>
            </div>
          </div>

          <div v-if="cutResult && cutResult.json_overview" class="json-overview">
            <h3>切分详情</h3>
            <pre class="json-content">{{ JSON.stringify(cutResult.json_overview, null, 2) }}</pre>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="closeModal">确定</button>
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
  name: 'TreeCutAdvanced',
  props: {
    apiUrl: {
      type: String,
      default: 'http://localhost:8001'
    }
  },
  data() {
    return {
      inputMode: 'example',
      modes: [
        { value: 'example', label: '示例数据', icon: '<path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z" fill="currentColor"/>' },
        { value: 'url', label: 'URL加载', icon: '<path d="M574 665.4a8.03 8.03 0 0 0-11.3 0L446.5 781.6c-53.8 53.8-144.6 59.5-204 0-59.5-59.5-53.8-150.2 0-204l116.2-116.2c3.1-3.1 3.1-8.2 0-11.3l-39.8-39.8a8.03 8.03 0 0 0-11.3 0L191.4 526.5c-84.6 84.6-84.6 221.5 0 306s221.5 84.6 306 0l116.2-116.2c3.1-3.1 3.1-8.2 0-11.3L574 665.4zm258.6-474c-84.6-84.6-221.5-84.6-306 0L410.3 307.6a8.03 8.03 0 0 0 0 11.3l39.7 39.7c3.1 3.1 8.2 3.1 11.3 0l116.2-116.2c53.8-53.8 144.6-59.5 204 0 59.5 59.5 53.8 150.2 0 204L665.3 562.6a8.03 8.03 0 0 0 0 11.3l39.8 39.8c3.1 3.1 8.2 3.1 11.3 0l116.2-116.2c84.5-84.6 84.5-221.5 0-306.1zM610.1 372.3a8.03 8.03 0 0 0-11.3 0L372.3 598.7a8.03 8.03 0 0 0 0 11.3l39.6 39.6c3.1 3.1 8.2 3.1 11.3 0l226.4-226.4c3.1-3.1 3.1-8.2 0-11.3l-39.5-39.6z" fill="currentColor"/>' },
        { value: 'file', label: '文件上传', icon: '<path d="M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.5-3.4-16.7-9.4-22.7z" fill="currentColor"/>' },
        { value: 'manual', label: '在线输入', icon: '<path d="M257.7 752c2 0 4-.2 6-.5L431.9 722c2-.4 3.9-1.3 5.3-2.8l423.9-423.9a9.96 9.96 0 0 0 0-14.1L694.9 114.9c-1.9-1.9-4.4-2.9-7.1-2.9s-5.2 1-7.1 2.9L256.8 538.8c-1.5 1.5-2.4 3.3-2.8 5.3l-29.5 168.2a33.5 33.5 0 0 0 9.4 29.8c6.6 6.4 14.9 9.9 23.8 9.9z" fill="currentColor"/>' }
      ],
      jsonUrl: '',
      isLoadingUrl: false,
      urlLoadError: '',
      urlLoadSuccess: false,
      loadedJsonData: null,
      uploadedFile: null,
      uploadedJsonData: null,
      manualNodes: [
        { name: 'Root', type: 'Root', layer: 0, nodes_passed: '', isBurr: false }
      ],
      manualEdges: [],
      outputDir: 'TreeGroup',
      isLoading: false,
      showModal: false,
      cutResult: null,
      errorMessage: '',
      exampleDataPreview: '{\n  "nodes": [...],\n  "edges": [...]\n}\n\n将使用 API 提供的示例数据'
    }
  },
  computed: {
    canPerformCut() {
      if (this.inputMode === 'example') return true
      if (this.inputMode === 'url') return !!this.loadedJsonData
      if (this.inputMode === 'file') return !!this.uploadedJsonData
      if (this.inputMode === 'manual') {
        return this.manualNodes.length > 0 && this.manualEdges.length > 0
      }
      return false
    }
  },
  methods: {
    async loadFromUrl() {
      if (!this.jsonUrl) return
      
      this.isLoadingUrl = true
      this.urlLoadError = ''
      this.urlLoadSuccess = false
      
      try {
        const response = await fetch(this.jsonUrl)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        
        const data = await response.json()
        this.loadedJsonData = data.tree_data || data
        this.urlLoadSuccess = true
        
        setTimeout(() => {
          this.urlLoadSuccess = false
        }, 3000)
      } catch (error) {
        this.urlLoadError = `加载失败: ${error.message}`
      } finally {
        this.isLoadingUrl = false
      }
    },
    
    handleFileSelect(event) {
      const file = event.target.files[0]
      if (file) {
        this.uploadedFile = file
        this.readFile(file)
      }
    },
    
    handleFileDrop(event) {
      const file = event.dataTransfer.files[0]
      if (file && file.type === 'application/json') {
        this.uploadedFile = file
        this.readFile(file)
      }
    },
    
    readFile(file) {
      const reader = new FileReader()
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result)
          this.uploadedJsonData = data.tree_data || data
        } catch (error) {
          this.errorMessage = `JSON 解析失败: ${error.message}`
          setTimeout(() => { this.errorMessage = '' }, 3000)
        }
      }
      reader.readAsText(file)
    },
    
    addNode() {
      this.manualNodes.push({
        name: '',
        type: '',
        layer: 0,
        nodes_passed: '',
        isBurr: false
      })
    },
    
    removeNode(index) {
      this.manualNodes.splice(index, 1)
    },
    
    addEdge() {
      this.manualEdges.push({
        from_node: '',
        to_node: ''
      })
    },
    
    removeEdge(index) {
      this.manualEdges.splice(index, 1)
    },
    
    getManualTreeData() {
      return {
        nodes: this.manualNodes.map(node => ({
          name: node.name,
          type: node.type,
          layer: node.layer,
          nodes_passed: node.nodes_passed ? node.nodes_passed.split(',').map(s => s.trim()) : [],
          children: [],
          isBurr: node.isBurr
        })),
        edges: this.manualEdges.map(edge => ({
          from_node: edge.from_node,
          to_node: edge.to_node
        }))
      }
    },
    
    async performCut() {
      this.isLoading = true
      this.errorMessage = ''
      
      try {
        let treeData = null
        
        if (this.inputMode === 'example') {
          const response = await fetch(`${this.apiUrl}/example-tree`)
          if (!response.ok) throw new Error('无法获取示例数据')
          const data = await response.json()
          treeData = data.tree_data
        } else if (this.inputMode === 'url') {
          treeData = this.loadedJsonData
        } else if (this.inputMode === 'file') {
          treeData = this.uploadedJsonData
        } else if (this.inputMode === 'manual') {
          treeData = this.getManualTreeData()
        }
        
        if (!treeData) {
          throw new Error('请先准备拓扑数据')
        }
        
        const response = await fetch(`${this.apiUrl}/tree-cut`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tree_data: treeData,
            output_dir: this.outputDir,
            show_graphs: false
          })
        })
        
        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || '切分失败')
        }
        
        const result = await response.json()
        this.cutResult = result
        this.showModal = true
        this.$emit('cut-complete', result)
      } catch (error) {
        this.errorMessage = error.message || '拓扑切分失败'
        setTimeout(() => { this.errorMessage = '' }, 3000)
        this.$emit('cut-error', error)
      } finally {
        this.isLoading = false
      }
    },
    
    resetInput() {
      this.jsonUrl = ''
      this.loadedJsonData = null
      this.uploadedFile = null
      this.uploadedJsonData = null
      this.urlLoadError = ''
      this.urlLoadSuccess = false
      this.manualNodes = [
        { name: 'Root', type: 'Root', layer: 0, nodes_passed: '', isBurr: false }
      ]
      this.manualEdges = []
    },
    
    closeModal() {
      this.showModal = false
    }
  }
}
</script>

<style scoped>
.tree-cut-advanced {
  max-width: 900px;
  margin: 0 auto;
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
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
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

.mode-btn .icon {
  display: inline-block;
}

/* 输入面板 */
.input-area {
  margin-bottom: 24px;
}

.input-panel {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.panel-header {
  margin-bottom: 20px;
}

.panel-header h3 {
  color: #333;
  margin-bottom: 8px;
  font-size: 18px;
}

.panel-header p {
  color: #666;
  font-size: 14px;
}

/* URL 输入 */
.url-input-group {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.url-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.url-input:focus {
  outline: none;
  border-color: #667eea;
}

.error-message {
  padding: 12px;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 6px;
  color: #cf1322;
  font-size: 14px;
  margin-top: 12px;
}

.success-message {
  padding: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
  color: #52c41a;
  font-size: 14px;
  margin-top: 12px;
}

/* 文件上传 */
.file-upload-area {
  margin-bottom: 16px;
}

.upload-box {
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
}

.upload-box:hover {
  border-color: #667eea;
  background: #f9f9ff;
}

.upload-icon {
  color: #667eea;
  margin-bottom: 12px;
}

.upload-box p {
  color: #666;
  font-size: 14px;
}

.file-name {
  color: #667eea;
  font-weight: 500;
}

/* 在线输入 */
.manual-section {
  margin-bottom: 24px;
}

.manual-section h4 {
  color: #333;
  margin-bottom: 12px;
  font-size: 16px;
}

.node-list, .edge-list {
  margin-bottom: 12px;
}

.node-item, .edge-item {
  margin-bottom: 12px;
}

.node-fields {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.field-input {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  flex: 1;
  min-width: 120px;
}

.field-input.small {
  flex: 0;
  width: 80px;
}

.field-select {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  min-width: 100px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: #666;
}

.btn-remove {
  padding: 8px 12px;
  background: #ff4d4f;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-remove:hover {
  background: #cf1322;
}

.arrow {
  color: #667eea;
  font-size: 18px;
  font-weight: bold;
}

.manual-preview, .loaded-preview, .example-preview {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.manual-preview h4, .loaded-preview h4 {
  color: #333;
  margin-bottom: 8px;
  font-size: 14px;
}

.manual-preview pre, .loaded-preview pre, .example-preview pre {
  background: #282c34;
  color: #abb2bf;
  padding: 12px;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}

/* 配置区域 */
.config-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.config-label {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: #666;
}

.config-input {
  flex: 1;
  padding: 10px 14px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  font-size: 14px;
}

.config-input:focus {
  outline: none;
  border-color: #667eea;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.cut-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  font-size: 16px;
  font-weight: 500;
  color: #fff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 6px rgba(102, 126, 234, 0.3);
}

.cut-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
}

.cut-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #667eea;
  color: white;
}

.btn-primary:hover {
  background: #5568d3;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #e8e8e8;
  color: #333;
}

.btn-secondary:hover {
  background: #d4d4d4;
}

/* 弹窗样式 (与之前相同) */
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
  max-width: 800px;
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
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.result-summary {
  background: #f9fafb;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}

.summary-item {
  display: flex;
  align-items: center;
  padding: 8px 0;
}

.summary-item .label {
  font-weight: 500;
  color: #666;
  min-width: 100px;
}

.summary-item .value.success {
  color: #52c41a;
  font-weight: 600;
}

.summary-item .value.highlight {
  color: #667eea;
  font-weight: 600;
  font-size: 18px;
}

.files-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}

.files-list {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: white;
  border-radius: 6px;
  margin-bottom: 8px;
}

.file-path {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: #555;
}

.json-overview h3 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}

.json-content {
  background: #282c34;
  color: #abb2bf;
  padding: 16px;
  border-radius: 8px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  overflow-x: auto;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: flex-end;
}

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
}

@media (max-width: 768px) {
  .mode-selector {
    flex-direction: column;
  }
  
  .mode-btn {
    min-width: 100%;
  }
  
  .node-fields {
    flex-direction: column;
  }
  
  .field-input, .field-select {
    width: 100%;
  }
}
</style>


