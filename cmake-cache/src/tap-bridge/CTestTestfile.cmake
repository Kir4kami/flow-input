# CMake generated Testfile for 
# Source directory: /mnt/hgfs/flow-input-yf/src/tap-bridge
# Build directory: /mnt/hgfs/flow-input-yf/cmake-cache/src/tap-bridge
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(ctest-tap-creator "ns3.39-tap-creator-default")
set_tests_properties(ctest-tap-creator PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/src/tap-bridge/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/src/tap-bridge/CMakeLists.txt;40;build_exec;/mnt/hgfs/flow-input-yf/src/tap-bridge/CMakeLists.txt;0;")
subdirs("examples")
