cd ../..
./ns3 build
cd examples/Reverie/
source config.sh
DIR=$(pwd)
DUMP_DIR=$DIR/dump

TASKNUM="$1"
if [ -z "$TASKNUM" ]; then
  echo "Error: tasknum parameter is required!"
  exit 1
fi

if [ -d "$DUMP_DIR" ]; then
    rm -rf "$DUMP_DIR"/*
fi

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
END_TIME=100000000000
FLOW_LAUNCH_END_TIME=5000000000  # 5秒，足够32MB流传输并达到稳态
#BUFFER_PER_PORT_PER_GBPS=5.12 # in KiloBytes per port per Gbps
#BUFFERSIZE=$(python3 -c "print(20*25*1000*$BUFFER_PER_PORT_PER_GBPS)") # in Bytes
ALPHAFILE=$DIR/alphas

RDMAREQRATE=2
TCPREQRATE=2

RDMACC=$INTCC

BUFFERMODEL="reverie"

for((i=1;i<=$TASKNUM;i++));do
	while [[ $(ps aux | grep sim-optimized | wc -l) -gt $N_CORES ]];do
		sleep 30;
		echo "waiting for cores, $N_CORES running..."
	done
	FCTFILE=$DUMP_DIR/evaluation.fct
	TORFILE=$DUMP_DIR/evaluation.tor
	DUMPFILE=$DUMP_DIR/evaluation.out
	PFCFILE=$DUMP_DIR/evaluation.pfc
	echo $FCTFILE
	(time ./ns3 run "sim --TASKINDEX=$i --DST=$DST --START_TIME=$START_TIME --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME --fctOutFile=$FCTFILE --torOutFile=$TORFILE --pfcOutFile=$PFCFILE" > $DUMPFILE 2>&1)&
	#sleep 5
	NUM=$(( $NUM+1  ))
done

echo "Total $NUM experiments"
