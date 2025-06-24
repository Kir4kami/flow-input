# Flow-Input

A tool for generating and processing network traffic patterns for NS-3 simulations.

>**Note**: Much more substantial information about ns-3 can be found at https://www.nsnam.org

This README excerpts some details from a more extensive tutorial that is maintained at: https://www.nsnam.org/documentation/latest/

## Prerequisites

Ensure the following are installed on your system:
- **Python 3**
- **gcc-9**
- **NS-3:3.39**

## Installation and Building NS-3

1. Clone the repository:
   ```bash
   git clone https://github.com/Kir4kami/flow-input.git
   ```

2. Configure and build NS-3:
   ```bash
   ./ns3 configure --enable-examples --enable-tests
   ./ns3
   ```

## Run Integrated Simulation (sim.sh)

To execute the complete simulation workflow with a single command:
```bash
cd examples/Reverie/
./sim.sh
```
>**Note**: This script will automatically handle all subsequent processes

## Traffic Generator

The traffic generator is located in `examples/Reverie/TrafficGenerator/`. It supports two types of input files: `deepseek` and `qwen`. The input file format is as follows:
- **First line**: Type of traffic and number of devices.
- **Subsequent lines**: Traffic details for each parallel strategy, with parameters:
  - `host_num`: Total number of nodes
  - `num_nodes`
  - `dp`
  - `msg_len`
  - `num_phases`: Used for TP
  - `num_iterations`: Used for TP
  - `device`: Device ID
  - `forward`: Forward or backward

### Running an Example

1. Navigate to the TrafficGenerator directory:
   ```bash
   cd examples/Reverie/TrafficGenerator/
   ```

2. Run the traffic generator with an input file:
   ```bash
   ./trafficGen.py --input_file deepseek.txt
   ```
   This generates an `rmda_result` folder.

3. Generate dependencies for the traffic file:
   ```bash
   ./merge_dependency.sh
   ```

4. Combine traffic files:
   ```bash
   ./merge_rdma.sh
   ```

5. The above steps generate a `task` folder, which serves as input for the main program.

## Running the Simulation

1. Navigate to the Reverie directory:
   ```bash
   cd examples/Reverie/
   ```

2. Run the simulation script:
   ```bash
   ./kira-parallel.sh
   ```

3. Results will be generated in `examples/Reverie/dump/`:
   - `evaluation.out`
   - `system1.log`

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.