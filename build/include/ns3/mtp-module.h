#ifdef NS3_MODULE_COMPILATION 
    error "Do not include ns3 module aggregator headers from other modules these are meant only for end user scripts." 
#endif 
#ifndef NS3_MODULE_MTP
    // Module headers: 
    #include <ns3/logical-process.h>
    #include <ns3/mtp-interface.h>
    #include <ns3/multithreaded-simulator-impl.h>
#endif 