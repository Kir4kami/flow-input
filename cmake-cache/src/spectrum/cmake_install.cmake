# Install script for directory: /home/kira/flow-input-test2/src/spectrum

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
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/kira/flow-input-test2/build/lib/libns3.39-spectrum-default.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so"
         OLD_RPATH "/home/kira/flow-input-test2/build/lib:"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-spectrum-default.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/home/kira/flow-input-test2/src/spectrum/helper/adhoc-aloha-noack-ideal-phy-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/helper/spectrum-analyzer-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/helper/spectrum-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/helper/tv-spectrum-transmitter-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/helper/waveform-generator-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/model/aloha-noack-mac-header.h"
    "/home/kira/flow-input-test2/src/spectrum/model/aloha-noack-net-device.h"
    "/home/kira/flow-input-test2/src/spectrum/model/constant-spectrum-propagation-loss.h"
    "/home/kira/flow-input-test2/src/spectrum/model/friis-spectrum-propagation-loss.h"
    "/home/kira/flow-input-test2/src/spectrum/model/half-duplex-ideal-phy-signal-parameters.h"
    "/home/kira/flow-input-test2/src/spectrum/model/half-duplex-ideal-phy.h"
    "/home/kira/flow-input-test2/src/spectrum/model/ism-spectrum-value-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/model/matrix-based-channel-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/microwave-oven-spectrum-value-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/model/two-ray-spectrum-propagation-loss-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/multi-model-spectrum-channel.h"
    "/home/kira/flow-input-test2/src/spectrum/model/non-communicating-net-device.h"
    "/home/kira/flow-input-test2/src/spectrum/model/single-model-spectrum-channel.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-analyzer.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-channel.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-converter.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-error-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-interference.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-model-300kHz-300GHz-log.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-model-ism2400MHz-res1MHz.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-phy.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-propagation-loss-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-transmit-filter.h"
    "/home/kira/flow-input-test2/src/spectrum/model/phased-array-spectrum-propagation-loss-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-signal-parameters.h"
    "/home/kira/flow-input-test2/src/spectrum/model/spectrum-value.h"
    "/home/kira/flow-input-test2/src/spectrum/model/three-gpp-channel-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/three-gpp-spectrum-propagation-loss-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/trace-fading-loss-model.h"
    "/home/kira/flow-input-test2/src/spectrum/model/tv-spectrum-transmitter.h"
    "/home/kira/flow-input-test2/src/spectrum/model/waveform-generator.h"
    "/home/kira/flow-input-test2/src/spectrum/model/wifi-spectrum-value-helper.h"
    "/home/kira/flow-input-test2/src/spectrum/test/spectrum-test.h"
    "/home/kira/flow-input-test2/build/include/ns3/spectrum-module.h"
    )
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/home/kira/flow-input-test2/cmake-cache/src/spectrum/examples/cmake_install.cmake")

endif()

