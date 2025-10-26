# CMake generated Testfile for 
# Source directory: /mnt/hgfs/flow-input-yf/src/fd-net-device
# Build directory: /mnt/hgfs/flow-input-yf/cmake-cache/src/fd-net-device
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(ctest-raw-sock-creator "ns3.39-raw-sock-creator-default")
set_tests_properties(ctest-raw-sock-creator PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/src/fd-net-device/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/src/fd-net-device/CMakeLists.txt;151;build_exec;/mnt/hgfs/flow-input-yf/src/fd-net-device/CMakeLists.txt;0;")
add_test(ctest-tap-device-creator "ns3.39-tap-device-creator-default")
set_tests_properties(ctest-tap-device-creator PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/src/fd-net-device/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/src/fd-net-device/CMakeLists.txt;187;build_exec;/mnt/hgfs/flow-input-yf/src/fd-net-device/CMakeLists.txt;0;")
subdirs("examples")
