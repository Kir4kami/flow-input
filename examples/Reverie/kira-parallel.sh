cd ../..
./ns3 build reverie-evaluation-sigcomm2023
cd examples/Reverie/
source config.sh
DIR=$(pwd)
DUMP_DIR=$DIR/dump
RESULTS_DIR=$DIR/results

if [ ! -d "$DUMP_DIR" ];then
	mkdir $DUMP_DIR
fi
if [ ! -d "$RESULTS_DIR" ];then
	mkdir $RESULTS_DIR
fi

cd $NS3

REVERIE=111

INTCC=3

NUM=0
DST=1
TASKNUM=4

alg=$REVERIE
egresslossyFrac=0.8
gamma=0.999

START_TIME=0
END_TIME=10000
FLOW_LAUNCH_END_TIME=3
BUFFER_PER_PORT_PER_GBPS=5.12 # in KiloBytes per port per Gbps
BUFFERSIZE=$(python3 -c "print(20*25*1000*$BUFFER_PER_PORT_PER_GBPS)") # in Bytes
ALPHAFILE=$DIR/alphas

RDMAREQRATE=2
TCPREQRATE=2

RDMACC=$INTCC

BUFFERMODEL="reverie"

for((i=1;i<=$TASKNUM;i++));do
	while [[ $(ps aux | grep reverie-evaluation-sigcomm2023-optimized | wc -l) -gt $N_CORES ]];do
		sleep 30;
		echo "waiting for cores, $N_CORES running..."
	done
	FCTFILE=$DUMP_DIR/evaluation.fct
	TORFILE=$DUMP_DIR/evaluation.tor
	DUMPFILE=$DUMP_DIR/evaluation.out
	PFCFILE=$DUMP_DIR/evaluation.pfc
	echo $FCTFILE
	(time ./ns3 run "reverie-evaluation-sigcomm2023 --TASKINDEX=$i --DST=$DST --powertcp=true --bufferalgIngress=$alg --bufferalgEgress=$alg --rdmacc=$RDMACC --enableEcn=true --egressLossyShare=$egresslossyFrac --bufferModel=$BUFFERMODEL --gamma=$gamma --START_TIME=$START_TIME --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME --buffersize=$BUFFERSIZE --fctOutFile=$FCTFILE --torOutFile=$TORFILE --alphasFile=$ALPHAFILE --pfcOutFile=$PFCFILE" > $DUMPFILE 2> $DUMPFILE)&
	#sleep 5
	NUM=$(( $NUM+1  ))
done

echo "Total $NUM experiments"
