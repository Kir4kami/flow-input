# CMake generated Testfile for 
# Source directory: /mnt/hgfs/flow-input-yf
# Build directory: /mnt/hgfs/flow-input-yf/cmake-cache
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(ctest-stdlib_pch_exec "ns3.39-stdlib_pch_exec-default")
set_tests_properties(ctest-stdlib_pch_exec PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/cmake-cache/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1501;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/CMakeLists.txt;149;process_options;/mnt/hgfs/flow-input-yf/CMakeLists.txt;0;")
subdirs("src")
subdirs("examples")
subdirs("scratch")
subdirs("utils")
