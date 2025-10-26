<template>
  <div class="tree-cut-container">
    <!-- 切分按钮 -->
    <button 
      class="cut-button" 
      @click="performCut"
      :disabled="isLoading"
    >
      <span v-if="!isLoading">
        <svg class="icon" viewBox="0 0 1024 1024" width="20" height="20">
          <path d="M512 85.333333c235.648 0 426.666667 191.018667 426.666667 426.666667s-191.018667 426.666667-426.666667 426.666667S85.333333 747.648 85.333333 512 276.352 85.333333 512 85.333333z m0 85.333334a341.333333 341.333333 0 1 0 0 682.666666 341.333333 341.333333 0 0 0 0-682.666666z m42.666667 170.666666v213.333334h213.333333v85.333333h-213.333333v213.333333h-85.333334v-213.333333H256v-85.333333h213.333333V341.333333h85.333334z" fill="currentColor"/>
        </svg>
        拓扑切分
      </span>
      <span v-else>
        <svg class="loading-icon" viewBox="0 0 1024 1024" width="20" height="20">
          <path d="M512 74.667C270.933 74.667 74.667 270.933 74.667 512S270.933 949.333 512 949.333 949.333 753.067 949.333 512H874.667c0 200.298-162.368 362.667-362.667 362.667S149.333 712.299 149.333 512 311.701 149.333 512 149.333V74.667z" fill="currentColor"/>
        </svg>
        切分中...
      </span>
    </button>

    <!-- 结果弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>拓扑切分结果</h2>
          <button class="close-button" @click="closeModal">
            <svg viewBox="0 0 1024 1024" width="24" height="24">
              <path d="M563.8 512l262.5-312.9c4.4-5.2.7-13.1-6.1-13.1h-79.8c-4.7 0-9.2 2.1-12.3 5.7L511.6 449.8 295.1 191.7c-3-3.6-7.5-5.7-12.3-5.7H203c-6.8 0-10.5 7.9-6.1 13.1L459.4 512 196.9 824.9A7.95 7.95 0 0 0 203 838h79.8c4.7 0 9.2-2.1 12.3-5.7l216.5-258.1 216.5 258.1c3 3.6 7.5 5.7 12.3 5.7h79.8c6.8 0 10.5-7.9 6.1-13.1L563.8 512z" fill="currentColor"/>
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <!-- 切分统计信息 -->
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

          <!-- 文件列表 -->
          <div v-if="cutResult && cutResult.result_files.length > 0" class="files-section">
            <h3>生成的文件 ({{ cutResult.result_files.length }})</h3>
            <div class="files-list">
              <div 
                v-for="(file, index) in cutResult.result_files" 
                :key="index"
                class="file-item"
              >
                <svg class="file-icon" viewBox="0 0 1024 1024" width="16" height="16">
                  <path d="M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.5-3.4-16.7-9.4-22.7zM790.2 326H602V137.8L790.2 326z m1.8 562H232V136h302v216a42 42 0 0 0 42 42h216v494z" fill="currentColor"/>
                </svg>
                <span class="file-path">{{ file }}</span>
              </div>
            </div>
          </div>

          <!-- JSON概览信息 -->
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
  name: 'TreeCutButton',
  props: {
    // API服务地址
    apiUrl: {
      type: String,
      default: 'http://localhost:8001'
    },
    // 树数据（可选）
    treeData: {
      type: Object,
      default: null
    },
    // 输出目录
    outputDir: {
      type: String,
      default: 'TreeGroup'
    }
  },
  data() {
    return {
      isLoading: false,
      showModal: false,
      cutResult: null,
      errorMessage: ''
    }
  },
  methods: {
    async performCut() {
      this.isLoading = true
      this.errorMessage = ''
      
      try {
        // 如果没有提供树数据，先获取示例数据
        let dataToUse = this.treeData
        if (!dataToUse) {
          const exampleResponse = await fetch(`${this.apiUrl}/example-tree`)
          if (!exampleResponse.ok) {
            throw new Error('无法获取示例数据')
          }
          const exampleData = await exampleResponse.json()
          dataToUse = exampleData.tree_data
        }

        // 调用切分接口
        const response = await fetch(`${this.apiUrl}/tree-cut`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            tree_data: dataToUse,
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

        // 触发事件，通知父组件
        this.$emit('cut-complete', result)
      } catch (error) {
        console.error('拓扑切分错误:', error)
        this.errorMessage = error.message || '拓扑切分失败，请检查API服务是否正常运行'
        
        // 3秒后自动隐藏错误提示
        setTimeout(() => {
          this.errorMessage = ''
        }, 3000)
        
        this.$emit('cut-error', error)
      } finally {
        this.isLoading = false
      }
    },
    closeModal() {
      this.showModal = false
    }
  }
}
</script>

<style scoped>
.tree-cut-container {
  position: relative;
}

/* 切分按钮样式 */
.cut-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
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

.cut-button:active:not(:disabled) {
  transform: translateY(0);
}

.cut-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.icon, .loading-icon {
  display: inline-block;
  vertical-align: middle;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 弹窗遮罩 */
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
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 弹窗内容 */
.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 800px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 弹窗头部 */
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
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-button:hover {
  background: #f5f5f5;
  color: #333;
}

/* 弹窗主体 */
.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

/* 结果摘要 */
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

.summary-item.message {
  flex-direction: column;
  align-items: flex-start;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid #e8e8e8;
}

.summary-item .label {
  font-weight: 500;
  color: #666;
  min-width: 100px;
}

.summary-item .value {
  color: #333;
}

.summary-item .value.success {
  color: #52c41a;
  font-weight: 600;
}

.summary-item .value.error {
  color: #ff4d4f;
  font-weight: 600;
}

.summary-item .value.highlight {
  color: #667eea;
  font-weight: 600;
  font-size: 18px;
}

/* 文件列表部分 */
.files-section {
  margin-bottom: 24px;
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
  transition: all 0.2s;
  border: 1px solid transparent;
}

.file-item:last-child {
  margin-bottom: 0;
}

.file-item:hover {
  border-color: #667eea;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
}

.file-icon {
  flex-shrink: 0;
  color: #667eea;
}

.file-path {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  color: #555;
  word-break: break-all;
}

/* JSON概览 */
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
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  overflow-x: auto;
  margin: 0;
  line-height: 1.6;
}

/* 弹窗底部 */
.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: flex-end;
}

.btn {
  padding: 10px 24px;
  border-radius: 6px;
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
  max-width: 500px;
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

/* 滚动条样式 */
.files-list::-webkit-scrollbar,
.modal-body::-webkit-scrollbar,
.json-content::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.files-list::-webkit-scrollbar-track,
.modal-body::-webkit-scrollbar-track,
.json-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.files-list::-webkit-scrollbar-thumb,
.modal-body::-webkit-scrollbar-thumb,
.json-content::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.files-list::-webkit-scrollbar-thumb:hover,
.modal-body::-webkit-scrollbar-thumb:hover,
.json-content::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .modal-content {
    width: 95%;
    max-height: 90vh;
  }
  
  .modal-header {
    padding: 16px;
  }
  
  .modal-body {
    padding: 16px;
  }
  
  .summary-item {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .summary-item .label {
    margin-bottom: 4px;
  }
}
</style>



