#!/bin/bash

# Input and output files
INPUT_FILE="deepseek.txt"
OUTPUT_FILE="dependence.txt"

# Check if input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file $INPUT_FILE does not exist."
    exit 1
fi

# Initialize variables
declare -A node_files  # Store file range for each node (node_name:start:end)
declare -A node_parents  # Store parent nodes for each node
declare -A node_name_map  # Map expected node names (e.g., TP1) to actual node names
declare -A mode_counters  # Track mode-specific counters (TP, EP, PP, DP)
mode_counters=( [TP]=0 [EP]=0 [PP]=0 [DP]=0 )
current_file_index=0  # Track current file index
node_count=0  # Track total nodes (excluding Root)
declare -a dependencies  # Store dependency records for sorting

# Function to parse parameters from input line
parse_params() {
    local args="$1"
    local -A params=(
        ["host_num"]=4096
        ["num_nodes"]=16
        ["dp"]=1
        ["msg_len"]="32*1024*1024"
        ["num_phases"]=15
        ["num_iterations"]=1
    )

    # Parse arguments
    local i=0
    local arg_array
    read -ra arg_array <<< "$args"
    while [ $i -lt ${#arg_array[@]} ]; do
        if [[ "${arg_array[$i]}" == --* ]]; then
            key=${arg_array[$i]#--}
            key=${key//-/_}  # Replace - with _ (e.g., host-num -> host_num)
            ((i++))
            if [ $i -ge ${#arg_array[@]} ]; then
                echo "Error: Missing value for ${arg_array[$((i-1))]}"
                exit 1
            fi
            if [ "$key" == "msg_len" ]; then
                # Evaluate msg_len expression (e.g., 32*(1024))
                params["$key"]=$(echo "${arg_array[$i]}" | bc)
            else
                params["$key"]=${arg_array[$i]}
            fi
        fi
        ((i++))
    done

    # Return parameters as space-separated key-value pairs
    for key in "${!params[@]}"; do
        echo "$key=${params[$key]}"
    done
}

# Function to get file count for a mode
get_file_count() {
    local mode=$1
    local host_num=$2
    local dp=$3
    local num_nodes=$4

    case $mode in
        EP|DP)
            if [ $((host_num % dp)) -ne 0 ]; then
                echo "Error: host_num $host_num not divisible by dp $dp" >&2
                exit 1
            fi
            echo $((host_num / dp))
            ;;
        TP)
            if [ $((host_num % num_nodes)) -ne 0 ]; then
                echo "Error: host_num $host_num not divisible by num_nodes $num_nodes" >&2
                exit 1
            fi
            echo $((host_num / num_nodes))
            ;;
        PP)
            echo $dp
            ;;
        *)
            echo 0
            ;;
    esac
}

# Function to trim whitespace
trim() {
    echo "$1" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# Read input file and process nodes
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines or comments
    line=$(trim "$line")
    if [ -z "$line" ] || [[ $line == \#* ]]; then
        continue
    fi

    # Parse line
    read -r layer mode parents args <<< "$line"
    if [ -z "$layer" ] || [ -z "$mode" ] || [ -z "$parents" ]; then
        echo "Error: Invalid line format: $line"
        exit 1
    fi

    # Validate mode
    if ! [[ "$mode" =~ ^(TP|EP|PP|DP)$ ]]; then
        echo "Error: Invalid mode $mode in line: $line"
        exit 1
    fi

    # Parse parameters
    eval "$(parse_params "$args")"
    host_num=${host_num:-4096}
    dp=${dp:-1}
    num_nodes=${num_nodes:-16}

    # Increment mode counter and generate expected node name
    ((mode_counters[$mode]++))
    expected_node_name="${mode}${mode_counters[$mode]}"

    # Generate actual node name (format: {node_count}_{mode}{layer})
    actual_node_name="${node_count}_${mode}${layer}"
    ((node_count++))

    # Map expected node name to actual node name
    node_name_map[$expected_node_name]=$actual_node_name
    echo "Mapping: $expected_node_name -> $actual_node_name" >&2

    # Parse parents (split by '/')
    IFS='/' read -ra parent_array <<< "$parents"
    parent_list=""
    for parent in "${parent_array[@]}"; do
        parent=$(trim "$parent")
        if [ "$parent" != "Root" ]; then
            if [ -z "${node_name_map[$parent]}" ]; then
                echo "Error: Parent node $parent does not exist in line: $line"
                exit 1
            fi
            parent=${node_name_map[$parent]}
        fi
        parent_list="$parent_list $parent"
    done
    node_parents[$actual_node_name]=$parent_list
    echo "Node $actual_node_name parents: $parent_list" >&2

    # Calculate file count for this node
    file_count=$(get_file_count "$mode" "$host_num" "$dp" "$num_nodes")
    if [ $file_count -eq 0 ]; then
        echo "Error: Invalid file count for mode $mode in line: $line"
        exit 1
    fi
    start_index=$current_file_index
    end_index=$((current_file_index + file_count - 1))
    node_files[$actual_node_name]="$start_index:$end_index"
    current_file_index=$((end_index + 1))
    echo "Node $actual_node_name files: $start_index-$end_index ($file_count files)" >&2

done < "$INPUT_FILE"

# Generate dependency records
for node in "${!node_files[@]}"; do
    # Skip Root node if present
    if [ "$node" == "Root" ]; then
        continue
    fi

    # Get file range for current node
    IFS=':' read -r start end <<< "${node_files[$node]}"

    # Get parent nodes
    parents=${node_parents[$node]}
    for parent in $parents; do
        # Skip if parent is Root
        if [ "$parent" == "Root" ]; then
            continue
        fi

        # Get parent's file range
        if [ -z "${node_files[$parent]}" ]; then
            echo "Error: No file range found for parent $parent of node $node"
            exit 1
        fi
        IFS=':' read -r dep_start dep_end <<< "${node_files[$parent]}"

        # Store dependency record
        dependencies+=("$start:$end:$dep_start:$dep_end")
    done
done

# Sort dependencies by start index and write to output file
echo -n "" > "$OUTPUT_FILE"  # Clear output file
for dep in "${dependencies[@]}"; do
    IFS=':' read -r start end dep_start dep_end <<< "$dep"
    echo "$start-$end:$dep_start-$dep_end"
done | sort -n -t':' -k1 >> "$OUTPUT_FILE"

# Verify total file count
total_files=$current_file_index
echo "Generated $OUTPUT_FILE with dependencies for $total_files files."

exit 0