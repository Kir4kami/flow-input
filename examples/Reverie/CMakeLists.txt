build_example(
  NAME sim
  SOURCE_FILES sim
    sim.cc
    kira_functions.cc
  HEADER_FILES
    kira_functions.h
  LIBRARIES_TO_LINK
    ${libpoint-to-point}
    ${libtraffic-control}
    ${libinternet}
    ${libapplications}
)
build_example(
  NAME test-parallel
  SOURCE_FILES 
    test-parallel.cc
    kira_functions.cc
  HEADER_FILES
    kira_functions.h
  LIBRARIES_TO_LINK
    ${libpoint-to-point}
    ${libtraffic-control}
    ${libinternet}
    ${libapplications}
)
set_source_files_properties(PROPERTIES SKIP_PRECOMPILE_HEADERS ON)