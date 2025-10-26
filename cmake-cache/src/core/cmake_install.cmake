# Install script for directory: /mnt/hgfs/flow-input-yf/src/core

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "default")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/mnt/hgfs/flow-input-yf/build/lib/libns3.39-core-default.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so"
         OLD_RPATH "/mnt/hgfs/flow-input-yf/build/lib:::::"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-core-default.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/mnt/hgfs/flow-input-yf/src/core/model/int64x64-128.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/example-as-test.h"
    "/mnt/hgfs/flow-input-yf/src/core/helper/csv-reader.h"
    "/mnt/hgfs/flow-input-yf/src/core/helper/event-garbage-collector.h"
    "/mnt/hgfs/flow-input-yf/src/core/helper/random-variable-stream-helper.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/abort.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/ascii-file.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/ascii-test.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/assert.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/attribute-accessor-helper.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/attribute-construction-list.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/attribute-container.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/attribute-helper.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/attribute.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/boolean.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/breakpoint.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/build-profile.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/calendar-scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/callback.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/command-line.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/config.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/default-deleter.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/default-simulator-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/deprecated.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/des-metrics.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/double.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/enum.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/event-id.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/event-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/fatal-error.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/fatal-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/fd-reader.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/environment-variable.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/global-value.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/hash-fnv.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/hash-function.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/hash-murmur3.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/hash.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/heap-scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/int-to-type.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/int64x64-double.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/int64x64.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/integer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/length.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/list-scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/log-macros-disabled.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/log-macros-enabled.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/log.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/make-event.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/map-scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/math.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/names.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/node-printer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/nstime.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object-base.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object-factory.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object-map.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object-ptr-container.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object-vector.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/object.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/pair.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/pointer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/priority-queue-scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/ptr.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/random-variable-stream.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/rng-seed-manager.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/rng-stream.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/scheduler.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/show-progress.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/simple-ref-count.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/simulation-singleton.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/simulator-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/simulator.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/singleton.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/string.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/synchronizer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/system-path.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/system-wall-clock-ms.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/system-wall-clock-timestamp.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/test.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/time-printer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/timer-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/timer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/trace-source-accessor.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/traced-callback.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/traced-value.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/trickle-timer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/tuple.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/type-id.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/type-name.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/type-traits.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/uinteger.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/unused.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/valgrind.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/vector.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/warnings.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/watchdog.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/realtime-simulator-impl.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/wall-clock-synchronizer.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/val-array.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/matrix-array.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/random-variable.h"
    "/mnt/hgfs/flow-input-yf/src/core/model/mixed-granularity.h"
    "/mnt/hgfs/flow-input-yf/build/include/ns3/config-store-config.h"
    "/mnt/hgfs/flow-input-yf/build/include/ns3/core-config.h"
    "/mnt/hgfs/flow-input-yf/build/include/ns3/core-module.h"
    )
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/mnt/hgfs/flow-input-yf/cmake-cache/src/core/examples/cmake_install.cmake")

endif()

