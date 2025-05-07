build_example(
  NAME reverie-evaluation-sigcomm2023
  SOURCE_FILES 
    reverie-evaluation-sigcomm2023.cc
    cdf.c
    kira_functions.cc
  HEADER_FILES
    cdf.h
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
set_source_files_properties(cdf.c PROPERTIES SKIP_PRECOMPILE_HEADERS ON)