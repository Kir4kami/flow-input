cd ../..
./ns3 build reverie-evaluation-sigcomm2023
cd examples/Reverie/
source config.sh
DIR=$(pwd)
DUMP_DIR=$DIR/dump

TASKNUM="$1"
if [ -z "$TASKNUM" ]; then
  echo "Error: tasknum parameter is required!"
  exit 1
fi

# 生成时间戳：格式 YYYYMMDD_HHMMSS
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 不再清空 dump 目录，保留历史日志
# if [ -d "$DUMP_DIR" ]; then
#     rm -rf "$DUMP_DIR"/*
# fi

if [ ! -d "$DUMP_DIR" ];then
	mkdir $DUMP_DIR
fi

cd $NS3

REVERIE=111

INTCC=3

NUM=0
DST=1

alg=$REVERIE
egresslossyFrac=0.8
gamma=0.999

START_TIME=0
END_TIME=10000
FLOW_LAUNCH_END_TIME=3
#BUFFER_PER_PORT_PER_GBPS=5.12 # in KiloBytes per port per Gbps
#BUFFERSIZE=$(python3 -c "print(20*25*1000*$BUFFER_PER_PORT_PER_GBPS)") # in Bytes
ALPHAFILE=$DIR/alphas

RDMAREQRATE=2
TCPREQRATE=2

RDMACC=$INTCC

BUFFERMODEL="reverie"

# 存储所有任务的日志文件路径
DUMPFILES=()

for((i=1;i<=$TASKNUM;i++));do
	while [[ $(ps aux | grep sim-optimized | wc -l) -gt $N_CORES ]];do
		sleep 30;
		echo "waiting for cores, $N_CORES running..."
	done
	# 使用时间戳和任务索引生成唯一文件名
	FCTFILE=$DUMP_DIR/evaluation.fct${i}_${TIMESTAMP}
	TORFILE=$DUMP_DIR/evaluation.tor${i}_${TIMESTAMP}
	DUMPFILE=$DUMP_DIR/evaluation.out${i}_${TIMESTAMP}
	PFCFILE=$DUMP_DIR/evaluation.pfc${i}_${TIMESTAMP}
	
	# 保存日志文件路径
	DUMPFILES+=("$DUMPFILE")
	
	echo "Task $i: FCTFILE=$FCTFILE"
	echo "Task $i: DUMPFILE=$DUMPFILE (timestamped)"
	(time ./ns3 run "sim --TASKINDEX=$i --DST=$DST --START_TIME=$START_TIME --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME --fctOutFile=$FCTFILE --torOutFile=$TORFILE --pfcOutFile=$PFCFILE" > $DUMPFILE 2> $DUMPFILE)&
	#sleep 5
	NUM=$(( $NUM+1  ))
done

echo "Total $NUM experiments"
echo "Waiting for all tasks to complete..."

# 等待所有后台任务完成
wait

echo "All tasks completed. Merging logs..."

# 合并所有任务的日志到 evaluation.out（供API读取）
LATEST_DUMPFILE=$DUMP_DIR/evaluation.out
> "$LATEST_DUMPFILE"  # 清空或创建文件

# 合并所有任务的日志，按时间戳排序
for dumpfile in "${DUMPFILES[@]}"; do
	if [ -f "$dumpfile" ]; then
		echo "=== Merging log from: $(basename $dumpfile) ===" >> "$LATEST_DUMPFILE"
		cat "$dumpfile" >> "$LATEST_DUMPFILE"
		echo "" >> "$LATEST_DUMPFILE"
	fi
done

echo "Logs merged to: $LATEST_DUMPFILE"
echo "Timestamped log files preserved:"
for dumpfile in "${DUMPFILES[@]}"; do
	echo "  - $(basename $dumpfile)"
done
