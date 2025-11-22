#!/bin/bash

# Input and output files
INPUT_FILE="deepseek.txt"
OUTPUT_FILE="dependence.txt"

# Check if input file exists and is not empty
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file $INPUT_FILE does not exist." >&2
    exit 1
fi
if [ ! -s "$INPUT_FILE" ]; then
    echo "Error: Input file $INPUT_FILE is empty." >&2
    exit 1
fi

# Check if bc is installed
if ! command -v bc &> /dev/null; then
    echo "Error: bc command not found. Please install bc." >&2
    exit 1
fi

# Initialize variables
header_line=""  # Store the first line of the input file
header_word=""  # Store the header word (e.g., deepseek)
max_devices=0   # Store the number of devices from the header
num_iterations=1  # Store the number of iterations from the header
first_tp_args=""  # Store the args of the first TP node
declare -A node_files  # Store file range for each node (node_name:start:end)
declare -A node_parents  # Store parent nodes for each node
declare -A node_name_map  # Map expected node names (e.g., TP1) to actual node names
declare -A mode_counters  # Track mode-specific counters (TP, EP, PP, DP)
mode_counters=( [TP]=0 [EP]=0 [PP]=0 [DP]=0 )
current_file_index=0  # Track current file index
node_count=0  # Track total nodes (excluding Root)
declare -a dependencies  # Store dependency records for sorting
declare -a iteration_dp_nodes  # Store DP nodes for each iteration
declare -a input_lines  # Store input file lines to avoid file pointer issues

# Function to parse parameters from input line
parse_params() {
    local args="$1"
    local -A params=(
        ["host_num"]=4096
        ["num_nodes"]=8
        ["dp"]=1
        ["msg_len"]="33554432"  # Default to 32*1024*1024
        ["num_phases"]=7
        ["device"]=""
        ["forward"]=""
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
                echo "Error: Missing value for ${arg_array[$((i-1))]}" >&2
                exit 1
            fi
            if [ "$key" == "msg_len" ]; then
                # Evaluate msg_len expression (e.g., 32*1024)
                params["$key"]=$(echo "${arg_array[$i]}" | bc 2>/dev/null)
                if [ -z "${params[$key]}" ]; then
                    echo "Error: Failed to evaluate msg_len expression: ${arg_array[$i]}" >&2
                    exit 1
                fi
            else
                params["$key"]=${arg_array[$i]}
            fi
        fi
        ((i++))
    done

    # Return parameters as space-separated key-value pairs, excluding num_iterations
    for key in "${!params[@]}"; do
        if [ "$key" != "num_iterations" ]; then
            echo "$key=${params[$key]}"
        fi
    done
}

# Function to get file count for a mode
get_file_count() {
    local mode=$1
    local host_num=$2
    local dp=$3
    local num_nodes=$4

    case $mode in
        EP)
            if [ $((host_num % max_devices)) -ne 0 ] || [ $(((host_num / max_devices) % dp)) -ne 0 ]; then
                echo "Error: host_num/max_devices ($host_num/max_devices) not divisible by dp $dp" >&2
                exit 1
            fi
            echo $((host_num / max_devices / dp))
            ;;
        DP)
            if [ $((host_num % dp)) -ne 0 ]; then
                echo "Error: host_num $host_num not divisible by dp $dp" >&2
                exit 1
            fi
            echo $((host_num / dp))
            ;;
        TP)
            if [ $((host_num % max_devices)) -ne 0 ] || [ $(((host_num / max_devices) % num_nodes)) -ne 0 ]; then
                echo "Error: host_num/max_devices ($host_num/max_devices) not divisible by num_nodes $num_nodes" >&2
                exit 1
            fi
            echo $((host_num / max_devices / num_nodes))
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

# Read input file into array to avoid file pointer issues
mapfile -t input_lines < "$INPUT_FILE"

# Read and parse the first line
header_line=$(trim "${input_lines[0]}")
if [ -z "$header_line" ]; then
    echo "Error: Header line is empty" >&2
    exit 1
fi

# Parse header line (expected format: <header_word> <max_devices> <num_iterations>)
read -r header_word max_devices num_iterations <<< "$header_line"
if [ -z "$header_word" ] || [ -z "$max_devices" ] || [ -z "$num_iterations" ] || ! [[ "$max_devices" =~ ^[0-9]+$ ]] || ! [[ "$num_iterations" =~ ^[0-9]+$ ]]; then
    echo "Error: Invalid header format: $header_line. Expected '<header_word> <number> <number>'" >&2
    exit 1
fi
echo "Header line: $header_line, header_word: $header_word, max_devices: $max_devices, num_iterations: $num_iterations" >&2
echo "Debug: num_iterations=$num_iterations before loop" >&2

# Process input file for each iteration
for ((iter=1; iter<=num_iterations; iter++)); do
    echo "Processing iteration $iter of $num_iterations" >&2
    mode_counters=( [TP]=0 [EP]=0 [PP]=0 [DP]=0 )  # Reset mode counters for each iteration
    line_number=0
    last_dp_node=""

    # Process each line from input_lines array, skipping the first line
    for ((i=1; i<${#input_lines[@]}; i++)); do
        line=$(trim "${input_lines[$i]}")
        ((line_number++))

        # Skip empty lines or comments
        if [ -z "$line" ] || [[ $line == \#* ]]; then
            continue
        fi

        # Parse line
        read -r layer mode parents args <<< "$line"
        if [ -z "$layer" ] || [ -z "$mode" ] || [ -z "$parents" ]; then
            echo "Error: Invalid line format at line $((line_number+1)): $line" >&2
            exit 1
        fi

        # Save args of the first TP node
        if [ "$mode" == "TP" ] && [ -z "$first_tp_args" ]; then
            first_tp_args="$args"
            echo "Saved first TP args: $first_tp_args" >&2
        fi

        # Validate mode
        if ! [[ "$mode" =~ ^(TP|EP|PP|DP)$ ]]; then
            echo "Error: Invalid mode $mode at line $((line_number+1)): $line" >&2
            exit 1
        fi

        # Parse parameters
        echo "Debug: Before parse_params for line $((line_number+1)), num_iterations=$num_iterations" >&2
        eval "$(parse_params "$args")"
        host_num=${host_num:-4096}
        dp=${dp:-1}
        num_nodes=${num_nodes:-16}
        device=${device:-""}
        forward=${forward:-""}
        echo "Debug: After parse_params for line $((line_number+1)), num_iterations=$num_iterations" >&2

        # Validate device parameter against max_devices
        if [ -n "$device" ] && ! [[ "$device" =~ ^[0-9]+(/[0-9]+)*$ ]]; then
            echo "Error: Invalid device format '$device' at line $((line_number+1)): $line" >&2
            exit 1
        fi
        if [ -n "$device" ]; then
            IFS='/' read -ra device_array <<< "$device"
            for dev in "${device_array[@]}"; do
                if [ "$dev" -ge "$max_devices" ]; then
                    echo "Error: Device $dev exceeds max_devices ($max_devices) at line $((line_number+1)): $line" >&2
                    exit 1
                fi
            done
        fi

        # Increment mode counter and generate expected node name
        ((mode_counters[$mode]++))
        expected_node_name="${mode}${mode_counters[$mode]}_iter${iter}"

        # Generate actual node name (format: {node_count}_{mode}{layer}_iter{iter})
        actual_node_name="${node_count}_${mode}${layer}_iter${iter}"
        ((node_count++))

        # Map expected node name to actual node name
        node_name_map[$expected_node_name]=$actual_node_name
        echo "Mapping: $expected_node_name -> $actual_node_name" >&2

        # Parse parents (split by '/')
        parent_list=""
        if [ "$parents" == "Root" ] && [ $iter -gt 1 ]; then
            # For the first node of non-first iteration, parent is the last DP node of previous iteration
            parent_list="${iteration_dp_nodes[$((iter-1))]}"
            if [ -z "$parent_list" ]; then
                echo "Error: No DP node found for iteration $((iter-1))" >&2
                exit 1
            fi
        else
            IFS='/' read -ra parent_array <<< "$parents"
            for parent in "${parent_array[@]}"; do
                parent=$(trim "$parent")
                if [ "$parent" != "Root" ]; then
                    parent="${parent}_iter${iter}"
                    if [ -z "${node_name_map[$parent]}" ]; then
                        echo "Error: Parent node $parent does not exist at line $((line_number+1)): $line" >&2
                        exit 1
                    fi
                    parent=${node_name_map[$parent]}
                fi
                parent_list="$parent_list $parent"
            done
        fi
        node_parents[$actual_node_name]=$parent_list
        echo "Node $actual_node_name parents: $parent_list" >&2

        # Calculate file count for this node
        file_count=$(get_file_count "$mode" "$host_num" "$dp" "$num_nodes")
        if [ $file_count -eq 0 ]; then
            echo "Error: Invalid file count for mode $mode at line $((line_number+1)): $line" >&2
            exit 1
        fi
        start_index=$current_file_index
        end_index=$((current_file_index + file_count - 1))
        node_files[$actual_node_name]="$start_index:$end_index"
        current_file_index=$((end_index + 1))
        echo "Node $actual_node_name files: $start_index-$end_index ($file_count files)" >&2

        # Store DP node for this iteration
        if [ "$mode" == "DP" ]; then
            iteration_dp_nodes[$iter]=$actual_node_name
            last_dp_node=$actual_node_name
            echo "Stored DP node for iter=$iter: $last_dp_node" >&2
        fi
    done

    # Add TP node after DP node for this iteration (except for the last iteration)
    echo "Debug: Checking TP node addition for iter=$iter, num_iterations=$num_iterations, last_dp_node='$last_dp_node', first_tp_args='$first_tp_args'" >&2
    if [ "$iter" -lt "$num_iterations" ] && [ -n "$last_dp_node" ] && [ -n "$first_tp_args" ]; then
        mode="TP"
        ((mode_counters[$mode]++))
        expected_node_name="${mode}${mode_counters[$mode]}_iter${iter}"
        actual_node_name="${node_count}_${mode}18_iter${iter}"
        ((node_count++))

        # Map expected node name to actual node name
        node_name_map[$expected_node_name]=$actual_node_name
        echo "Mapping: $expected_node_name -> $actual_node_name" >&2

        # Set parent to last DP node
        parent_list=$last_dp_node
        node_parents[$actual_node_name]=$parent_list
        echo "Node $actual_node_name parents: $parent_list" >&2

        # Use first TP node's args
        eval "$(parse_params "$first_tp_args")"
        host_num=${host_num:-128}
        dp=${dp:-8}
        num_nodes=${num_nodes:-8}
        file_count=$(get_file_count "$mode" "$host_num" "$dp" "$num_nodes")
        start_index=$current_file_index
        end_index=$((current_file_index + file_count - 1))
        node_files[$actual_node_name]="$start_index:$end_index"
        current_file_index=$((end_index + 1))
        echo "Node $actual_node_name files: $start_index-$end_index ($file_count files)" >&2
    else
        echo "Skipping TP node addition for iter=$iter: condition not met (iter<$num_iterations=$iter<$num_iterations, last_dp_node='$last_dp_node', first_tp_args='$first_tp_args')" >&2
    fi
done

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
            echo "Error: No file range found for parent $parent of node $node" >&2
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