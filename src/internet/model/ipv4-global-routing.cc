//
// Copyright (c) 2008 University of Washington
//
// This program is free software; you can redistribute it and/or modify
// it under the terms of the GNU General Public License version 2 as
// published by the Free Software Foundation;
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
//

#include "ipv4-global-routing.h"

#include "global-route-manager.h"
#include "ipv4-queue-disc-item.h"
#include "ipv4-route.h"
#include "ipv4-routing-table-entry.h"

#include "ns3/boolean.h"
#include "ns3/log.h"
#include "ns3/names.h"
#include "ns3/net-device.h"
#include "ns3/node.h"
#include "ns3/object.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "udp-header.h"
#include "tcp-header.h"
#include "ns3/hash.h"

#include <iomanip>
#include <vector>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("Ipv4GlobalRouting");

NS_OBJECT_ENSURE_REGISTERED(Ipv4GlobalRouting);

TypeId
Ipv4GlobalRouting::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::Ipv4GlobalRouting")
            .SetParent<Object>()
            .SetGroupName("Internet")
            .AddAttribute("RandomEcmpRouting",
                          "Set to true if packets are randomly routed among ECMP; set to false for "
                          "using only one route consistently",
                          BooleanValue(false),
                          MakeBooleanAccessor(&Ipv4GlobalRouting::m_randomEcmpRouting),
                          MakeBooleanChecker())
            .AddAttribute("FlowEcmpRouting",
                          "Set to true if flows are randomly routed among ECMP; set to false for "
                          "using only one route consistently",
                          BooleanValue(false),
                          MakeBooleanAccessor(&Ipv4GlobalRouting::m_flowEcmpRouting),
                          MakeBooleanChecker())
            .AddAttribute("RespondToInterfaceEvents",
                          "Set to true if you want to dynamically recompute the global routes upon "
                          "Interface notification events (up/down, or add/remove address)",
                          BooleanValue(false),
                          MakeBooleanAccessor(&Ipv4GlobalRouting::m_respondToInterfaceEvents),
                          MakeBooleanChecker());
    return tid;
}

Ipv4GlobalRouting::Ipv4GlobalRouting()
    : m_randomEcmpRouting(false),
      m_respondToInterfaceEvents(false)
{
    NS_LOG_FUNCTION(this);

    m_rand = CreateObject<UniformRandomVariable>();
}

Ipv4GlobalRouting::~Ipv4GlobalRouting()
{
    NS_LOG_FUNCTION(this);
}

void
Ipv4GlobalRouting::AddHostRouteTo(Ipv4Address dest, Ipv4Address nextHop, uint32_t interface)
{
    NS_LOG_FUNCTION(this << dest << nextHop << interface);
    Ipv4RoutingTableEntry* route = new Ipv4RoutingTableEntry();
    *route = Ipv4RoutingTableEntry::CreateHostRouteTo(dest, nextHop, interface);
    m_hostRoutes.push_back(route);
}

void
Ipv4GlobalRouting::AddHostRouteTo(Ipv4Address dest, uint32_t interface)
{
    NS_LOG_FUNCTION(this << dest << interface);
    Ipv4RoutingTableEntry* route = new Ipv4RoutingTableEntry();
    *route = Ipv4RoutingTableEntry::CreateHostRouteTo(dest, interface);
    m_hostRoutes.push_back(route);
}

void
Ipv4GlobalRouting::AddNetworkRouteTo(Ipv4Address network,
                                     Ipv4Mask networkMask,
                                     Ipv4Address nextHop,
                                     uint32_t interface)
{
    NS_LOG_FUNCTION(this << network << networkMask << nextHop << interface);
    Ipv4RoutingTableEntry* route = new Ipv4RoutingTableEntry();
    *route = Ipv4RoutingTableEntry::CreateNetworkRouteTo(network, networkMask, nextHop, interface);
    m_networkRoutes.push_back(route);
}

void
Ipv4GlobalRouting::AddNetworkRouteTo(Ipv4Address network, Ipv4Mask networkMask, uint32_t interface)
{
    NS_LOG_FUNCTION(this << network << networkMask << interface);
    Ipv4RoutingTableEntry* route = new Ipv4RoutingTableEntry();
    *route = Ipv4RoutingTableEntry::CreateNetworkRouteTo(network, networkMask, interface);
    m_networkRoutes.push_back(route);
}

void
Ipv4GlobalRouting::AddASExternalRouteTo(Ipv4Address network,
                                        Ipv4Mask networkMask,
                                        Ipv4Address nextHop,
                                        uint32_t interface)
{
    NS_LOG_FUNCTION(this << network << networkMask << nextHop << interface);
    Ipv4RoutingTableEntry* route = new Ipv4RoutingTableEntry();
    *route = Ipv4RoutingTableEntry::CreateNetworkRouteTo(network, networkMask, nextHop, interface);
    m_ASexternalRoutes.push_back(route);
}

// Flow based ECMP
uint32_t
Ipv4GlobalRouting::GetTupleValue(const Ipv4Header& header, Ptr<const Packet> ipPayload)
{
    uint32_t perturbation = 12345678;
    Ipv4Address src = header.GetSource();
    Ipv4Address dest = header.GetDestination();
    uint8_t prot = header.GetProtocol();
    uint16_t fragOffset = header.GetFragmentOffset();
    TcpHeader tcpHdr;
    UdpHeader udpHdr;
    uint16_t srcPort = 0;
    uint16_t destPort = 0;

    if (prot == 6 && fragOffset == 0) // TCP
    {
        ipPayload->PeekHeader(tcpHdr);
        srcPort = tcpHdr.GetSourcePort();
        destPort = tcpHdr.GetDestinationPort();
    }
    else if (prot == 17 && fragOffset == 0) // UDP
    {
        ipPayload->PeekHeader(udpHdr);
        srcPort = udpHdr.GetSourcePort();
        destPort = udpHdr.GetDestinationPort();
    }
    if (prot != 6 && prot != 17)
    {
        NS_LOG_WARN("Unknown transport protocol, no port number included in hash computation");
    }

    uint8_t buf[17];
    src.Serialize(buf);
    dest.Serialize(buf + 4);
    buf[8] = prot;
    buf[9] = (srcPort >> 8) & 0xff;
    buf[10] = srcPort & 0xff;
    buf[11] = (destPort >> 8) & 0xff;
    buf[12] = destPort & 0xff;
    buf[13] = (perturbation >> 24) & 0xff;
    buf[14] = (perturbation >> 16) & 0xff;
    buf[15] = (perturbation >> 8) & 0xff;
    buf[16] = perturbation & 0xff;

    uint32_t hashtuple = Hash32((char*) buf, 17);
    return hashtuple;
}

Ptr<Ipv4Route>
Ipv4GlobalRouting::LookupGlobal(Ipv4Address dest, uint32_t flowHash, Ptr<NetDevice> oif)
{
    NS_LOG_FUNCTION(this << dest << flowHash << oif);
    NS_LOG_LOGIC("Looking for route for destination " << dest);
    Ptr<Ipv4Route> rtentry = nullptr;
    typedef std::vector<Ipv4RoutingTableEntry*> RouteVec_t;
    RouteVec_t allRoutes;

    NS_LOG_LOGIC("Number of m_hostRoutes = " << m_hostRoutes.size());
    for (HostRoutesCI i = m_hostRoutes.begin(); i != m_hostRoutes.end(); i++)
    {
        NS_ASSERT((*i)->IsHost());
        if ((*i)->GetDest() == dest)
        {
            if (oif)
            {
                if (oif != m_ipv4->GetNetDevice((*i)->GetInterface()))
                {
                    NS_LOG_LOGIC("Not on requested interface, skipping");
                    continue;
                }
            }
            allRoutes.push_back(*i);
            NS_LOG_LOGIC(allRoutes.size() << "Found global host route" << *i);
        }
    }
    if (allRoutes.empty()) // if no host route is found
    {
        NS_LOG_LOGIC("Number of m_networkRoutes" << m_networkRoutes.size());
        for (NetworkRoutesI j = m_networkRoutes.begin(); j != m_networkRoutes.end(); j++)
        {
            Ipv4Mask mask = (*j)->GetDestNetworkMask();
            Ipv4Address entry = (*j)->GetDestNetwork();
            if (mask.IsMatch(dest, entry))
            {
                if (oif)
                {
                    if (oif != m_ipv4->GetNetDevice((*j)->GetInterface()))
                    {
                        NS_LOG_LOGIC("Not on requested interface, skipping");
                        continue;
                    }
                }
                allRoutes.push_back(*j);
                NS_LOG_LOGIC(allRoutes.size() << "Found global network route" << *j);
            }
        }
    }
    if (allRoutes.empty()) // consider external if no host/network found
    {
        for (ASExternalRoutesI k = m_ASexternalRoutes.begin(); k != m_ASexternalRoutes.end(); k++)
        {
            Ipv4Mask mask = (*k)->GetDestNetworkMask();
            Ipv4Address entry = (*k)->GetDestNetwork();
            if (mask.IsMatch(dest, entry))
            {
                NS_LOG_LOGIC("Found external route" << *k);
                if (oif)
                {
                    if (oif != m_ipv4->GetNetDevice((*k)->GetInterface()))
                    {
                        NS_LOG_LOGIC("Not on requested interface, skipping");
                        continue;
                    }
                }
                allRoutes.push_back(*k);
                break;
            }
        }
    }
    if (!allRoutes.empty()) // if route(s) is found
    {
        NS_ABORT_MSG_IF(m_randomEcmpRouting && m_flowEcmpRouting, "Ecmp mode selection");
        uint32_t selectIndex;
        if (m_flowEcmpRouting)
        {
            selectIndex = flowHash % allRoutes.size();
        }
        else if (m_randomEcmpRouting)
        {
            selectIndex = m_rand->GetInteger(0, allRoutes.size() - 1);
        }
        else
        {
            selectIndex = 0;
        }
        Ipv4RoutingTableEntry* route = allRoutes.at(selectIndex);
        rtentry = Create<Ipv4Route>();
        rtentry->SetDestination(route->GetDest());
        rtentry->SetSource(m_ipv4->GetAddress(route->GetInterface(), 0).GetLocal());
        rtentry->SetGateway(route->GetGateway());
        uint32_t interfaceIdx = route->GetInterface();
        rtentry->SetOutputDevice(m_ipv4->GetNetDevice(interfaceIdx));
        return rtentry;
    }
    else
    {
        return nullptr;
    }
}

Ptr<Ipv4Route>
Ipv4GlobalRouting::LookupGlobal(Ipv4Address dest, Ptr<NetDevice> oif)
{
    NS_LOG_FUNCTION(this << dest << oif);
    return LookupGlobal(dest, 0, oif); // Use flowHash=0 for non-flow ECMP
}

Ptr<Ipv4Route>
Ipv4GlobalRouting::LookupGlobal(const Ipv4Header& header, Ptr<const Packet> ipPayload, Ptr<NetDevice> oif)
{
    NS_LOG_FUNCTION(this << header.GetDestination() << oif);
    NS_LOG_LOGIC("Looking for route for destination " << header.GetDestination());
    NS_ABORT_MSG_IF(m_randomEcmpRouting && m_flowEcmpRouting, "Ecmp mode selection");
    Ptr<Ipv4Route> rtentry = nullptr;
    typedef std::vector<Ipv4RoutingTableEntry*> RouteVec_t;
    RouteVec_t allRoutes;

    NS_LOG_LOGIC("Number of m_hostRoutes = " << m_hostRoutes.size());
    for (HostRoutesCI i = m_hostRoutes.begin(); i != m_hostRoutes.end(); i++)
    {
        NS_ASSERT((*i)->IsHost());
        if ((*i)->GetDest() == header.GetDestination())
        {
            if (oif)
            {
                if (oif != m_ipv4->GetNetDevice((*i)->GetInterface()))
                {
                    NS_LOG_LOGIC("Not on requested interface, skipping");
                    continue;
                }
            }
            allRoutes.push_back(*i);
            NS_LOG_LOGIC(allRoutes.size() << "Found global host route" << *i);
        }
    }
    if (allRoutes.empty()) // if no host route is found
    {
        NS_LOG_LOGIC("Number of m_networkRoutes" << m_networkRoutes.size());
        for (NetworkRoutesI j = m_networkRoutes.begin(); j != m_networkRoutes.end(); j++)
        {
            Ipv4Mask mask = (*j)->GetDestNetworkMask();
            Ipv4Address entry = (*j)->GetDestNetwork();
            if (mask.IsMatch(header.GetDestination(), entry))
            {
                if (oif)
                {
                    if (oif != m_ipv4->GetNetDevice((*j)->GetInterface()))
                    {
                        NS_LOG_LOGIC("Not on requested interface, skipping");
                        continue;
                    }
                }
                allRoutes.push_back(*j);
                NS_LOG_LOGIC(allRoutes.size() << "Found global network route" << *j);
            }
        }
    }
    if (allRoutes.empty()) // consider external if no host/network found
    {
        for (ASExternalRoutesI k = m_ASexternalRoutes.begin(); k != m_ASexternalRoutes.end(); k++)
        {
            Ipv4Mask mask = (*k)->GetDestNetworkMask();
            Ipv4Address entry = (*k)->GetDestNetwork();
            if (mask.IsMatch(header.GetDestination(), entry))
            {
                NS_LOG_LOGIC("Found external route" << *k);
                if (oif)
                {
                    if (oif != m_ipv4->GetNetDevice((*k)->GetInterface()))
                    {
                        NS_LOG_LOGIC("Not on requested interface, skipping");
                        continue;
                    }
                }
                allRoutes.push_back(*k);
                break;
            }
        }
    }
    if (!allRoutes.empty()) // if route(s) is found
    {
        uint32_t selectIndex;
        if (m_flowEcmpRouting && (allRoutes.size() > 1))
        {
            selectIndex = GetTupleValue(header, ipPayload) % allRoutes.size();
        }
        else if (m_randomEcmpRouting)
        {
            selectIndex = m_rand->GetInteger(0, allRoutes.size() - 1);
        }
        else
        {
            selectIndex = 0;
        }
        Ipv4RoutingTableEntry* route = allRoutes.at(selectIndex);
        rtentry = Create<Ipv4Route>();
        rtentry->SetDestination(route->GetDest());
        rtentry->SetSource(m_ipv4->GetAddress(route->GetInterface(), 0).GetLocal());
        rtentry->SetGateway(route->GetGateway());
        uint32_t interfaceIdx = route->GetInterface();
        rtentry->SetOutputDevice(m_ipv4->GetNetDevice(interfaceIdx));
        return rtentry;
    }
    else
    {
        return nullptr;
    }
}

uint32_t
Ipv4GlobalRouting::GetNRoutes() const
{
    NS_LOG_FUNCTION(this);
    uint32_t n = 0;
    n += m_hostRoutes.size();
    n += m_networkRoutes.size();
    n += m_ASexternalRoutes.size();
    return n;
}

Ipv4RoutingTableEntry*
Ipv4GlobalRouting::GetRoute(uint32_t index) const
{
    NS_LOG_FUNCTION(this << index);
    if (index < m_hostRoutes.size())
    {
        uint32_t tmp = 0;
        for (HostRoutesCI i = m_hostRoutes.begin(); i != m_hostRoutes.end(); i++)
        {
            if (tmp == index)
            {
                return *i;
            }
            tmp++;
        }
    }
    index -= m_hostRoutes.size();
    uint32_t tmp = 0;
    if (index < m_networkRoutes.size())
    {
        for (NetworkRoutesCI j = m_networkRoutes.begin(); j != m_networkRoutes.end(); j++)
        {
            if (tmp == index)
            {
                return *j;
            }
            tmp++;
        }
    }
    index -= m_networkRoutes.size();
    tmp = 0;
    for (ASExternalRoutesCI k = m_ASexternalRoutes.begin(); k != m_ASexternalRoutes.end(); k++)
    {
        if (tmp == index)
        {
            return *k;
        }
        tmp++;
    }
    NS_ASSERT(false);
    return nullptr;
}

void
Ipv4GlobalRouting::RemoveRoute(uint32_t index)
{
    NS_LOG_FUNCTION(this << index);
    if (index < m_hostRoutes.size())
    {
        uint32_t tmp = 0;
        for (HostRoutesI i = m_hostRoutes.begin(); i != m_hostRoutes.end(); i++)
        {
            if (tmp == index)
            {
                NS_LOG_LOGIC("Removing route " << index << "; size = " << m_hostRoutes.size());
                delete *i;
                m_hostRoutes.erase(i);
                NS_LOG_LOGIC("Done removing host route "
                             << index << "; host route remaining size = " << m_hostRoutes.size());
                return;
            }
            tmp++;
        }
    }
    index -= m_hostRoutes.size();
    uint32_t tmp = 0;
    for (NetworkRoutesI j = m_networkRoutes.begin(); j != m_networkRoutes.end(); j++)
    {
        if (tmp == index)
        {
            NS_LOG_LOGIC("Removing route " << index << "; size = " << m_networkRoutes.size());
            delete *j;
            m_networkRoutes.erase(j);
            NS_LOG_LOGIC("Done removing network route "
                         << index << "; network route remaining size = " << m_networkRoutes.size());
            return;
        }
        tmp++;
    }
    index -= m_networkRoutes.size();
    tmp = 0;
    for (ASExternalRoutesI k = m_ASexternalRoutes.begin(); k != m_ASexternalRoutes.end(); k++)
    {
        if (tmp == index)
        {
            NS_LOG_LOGIC("Removing route " << index << "; size = " << m_ASexternalRoutes.size());
            delete *k;
            m_ASexternalRoutes.erase(k);
            NS_LOG_LOGIC("Done removing network route "
                         << index << "; network route remaining size = " << m_networkRoutes.size());
            return;
        }
        tmp++;
    }
    NS_ASSERT(false);
}

int64_t
Ipv4GlobalRouting::AssignStreams(int64_t stream)
{
    NS_LOG_FUNCTION(this << stream);
    m_rand->SetStream(stream);
    return 1;
}

void
Ipv4GlobalRouting::DoDispose()
{
    NS_LOG_FUNCTION(this);
    for (HostRoutesI i = m_hostRoutes.begin(); i != m_hostRoutes.end(); i = m_hostRoutes.erase(i))
    {
        delete (*i);
    }
    for (NetworkRoutesI j = m_networkRoutes.begin(); j != m_networkRoutes.end();
         j = m_networkRoutes.erase(j))
    {
        delete (*j);
    }
    for (ASExternalRoutesI l = m_ASexternalRoutes.begin(); l != m_ASexternalRoutes.end();
         l = m_ASexternalRoutes.erase(l))
    {
        delete (*l);
    }

    Ipv4RoutingProtocol::DoDispose();
}

void
Ipv4GlobalRouting::PrintRoutingTable(Ptr<OutputStreamWrapper> stream, Time::Unit unit) const
{
    NS_LOG_FUNCTION(this << stream);
    std::ostream* os = stream->GetStream();
    std::ios oldState(nullptr);
    oldState.copyfmt(*os);

    *os << std::resetiosflags(std::ios::adjustfield) << std::setiosflags(std::ios::left);

    *os << "Node: " << m_ipv4->GetObject<Node>()->GetId() << ", Time: " << Now().As(unit)
        << ", Local time: " << m_ipv4->GetObject<Node>()->GetLocalTime().As(unit)
        << ", Ipv4GlobalRouting table" << std::endl;

    if (GetNRoutes() > 0)
    {
        *os << "Destination     Gateway         Genmask         Flags Metric Ref    Use Iface"
            << std::endl;
        for (uint32_t j = 0; j < GetNRoutes(); j++)
        {
            std::ostringstream dest;
            std::ostringstream gw;
            std::ostringstream mask;
            std::ostringstream flags;
            Ipv4RoutingTableEntry route = GetRoute(j);
            dest << route.GetDest();
            *os << std::setw(16) << dest.str();
            gw << route.GetGateway();
            *os << std::setw(16) << gw.str();
            mask << route.GetDestNetworkMask();
            *os << std::setw(16) << mask.str();
            flags << "U";
            if (route.IsHost())
            {
                flags << "H";
            }
            else if (route.IsGateway())
            {
                flags << "G";
            }
            *os << std::setw(6) << flags.str();
            *os << "-"
                << "      ";
            *os << "-"
                << "      ";
            *os << "-"
                << "   ";
            if (!Names::FindName(m_ipv4->GetNetDevice(route.GetInterface())).empty())
            {
                *os << Names::FindName(m_ipv4->GetNetDevice(route.GetInterface()));
            }
            else
            {
                *os << route.GetInterface();
            }
            *os << std::endl;
        }
    }
    *os << std::endl;
    (*os).copyfmt(oldState);
}

Ptr<Ipv4Route>
Ipv4GlobalRouting::RouteOutput(Ptr<Packet> p,
                               const Ipv4Header& header,
                               Ptr<NetDevice> oif,
                               Socket::SocketErrno& sockerr)
{
    NS_LOG_FUNCTION(this << p << &header << oif << &sockerr);
    uint32_t flowHash = 0;
    if (m_flowEcmpRouting)
    {
        flowHash = Ipv4QueueDiscItem(p, Address(), header.GetProtocol(), header).Hash(0);
    }
    Ptr<Ipv4Route> rtentry;
    if (header.GetDestination().IsMulticast())
    {
        NS_LOG_LOGIC("Multicast destination-- returning false");
        return nullptr;
    }
    NS_LOG_LOGIC("Unicast destination- looking up");
    if (m_flowEcmpRouting && flowHash != 0)
    {
        rtentry = LookupGlobal(header.GetDestination(), flowHash, oif);
    }
    else
    {
        rtentry = LookupGlobal(header, p, oif);
    }
    if (rtentry)
    {
        sockerr = Socket::ERROR_NOTERROR;
    }
    else
    {
        sockerr = Socket::ERROR_NOROUTETOHOST;
    }
    return rtentry;
}

bool
Ipv4GlobalRouting::RouteInput(Ptr<const Packet> p,
                              const Ipv4Header& header,
                              Ptr<const NetDevice> idev,
                              const UnicastForwardCallback& ucb,
                              const MulticastForwardCallback& mcb,
                              const LocalDeliverCallback& lcb,
                              const ErrorCallback& ecb)
{
    NS_LOG_FUNCTION(this << p << header << header.GetSource() << header.GetDestination() << idev
                         << &lcb << &ecb);
    NS_ASSERT(m_ipv4->GetInterfaceForDevice(idev) >= 0);
    uint32_t iif = m_ipv4->GetInterfaceForDevice(idev);
    uint32_t flowHash = 0;
    if (m_flowEcmpRouting)
    {
        flowHash = Ipv4QueueDiscItem(p->Copy(), Address(), header.GetProtocol(), header).Hash(0);
    }

    if (m_ipv4->IsDestinationAddress(header.GetDestination(), iif))
    {
        if (!lcb.IsNull())
        {
            NS_LOG_LOGIC("Local delivery to " << header.GetDestination());
            lcb(p, header, iif);
            return true;
        }
        else
        {
            return false;
        }
    }

    if (!m_ipv4->IsForwarding(iif))
    {
        NS_LOG_LOGIC("Forwarding disabled for this interface");
        ecb(p, header, Socket::ERROR_NOROUTETOHOST);
        return true;
    }
    NS_LOG_LOGIC("Unicast destination- looking up global route");
    Ptr<Ipv4Route> rtentry;
    if (m_flowEcmpRouting && flowHash != 0)
    {
        rtentry = LookupGlobal(header.GetDestination(), flowHash);
    }
    else
    {
        rtentry = LookupGlobal(header, p);
    }
    if (rtentry)
    {
        NS_LOG_LOGIC("Found unicast destination- calling unicast callback");
        ucb(rtentry, p, header);
        return true;
    }
    else
    {
        NS_LOG_LOGIC("Did not find unicast destination- returning false");
        return false;
    }
}

void
Ipv4GlobalRouting::NotifyInterfaceUp(uint32_t i)
{
    NS_LOG_FUNCTION(this << i);
    if (m_respondToInterfaceEvents && Simulator::Now().GetSeconds() > 0)
    {
        GlobalRouteManager::DeleteGlobalRoutes();
        GlobalRouteManager::BuildGlobalRoutingDatabase();
        GlobalRouteManager::InitializeRoutes();
    }
}

void
Ipv4GlobalRouting::NotifyInterfaceDown(uint32_t i)
{
    NS_LOG_FUNCTION(this << i);
    if (m_respondToInterfaceEvents && Simulator::Now().GetSeconds() > 0)
    {
        GlobalRouteManager::DeleteGlobalRoutes();
        GlobalRouteManager::BuildGlobalRoutingDatabase();
        GlobalRouteManager::InitializeRoutes();
    }
}

void
Ipv4GlobalRouting::NotifyAddAddress(uint32_t interface, Ipv4InterfaceAddress address)
{
    NS_LOG_FUNCTION(this << interface << address);
    if (m_respondToInterfaceEvents && Simulator::Now().GetSeconds() > 0)
    {
        GlobalRouteManager::DeleteGlobalRoutes();
        GlobalRouteManager::BuildGlobalRoutingDatabase();
        GlobalRouteManager::InitializeRoutes();
    }
}

void
Ipv4GlobalRouting::NotifyRemoveAddress(uint32_t interface, Ipv4InterfaceAddress address)
{
    NS_LOG_FUNCTION(this << interface << address);
    if (m_respondToInterfaceEvents && Simulator::Now().GetSeconds() > 0)
    {
        GlobalRouteManager::DeleteGlobalRoutes();
        GlobalRouteManager::BuildGlobalRoutingDatabase();
        GlobalRouteManager::InitializeRoutes();
    }
}

void
Ipv4GlobalRouting::SetIpv4(Ptr<Ipv4> ipv4)
{
    NS_LOG_FUNCTION(this << ipv4);
    NS_ASSERT(!m_ipv4 && ipv4);
    m_ipv4 = ipv4;
}

} // namespace ns3