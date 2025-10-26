# CMake generated Testfile for 
# Source directory: /mnt/hgfs/flow-input-yf/examples/Reverie
# Build directory: /mnt/hgfs/flow-input-yf/cmake-cache/examples/Reverie
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(ctest-sim "ns3.39-sim-default")
set_tests_properties(ctest-sim PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/examples/Reverie/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1812;build_exec;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;1;build_example;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;0;")
add_test(ctest-test-parallel "ns3.39-test-parallel-default")
set_tests_properties(ctest-test-parallel PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/examples/Reverie/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1812;build_exec;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;14;build_example;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;0;")
add_test(ctest-reverie-evaluation-sigcomm2023 "ns3.39-reverie-evaluation-sigcomm2023-default")
set_tests_properties(ctest-reverie-evaluation-sigcomm2023 PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/examples/Reverie/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1812;build_exec;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;27;build_example;/mnt/hgfs/flow-input-yf/examples/Reverie/CMakeLists.txt;0;")
