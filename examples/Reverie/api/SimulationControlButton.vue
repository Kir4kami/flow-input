<template>
  <div class="simulation-control-container">
    <!-- 仿真控制按钮 -->
    <button 
      class="control-button" 
      @click="startSimulation"
      :disabled="isLoading"
    >
      <span v-if="!isLoading">
        <svg class="icon" viewBox="0 0 1024 1024" width="20" height="20">
          <path d="M512 85.333333c235.648 0 426.666667 191.018667 426.666667 426.666667s-191.018667 426.666667-426.666667 426.666667S85.333333 747.648 85.333333 512 276.352 85.333333 512 85.333333z m0 85.333334a341.333333 341.333333 0 1 0 0 682.666666 341.333333 341.333333 0 0 0 0-682.666666z m42.666667 170.666666v213.333334h213.333333v85.333333h-213.333333v213.333333h-85.333334v-213.333333H256v-85.333333h213.333333V341.333333h85.333334z" fill="currentColor"/>
        </svg>
        启动仿真
      </span>
      <span v-else>
        <svg class="loading-icon" viewBox="0 0 1024 1024" width="20" height="20">
          <path d="M512 74.667C270.933 74.667 74.667 270.933 74.667 512S270.933 949.333 512 949.333 949.333 753.067 949.333 512H874.667c0 200.298-162.368 362.667-362.667 362.667S149.333 712.299 149.333 512 311.701 149.333 512 149.333V74.667z" fill="currentColor"/>
        </svg>
        仿真中...
      </span>
    </button>

    <!-- 结果弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>仿真执行结果</h2>
          <button class="close-button" @click="closeModal">×</button>
        </div>

        <div class="modal-body">
          <div v-if="simulationResult" class="result-summary">
            <div class="summary-item">
              <span class="label">执行状态：</span>
              <span :class="['value', simulationResult.success ? 'success' : 'error']">
                {{ simulationResult.success ? '成功' : '失败' }}
              </span>
            </div>
            <div class="summary-item">
              <span class="label">仿真ID：</span>
              <span class="value">{{ simulationResult.simulation_id }}</span>
            </div>
            <div class="summary-item">
              <span class="label">运行状态：</span>
              <span class="value">{{ simulationResult.status }}</span>
            </div>
            <div class="summary-item message">
              <span class="label">消息：</span>
              <span class="value">{{ simulationResult.message }}</span>
            </div>
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
  name: 'SimulationControlButton',
  props: {
    apiUrl: {
      type: String,
      default: 'http://localhost:8000'
    },
    taskNum: {
      type: Number,
      default: 4
    },
    enableMixedGranularity: {
      type: Boolean,
      default: true
    },
    llmModel: {
      type: String,
      default: 'deepseek'
    },
    simulationTime: {
      type: Number,
      default: 10.0
    }
  },
  data() {
    return {
      isLoading: false,
      showModal: false,
      simulationResult: null,
      errorMessage: ''
    }
  },
  methods: {
    async startSimulation() {
      this.isLoading = true
      this.errorMessage = ''
      
      try {
        // 启动稳态监控
        await fetch(`${this.apiUrl}/start-steady-state-monitor`, {
          method: 'POST'
        })

        // 启动仿真
        const response = await fetch(`${this.apiUrl}/run-simulation`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            task_num: this.taskNum,
            llm_model: this.llmModel,
            enable_mixed_granularity: this.enableMixedGranularity,
            simulation_time: this.simulationTime
          })
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || '仿真启动失败')
        }

        const result = await response.json()
        this.simulationResult = result
        this.showModal = true

        this.$emit('simulation-started', result)
      } catch (error) {
        console.error('仿真启动错误:', error)
        this.errorMessage = error.message || '仿真启动失败，请检查API服务是否正常运行'
        
        setTimeout(() => {
          this.errorMessage = ''
        }, 3000)
        
        this.$emit('simulation-error', error)
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
.simulation-control-container {
  position: relative;
}

/* 控制按钮样式 */
.control-button {
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

.control-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
}

.control-button:active:not(:disabled) {
  transform: translateY(0);
}

.control-button:disabled {
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

