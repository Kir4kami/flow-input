# Install script for directory: /home/kira/flow-input-test2/src/wifi

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
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/kira/flow-input-test2/build/lib/libns3.39-wifi-default.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so"
         OLD_RPATH "/home/kira/flow-input-test2/build/lib:"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-wifi-default.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/home/kira/flow-input-test2/src/wifi/helper/athstats-helper.h"
    "/home/kira/flow-input-test2/src/wifi/helper/spectrum-wifi-helper.h"
    "/home/kira/flow-input-test2/src/wifi/helper/wifi-helper.h"
    "/home/kira/flow-input-test2/src/wifi/helper/wifi-mac-helper.h"
    "/home/kira/flow-input-test2/src/wifi/helper/wifi-radio-energy-model-helper.h"
    "/home/kira/flow-input-test2/src/wifi/helper/yans-wifi-helper.h"
    "/home/kira/flow-input-test2/src/wifi/model/adhoc-wifi-mac.h"
    "/home/kira/flow-input-test2/src/wifi/model/ampdu-subframe-header.h"
    "/home/kira/flow-input-test2/src/wifi/model/ampdu-tag.h"
    "/home/kira/flow-input-test2/src/wifi/model/amsdu-subframe-header.h"
    "/home/kira/flow-input-test2/src/wifi/model/ap-wifi-mac.h"
    "/home/kira/flow-input-test2/src/wifi/model/block-ack-agreement.h"
    "/home/kira/flow-input-test2/src/wifi/model/block-ack-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/block-ack-type.h"
    "/home/kira/flow-input-test2/src/wifi/model/block-ack-window.h"
    "/home/kira/flow-input-test2/src/wifi/model/capability-information.h"
    "/home/kira/flow-input-test2/src/wifi/model/channel-access-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/ctrl-headers.h"
    "/home/kira/flow-input-test2/src/wifi/model/edca-parameter-set.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/default-emlsr-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-capabilities.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-configuration.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-operation.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/tid-to-link-mapping-element.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/eht-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/emlsr-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/eht/multi-link-element.h"
    "/home/kira/flow-input-test2/src/wifi/model/error-rate-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/extended-capabilities.h"
    "/home/kira/flow-input-test2/src/wifi/model/fcfs-wifi-queue-scheduler.h"
    "/home/kira/flow-input-test2/src/wifi/model/frame-capture-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/constant-obss-pd-algorithm.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-capabilities.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-configuration.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-operation.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/he-ru.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/mu-edca-parameter-set.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/mu-snr-tag.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/multi-user-scheduler.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/obss-pd-algorithm.h"
    "/home/kira/flow-input-test2/src/wifi/model/he/rr-multi-user-scheduler.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-capabilities.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-configuration.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-operation.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/ht/ht-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/interference-helper.h"
    "/home/kira/flow-input-test2/src/wifi/model/mac-rx-middle.h"
    "/home/kira/flow-input-test2/src/wifi/model/mac-tx-middle.h"
    "/home/kira/flow-input-test2/src/wifi/model/mgt-headers.h"
    "/home/kira/flow-input-test2/src/wifi/model/mpdu-aggregator.h"
    "/home/kira/flow-input-test2/src/wifi/model/msdu-aggregator.h"
    "/home/kira/flow-input-test2/src/wifi/model/nist-error-rate-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/dsss-error-rate-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/dsss-parameter-set.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/dsss-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/dsss-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/erp-information.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/erp-ofdm-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/erp-ofdm-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/ofdm-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-ht/ofdm-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/non-inheritance.h"
    "/home/kira/flow-input-test2/src/wifi/model/originator-block-ack-agreement.h"
    "/home/kira/flow-input-test2/src/wifi/model/phy-entity.h"
    "/home/kira/flow-input-test2/src/wifi/model/preamble-detection-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/qos-frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/qos-txop.h"
    "/home/kira/flow-input-test2/src/wifi/model/qos-utils.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/aarf-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/aarfcd-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/amrr-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/aparf-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/arf-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/cara-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/constant-rate-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/ideal-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/minstrel-ht-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/minstrel-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/onoe-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/parf-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/rraa-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/rrpaa-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/rate-control/thompson-sampling-wifi-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/recipient-block-ack-agreement.h"
    "/home/kira/flow-input-test2/src/wifi/model/reduced-neighbor-report.h"
    "/home/kira/flow-input-test2/src/wifi/model/reference/error-rate-tables.h"
    "/home/kira/flow-input-test2/src/wifi/model/simple-frame-capture-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/snr-tag.h"
    "/home/kira/flow-input-test2/src/wifi/model/spectrum-wifi-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/ssid.h"
    "/home/kira/flow-input-test2/src/wifi/model/sta-wifi-mac.h"
    "/home/kira/flow-input-test2/src/wifi/model/status-code.h"
    "/home/kira/flow-input-test2/src/wifi/model/supported-rates.h"
    "/home/kira/flow-input-test2/src/wifi/model/table-based-error-rate-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/threshold-preamble-detection-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/txop.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-capabilities.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-configuration.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-frame-exchange-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-operation.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/vht/vht-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-ack-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-acknowledgment.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-assoc-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-bandwidth-filter.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-default-ack-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-default-assoc-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-default-protection-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-information-element.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-header.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-queue-container.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-queue-elem.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-queue-scheduler-impl.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-queue-scheduler.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-queue.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac-trailer.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mac.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mgt-header.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mode.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mpdu-type.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-mpdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-net-device.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-band.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-common.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-listener.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-operating-channel.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-state-helper.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy-state.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-phy.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-ppdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-protection-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-protection.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-psdu.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-radio-energy-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-remote-station-info.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-remote-station-manager.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-spectrum-phy-interface.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-spectrum-signal-parameters.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-standards.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-tx-current-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-tx-parameters.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-tx-timer.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-tx-vector.h"
    "/home/kira/flow-input-test2/src/wifi/model/wifi-utils.h"
    "/home/kira/flow-input-test2/src/wifi/model/yans-error-rate-model.h"
    "/home/kira/flow-input-test2/src/wifi/model/yans-wifi-channel.h"
    "/home/kira/flow-input-test2/src/wifi/model/yans-wifi-phy.h"
    "/home/kira/flow-input-test2/build/include/ns3/wifi-module.h"
    )
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/home/kira/flow-input-test2/cmake-cache/src/wifi/examples/cmake_install.cmake")

endif()

