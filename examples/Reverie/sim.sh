#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 默认参数（请保持小写）
LLM="qwen"
# 1 表示单任务（不切分），4 表示四任务并行
TASKNUM=1

# 允许通过环境变量覆盖参数，便于前端/脚本控制
if [ -n "$LLM_OVERRIDE" ]; then
  LLM="$LLM_OVERRIDE"
fi
if [ -n "$TASKNUM_OVERRIDE" ]; then
  TASKNUM="$TASKNUM_OVERRIDE"
fi

USE_CUSTOM_LOAD="${USE_CUSTOM_LOAD:-0}"

if [ "$USE_CUSTOM_LOAD" != "1" ]; then
  # 传统流程：使用 TrafficGenerator 生成流量文件
  cd "$SCRIPT_DIR/TrafficGenerator" || exit 1

  INPUT_FILE="${LLM}.txt"
  if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file $INPUT_FILE not found in $(pwd)!"
    exit 1
  fi

  echo "Running trafficGen.py with input: $INPUT_FILE..."
  python3 trafficGen.py --input_file "$INPUT_FILE" || {
    echo "Error: trafficGen.py failed"
    exit 1
  }

  if [ "$TASKNUM" -eq 1 ]; then
    echo "Running in single-task mode (TASKNUM=1)"

    echo "Running merge_dependency.sh..."
    bash merge_dependency.sh -i "${LLM}.txt" || {
      echo "Error: merge_dependency.sh failed"
      exit 1
    }

    echo "Running merge_rdma.sh..."
    bash merge_rdma.sh || {
      echo "Error: merge_rdma.sh failed"
      exit 1
    }

    TARGET_DIR="../task1"
    if [ -d "$TARGET_DIR" ]; then
      rm -rf "$TARGET_DIR" || {
        echo "Error: Failed to remove old task1 directory"
        exit 1
      }
    fi
    mkdir -p "$TARGET_DIR" || {
      echo "Error: Failed to create task1 directory"
      exit 1
    }

    cp -v rdma_result/all_rdma_files/* "$TARGET_DIR/" || {
      echo "Error: Failed to copy traffic files to task1 directory"
      exit 1
    }

    if [ -f "dependence.txt" ]; then
      mv dependence.txt "$TARGET_DIR/"
    else
      echo "Error: dependence.txt not found in TrafficGenerator directory"
      exit 1
    fi
  else
    echo "Running in multi-task mode (TASKNUM=$TASKNUM)"
    declare -a task_dirs=(
      "1_TP1"
      "2_EP2"
      "3_PP3"
      "21_DP17"
    )

    if [ "$TASKNUM" -gt ${#task_dirs[@]} ]; then
      echo "Error: TASKNUM ($TASKNUM) exceeds available task directories (${#task_dirs[@]})"
      exit 1
    fi

    for dir in "${task_dirs[@]}"; do
      if [ ! -d "rdma_result/$dir" ]; then
        echo "Error: Required directory rdma_result/$dir not found!"
        exit 1
      fi
    done

    for ((i = 1; i <= TASKNUM; i++)); do
      TARGET_DIR="../task$i"
      SOURCE_DIR="rdma_result/${task_dirs[$((i - 1))]}"

      if [ -d "$TARGET_DIR" ]; then
        rm -rf "$TARGET_DIR" || {
          echo "Error: Failed to remove old $TARGET_DIR directory"
          exit 1
        }
      fi

      mkdir -p "$TARGET_DIR" || {
        echo "Error: Failed to create $TARGET_DIR directory"
        exit 1
      }
      echo "Created directory: $TARGET_DIR"

      echo "Copying contents from $SOURCE_DIR to $TARGET_DIR..."
      cp -rv "$SOURCE_DIR"/* "$TARGET_DIR/" || {
        echo "Error: Failed to copy files from $SOURCE_DIR to $TARGET_DIR"
        exit 1
      }

      if [ -f "$TARGET_DIR/rdma_operate.txt" ]; then
        echo "Renaming rdma_operate.txt to rdma_operate0.txt in $TARGET_DIR"
        mv -v "$TARGET_DIR/rdma_operate.txt" "$TARGET_DIR/rdma_operate0.txt" || {
          echo "Error: Failed to rename file in $TARGET_DIR"
          exit 1
        }
      else
        echo "Warning: rdma_operate.txt not found in $TARGET_DIR"
      fi
    done
  fi

  cd "$SCRIPT_DIR" || exit 1
else
  echo "Using custom load from frontend; skipping TrafficGenerator pipeline."
  cd "$SCRIPT_DIR" || exit 1
fi

echo "Running kira-parallel.sh with TASKNUM=$TASKNUM..."
bash kira-parallel.sh "$TASKNUM"

