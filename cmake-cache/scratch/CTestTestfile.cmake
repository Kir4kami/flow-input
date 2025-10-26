# CMake generated Testfile for 
# Source directory: /mnt/hgfs/flow-input-yf/scratch
# Build directory: /mnt/hgfs/flow-input-yf/cmake-cache/scratch
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(ctest-scratch_scratch-simulator "ns3.39-scratch-simulator-default")
set_tests_properties(ctest-scratch_scratch-simulator PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/scratch/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;57;build_exec;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;69;create_scratch;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;0;")
add_test(ctest-scratch_subdir_scratch-subdir "ns3.39-scratch-subdir-default")
set_tests_properties(ctest-scratch_subdir_scratch-subdir PROPERTIES  WORKING_DIRECTORY "/mnt/hgfs/flow-input-yf/build/scratch/subdir/" _BACKTRACE_TRIPLES "/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1584;add_test;/mnt/hgfs/flow-input-yf/build-support/macros-and-definitions.cmake;1659;set_runtime_outputdirectory;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;57;build_exec;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;99;create_scratch;/mnt/hgfs/flow-input-yf/scratch/CMakeLists.txt;0;")
subdirs("nested-subdir")
