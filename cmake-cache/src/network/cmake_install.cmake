# Install script for directory: /mnt/hgfs/flow-input-yf/src/network

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
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/mnt/hgfs/flow-input-yf/build/lib/libns3.39-network-default.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so"
         OLD_RPATH "/mnt/hgfs/flow-input-yf/build/lib:::::"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.39-network-default.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/mnt/hgfs/flow-input-yf/src/network/helper/application-container.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/delay-jitter-estimation.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/net-device-container.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/node-container.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/packet-socket-helper.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/simple-net-device-helper.h"
    "/mnt/hgfs/flow-input-yf/src/network/helper/trace-helper.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/address.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/application.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/buffer.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/byte-tag-list.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/channel-list.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/channel.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/chunk.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/header.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/net-device.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/nix-vector.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/node-list.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/node.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/packet-metadata.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/packet-tag-list.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/packet.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/socket-factory.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/socket.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/tag-buffer.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/model/trailer.h"
    "/mnt/hgfs/flow-input-yf/src/network/test/header-serialization-test.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/address-utils.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/bit-deserializer.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/bit-serializer.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/crc32.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/data-rate.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/drop-tail-queue.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/dynamic-queue-limits.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/error-channel.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/error-model.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/ethernet-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/ethernet-trailer.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/flow-id-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/generic-phy.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/inet-socket-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/inet6-socket-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/ipv4-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/ipv6-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/llc-snap-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/lollipop-counter.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/mac16-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/mac48-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/mac64-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/mac8-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/net-device-queue-interface.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/output-stream-wrapper.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-burst.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-data-calculators.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-probe.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-socket-address.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-socket-client.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-socket-factory.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-socket-server.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packet-socket.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/packetbb.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/pcap-file-wrapper.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/pcap-file.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/pcap-test.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/queue-fwd.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/queue-item.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/queue-limits.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/queue-size.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/queue.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/radiotap-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/sequence-number.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/simple-channel.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/simple-net-device.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/sll-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/timestamp-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/seq-ts-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/broadcom-egress-queue.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/bufferlog-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/custom-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/custom-priority-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/feedback-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/interface-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/int-header.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/rdma-tag.h"
    "/mnt/hgfs/flow-input-yf/src/network/utils/unsched-tag.h"
    "/mnt/hgfs/flow-input-yf/build/include/ns3/network-module.h"
    )
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for each subdirectory.
  include("/mnt/hgfs/flow-input-yf/cmake-cache/src/network/examples/cmake_install.cmake")

endif()

